"""Worker jobs (RQ). 웹 요청에서는 FFmpeg를 실행하지 않고 모두 여기서 실행한다."""

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import timedelta

from botocore.exceptions import BotoCoreError, ClientError

from . import config, fixes, media, rules, storage
from .db import Diagnostic, File, FixJob, Session, create_event, new_id, now


def log(event: str, **fields):
    print(json.dumps({"event": event, **fields}, ensure_ascii=False, default=str), file=sys.stderr, flush=True)


def diagnose_path(path: str, ext: str, size_bytes: int, settings: dict) -> tuple[list[dict], dict]:
    probe = media.probe(path)
    ctx = {"ext": ext, "supportedExtensions": config.SUPPORTED_EXTENSIONS, "sizeBytes": size_bytes, "settings": settings,
           "probe": probe, "decode": None, "audio": None}
    metrics = {"sizeBytes": size_bytes, "probe": _probe_summary(probe)}
    if probe:
        ctx["decode"] = media.decode_check(path)
        audio = next((s for s in probe["streams"] if s.get("codec_type") == "audio"), None)
        if audio and int(audio.get("channels") or 0) > 0:
            try:
                ctx["audio"] = media.analyze_audio(path, int(audio["channels"]))
            except media.MediaError as e:
                metrics["audioError"] = e.code
        metrics["audio"] = ctx["audio"]
        metrics["channelDecision"] = rules.assess_channels(ctx["audio"])
    return rules.evaluate(ctx), metrics


def _probe_summary(probe):
    if not probe:
        return None
    f = probe["format"]
    return {
        "container": f.get("format_name"),
        "durationSec": round(float(f.get("duration") or 0), 2),
        "bitRate": int(f.get("bit_rate") or 0) or None,
        "streams": [
            {k: s.get(k) for k in ("index", "codec_type", "codec_name", "width", "height", "avg_frame_rate",
                                   "sample_rate", "channels", "channel_layout", "duration")}
            for s in probe.get("streams", [])
        ],
    }


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _error_code(e: Exception) -> str:
    if isinstance(e, media.MediaError):
        return e.code
    if isinstance(e, subprocess.TimeoutExpired):
        return "WORKER_TIMEOUT"
    if isinstance(e, (BotoCoreError, ClientError)):
        return "STORAGE_ERROR"
    return "INTERNAL_ERROR"


def _run_diagnostic(s, diag: Diagnostic, f: File, path: str) -> None:
    diag.status, diag.started_at = "RUNNING", now()
    s.commit()
    results, metrics = diagnose_path(path, _ext(f.original_name), f.size_bytes, _settings(f))
    diag.results_json, diag.metrics_json = results, metrics
    diag.overall_status = rules.overall_status(results)
    diag.ruleset_version = rules.RULESET["version"]
    diag.status, diag.finished_at = "DONE", now()
    f.metadata_json = metrics["probe"]


def _settings(f: File) -> dict:
    return {"mode": f.job.mode, "maxFileSizeMb": f.job.max_file_size_mb}


def run_diagnostic(diagnostic_id: str) -> None:
    t0 = time.monotonic()
    with Session() as s, tempfile.TemporaryDirectory() as tmp:
        diag = s.get(Diagnostic, diagnostic_id)
        f = s.get(File, diag.file_id)
        f.status = "ANALYZING"
        try:
            path = os.path.join(tmp, "input." + (_ext(f.original_name) or "bin"))
            storage.download(f.object_key, path)
            _run_diagnostic(s, diag, f, path)
            f.status = diag.overall_status
            create_event(s, "diagnosis_completed", f.job_id, f.id, overallStatus=diag.overall_status,
                         issueCodes=[r["ruleId"] for r in diag.results_json if r["status"] in ("WARN", "FAIL")],
                         processingMs=int((time.monotonic() - t0) * 1000))
        except Exception as e:  # noqa: BLE001 — 사용자에게는 코드만, 로그에는 상세
            log("diagnostic_failed", diagnosticId=diagnostic_id, error=repr(e)[:2000])
            diag.status, diag.error_code, diag.finished_at = "FAILED", _error_code(e), now()
            f.status = "FAILED"
            create_event(s, "diagnosis_failed", f.job_id, f.id, errorCode=diag.error_code)
        s.commit()


def run_fix(fix_job_id: str) -> None:
    t0 = time.monotonic()
    with Session() as s, tempfile.TemporaryDirectory() as tmp:
        fx = s.get(FixJob, fix_job_id)
        src_file = s.get(File, fx.file_id)
        prev_status = src_file.status
        fx.status, src_file.status = "RUNNING", "FIXING"
        s.commit()
        try:
            in_ext = _ext(src_file.original_name)
            src = os.path.join(tmp, "input." + in_ext)
            storage.download(src_file.object_key, src)
            has_video = any(st.get("codec_type") == "video" for st in (src_file.metadata_json or {}).get("streams", []))
            out_ext = fixes.output_ext(fx.fix_id, in_ext, has_video)
            dst = os.path.join(tmp, "output." + out_ext)
            media.ffmpeg_convert(fixes.build_args(fx.fix_id, fx.params_json, src, dst, has_video))

            stem = src_file.original_name.rsplit(".", 1)[0]
            out = File(id=new_id("f"), job_id=src_file.job_id, parent_file_id=src_file.id, original_name=f"{stem}_{fx.fix_id.lower()}.{out_ext}",
                       size_bytes=os.path.getsize(dst), status="VERIFYING")
            out.object_key = f"outputs/{src_file.job_id}/{out.id}.{out_ext}"
            s.add(out)
            s.flush()
            storage.upload(dst, out.object_key)
            fx.output_file_id = out.id
            src_file.status = "VERIFYING"
            s.commit()

            verification = Diagnostic(id=new_id("d"), file_id=out.id)
            s.add(verification)
            s.flush()
            fx.verification_id = verification.id
            _run_diagnostic(s, verification, out, dst)

            before = s.query(Diagnostic).filter_by(file_id=src_file.id, status="DONE").order_by(Diagnostic.created_at.desc()).first()
            checks = fixes.verify(fx.fix_id, fx.params_json, {"sizeBytes": src_file.size_bytes, "results": before.results_json if before else []},
                                  {"sizeBytes": out.size_bytes, "results": verification.results_json}, src_file.job.max_file_size_mb)
            fx.checks_json = checks
            passed = all(c["status"] == "PASS" for c in checks)
            if passed:
                fx.status, out.status = "SUCCEEDED", verification.overall_status
            else:
                # 검증 실패 output은 격리: 다운로드 불가
                fx.status, fx.error_code, out.status = "REJECTED", "VERIFY_FAILED", "FAILED"
            create_event(s, "verification_passed" if passed else "verification_failed", src_file.job_id, src_file.id,
                         fixId=fx.fix_id, outputStatus=out.status)
        except Exception as e:  # noqa: BLE001
            log("fix_failed", fixJobId=fix_job_id, error=repr(e)[:2000])
            fx.status, fx.error_code = "FAILED", _error_code(e)
            fx.error_message = "파일 변환에 실패했습니다. 원본은 그대로 보존됩니다."
        fx.finished_at = now()
        src_file.status = prev_status
        create_event(s, "fix_completed", src_file.job_id, src_file.id, fixId=fx.fix_id, status=fx.status,
                     processingMs=int((time.monotonic() - t0) * 1000))
        s.commit()


def cleanup_expired() -> int:
    """retention이 지난 원본/결과 파일을 storage에서 지운다. 운영에서는 bucket lifecycle rule도 함께 건다."""
    cutoff = now() - timedelta(hours=config.FILE_RETENTION_HOURS)
    n = 0
    with Session() as s:
        for f in s.query(File).filter(File.created_at < cutoff, File.status != "EXPIRED"):
            try:
                storage.delete(f.object_key)
            except (BotoCoreError, ClientError) as e:
                log("cleanup_failed", fileId=f.id, error=repr(e))
                continue
            f.status = "EXPIRED"
            n += 1
        s.commit()
    if n:
        log("cleanup_done", expired=n)
    return n
