"""진단 엔진 + FFmpeg 변환을 실제 미디어 파일로 검증한다 (PRD 17 QA)."""

import os

import pytest

from preflight import fixes, media
from preflight.rules import overall_status
from preflight.tasks import diagnose_path


def diagnose(path, **settings):
    results, metrics = diagnose_path(path, path.rsplit(".", 1)[1], os.path.getsize(path), {"mode": "speech", **settings})
    by_rule = {r["ruleId"]: r for r in results}
    return overall_status(results), by_rule, metrics


def issues(by_rule):
    return {k: r["status"] for k, r in by_rule.items() if r["status"] in ("WARN", "FAIL")}


@pytest.mark.parametrize("name", ["normal_stereo.mp4", "mono.mp4"])
def test_정상_파일은_READY이고_채널_경고가_없다(samples, name):
    # Given 정상 stereo/mono 파일
    # When 진단하면
    status, by_rule, _ = diagnose(samples[name])
    # Then READY이고 채널 수 자체는 오류로 보지 않는다 (QA-001, QA-004)
    assert status == "READY"
    assert issues(by_rule) == {}


def test_손상_파일은_DECODE_FAILED(samples):
    status, by_rule, _ = diagnose(samples["corrupt.mp4"])
    assert status == "NOT_READY"
    assert by_rule["FILE-002"]["errorCode"] == "DECODE_FAILED"


def test_오디오_없는_파일은_NO_AUDIO(samples):
    status, by_rule, _ = diagnose(samples["no_audio.mp4"])
    assert status == "NOT_READY"
    assert by_rule["AUDIO-001"]["errorCode"] == "NO_AUDIO"
    assert by_rule["AUDIO-005"]["status"] == "NOT_APPLICABLE"


def test_한쪽_채널이_무음이면_AUDIO_005가_정상채널_복제를_권장한다(samples):
    # Given R 채널이 무음인 파일 (QA-005)
    status, by_rule, metrics = diagnose(samples["dead_right.mp4"])
    # Then 원인과 조치가 L 채널 기준 Channel Correction으로 연결된다
    assert status == "NOT_READY"
    assert by_rule["AUDIO-005"]["status"] == "FAIL"
    assert by_rule["AUDIO-005"]["recommendedFix"] == "FIX-001"
    assert metrics["channelDecision"] == {"state": "ONE_SIDED", "sourceChannel": 0, "reasons": ["DEAD_CHANNEL"]}


def test_역상_stereo는_레벨이_같아도_모노_다운믹스_상쇄로_탐지한다(samples):
    # Given L/R 음량은 같지만 R이 역상인 파일 (실제 장애 가설: SUCCESS인데 STT 0건)
    status, by_rule, metrics = diagnose(samples["phase_inverted.mp4"])
    # Then 레벨 비교(AUDIO-005)는 통과하지만 다운믹스 검사(AUDIO-008)가 잡아낸다
    assert by_rule["AUDIO-005"]["status"] == "PASS"
    assert by_rule["AUDIO-008"]["status"] == "FAIL"
    assert metrics["audio"]["stereo"]["correlation"] < -0.9
    assert metrics["audio"]["stereo"]["downmixSpeechRatio"] < 0.05
    # 단정 표현을 쓰지 않는다
    assert "가능성" in by_rule["AUDIO-008"]["message"]
    assert status == "NOT_READY"


def test_판단이_애매한_레벨차이는_Review로만_표시하고_자동수정을_제안하지_않는다(samples):
    # Given R이 14dB 작지만 음성이 살아 있는 파일 (Scenario D)
    status, by_rule, metrics = diagnose(samples["weak_right.mp4"])
    assert status == "REVIEW_REQUIRED"
    assert by_rule["AUDIO-005"]["recommendedFix"] is None
    assert metrics["channelDecision"]["state"] == "UNCERTAIN"


def test_무음_파일은_NO_SPEECH(samples):
    status, by_rule, _ = diagnose(samples["silent.mp4"])
    assert status == "NOT_READY"
    assert by_rule["AUDIO-006"]["errorCode"] == "NO_SPEECH"


def test_용량_제한_초과는_모드별로_다른_최적화를_권장한다(samples):
    _, speech, _ = diagnose(samples["large_normal.mp4"], maxFileSizeMb=1)
    _, video, _ = diagnose(samples["large_normal.mp4"], mode="video", maxFileSizeMb=1)
    assert speech["FILE-003"]["recommendedFix"] == "FIX-002"
    assert video["FILE-003"]["recommendedFix"] == "FIX-006"


def _apply(tmp_path, samples, name, fix_id, params):
    src = samples[name]
    has_video = True
    dst = str(tmp_path / f"out.{fixes.output_ext(fix_id, 'mp4', has_video)}")
    media.ffmpeg_convert(fixes.build_args(fix_id, fixes.validate_params(fix_id, params, 2), src, dst, has_video))
    return dst


@pytest.mark.parametrize("name", ["phase_inverted.mp4", "dead_right.mp4"])
def test_채널_교정_후_재검증하면_READY가_되고_영상은_재인코딩하지_않는다(tmp_path, samples, name):
    # Given 채널 이상 파일 (QA-006)
    # When FIX-001(L → L/R 복제)을 적용하면
    out = _apply(tmp_path, samples, name, "FIX-001", {"sourceChannel": 0})
    # Then 재진단 결과 READY
    status, by_rule, _ = diagnose(out)
    assert status == "READY", issues(by_rule)
    # And 영상 stream은 원본 codec 그대로 복사된다
    assert media.probe(out)["streams"][0]["codec_name"] == media.probe(samples[name])["streams"][0]["codec_name"]


def test_단순_모노_변환은_역상_파일을_고치지_못한다(tmp_path, samples):
    # Given 역상 파일에 과거에 실패했던 -ac 1을 적용하면
    out = str(tmp_path / "mono.mp4")
    media.ffmpeg_convert(["-i", samples["phase_inverted.mp4"], "-c:v", "copy", "-ac", "1", out])
    # Then 음성이 상쇄되어 여전히 NOT_READY (사용자 실제 경험과 일치)
    status, by_rule, _ = diagnose(out)
    assert status == "NOT_READY"
    assert by_rule["AUDIO-006"]["status"] == "FAIL"


def test_MP3_추출은_용량을_줄이고_디코드된다(tmp_path, samples):
    # Given 용량 초과 파일 (QA-008)
    out = _apply(tmp_path, samples, "large_normal.mp4", "FIX-002", {"bitrateKbps": 64})
    status, by_rule, _ = diagnose(out, maxFileSizeMb=1)
    assert out.endswith(".mp3")
    assert os.path.getsize(out) < os.path.getsize(samples["large_normal.mp4"])
    assert status == "READY", issues(by_rule)


def test_수정본이_디코드되지_않으면_검증에_실패한다():
    # Given 디코드 실패한 output 진단 결과 (QA-010)
    after = {"sizeBytes": 10, "results": [{"ruleId": "FILE-002", "status": "FAIL"}, {"ruleId": "AUDIO-001", "status": "NOT_APPLICABLE"}]}
    checks = fixes.verify("FIX-001", {"sourceChannel": 0}, {"sizeBytes": 10, "results": []}, after, None)
    assert {c["ruleId"]: c["status"] for c in checks}["OUTPUT-001"] == "FAIL"


def test_fix_파라미터는_whitelist_값만_허용한다():
    with pytest.raises(ValueError):
        fixes.validate_params("FIX-002", {"bitrateKbps": "128k; rm -rf /"}, 2)
    with pytest.raises(ValueError):
        fixes.validate_params("FIX-001", {"sourceChannel": 3}, 2)
