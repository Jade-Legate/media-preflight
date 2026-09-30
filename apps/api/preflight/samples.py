"""PRD 17.1 synthetic test media. 실제 업무 영상은 저장소에 넣지 않는다.

python -m preflight.samples ./samples
"""

import os
import sys

from .media import probe, run

SPEECH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "speech.wav")  # macOS TTS로 만든 합성 음성

# name -> (audio filter_complex producing [a], video source)
_STEREO = {
    "normal_stereo": "[0:a]asplit[l][r0];[r0]volume=0.8[r];[l][r]join=inputs=2:channel_layout=stereo,aformat=channel_layouts=stereo[a]",
    # 실제 장애 재현 가설: R이 L의 역상 → 모노 다운믹스 시 상쇄
    "phase_inverted": "[0:a]aeval=val(0)|-val(0):channel_layout=stereo,aformat=channel_layouts=stereo[a]",
    "dead_right": "[0:a]aeval=val(0)|0:channel_layout=stereo,aformat=channel_layouts=stereo[a]",
    # 정상 stereo 연출일 수도 있는 애매한 경우(Scenario D) → Review, auto fix 없음
    "weak_right": "[0:a]aeval=val(0)|val(0)*0.2:channel_layout=stereo,aformat=channel_layouts=stereo[a]",
}
_VIDEO = ["-f", "lavfi", "-i", "color=c=0x1d3557:s=640x360:r=25"]


def make_samples(outdir: str) -> dict[str, str]:
    os.makedirs(outdir, exist_ok=True)
    paths = {}
    t = ["-t", probe(SPEECH)["format"]["duration"]]

    def ff(name, args):
        path = os.path.join(outdir, name)
        p = run(["ffmpeg", "-v", "error", "-y", *args, path], 300)
        if p.returncode:
            raise RuntimeError(p.stderr.decode())
        paths[name] = path

    for name, graph in _STEREO.items():
        ff(f"{name}.mp4", ["-i", SPEECH, *_VIDEO, "-filter_complex", graph, "-map", "1:v", "-map", "[a]",
                           "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-ar", "44100", *t])
    ff("mono.mp4", ["-i", SPEECH, *_VIDEO, "-map", "1:v", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast",
                    "-c:a", "aac", *t])
    ff("no_audio.mp4", [*_VIDEO, "-t", "5", "-c:v", "libx264", "-preset", "veryfast"])
    ff("silent.mp4", [*_VIDEO, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "5",
                      "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac"])
    # 용량 초과 시나리오용: 고비트레이트 영상(약 5MB)
    ff("large_normal.mp4", ["-i", SPEECH, "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30",
                            "-filter_complex", _STEREO["normal_stereo"], "-map", "1:v", "-map", "[a]",
                            "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4M", "-c:a", "aac", *t])
    corrupt = os.path.join(outdir, "corrupt.mp4")
    with open(corrupt, "wb") as f:
        f.write(b"\x00\x00\x00\x18ftypmp42" + os.urandom(200_000))
    paths["corrupt.mp4"] = corrupt
    return paths


if __name__ == "__main__":
    for k, v in make_samples(sys.argv[1] if len(sys.argv) > 1 else "samples").items():
        print(k, v)
