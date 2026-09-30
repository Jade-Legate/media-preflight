"""ffprobe/ffmpeg 호출과 오디오 신호 측정. 판정은 rules.py가 한다."""

import json
import subprocess

import numpy as np

from . import config

SAMPLE_RATE = 16000
FRAME = 512  # 32ms @16kHz
SILENCE_DB = -50.0  # 이 값 미만 frame은 무음
SPEECH_DB = -45.0  # speech proxy: 이 값 이상이면서
SPEECH_BAND = (250.0, 4000.0)  # 음성 대역 에너지 비율이
SPEECH_BAND_RATIO = 0.5  # 이 값 이상인 frame
_band_mask = (lambda f: (f >= SPEECH_BAND[0]) & (f <= SPEECH_BAND[1]))(np.fft.rfftfreq(FRAME, 1 / SAMPLE_RATE))


class MediaError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def run(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    # 항상 argument array로 실행한다(shell 문자열 결합 금지).
    return subprocess.run(args, capture_output=True, timeout=timeout or config.JOB_TIMEOUT_SECONDS)


def probe(path: str) -> dict | None:
    p = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path], 120)
    if p.returncode != 0:
        return None
    data = json.loads(p.stdout or b"{}")
    return data if data.get("format") else None


def decode_check(path: str) -> dict:
    # 영상은 keyframe만 디코드한다: 손상/열 수 없는 파일은 잡으면서 전체 디코드 대비 약 10배 빠르다.
    # 오디오(STT가 실제로 쓰는 신호)는 전체를 디코드한다.
    p = run(["ffmpeg", "-v", "error", "-nostdin", "-skip_frame", "nokey", "-i", path,
             "-map", "0:v?", "-map", "0:a?", "-f", "null", "-"])
    errors = [l for l in p.stderr.decode(errors="replace").splitlines() if l.strip()]
    return {"exitCode": p.returncode, "errorCount": len(errors), "firstErrors": errors[:3]}


def _db(x):
    return np.maximum(20 * np.log10(np.maximum(x, 1e-12)), -120.0)


def analyze_audio(path: str, channels: int) -> dict:
    """첫 audio stream을 16kHz float PCM으로 스트리밍 디코드해 채널별 지표를 누적한다.

    메모리는 파일 길이와 무관하게 chunk 크기만큼만 쓴다.
    """
    channels = max(1, channels)
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-map", "0:a:0", "-ac", str(channels),
         "-ar", str(SAMPLE_RATE), "-f", "f32le", "-acodec", "pcm_f32le", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    frames_per_chunk = 256
    chunk_bytes = FRAME * channels * 4 * frames_per_chunk

    sumsq = np.zeros(channels)
    peak = np.zeros(channels)
    silent = np.zeros(channels)
    speech = np.zeros(channels)
    # stereo 상관/다운믹스 누적값 (L=ch0, R=ch1)
    s_l = s_r = s_lr = s_ll = s_rr = 0.0
    m_sumsq = m_silent = m_speech = 0.0
    n_frames = 0
    n_samples = 0
    rest = b""

    while True:
        buf = proc.stdout.read(chunk_bytes)
        if not buf:
            break
        buf = rest + buf
        usable = len(buf) - len(buf) % (FRAME * channels * 4)
        rest = buf[usable:]
        if not usable:
            continue
        x = np.frombuffer(buf[:usable], dtype=np.float32).astype(np.float64).reshape(-1, FRAME, channels)
        n_frames += x.shape[0]
        n_samples += x.shape[0] * FRAME
        sumsq += (x**2).sum(axis=(0, 1))
        peak = np.maximum(peak, np.abs(x).max(axis=(0, 1)))
        frame_db = _db(np.sqrt((x**2).mean(axis=1)))  # (frames, ch)
        silent += (frame_db < SILENCE_DB).sum(axis=0)
        speech += _speech_frames(x, frame_db).sum(axis=0)
        if channels >= 2:
            l, r = x[..., 0], x[..., 1]
            s_l += l.sum(); s_r += r.sum(); s_lr += (l * r).sum(); s_ll += (l * l).sum(); s_rr += (r * r).sum()
            m = ((l + r) / 2)[..., None]
            m_db = _db(np.sqrt((m**2).mean(axis=1)))
            m_sumsq += (m**2).sum()
            m_silent += (m_db < SILENCE_DB).sum()
            m_speech += _speech_frames(m, m_db).sum()
    proc.wait()

    if n_frames == 0:
        raise MediaError("AUDIO_DECODE_FAILED", "오디오 샘플을 디코드하지 못했습니다.")

    names = ["L", "R"] if channels == 2 else [f"C{i}" for i in range(channels)]
    rms_db = _db(np.sqrt(sumsq / n_samples))
    per_channel = [
        {
            "channel": names[i],
            "rmsDb": round(float(rms_db[i]), 1),
            "peakDb": round(float(_db(peak[i])), 1),
            "silenceRatio": round(float(silent[i] / n_frames), 3),
            "speechRatio": round(float(speech[i] / n_frames), 3),
        }
        for i in range(channels)
    ]
    result = {"channels": channels, "analyzedSeconds": round(n_samples / SAMPLE_RATE, 2), "perChannel": per_channel, "stereo": None}

    if channels >= 2:
        n = n_samples
        cov = s_lr / n - (s_l / n) * (s_r / n)
        var_l = s_ll / n - (s_l / n) ** 2
        var_r = s_rr / n - (s_r / n) ** 2
        corr = cov / np.sqrt(var_l * var_r) if var_l > 1e-12 and var_r > 1e-12 else None
        m_rms_db = float(_db(np.sqrt(m_sumsq / n)))
        louder = float(max(rms_db[0], rms_db[1]))
        result["stereo"] = {
            "deltaDb": round(abs(float(rms_db[0] - rms_db[1])), 1),
            "correlation": None if corr is None else round(float(corr), 3),
            "downmixRmsDb": round(m_rms_db, 1),
            # 같은 신호가 양쪽에 있으면 0dB, 한쪽이 무음이면 약 6dB, 역상이면 급격히 커진다.
            "downmixLossDb": round(louder - m_rms_db, 1),
            "downmixSilenceRatio": round(float(m_silent / n_frames), 3),
            "downmixSpeechRatio": round(float(m_speech / n_frames), 3),
        }
    return result


def _speech_frames(x: np.ndarray, frame_db: np.ndarray) -> np.ndarray:
    """에너지 + 음성 대역 비율 기반의 간이 VAD. 진짜 VAD가 아니라 '음성일 가능성' proxy다."""
    spec = np.abs(np.fft.rfft(x, axis=1)) ** 2  # (frames, bins, ch)
    total = spec.sum(axis=1) + 1e-20
    band = spec[:, _band_mask, :].sum(axis=1)
    return (frame_db >= SPEECH_DB) & (band / total >= SPEECH_BAND_RATIO)


def ffmpeg_convert(args: list[str]) -> None:
    p = run(["ffmpeg", "-v", "error", "-nostdin", "-y", *args])
    if p.returncode != 0:
        raise MediaError("FIX_FAILED", p.stderr.decode(errors="replace")[-800:])
