# Media Preflight: AI Media Preflight & Troubleshooting Assistant

> AI가 성공했다고 했는데, 왜 결과는 0개일까?

AI 음성·영상 분석 **전에** 미디어 파일이 실제로 처리 가능한 상태인지 진단하고, 문제가 있으면 원인·영향·조치를 설명하고,
근거가 명확한 문제는 FFmpeg로 자동 수정한 뒤 **같은 검사를 다시 실행해 통과한 파일만** 내려주는 웹 서비스입니다.

**Diagnose → Explain → Fix → Verify → Process**

## 무엇을 검사하나 (ruleset 1.0.0)

| 영역 | Rule | 비고 |
|---|---|---|
| File Integrity | FILE-001 포맷, FILE-002 디코드, FILE-003 크기(사용자 설정), MEDIA-001 video track | 용량 한도는 서비스·계정별로 달라 하드코딩하지 않음 |
| Audio Availability | AUDIO-001 track, 002 codec, 003 sample rate, 004 채널 수, 009 A/V 길이 | 채널 수 자체는 오류가 아님 |
| Audio Signal Integrity ★ | AUDIO-005 L/R 레벨, 006 무음 비율, 007 음성 활동 proxy, 008 L/R 상관·**모노 다운믹스 손실** | 레벨이 같은 역상 파일은 005로 안 잡히고 008이 잡음 |

결과는 `READY` / `REVIEW_REQUIRED` / `NOT_READY`이며 모든 결과에 raw metric이 함께 저장됩니다.

**자동수정 조건.** 한쪽 채널이 사실상 무음(≥20dB 차이, 무음 ≥90%)이거나 모노로 합치면 음성이 사라질 때(손실 ≥10dB, 음성 구간 절반 이하)만
`FIX-001 Channel Correction`을 제안합니다. 레벨 차이만 있거나 상관계수만 낮으면 Review Required로 두고 자동수정하지 않습니다.

| Fix | 내용 |
|---|---|
| FIX-001 | 정상 채널을 L/R에 복제, 영상은 `-c:v copy` |
| FIX-002 | Speech-only: 오디오만 MP3로 추출 (64–192kbps) |
| FIX-003 / 004 | AAC transcode / 16kHz resample |
| FIX-006 | Video analysis: H.264 재압축 (CRF 23/28/32, ≤720p) |

용량 최적화에는 채널 교정을 함께 적용할 수 있고, batch로 여러 파일에 독립 작업으로 적용됩니다(한 파일 실패가 전체를 멈추지 않음).

## Architecture

```
Browser ── Next.js (apps/web)
   │ REST                          ┌── signed URL PUT/GET ──┐
   ▼                               ▼                        │
FastAPI (apps/api) ── PostgreSQL   S3-compatible storage ◀──┘
   │ enqueue
   ▼
Redis Queue ──▶ Media Worker (같은 이미지, python -m preflight.worker)
                 ffprobe · ffmpeg · numpy 채널 신호 분석
```

- 웹 요청에서 FFmpeg를 실행하지 않고, 모든 변환은 worker job으로 처리합니다.
- 파일은 API 서버를 거치지 않고 object storage로 직접 올리고 받습니다(짧은 TTL signed URL). 원본과 결과는 다른 key를 쓰고, 24시간 뒤 삭제됩니다.
- FFmpeg 인자는 whitelist 값만 허용하고 argument array로 실행합니다.

| 경로 | 역할 |
|---|---|
| `apps/api/preflight/media.py` | ffprobe/ffmpeg 호출, 스트리밍 채널 신호 측정 |
| `apps/api/preflight/rules.py` | rule registry, 임계값(RULESET), 채널 판단 |
| `apps/api/preflight/fixes.py` | fix catalog, ffmpeg 인자, 수정 후 검증 |
| `apps/api/preflight/tasks.py` | worker job(진단/수정/재검증/정리) |
| `apps/api/preflight/main.py` | REST API |
| `apps/api/preflight/samples.py` | 합성 테스트 미디어 생성 |
| `apps/web` | 업로드, 결과/수정, `/showcase` |

## API

| Method | Endpoint | |
|---|---|---|
| POST | `/api/v1/jobs` | job 생성 + 파일별 upload URL |
| POST | `/api/v1/jobs/{jobId}/files/complete` | 업로드 완료 |
| POST | `/api/v1/files/{fileId}/diagnose` | 진단 시작 (202, idempotent) |
| GET | `/api/v1/diagnostics/{id}` | 진단 결과 |
| POST | `/api/v1/files/{fileId}/fix` | 수정 시작 (202) |
| POST | `/api/v1/batch/optimize` | batch 최적화 (202) |
| GET | `/api/v1/jobs/{jobId}` | 전체 상태 (frontend polling) |
| GET | `/api/v1/files/{fileId}/download` | signed download URL |
| GET | `/api/v1/kpi` | Time to Diagnosis/Resolution, Verification Pass Rate 등 |
| GET | `/api/v1/health` | db/redis/storage/worker |

오류는 항상 `{"error": {"code", "message", "details", "requestId"}}` 형식입니다.

## 로컬 실행

Docker만 있으면 됩니다(ffmpeg는 이미지 안에 있음).

```bash
docker compose up -d --build
```

- 웹: http://localhost:3000 · 프로젝트 소개: http://localhost:3000/showcase
- API: http://localhost:8000/docs
- 테스트용 샘플 미디어: `docker compose run --rm -v "$PWD/samples:/out" api python -m preflight.samples /out`

## 테스트

모킹 없이 실제 Postgres·Redis·S3와 합성 미디어로 검증합니다(PRD 17장 QA-001~012).

```bash
docker compose run --rm -v "$PWD/apps/api:/app" -e OBJECT_STORAGE_PUBLIC_ENDPOINT=http://s3:9000 api pytest -q
```

## 배포

- Web: Vercel (`apps/web`, `NEXT_PUBLIC_API_URL`)
- API + Worker + PostgreSQL + Key Value: Render Blueprint (`render.yaml`)
- Object storage: Cloudflare R2 (bucket CORS에 웹 origin의 `PUT`, `GET` 허용 + 24h lifecycle rule)

환경 변수는 `.env.example`을 참고하세요.

## 범위 밖 (Roadmap)

- V3: CLOVA Speech API 연동, STT 결과 검증(Zero-output 탐지)
- V4: Scene Analysis / Metadata / Search / Reuse
- 음성 활동은 에너지 + 음성 대역 비율 기반 **proxy**이며 진짜 VAD가 아닙니다.
