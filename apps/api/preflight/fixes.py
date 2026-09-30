"""Auto Fix / Optimization catalog.

각 fix는 결정적(deterministic) FFmpeg 변환이다. 원본은 건드리지 않고 별도 output을 만든 뒤,
원본과 동일한 diagnostics + fix별 검증을 다시 실행한다.
"""

VIDEO_COPY_CONTAINERS = {"mp4", "mov", "mkv"}  # -c:v copy + AAC를 안전하게 담을 수 있는 컨테이너

FIXES = {
    "FIX-001": {"title": "Audio Channel Correction", "desc": "정상 채널을 양쪽(L/R)에 복제합니다. 영상은 재인코딩하지 않고 복사합니다."},
    "FIX-002": {"title": "Audio Extraction → MP3", "desc": "Speech-only: 영상을 제거하고 오디오만 MP3로 추출해 용량을 줄입니다."},
    "FIX-003": {"title": "Audio Transcode → AAC", "desc": "오디오를 AAC로 변환합니다. 영상은 복사합니다."},
    "FIX-004": {"title": "Resample → 16 kHz", "desc": "오디오를 16 kHz로 재샘플링합니다(호환성 목적)."},
    "FIX-006": {"title": "Compressed MP4", "desc": "Video analysis: 영상을 유지하면서 H.264로 재압축해 용량을 줄입니다."},
}

MP3_BITRATES = {64, 96, 128, 192}
CRF_VALUES = {23, 28, 32}
MAX_HEIGHTS = {None, 1080, 720, 480}


def validate_params(fix_id: str, params: dict, channels: int) -> dict:
    """사용자 입력을 whitelist 값으로만 정규화한다. ffmpeg 인자에 자유 문자열이 들어가지 않게 한다."""
    if fix_id not in FIXES:
        raise ValueError("UNKNOWN_FIX")
    p = {}
    src = params.get("sourceChannel")
    if fix_id == "FIX-001" and src is None:
        raise ValueError("sourceChannel is required")
    if src is not None:
        if channels < 2 or src not in (0, 1):
            raise ValueError("sourceChannel must be 0(L) or 1(R) on a stereo file")
        p["sourceChannel"] = src
    if fix_id == "FIX-002":
        p["bitrateKbps"] = int(params.get("bitrateKbps", 128))
        if p["bitrateKbps"] not in MP3_BITRATES:
            raise ValueError(f"bitrateKbps must be one of {sorted(MP3_BITRATES)}")
    if fix_id == "FIX-006":
        p["crf"] = int(params.get("crf", 28))
        p["maxHeight"] = params.get("maxHeight", 720)
        if p["crf"] not in CRF_VALUES or p["maxHeight"] not in MAX_HEIGHTS:
            raise ValueError("invalid crf/maxHeight")
    return p


def output_ext(fix_id: str, input_ext: str, has_video: bool) -> str:
    if fix_id == "FIX-002":
        return "mp3"
    if fix_id == "FIX-006":
        return "mp4"
    if has_video:
        return input_ext if input_ext in VIDEO_COPY_CONTAINERS else "mkv"
    return "wav" if input_ext == "wav" else "m4a"


def build_args(fix_id: str, params: dict, src: str, dst: str, has_video: bool) -> list[str]:
    args = ["-i", src]
    audio_filter = []
    if "sourceChannel" in params:
        c = params["sourceChannel"]
        audio_filter.append(f"pan=stereo|c0=c{c}|c1=c{c}")
    if fix_id == "FIX-004":
        audio_filter.append("aresample=16000")
    af = ["-af", ",".join(audio_filter)] if audio_filter else []
    wav = dst.endswith(".wav")
    acodec = ["-c:a", "pcm_s16le"] if wav else ["-c:a", "aac", "-b:a", "192k"]

    if fix_id == "FIX-002":
        return args + ["-vn", "-map", "0:a:0", *af, "-c:a", "libmp3lame", "-b:a", f"{params['bitrateKbps']}k", dst]
    if fix_id == "FIX-006":
        vf = ["-vf", f"scale=-2:'min({params['maxHeight']},ih)'"] if params["maxHeight"] else []
        return args + ["-map", "0:v:0?", "-map", "0:a:0?", *vf, "-c:v", "libx264", "-preset", "veryfast",
                       "-crf", str(params["crf"]), *af, "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", dst]
    # FIX-001 / 003 / 004: 영상은 복사, 오디오만 변환
    video = ["-map", "0:v:0?", "-c:v", "copy"] if has_video else []
    return args + [*video, "-map", "0:a:0", *af, *acodec, dst]


def verify(fix_id: str, params: dict, before: dict, after: dict, max_size_mb) -> list[dict]:
    """fix별 추가 검증. before/after는 diagnostics 결과(results, sizeBytes)."""
    res = {r["ruleId"]: r for r in after["results"]}
    checks = [
        _check("OUTPUT-001", "Post-fix decode", res.get("FILE-002", {}).get("status") in ("PASS", "WARN"),
               "수정된 파일이 정상 디코딩됩니다.", "수정된 파일을 디코딩할 수 없습니다."),
        _check("OUTPUT-002", "Post-fix audio", res.get("AUDIO-001", {}).get("status") == "PASS",
               "수정된 파일에 오디오가 있습니다.", "수정된 파일에 오디오가 없습니다."),
    ]
    if "sourceChannel" in params:
        ok = all(res.get(i, {}).get("status") in ("PASS", "NOT_APPLICABLE") for i in ("AUDIO-005", "AUDIO-008"))
        checks.append(_check("OUTPUT-003", "Channel integrity", ok, "L/R 채널 검사를 통과했습니다.", "채널 교정 후에도 채널 이상이 남아 있습니다."))
    if fix_id in ("FIX-002", "FIX-006"):
        smaller = after["sizeBytes"] < before["sizeBytes"]
        under = not max_size_mb or after["sizeBytes"] <= max_size_mb * 1024**2
        checks.append(_check("OUTPUT-004", "Size reduced", smaller and under,
                             f"{_mb(before['sizeBytes'])} MB → {_mb(after['sizeBytes'])} MB",
                             f"{_mb(before['sizeBytes'])} MB → {_mb(after['sizeBytes'])} MB (목표 미달)"))
    return checks


def _check(rule_id, title, ok, pass_msg, fail_msg):
    return {"ruleId": rule_id, "title": title, "status": "PASS" if ok else "FAIL", "message": pass_msg if ok else fail_msg}


def _mb(b):
    return round(b / 1024**2, 1)
