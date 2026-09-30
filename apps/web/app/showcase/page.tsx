import type { Metadata } from "next";
import Link from "next/link";
import Demo from "@/components/Demo";

export const metadata: Metadata = {
  title: "Media Preflight · Project",
  description: "AI가 성공했다고 했는데, 왜 결과는 0개일까? — AI 처리 성공과 실제 업무 성공 사이의 gap을 줄이는 제품 기획·구현.",
};

const GITHUB_URL = process.env.NEXT_PUBLIC_GITHUB_URL ?? "https://github.com/Jade-Legate/media-preflight";
const PDF_URL = process.env.NEXT_PUBLIC_PORTFOLIO_PDF_URL;

const REQUIREMENTS: [string, string, string, string, string][] = [
  ["File Format", "지원하지 않는 파일", "처리 불가능 파일 사전 차단", "P0", "FILE-001"],
  ["File Integrity / Decode", "손상 파일", "Decode 실패 방지", "P0", "FILE-002"],
  ["File Size (사용자 설정)", "AI 서비스 용량 제한", "업로드 거부 사전 탐지 → MP3/MP4 최적화", "P0", "FILE-003"],
  ["Audio Track", "음성 트랙 없음", "STT 불가능 상태 탐지", "P0", "AUDIO-001"],
  ["Channel Count", "다채널 구조", "채널 분석의 전제 (채널 수 자체는 오류 아님)", "P0", "AUDIO-004"],
  ["Channel Level", "L/R 음량 편차", "한쪽 채널 이상 탐지", "P0", "AUDIO-005"],
  ["Silence Ratio", "실질적 무음", "STT 0건 가능성 탐지", "P0", "AUDIO-006"],
  ["Speech Activity", "음성 자체 부족/편중", "분석 가능성 판단", "P0", "AUDIO-007"],
  ["L/R Correlation · Mono Downmix", "채널 간 상쇄", "위상/상관관계 이상 가능성 탐지", "P1→P0", "AUDIO-008"],
  ["Sample Rate", "음성 입력 조건", "변환 필요성 판단", "P1", "AUDIO-003"],
  ["Codec", "처리 호환성", "지원 여부 확인", "P1", "AUDIO-002"],
  ["Video Resolution / Frame Rate", "영상 분석 품질", "Scene Analysis 시 필요", "P2", "metadata만 수집"],
  ["Blur / Noise", "영상 품질", "영상 인식 품질 개선", "P3", "V1 제외"],
];

export default function Showcase() {
  return (
    <div>
      <section className="hero">
        <p className="muted small">AI Media Preflight &amp; Troubleshooting Assistant</p>
        <h1>AI가 성공했다고 했는데, 왜 결과는 0개일까?</h1>
        <p className="lead">
          네이버클라우드에서 교육 영상의 STT 데이터를 구축하던 중, 처리 상태는 SUCCESS였지만 추출 문장이 0개인 문제를 경험했습니다.
          원인을 찾고 해결하는 데 약 2시간이 걸렸습니다. 이 프로젝트는 그 troubleshooting 과정을{" "}
          <b>진단 → 설명 → 자동수정 → 재검증</b>이라는 제품 workflow로 바꾼 것입니다.
        </p>
        <div className="toc" style={{ marginTop: 20 }}>
          <a className="btn primary" href="#demo">Try the Demo</a>
          <a className="btn" href="#requirements">View PRD</a>
          <a className="btn" href="#architecture">Architecture</a>
          <a className="btn" href="#kpi">KPI &amp; Roadmap</a>
          <a className="btn" href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub ↗</a>
          {PDF_URL && <a className="btn" href={PDF_URL} target="_blank" rel="noreferrer">Portfolio PDF ↗</a>}
          <Link className="btn" href="/">실제 파일로 써보기</Link>
        </div>
      </section>

      <section className="block" id="problem">
        <h2>Problem</h2>
        <div className="compare">
          <div className="card">
            <h3>System Success</h3>
            <p>파일이 처리 pipeline을 통과함</p>
            <pre className="pre">{`Upload → AI Processing → SUCCESS`}</pre>
          </div>
          <div className="card">
            <h3>Business Success</h3>
            <p>실제로 사용할 수 있는 STT 결과가 생성됨</p>
            <pre className="pre">{`SUCCESS → 문장 0개 → ❓`}</pre>
          </div>
        </div>
        <p style={{ marginTop: 16 }}>
          가장 큰 pain point는 실패 자체가 아니라 <b>실패했는데 실패라고 알려주지 않는 것</b>입니다. 시스템은 왜 0건인지, 어떻게 고치는지
          알려주지 않았고 사용자가 직접 진단 시스템 역할을 해야 했습니다. 여기에 AI 서비스의 입력 용량 제한 때문에 MP4를 MP3로 바꿔 다시
          올리는 재작업도 반복됐습니다.
        </p>
      </section>

      <section className="block" id="why">
        <h2>Why this matters</h2>
        <div className="compare">
          <pre className="pre">{`Before
CLOVA Speech 업로드
  ↓ SUCCESS
  ↓ STT = 0
  ↓ 원인 불명
  ↓ 영상/오디오/채널/형식 직접 비교
  ↓ 변환 방법 여러 번 시도
  ↓ 약 2시간
  ↓ 해결 → 약 100개 파일에 수동 적용`}</pre>
          <pre className="pre">{`After
파일 업로드
  ↓ AI Readiness Check
  ↓ ✕ 모노 다운믹스 시 음성 상쇄
  ↓ 원인·영향·조치 설명
  ↓ [자동으로 수정하기]
  ↓ 동일 검사 재실행 → READY
  ↓ 다운로드 → AI 서비스`}</pre>
        </div>
        <p className="small muted" style={{ marginTop: 12 }}>
          핵심 가치: Troubleshooting Time Reduction. &lsquo;수분 이내&rsquo;는 목표치이며, 실제 달성 여부는 운영 데이터(Time to Resolution)로 측정합니다.
        </p>
      </section>

      <section className="block" id="how">
        <h2>How I solved it</h2>
        <div className="flow">
          <span>Diagnose</span><i>→</i><span>Explain</span><i>→</i><span>Fix</span><i>→</i><span>Verify</span><i>→</i><span>Process</span>
        </div>
        <ol style={{ marginTop: 16 }}>
          <li><b>File Pre-check / Diagnostics</b>: 형식·디코드·크기·track·codec·sample rate·채널 수를 ffprobe/ffmpeg로 측정</li>
          <li><b>Audio Signal Integrity</b>: 채널별 RMS·무음 비율·음성 활동, L/R 상관계수, 모노 다운믹스 손실을 계산</li>
          <li><b>Problem Diagnosis</b>: rule engine이 Ready / Review Required / Not Ready로 분류하고 원인·영향·조치를 설명</li>
          <li><b>Auto Fix / Optimization</b>: 근거가 명확한 경우에만 FFmpeg 변환(채널 교정, MP3 추출, MP4 압축), batch 지원</li>
          <li><b>Verification</b>: 수정본에 동일 진단 + fix별 검증을 다시 실행, 통과해야만 다운로드</li>
        </ol>
        <h3 style={{ marginTop: 20 }}>Exception handling: 자동수정에도 조건을 붙였습니다</h3>
        <pre className="pre">{`Channel Analysis
  ├─ L/R 정상                          → 그대로 진행 (stereo 자체는 오류 아님)
  ├─ 한쪽 채널 이상 (근거 명확)          → Channel Correction 제안
  │    · 한쪽이 사실상 무음 (≥20dB 차이 & 무음 ≥90%)
  │    · 모노로 합치면 음성이 사라짐 (손실 ≥10dB & 음성구간 절반 이하)
  └─ 판단 불확실 (레벨 차이만 큼, 상관 낮음) → Review Required, 자동수정 없음`}</pre>
      </section>

      <section className="block" id="demo">
        <h2>Interactive Demo</h2>
        <p className="muted">파일 업로드 없이 핵심 흐름을 확인할 수 있습니다. 수치는 합성 샘플을 실제 분석기로 측정한 값입니다.</p>
        <Demo />
      </section>

      <section className="block" id="requirements">
        <h2>Product Requirements: 왜 이 검사를 넣었는가</h2>
        <p>
          &ldquo;검사할 수 있는 것은 전부 검사한다&rdquo;가 아니라 <b>&ldquo;사용자의 핵심 실패 원인부터 검사한다&rdquo;</b>. 실제 장애의 원인은 영상
          화질이 아니라 음성 채널 조건이었기 때문에 V1은 Video Integrity를 최소로 두고 Audio Signal Integrity를 핵심 기능으로 설계했습니다.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>검사 항목</th><th>실제 Pain Point</th><th>제품적 목적</th><th>우선순위</th><th>구현</th></tr>
            </thead>
            <tbody>
              {REQUIREMENTS.map(([a, b, c, d, e]) => (
                <tr key={a}><td>{a}</td><td>{b}</td><td>{c}</td><td><b>{d}</b></td><td className="mono small">{e}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>
          AUDIO-008은 P1로 시작했지만, 레벨이 같은 역상 파일은 L/R 음량 비교(AUDIO-005)로 잡히지 않는다는 것을 테스트로 확인하고 P0로 올렸습니다.
          용량 한도는 서비스·계정별로 달라 하드코딩하지 않고 사용자가 입력합니다.
        </p>
      </section>

      <section className="block" id="architecture">
        <h2>Architecture</h2>
        <pre className="pre">{`[Browser] ── Next.js (Vercel)
    │  REST/JSON                    ┌─ signed URL PUT/GET ─┐
    ▼                               ▼                      │
 FastAPI (Cloud Run) ── PostgreSQL (jobs, diagnostics, fix_jobs, events)
    │  enqueue
    ▼
 Cloud Tasks ──▶ Media Worker (Cloud Run, 비공개) ── ffprobe / ffmpeg / numpy signal analysis
                      │
                      ▼
             S3-compatible Object Storage (GCS)  ← 원본·결과 분리, 24h 후 삭제

 - - - - - - - - - - - - Concept (V3+, 미구현) - - - - - - - - - - - -
 Verified file ─▶ CLOVA Speech API ─▶ STT ─┬─▶ Zero-output 검증
                                           └─▶ Scene Analysis ─▶ Metadata ─▶ Human Review ─▶ Search / Reuse`}</pre>
        <ul className="small" style={{ marginTop: 12 }}>
          <li>웹 요청에서는 FFmpeg를 실행하지 않습니다. 모든 변환은 worker job으로 처리합니다.</li>
          <li>Cloud Run은 요청이 없으면 꺼지므로 상시 실행 worker 대신 Cloud Tasks가 worker를 호출합니다(로컬은 Redis Queue).</li>
          <li>파일은 서버를 거치지 않고 짧은 TTL의 signed URL로 object storage에 직접 업로드/다운로드합니다.</li>
          <li>진단 rule과 임계값은 registry(<code>rules.py</code>) 한 곳에서 관리하고, 모든 결과에 raw metric을 남깁니다.</li>
          <li>FFmpeg 인자는 whitelist 값만 허용하고 argument array로 실행합니다(shell 문자열 결합 없음).</li>
        </ul>
      </section>

      <section className="block" id="kpi">
        <h2>KPI</h2>
        <pre className="pre">{`North Star: First-Pass Processing Success Rate
  │  최초 업로드 후 수정·재업로드 없이 AI 분석 결과가 정상 생성된 비율
  ├─ Input Quality
  │    ├─ Media Readiness Detection Rate   실제 문제 중 사전 탐지 비율 (labeled set)
  │    └─ False Positive Rate              정상 파일을 문제로 판단한 비율
  ├─ Operational Efficiency
  │    ├─ Time to Diagnosis                ✓ 측정 중
  │    ├─ Time to Resolution               ✓ 측정 중
  │    └─ Re-upload / Reprocessing Rate
  └─ AI Output Quality
       ├─ Zero-Output Rate                 SUCCESS인데 STT 0건 (V3: API 연동 후)
       ├─ Verification Pass Rate           ✓ 측정 중
       └─ Manual Review Rate               ✓ 측정 중`}</pre>
        <p className="small muted" style={{ marginTop: 10 }}>
          Zero-Output Rate는 System Success와 Business Success의 차이를 직접 측정하는 지표입니다. 사람이 수정하지 않았다고 AI 결과가
          정확하다는 뜻은 아니므로 Human Correction Rate를 &lsquo;정확도&rsquo;와 동일시하지 않습니다. 이 서비스에서 측정 가능한 지표는{" "}
          <code>GET /api/v1/kpi</code>로 집계합니다.
        </p>
      </section>

      <section className="block" id="roadmap">
        <h2>Roadmap</h2>
        <div className="table-scroll">
          <table>
            <thead><tr><th>단계</th><th>범위</th><th>상태</th></tr></thead>
            <tbody>
              <tr><td>V1</td><td>Preflight + Diagnosis (File / Audio / Channel / Speech)</td><td>✓ 구현</td></tr>
              <tr><td>V2</td><td>Auto Fix + Batch Processing + Verification</td><td>✓ 구현</td></tr>
              <tr><td>V3</td><td>CLOVA Speech API 연계, STT 결과 검증(Zero-output 탐지)</td><td>Concept</td></tr>
              <tr><td>V4</td><td>STT / Metadata / Search / Content Reuse</td><td>Concept</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="block" id="role">
        <h2>My Role / Evidence</h2>
        <p>문제 정의, 요구사항·우선순위, 진단 rule과 예외 처리 설계, KPI·로드맵 기획, 그리고 동작하는 MVP 구현.</p>
        <div className="compare">
          <div className="card">
            <h3>실제 경험으로 확인된 것</h3>
            <ul className="small">
              <li><code>-ac 1</code>(모노 변환) 방식은 실패했다.</li>
              <li>Premiere의 Fill Left with Right 방식은 성공했다.</li>
              <li>FFmpeg <code>pan=stereo|c0=c0|c1=c0</code>로 같은 방향의 처리가 가능했다.</li>
              <li><code>-c:v copy</code>로 영상은 재인코딩하지 않았다.</li>
              <li>수정 파일은 CLOVA Speech에서 정상 STT 결과를 생성했다.</li>
            </ul>
          </div>
          <div className="card">
            <h3>가설로 구분하는 것</h3>
            <ul className="small">
              <li>원인을 &lsquo;위상 상쇄&rsquo;로 확정하지 않습니다. 당시 원본의 L/R 측정값이 없기 때문입니다.</li>
              <li>표현: &ldquo;L/R 채널 간 신호 이상으로 원인을 좁혔고, 정상 채널 복제로 교정했을 때 정상 처리됨을 검증했다.&rdquo;</li>
              <li>역상 합성 샘플에서 <code>-ac 1</code>은 실패, 채널 복제는 성공하는 것을 재현해 가설과 일치함을 확인했습니다.</li>
              <li>제품은 원인을 100% 판정한다고 주장하지 않고 &lsquo;가능성&rsquo;과 측정 근거를 함께 보여줍니다.</li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}
