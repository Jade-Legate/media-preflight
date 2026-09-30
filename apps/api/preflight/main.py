import os
import re
import statistics
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from . import config, fixes, jobqueue, rules, storage, tasks
from .db import Diagnostic, File, FixJob, Job, Session, create_event, init_db, new_id

@asynccontextmanager
async def lifespan(_):
    init_db()
    if config.S3_CREATE_BUCKET or config.STORAGE_BACKEND == "local":
        storage.ensure_bucket()
    if config.QUEUE_BACKEND == "thread":
        _fail_interrupted_jobs()
        from .worker import _cleanup_loop

        threading.Thread(target=_cleanup_loop, daemon=True).start()
    yield


def _fail_interrupted_jobs():
    """단일 서버 재시작 시 메모리의 작업은 사라진다 → 진행 중이던 작업을 FAILED로 정리해 UI가 무한 대기하지 않게 한다."""
    with Session() as s:
        for d in s.query(Diagnostic).filter(Diagnostic.status.in_(["QUEUED", "RUNNING"])):
            d.status, d.error_code = "FAILED", "WORKER_TIMEOUT"
        for x in s.query(FixJob).filter(FixJob.status.in_(["QUEUED", "RUNNING"])):
            x.status, x.error_code = "FAILED", "WORKER_TIMEOUT"
        for f in s.query(File).filter(File.status.in_(["QUEUED", "ANALYZING", "FIXING", "VERIFYING"])):
            f.status = "FAILED"
        s.commit()


app = FastAPI(title="Media Preflight API", version=rules.RULESET["version"], lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.WEB_ORIGINS, allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------- errors


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status, self.code, self.message, self.details = status, code, message, details or {}


def _error(status, code, message, details=None):
    body = {"error": {"code": code, "message": message, "details": details or {}, "requestId": f"req_{uuid.uuid4().hex[:12]}"}}
    return JSONResponse(body, status_code=status)


@app.exception_handler(APIError)
async def _api_error(_: Request, e: APIError):
    return _error(e.status, e.code, e.message, e.details)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, e: RequestValidationError):
    return _error(422, "VALIDATION_ERROR", "요청 값이 올바르지 않습니다.", {"errors": [
        {"loc": list(err["loc"]), "msg": err["msg"]} for err in e.errors()]})


@app.exception_handler(Exception)
async def _unhandled(_: Request, e: Exception):
    tasks.log("api_error", error=repr(e)[:2000])
    return _error(500, "INTERNAL_ERROR", "일시적인 오류가 발생했습니다. 잠시 후 다시 시도하세요.")


# ---------------------------------------------------------------- helpers


def sanitize_filename(name: str) -> str:
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip().lstrip(".")
    return name[-200:] or "file"


def _get(s, model, id_, what):
    obj = s.get(model, id_)
    if not obj:
        raise APIError(404, "NOT_FOUND", f"{what}을(를) 찾을 수 없습니다.")
    return obj


def _latest_diag(s, file_id, done_only=False):
    q = s.query(Diagnostic).filter_by(file_id=file_id)
    if done_only:
        q = q.filter_by(status="DONE")
    return q.order_by(Diagnostic.created_at.desc()).first()


def _diag_json(d: Diagnostic | None):
    if not d:
        return None
    return {
        "diagnosticId": d.id, "fileId": d.file_id, "status": d.status, "overallStatus": d.overall_status,
        "rulesetVersion": d.ruleset_version, "results": d.results_json or [], "metrics": d.metrics_json,
        "errorCode": d.error_code, "startedAt": d.started_at, "finishedAt": d.finished_at,
    }


def _file_json(f: File):
    return {"fileId": f.id, "name": f.original_name, "sizeBytes": f.size_bytes, "status": f.status,
            "parentFileId": f.parent_file_id, "createdAt": f.created_at,
            "downloadable": f.parent_file_id is not None and f.status not in ("FAILED", "EXPIRED", "VERIFYING")}


def _fix_json(s, fx: FixJob):
    out = s.get(File, fx.output_file_id) if fx.output_file_id else None
    return {
        "fixJobId": fx.id, "fixId": fx.fix_id, "title": fixes.FIXES[fx.fix_id]["title"], "params": fx.params_json,
        "status": fx.status, "errorCode": fx.error_code, "errorMessage": fx.error_message, "checks": fx.checks_json,
        "output": _file_json(out) if out else None,
        "verification": _diag_json(s.get(Diagnostic, fx.verification_id)) if fx.verification_id else None,
        "createdAt": fx.created_at, "finishedAt": fx.finished_at,
    }


def _enqueue_diagnostic(s, f: File) -> Diagnostic:
    running = s.query(Diagnostic).filter(Diagnostic.file_id == f.id, Diagnostic.status.in_(["QUEUED", "RUNNING"])).first()
    if running:  # idempotent: 진행 중인 진단이 있으면 그대로 반환
        return running
    d = Diagnostic(id=new_id("d"), file_id=f.id)
    s.add(d)
    f.status = "QUEUED"
    s.commit()
    jobqueue.enqueue("diagnose", d.id)
    return d


def _enqueue_fix(s, f: File, fix_id: str, params: dict) -> FixJob:
    diag = _latest_diag(s, f.id, done_only=True)
    if not diag:
        raise APIError(409, "NOT_DIAGNOSED", "진단이 끝난 파일만 수정할 수 있습니다.")
    channels = next((st.get("channels") or 0 for st in (f.metadata_json or {}).get("streams", []) if st.get("codec_type") == "audio"), 0)
    try:
        clean = fixes.validate_params(fix_id, params, channels)
    except ValueError as e:
        raise APIError(422, "INVALID_FIX_PARAMS", str(e))
    if fix_id == "FIX-001" and (diag.metrics_json or {}).get("channelDecision", {}).get("state") != "ONE_SIDED":
        # 자동수정은 높은 확실성의 rule에만 연결한다(Scenario D).
        raise APIError(409, "CHANNEL_UNCERTAIN", "오디오 채널 상태를 자동으로 판단할 수 없어 자동 수정을 제공하지 않습니다.")
    running = s.query(FixJob).filter(FixJob.file_id == f.id, FixJob.fix_id == fix_id,
                                     FixJob.status.in_(["QUEUED", "RUNNING"])).all()
    for fx in running:
        if fx.params_json == clean:
            return fx
    fx = FixJob(id=new_id("x"), file_id=f.id, fix_id=fix_id, params_json=clean)
    s.add(fx)
    create_event(s, "fix_started", f.job_id, f.id, fixId=fix_id)
    s.commit()
    jobqueue.enqueue("fix", fx.id)
    return fx


# ---------------------------------------------------------------- routes


class FileSpec(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    sizeBytes: int


class CreateJob(BaseModel):
    files: list[FileSpec] = Field(min_length=1, max_length=200)
    mode: Literal["speech", "video"] = "speech"
    maxFileSizeMb: int | None = Field(default=None, ge=1, le=100_000)


@app.post("/api/v1/jobs", status_code=201)
def create_job(body: CreateJob):
    invalid = []
    for spec in body.files:
        ext = tasks._ext(spec.name)
        if ext not in config.SUPPORTED_EXTENSIONS:
            invalid.append({"name": spec.name, "code": "UNSUPPORTED_FORMAT"})
        elif spec.sizeBytes <= 0:
            invalid.append({"name": spec.name, "code": "EMPTY_FILE"})
        elif spec.sizeBytes > config.MAX_UPLOAD_BYTES:
            invalid.append({"name": spec.name, "code": "UPLOAD_TOO_LARGE"})
    if invalid:
        raise APIError(422, "INVALID_FILES", "업로드할 수 없는 파일이 있습니다.",
                       {"files": invalid, "maxUploadBytes": config.MAX_UPLOAD_BYTES})
    with Session() as s:
        job = Job(id=new_id("j"), mode=body.mode, max_file_size_mb=body.maxFileSizeMb)
        s.add(job)
        out = []
        for spec in body.files:
            name = sanitize_filename(spec.name)
            fid = new_id("f")
            f = File(id=fid, job_id=job.id, original_name=name, size_bytes=spec.sizeBytes,
                     object_key=f"uploads/{job.id}/{fid}.{tasks._ext(name)}")
            s.add(f)
            out.append({"fileId": fid, "name": name, "uploadUrl": storage.create_upload_url(f.object_key)})
        create_event(s, "upload_started", job.id, fileCount=len(out), mode=body.mode)
        s.commit()
    return {"jobId": job.id, "files": out}


class CompleteUpload(BaseModel):
    fileId: str


@app.post("/api/v1/jobs/{job_id}/files/complete")
def complete_upload(job_id: str, body: CompleteUpload):
    with Session() as s:
        f = _get(s, File, body.fileId, "파일")
        if f.job_id != job_id:
            raise APIError(404, "NOT_FOUND", "파일을 찾을 수 없습니다.")
        size = storage.read_size(f.object_key)
        if size is None:
            raise APIError(409, "UPLOAD_NOT_FOUND", "업로드된 파일이 storage에 없습니다. 다시 업로드하세요.")
        if f.status == "UPLOADING":
            f.size_bytes, f.status = size, "QUEUED"
            create_event(s, "upload_completed", job_id, f.id, sizeBytes=size)
        s.commit()
        return {"fileId": f.id, "sizeBytes": f.size_bytes}


@app.post("/api/v1/files/{file_id}/diagnose", status_code=202)
def diagnose(file_id: str):
    with Session() as s:
        f = _get(s, File, file_id, "파일")
        if f.status in ("UPLOADING", "EXPIRED"):
            raise APIError(409, "FILE_NOT_AVAILABLE", "업로드가 끝나지 않았거나 보존기간이 지난 파일입니다.")
        return {"diagnosticId": _enqueue_diagnostic(s, f).id}


@app.get("/api/v1/diagnostics/{diagnostic_id}")
def read_diagnostic(diagnostic_id: str):
    with Session() as s:
        return _diag_json(_get(s, Diagnostic, diagnostic_id, "진단"))


class FixRequest(BaseModel):
    fixId: str
    params: dict = {}


@app.post("/api/v1/files/{file_id}/fix", status_code=202)
def create_fix(file_id: str, body: FixRequest):
    with Session() as s:
        f = _get(s, File, file_id, "파일")
        return {"fixJobId": _enqueue_fix(s, f, body.fixId, body.params).id}


class BatchOptimize(BaseModel):
    jobId: str
    fileIds: list[str] = Field(min_length=1, max_length=200)
    fixId: Literal["FIX-002", "FIX-006"]
    params: dict = {}
    applyChannelCorrection: bool = True


@app.post("/api/v1/batch/optimize", status_code=202)
def batch_optimize(body: BatchOptimize):
    """파일별 독립 fix job. 한 파일 실패가 batch 전체를 멈추지 않는다."""
    queued, skipped = [], []
    with Session() as s:
        for fid in body.fileIds:
            f = s.get(File, fid)
            if not f or f.job_id != body.jobId:
                skipped.append({"fileId": fid, "code": "NOT_FOUND"})
                continue
            params = dict(body.params)
            decision = ((_latest_diag(s, fid, done_only=True) or Diagnostic()).metrics_json or {}).get("channelDecision", {})
            if body.applyChannelCorrection and decision.get("state") == "ONE_SIDED":
                params["sourceChannel"] = decision["sourceChannel"]
            try:
                queued.append({"fileId": fid, "fixJobId": _enqueue_fix(s, f, body.fixId, params).id})
            except APIError as e:
                skipped.append({"fileId": fid, "code": e.code})
    return {"batchId": new_id("b"), "queued": queued, "skipped": skipped}


@app.get("/api/v1/jobs/{job_id}")
def read_job(job_id: str):
    with Session() as s:
        job = _get(s, Job, job_id, "작업")
        originals = [f for f in job.files if f.parent_file_id is None]
        files = []
        for f in originals:
            fx = s.query(FixJob).filter_by(file_id=f.id).order_by(FixJob.created_at).all()
            files.append({**_file_json(f), "diagnostic": _diag_json(_latest_diag(s, f.id)),
                          "fixes": [_fix_json(s, x) for x in fx]})
        in_progress = any(f["status"] in ("UPLOADING", "QUEUED", "ANALYZING", "FIXING", "VERIFYING") for f in files) or any(
            x["status"] in ("QUEUED", "RUNNING") for f in files for x in f["fixes"])
        summary = {k: 0 for k in ("READY", "REVIEW_REQUIRED", "NOT_READY", "FAILED", "IN_PROGRESS", "OPTIMIZATION_REQUIRED")}
        for f in files:
            d = f["diagnostic"]
            if f["status"] in summary:
                summary[f["status"]] += 1
            else:
                summary["IN_PROGRESS"] += 1
            if d and any(r["ruleId"] == "FILE-003" and r["status"] == "WARN" for r in d["results"]):
                summary["OPTIMIZATION_REQUIRED"] += 1
        return {"jobId": job.id, "mode": job.mode, "maxFileSizeMb": job.max_file_size_mb, "createdAt": job.created_at,
                "status": "PROCESSING" if in_progress else "COMPLETED", "summary": summary, "files": files,
                "fixCatalog": fixes.FIXES}


@app.get("/api/v1/files/{file_id}/download")
def download(file_id: str):
    with Session() as s:
        f = _get(s, File, file_id, "파일")
        if f.status in ("EXPIRED", "FAILED", "VERIFYING", "UPLOADING"):
            raise APIError(409, "NOT_DOWNLOADABLE", "검증을 통과하지 못했거나 보존기간이 지난 파일입니다.")
        create_event(s, "download_requested", f.job_id, f.id)
        s.commit()
        return {"url": storage.create_download_url(f.object_key, f.original_name), "expiresIn": config.SIGNED_URL_TTL_SECONDS}


@app.put("/api/v1/blobs/{key:path}")
async def put_blob(key: str, exp: int, sig: str, request: Request):
    """STORAGE_BACKEND=local 전용: signed URL 업로드."""
    if config.STORAGE_BACKEND != "local" or not storage.verify(key, "PUT", exp, sig):
        raise APIError(403, "INVALID_SIGNATURE", "업로드 링크가 만료되었거나 올바르지 않습니다.")
    path = storage.local_path(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    size = 0
    with open(path + ".part", "wb") as fh:
        async for chunk in request.stream():
            size += len(chunk)
            if size > config.MAX_UPLOAD_BYTES:
                fh.close()
                os.remove(path + ".part")
                raise APIError(413, "UPLOAD_TOO_LARGE", "업로드 한도를 초과했습니다.")
            fh.write(chunk)
    os.replace(path + ".part", path)
    return {"ok": True, "sizeBytes": size}


@app.get("/api/v1/blobs/{key:path}")
def get_blob(key: str, exp: int, sig: str, name: str = "file"):
    if config.STORAGE_BACKEND != "local" or not storage.verify(key, "GET", exp, sig):
        raise APIError(403, "INVALID_SIGNATURE", "다운로드 링크가 만료되었거나 올바르지 않습니다.")
    path = storage.local_path(key)
    if not os.path.exists(path):
        raise APIError(404, "NOT_FOUND", "파일이 없거나 보존기간이 지났습니다.")
    return FileResponse(path, filename=sanitize_filename(name))


@app.get("/api/v1/health")
def health():
    checks = {}
    for name, fn in (("db", lambda: Session().execute(text("select 1"))), ("queue", jobqueue.ping),
                     ("storage", storage.check)):
        try:
            fn()
            checks[name] = "ok"
        except Exception:  # noqa: BLE001
            checks[name] = "error"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"ok": ok, **checks}, status_code=200 if ok else 503)


@app.get("/api/v1/kpi")
def kpi():
    """PRD 15장 KPI 중 이 서비스 안에서 측정 가능한 지표."""
    # ponytail: 전체 row를 Python으로 집계, 데이터가 커지면 SQL 집계/분석 DB로 이동
    with Session() as s:
        originals = s.query(File).filter(File.parent_file_id.is_(None)).all()
        first = {}
        for d in s.query(Diagnostic).filter_by(status="DONE").order_by(Diagnostic.created_at):
            first.setdefault(d.file_id, d)
        diagnosed = [f for f in originals if f.id in first]
        fx_all = s.query(FixJob).all()
        outputs = {f.id: f for f in s.query(File).filter(File.parent_file_id.isnot(None))}

    def rate(n, d):
        return round(n / d, 3) if d else None

    def median(xs):
        return round(statistics.median(xs), 1) if xs else None

    n = len(diagnosed)
    statuses = [first[f.id].overall_status for f in diagnosed]
    issue_freq = {}
    for f in diagnosed:
        for r in first[f.id].results_json:
            if r["status"] in ("WARN", "FAIL"):
                issue_freq[r["ruleId"]] = issue_freq.get(r["ruleId"], 0) + 1
    verified = [x for x in fx_all if x.status in ("SUCCEEDED", "REJECTED")]
    resolution = []
    for f in diagnosed:
        if first[f.id].overall_status == "READY":
            continue
        ok = [x.finished_at for x in fx_all if x.file_id == f.id and x.status == "SUCCEEDED"
              and outputs.get(x.output_file_id) and outputs[x.output_file_id].status == "READY"]
        if ok:
            resolution.append((min(ok) - first[f.id].finished_at).total_seconds())
    return {
        "diagnosedFiles": n,
        "firstPassReadyRate": rate(statuses.count("READY"), n),
        "manualReviewRate": rate(statuses.count("REVIEW_REQUIRED"), n),
        "notReadyRate": rate(statuses.count("NOT_READY"), n),
        "medianTimeToDiagnosisSec": median([(first[f.id].finished_at - f.created_at).total_seconds() for f in diagnosed]),
        "medianTimeToResolutionSec": median(resolution),
        "verificationPassRate": rate(sum(x.status == "SUCCEEDED" for x in verified), len(verified)),
        "issueFrequency": dict(sorted(issue_freq.items(), key=lambda kv: -kv[1])),
        "notMeasuredHere": ["Zero-Output Rate (V2: CLOVA Speech 연동 후)", "Issue Detection / False Positive Rate (labeled test set)"],
    }
