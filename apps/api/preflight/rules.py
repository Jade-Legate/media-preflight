"""Media Diagnostics rule registry.

'파일이 좋은가'가 아니라 'AI 음성 처리에서 실패할 가능성이 있는가'를 판정한다.
임계값은 RULESET 한 곳에서 관리하고, 모든 결과에 raw metric을 남겨 사람이 검증할 수 있게 한다.
"""

RULESET = {
    "version": "1.0.0",
    "channel_imbalance_warn_db": 6.0,
    "channel_dead_delta_db": 20.0,
    "dead_channel_silence_ratio": 0.90,
    "silence_fail_ratio": 0.95,
    "silence_warn_ratio": 0.90,
    "speech_low_ratio": 0.05,
    "speech_skew_strong_ratio": 0.15,
    "speech_skew_weak_ratio": 0.03,
    "downmix_loss_fail_db": 10.0,
    "downmix_speech_keep_ratio": 0.5,
    "correlation_warn": -0.3,
    "min_sample_rate": 16000,
    "duration_mismatch_sec": 1.0,
    "duration_mismatch_ratio": 0.02,
    "compatible_audio_codecs": [
        "aac", "mp3", "ac3", "eac3", "vorbis", "opus", "flac", "alac", "wmav2",
        "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "pcm_s16be", "pcm_u8",
    ],
}

CATEGORY = {
    "FILE": "File Integrity",
    "MEDIA": "File Integrity",
    "AUDIO-001": "Audio Availability",
    "AUDIO-002": "Audio Availability",
    "AUDIO-003": "Audio Availability",
    "AUDIO-004": "Audio Availability",
    "AUDIO-009": "Audio Availability",
    "AUDIO": "Audio Signal Integrity",
    "OUTPUT": "Verification",
}

SEVERITY = {"FAIL": "ERROR", "WARN": "WARNING", "PASS": "INFO", "NOT_APPLICABLE": "INFO"}


def _result(rule_id, title, status, metrics=None, message="", impact="", action="", fix=None, code=None):
    category = CATEGORY.get(rule_id) or CATEGORY[rule_id.split("-")[0]]
    return {
        "ruleId": rule_id,
        "title": title,
        "category": category,
        "status": status,
        "severity": SEVERITY[status],
        "metrics": metrics or {},
        "message": message,
        "impact": impact,
        "action": action,
        "recommendedFix": fix,
        "errorCode": code,
    }


def _na(rule_id, title, why):
    return _result(rule_id, title, "NOT_APPLICABLE", message=why)


# ---------------------------------------------------------------- channel decision


def assess_channels(audio: dict | None) -> dict:
    """L/R 상태를 OK / ONE_SIDED(자동수정 가능) / UNCERTAIN(수동 검토)로 분류한다.

    채널 수 자체는 오류가 아니다. 자동수정은 측정 근거가 명확한 경우에만 연결한다.
    """
    if not audio or not audio.get("stereo"):
        return {"state": "NOT_APPLICABLE", "sourceChannel": None, "reasons": []}
    r = RULESET
    left, right = audio["perChannel"][0], audio["perChannel"][1]
    st = audio["stereo"]
    strong_i = 0 if (left["speechRatio"], left["rmsDb"]) >= (right["speechRatio"], right["rmsDb"]) else 1
    strong, weak = (left, right) if strong_i == 0 else (right, left)
    has_speech = strong["speechRatio"] >= r["speech_low_ratio"]

    reasons = []
    dead = (
        has_speech
        and st["deltaDb"] >= r["channel_dead_delta_db"]
        and weak["silenceRatio"] >= r["dead_channel_silence_ratio"]
    )
    if dead:
        reasons.append("DEAD_CHANNEL")
    collapse = (
        has_speech
        and st["downmixLossDb"] >= r["downmix_loss_fail_db"]
        and st["downmixSpeechRatio"] < strong["speechRatio"] * r["downmix_speech_keep_ratio"]
    )
    if collapse:
        reasons.append("DOWNMIX_COLLAPSE")
    if dead or collapse:
        return {"state": "ONE_SIDED", "sourceChannel": strong_i, "reasons": reasons}

    if st["deltaDb"] >= r["channel_imbalance_warn_db"]:
        reasons.append("LEVEL_IMBALANCE")
    if st["correlation"] is not None and st["correlation"] <= r["correlation_warn"]:
        reasons.append("NEGATIVE_CORRELATION")
    if strong["speechRatio"] >= r["speech_skew_strong_ratio"] and weak["speechRatio"] <= r["speech_skew_weak_ratio"]:
        reasons.append("SPEECH_SKEW")
    return {"state": "UNCERTAIN" if reasons else "OK", "sourceChannel": strong_i, "reasons": reasons}


# ---------------------------------------------------------------- rules


def evaluate(ctx: dict) -> list[dict]:
    """ctx: ext, sizeBytes, settings{mode,maxFileSizeMb}, probe, decode, audio"""
    r = RULESET
    probe = ctx.get("probe")
    mode = ctx["settings"].get("mode", "speech")
    out = []

    ext_ok = ctx["ext"] in ctx["supportedExtensions"]
    if not ext_ok:
        out.append(_result("FILE-001", "지원 포맷", "FAIL", {"extension": ctx["ext"]},
                           f".{ctx['ext']} 형식은 지원하지 않습니다.", "업로드 또는 AI 처리 단계에서 거부됩니다.",
                           "MP4/MOV/MKV 또는 MP3/WAV/M4A 등 지원 포맷으로 변환하세요.", code="UNSUPPORTED_FORMAT"))
    else:
        out.append(_result("FILE-001", "지원 포맷", "PASS", {"extension": ctx["ext"], "container": (probe or {}).get("format", {}).get("format_name")},
                           "지원되는 파일 형식입니다."))

    if probe is None:
        out.append(_result("FILE-002", "파일 디코드", "FAIL", {}, "파일 구조를 읽을 수 없습니다. 손상되었거나 미디어 파일이 아닐 수 있습니다.",
                           "AI 서비스가 파일을 열지 못하거나 빈 결과를 반환할 수 있습니다.",
                           "원본에서 다시 내보내기(export)하거나 재인코딩한 뒤 다시 업로드하세요.", code="DECODE_FAILED"))
        return out + [_na(i, t, "파일을 읽을 수 없어 검사하지 않았습니다.") for i, t in _AFTER_DECODE]

    dec = ctx["decode"]
    if dec["exitCode"] != 0:
        out.append(_result("FILE-002", "파일 디코드", "FAIL", dec, "실제 디코딩 중 오류로 중단되었습니다.",
                           "AI 서비스가 파일을 끝까지 처리하지 못할 수 있습니다.", "원본에서 다시 내보내거나 재인코딩하세요.", code="DECODE_FAILED"))
    elif dec["errorCount"]:
        out.append(_result("FILE-002", "파일 디코드", "WARN", dec, f"디코딩은 완료됐지만 오류 메시지 {dec['errorCount']}건이 발생했습니다.",
                           "일부 구간의 영상/음성이 손상되었을 수 있습니다.", "문제 구간을 재생해 확인하세요."))
    else:
        out.append(_result("FILE-002", "파일 디코드", "PASS", dec, "끝까지 정상 디코딩됩니다."))

    size_mb = round(ctx["sizeBytes"] / 1024**2, 1)
    limit = ctx["settings"].get("maxFileSizeMb")
    if limit and size_mb > limit:
        fix = "FIX-002" if mode == "speech" else "FIX-006"
        out.append(_result("FILE-003", "파일 크기", "WARN", {"sizeMb": size_mb, "limitMb": limit},
                           f"{size_mb} MB > 설정 제한 {limit} MB",
                           "AI 서비스의 입력 용량 제한에 걸려 업로드가 거부될 수 있습니다.",
                           "음성 분석만 필요하면 MP3로 오디오를 추출하고, 영상이 필요하면 MP4를 압축하세요.", fix, "FILE_TOO_LARGE"))
    else:
        out.append(_result("FILE-003", "파일 크기", "PASS", {"sizeMb": size_mb, "limitMb": limit},
                           "설정된 제한 이내입니다." if limit else "용량 제한을 설정하지 않았습니다."))

    streams = probe.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(probe["format"].get("duration") or 0)

    if video:
        out.append(_result("MEDIA-001", "Video track", "PASS",
                           {"codec": video.get("codec_name"), "width": video.get("width"), "height": video.get("height"), "fps": _fps(video)},
                           "영상 track이 있습니다."))
    elif mode == "video":
        out.append(_result("MEDIA-001", "Video track", "WARN", {}, "영상 track이 없습니다.",
                           "영상 분석(Scene Analysis)을 할 수 없습니다.", "음성 분석만 필요하면 Speech-only 모드를 사용하세요."))
    else:
        out.append(_result("MEDIA-001", "Video track", "PASS", {}, "Speech-only 모드: 영상 track이 필요하지 않습니다."))

    if not audio_stream:
        out.append(_result("AUDIO-001", "Audio track", "FAIL", {}, "오디오 track이 없습니다.",
                           "STT(음성인식) 결과가 생성될 수 없습니다.", "오디오가 포함된 원본으로 다시 내보내세요.", code="NO_AUDIO"))
        return out + [_na(i, t, "오디오 track이 없어 검사하지 않았습니다.") for i, t in _AUDIO_RULES]
    out.append(_result("AUDIO-001", "Audio track", "PASS", {"streams": sum(s.get("codec_type") == "audio" for s in streams)}, "오디오 track이 있습니다."))

    codec = audio_stream.get("codec_name")
    if codec in r["compatible_audio_codecs"]:
        out.append(_result("AUDIO-002", "Audio codec", "PASS", {"codec": codec}, f"{codec}: 호환 codec입니다."))
    else:
        out.append(_result("AUDIO-002", "Audio codec", "WARN", {"codec": codec}, f"{codec}: AI 서비스 호환 목록에 없는 codec입니다.",
                           "업로드는 되더라도 디코드 단계에서 실패할 수 있습니다.", "AAC로 오디오를 변환하세요(영상은 그대로 복사).", "FIX-003"))

    sr = int(audio_stream.get("sample_rate") or 0)
    if sr and sr < r["min_sample_rate"]:
        out.append(_result("AUDIO-003", "Sample rate", "WARN", {"sampleRate": sr, "minimum": r["min_sample_rate"]},
                           f"{sr} Hz로 권장값({r['min_sample_rate']} Hz)보다 낮습니다.",
                           "음성인식 정확도가 떨어질 수 있습니다. 재샘플링은 호환성만 맞출 뿐 음질을 복원하지는 않습니다.",
                           "가능하면 더 높은 품질의 원본을 사용하고, 호환성만 필요하면 16kHz로 재샘플링하세요.", "FIX-004"))
    else:
        out.append(_result("AUDIO-003", "Sample rate", "PASS", {"sampleRate": sr}, f"{sr} Hz"))

    ch = int(audio_stream.get("channels") or 0)
    if ch <= 0:
        out.append(_result("AUDIO-004", "Channel 수", "FAIL", {"channels": ch}, "오디오 채널 정보가 비정상입니다.",
                           "음성 신호를 읽을 수 없습니다.", "원본에서 다시 내보내세요.", code="DECODE_FAILED"))
        return out + [_na(i, t, "채널 정보가 없어 검사하지 않았습니다.") for i, t in _SIGNAL_RULES + [("AUDIO-009", "Audio/Video 길이")]]
    layout = {1: "mono", 2: "stereo"}.get(ch, f"{ch}-channel")
    msg = f"{layout} ({ch}ch)." + (" 앞의 2개 채널(L/R)을 기준으로 분석합니다." if ch > 2 else "")
    out.append(_result("AUDIO-004", "Channel 수", "PASS", {"channels": ch, "layout": audio_stream.get("channel_layout")}, msg))

    a_dur = float(audio_stream.get("duration") or 0)
    v_dur = float((video or {}).get("duration") or 0)
    if a_dur and v_dur and abs(a_dur - v_dur) > max(r["duration_mismatch_sec"], v_dur * r["duration_mismatch_ratio"]):
        out.append(_result("AUDIO-009", "Audio/Video 길이", "WARN", {"audioSec": round(a_dur, 2), "videoSec": round(v_dur, 2)},
                           f"오디오 {a_dur:.1f}s / 영상 {v_dur:.1f}s로 길이가 다릅니다.",
                           "STT 타임스탬프가 영상과 어긋나거나 일부 구간이 누락될 수 있습니다.", "편집 툴에서 내보내기 범위를 확인하세요."))
    else:
        out.append(_result("AUDIO-009", "Audio/Video 길이", "PASS", {"audioSec": round(a_dur or duration, 2), "videoSec": round(v_dur, 2) or None}, "길이가 일치합니다."))

    out += _signal_rules(ctx.get("audio"))
    return out


def _signal_rules(audio: dict | None) -> list[dict]:
    r = RULESET
    if not audio:
        return [_na(i, t, "오디오 신호를 측정하지 못했습니다.") for i, t in _SIGNAL_RULES]
    out = []
    per = audio["perChannel"][:2] if audio["channels"] >= 2 else audio["perChannel"][:1]
    st = audio.get("stereo")
    decision = assess_channels(audio)
    src = decision["sourceChannel"]
    src_name = None if src is None else ("L" if src == 0 else "R")
    ch_metrics = {c["channel"]: c for c in per}

    # AUDIO-005 channel level imbalance
    if not st:
        out.append(_na("AUDIO-005", "L/R 신호 균형", "mono 파일입니다."))
    elif "DEAD_CHANNEL" in decision["reasons"]:
        weak = "R" if src == 0 else "L"
        out.append(_result("AUDIO-005", "L/R 신호 균형", "FAIL", {**_lr(per, "rmsDb"), "deltaDb": st["deltaDb"]},
                           f"{weak} 채널의 신호가 비정상적으로 낮습니다({st['deltaDb']} dB 차이, 무음 비율 {ch_metrics[weak]['silenceRatio']:.0%}).",
                           "AI 서비스가 채널을 합치거나 한 채널만 읽으면 음성이 약해지거나 STT 결과가 비어 있을 수 있습니다.",
                           f"정상 채널({src_name})을 양쪽에 복제하는 Channel Correction을 적용하세요.", "FIX-001"))
    elif st["deltaDb"] >= r["channel_imbalance_warn_db"]:
        out.append(_result("AUDIO-005", "L/R 신호 균형", "WARN", {**_lr(per, "rmsDb"), "deltaDb": st["deltaDb"]},
                           f"L/R 음량 차이가 {st['deltaDb']} dB입니다.",
                           "정상적인 stereo 연출일 수도 있어 자동으로 판단하지 않습니다.",
                           "양쪽 채널을 들어보고 한쪽에만 음성이 있는지 확인하세요.", code="CHANNEL_UNCERTAIN"))
    else:
        out.append(_result("AUDIO-005", "L/R 신호 균형", "PASS", {**_lr(per, "rmsDb"), "deltaDb": st["deltaDb"]}, "L/R 음량이 균형적입니다."))

    # AUDIO-006 silence ratio
    sil = {c["channel"]: c["silenceRatio"] for c in per}
    if all(v >= r["silence_fail_ratio"] for v in sil.values()):
        out.append(_result("AUDIO-006", "무음 비율", "FAIL", sil, "모든 채널이 사실상 무음입니다.",
                           "처리 상태는 SUCCESS로 표시되어도 STT 결과가 0건일 가능성이 높습니다.",
                           "원본 녹음/편집 단계에서 오디오가 포함되었는지 확인하세요.", code="NO_SPEECH"))
    elif any(v >= r["silence_warn_ratio"] for v in sil.values()):
        dead = ", ".join(k for k, v in sil.items() if v >= r["silence_warn_ratio"])
        out.append(_result("AUDIO-006", "무음 비율", "WARN", sil, f"{dead} 채널의 무음 비율이 매우 높습니다.",
                           "해당 채널만 사용되면 음성이 누락될 수 있습니다.", "L/R 신호 균형 결과를 함께 확인하세요."))
    else:
        out.append(_result("AUDIO-006", "무음 비율", "PASS", sil, "무음 비율이 정상 범위입니다."))

    # AUDIO-007 speech activity proxy
    sp = {c["channel"]: c["speechRatio"] for c in per}
    best = max(sp.values())
    if best < r["speech_low_ratio"]:
        out.append(_result("AUDIO-007", "음성 활동(Speech activity)", "WARN", sp, f"음성으로 보이는 구간이 {best:.0%}에 불과합니다.",
                           "음악/효과음 위주이거나 음성이 매우 작아 STT 결과가 거의 없을 수 있습니다.",
                           "음성이 실제로 들리는지 확인하세요.", code="NO_SPEECH"))
    elif len(sp) == 2 and best >= r["speech_skew_strong_ratio"] and min(sp.values()) <= r["speech_skew_weak_ratio"]:
        out.append(_result("AUDIO-007", "음성 활동(Speech activity)", "WARN", sp, "음성 신호가 한쪽 채널에 편중되어 있습니다.",
                           "AI 서비스의 채널 처리 방식에 따라 음성이 누락될 수 있습니다.", "L/R 신호 균형 결과를 함께 확인하세요."))
    else:
        out.append(_result("AUDIO-007", "음성 활동(Speech activity)", "PASS", sp, f"음성 구간 비율 {best:.0%}"))

    # AUDIO-008 L/R correlation + mono downmix
    if not st:
        out.append(_na("AUDIO-008", "L/R 상관관계 / 모노 다운믹스", "mono 파일입니다."))
    else:
        m = {k: st[k] for k in ("correlation", "downmixLossDb", "downmixSpeechRatio")}
        if "DOWNMIX_COLLAPSE" in decision["reasons"]:
            out.append(_result("AUDIO-008", "L/R 상관관계 / 모노 다운믹스", "FAIL", m,
                               f"모노로 합치면 신호가 {st['downmixLossDb']} dB 줄고 음성 구간이 {st['downmixSpeechRatio']:.0%}로 감소합니다. "
                               "채널 간 위상/상관관계 이상 가능성이 있습니다.",
                               "AI 서비스가 내부에서 모노로 변환하면 음성이 상쇄되어 STT 결과가 비어 있을 수 있습니다.",
                               f"정상 채널({src_name})을 양쪽에 복제하세요. 단순 모노 변환(-ac 1)은 같은 상쇄를 재현하므로 해결책이 아닙니다.", "FIX-001"))
        elif "NEGATIVE_CORRELATION" in decision["reasons"]:
            out.append(_result("AUDIO-008", "L/R 상관관계 / 모노 다운믹스", "WARN", m,
                               f"L/R 상관계수가 {st['correlation']}로 낮습니다. 채널 간 위상/상관관계 이상 가능성이 있습니다.",
                               "모노 변환 시 일부 신호가 약해질 수 있습니다.", "모노로 들어보고 음성이 약해지는지 확인하세요.", code="CHANNEL_UNCERTAIN"))
        else:
            out.append(_result("AUDIO-008", "L/R 상관관계 / 모노 다운믹스", "PASS", m, "모노로 합쳐도 음성이 유지됩니다."))
    return out


def _lr(per, key):
    return {f"{c['channel'].lower()}{key[0].upper()}{key[1:]}": c[key] for c in per}


def _fps(stream):
    try:
        n, d = stream.get("avg_frame_rate", "0/1").split("/")
        return round(int(n) / int(d), 2) if int(d) else None
    except ValueError:
        return None


_SIGNAL_RULES = [
    ("AUDIO-005", "L/R 신호 균형"),
    ("AUDIO-006", "무음 비율"),
    ("AUDIO-007", "음성 활동(Speech activity)"),
    ("AUDIO-008", "L/R 상관관계 / 모노 다운믹스"),
]
_AUDIO_RULES = [("AUDIO-002", "Audio codec"), ("AUDIO-003", "Sample rate"), ("AUDIO-004", "Channel 수"),
                ("AUDIO-009", "Audio/Video 길이")] + _SIGNAL_RULES
_AFTER_DECODE = [("FILE-003", "파일 크기"), ("MEDIA-001", "Video track"), ("AUDIO-001", "Audio track")] + _AUDIO_RULES


def overall_status(results: list[dict]) -> str:
    statuses = {r["status"] for r in results}
    if "FAIL" in statuses:
        return "NOT_READY"
    if "WARN" in statuses:
        return "REVIEW_REQUIRED"
    return "READY"
