import type { Metadata } from "next";
import Link from "next/link";
import Demo from "@/components/Demo";

export const metadata: Metadata = {
  title: "Media Preflight · 프로젝트 상세",
  description: "AI가 성공했다고 했는데, 왜 결과는 0개일까? — AI 처리 성공과 실제 업무 성공 사이의 gap을 줄이는 제품 기획·구현.",
};

const GITHUB_URL = process.env.NEXT_PUBLIC_GITHUB_URL ?? "https://github.com/Jade-Legate/media-preflight";

const TOC: [string, string][] = [
  ["problem", "문제"],
  ["solution", "해결"],
  ["decisions", "기획 판단"],
  ["demo", "데모"],
  ["requirements", "요구사항"],
  ["verification", "검증"],
  ["kpi", "KPI"],
  ["architecture", "아키텍처"],
  ["roadmap", "로드맵·역할"],
];

const REQUIREMENTS: [string, string, string, string][] = [
  ["포맷 · 디코드 · 파일 크기(사용자 설정)", "지원 불가 · 손상 · 용량 초과", "처리 불가 입력 사전 차단, MP3/MP4 최적화 제안", "P0"],
  ["Audio track · 채널 수", "음성 없음 / 채널 구조", "STT 불가 탐지, 채널 분석의 전제 (채널 수 자체는 오류 아님)", "P0"],
  ["채널별 음량 · 무음 비율 · 음성 활동", "한쪽 채널 이상, 실질적 무음", "'SUCCESS인데 0건' 가능성 탐지", "P0"],
  ["L/R 상관관계 · 모노 다운믹스 손실", "채널 간 상쇄", "위상/상관관계 이상 '가능성' 탐지", "P1→P0 *"],
  ["Codec · Sample rate", "처리 호환성", "변환 필요성 판단", "P1"],
  ["해상도 · Frame rate", "영상 분석 품질", "Scene Analysis 단계에서 필요 (metadata만 수집)", "P2"],
  ["Blur · Noise", "영상 품질", "영상 인식 품질 개선", "P3 (V1 제외)"],
];

const DECISIONS: [string, React.ReactNode][] = [
  [
    "① 전부가 아니라 '실패 원인부터' 검사한다",
    <>
      영상 화질(해상도·blur·noise)까지 검사하면 범위만 커집니다. 실제 실패 원인은 <b>음성 채널 조건</b>이었기 때문에 V1은 Video Integrity를
      최소로 두고 <b>Audio Signal Integrity</b>를 핵심으로 설계했습니다. 이름도 File Validation이 아니라 <b>AI Processing Readiness Check</b>입니다.
    </>,
  ],
  [
    "② 채널 수는 오류가 아니다",
    <>
      stereo는 정상입니다. &lsquo;Channel = 2 → 경고&rsquo;는 오탐입니다. 봐야 하는 것은 <b>채널 간 상태 이상</b>: 채널별 음량, 무음 비율, 음성 활동,
      L/R 상관관계, 그리고 <b>모노로 합쳤을 때 음성이 사라지는지</b>입니다.
    </>,
  ],
  [
    "③ 자동 수정에도 조건을 붙인다",
    <>
      무조건 L→L/R 복제를 하면 정상 stereo 콘텐츠를 망칩니다. 근거가 명확할 때만 자동 수정하고, 애매하면 <b>Review Required + 수동 검토</b>로
      둡니다. &lsquo;AI가 알아서 고친다&rsquo;가 아니라 <b>검증된 결정적 변환</b>을 제품화했습니다.
    </>,
  ],
  [
    "④ 사실과 가설을 구분한다",
    <>
      확인된 사실은 <code>-ac 1</code>(모노 변환) 실패, 정상 채널 복제(<code>pan</code> + <code>-c:v copy</code>) 후 정상 STT입니다. 당시 L/R 측정값이 없으므로
      원인을 &lsquo;위상 상쇄&rsquo;로 <b>확정하지 않고</b>, 제품도 &lsquo;가능성 + 측정 근거&rsquo;로 표현합니다.
    </>,
  ],
];

export default function Showcase() {
  return (
    <div>
      <section className="hero">
        <p className="muted small">AI 영상 프로덕트 기획 포트폴리오 · Jisun Kim</p>
        <h1>AI가 성공했다고 했는데, 왜 결과는 0개일까?</h1>
        <p className="lead">
          AI 음성·영상 분석 전에 미디어 입력을 진단하고, 원인을 설명하고, 자동 수정한 뒤 재검증하는 웹 서비스{" "}
          <b>AI Media Preflight &amp; Troubleshooting Assistant</b>의 기획과 구현 과정입니다.
        </p>
        <div className="row" style={{ marginTop: 16 }}>
          <Link className="btn primary" href="/">직접 써보기</Link>
          <a className="btn" href="#demo">샘플로 체험하기</a>
          <a className="btn" href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub ↗</a>
        </div>
        <nav className="toc" aria-label="목차" style={{ marginTop: 20 }}>
          {TOC.map(([id, label], i) => (
            <a key={id} href={`#${id}`} className="small">{i + 1}. {label}</a>
          ))}
        </nav>
      </section>

      <section className="block" id="problem">
        <h2>1. 문제: 시스템은 성공했는데, 결과는 0개</h2>
        <p>
          교육 영상의 STT 데이터를 CLOVA Speech로 구축하던 중, 처리 상태는 <b>SUCCESS</b>인데 추출 문장이 <b>0개</b>인 장애를 겪었습니다.
          시스템은 원인도 해결 방법도 알려주지 않았고, 영상·오디오·채널·포맷을 직접 비교하며 원인을 좁히는 데 <b>약 2시간</b>이 걸렸습니다.
          해결 후에는 같은 조치를 약 100개 파일에 수동으로 적용했고, 입력 용량 제한 때문에 MP4를 MP3로 바꿔 재업로드하는 작업도 반복됐습니다.
        </p>
        <div className="quote">
          <b>Pain Point 정의.</b> 가장 큰 비용은 실패 자체가 아니라 <b>&ldquo;실패했는데 실패라고 알려주지 않는 것&rdquo;</b>입니다.
          <br />System Success(파이프라인 통과) ≠ Business Success(쓸 수 있는 STT 결과). 이 차이를 사람이 직접 진단해야 했습니다.
        </div>
        <div className="compare">
          <pre className="pre">{`Before  (사람이 진단 시스템 역할)
CLOVA Speech 업로드
  ↓ SUCCESS
  ↓ STT 문장 0개, 원인 표시 없음
  ↓ 영상/오디오/채널/포맷 직접 비교
  ↓ 변환 방법 여러 번 시도 (-ac 1 실패)
  ↓ 약 2시간 → 해결 방법 발견
  ↓ 약 100개 파일에 수동 적용`}</pre>
          <pre className="pre">{`After  (Media Preflight)
파일 업로드 (여러 개 가능)
  ↓ AI Readiness Check
  ↓ ✕ NOT READY: 모노 합산 시 음성 소멸
  ↓   원인 가능성 · 예상 영향 · 권장 조치
  ↓ [자동으로 수정하기]
  ↓ 동일 검사 재실행 → ● READY
  ↓ 다운로드 → AI 서비스`}</pre>
        </div>
      </section>

      <section className="block" id="solution">
        <h2>2. 해결: troubleshooting 과정을 제품 workflow로</h2>
        <div className="flow">
          <span>Diagnose</span><i>→</i><span>Explain</span><i>→</i><span>Fix</span><i>→</i><span>Verify</span><i>→</i><span>Process</span>
        </div>
        <div className="table-scroll" style={{ marginTop: 14 }}>
          <table>
            <tbody>
              <tr><td><b>Diagnose</b></td><td>포맷·디코드·크기·track·codec·채널 수를 측정하고, 채널별 음량·무음 비율·음성 활동·L/R 상관관계·모노 다운믹스 손실을 계산</td></tr>
              <tr><td><b>Explain</b></td><td>Ready / Review Required / Not Ready로 분류하고, 문제마다 원인·예상 영향·권장 조치를 설명</td></tr>
              <tr><td><b>Fix</b></td><td>근거가 명확할 때만 FFmpeg 자동 수정: 채널 교정, MP3 추출(Speech-only), MP4 압축(Video). 여러 파일 batch 처리</td></tr>
              <tr><td><b>Verify</b></td><td>수정본에 같은 진단을 다시 실행하고, 통과한 파일만 다운로드 제공</td></tr>
              <tr><td><b>Process</b></td><td>AI 서비스로 전달 (V3: CLOVA Speech API 직접 연동 예정)</td></tr>
            </tbody>
          </table>
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>
          목표 가치는 Troubleshooting Time 약 2시간 → 수분입니다. 실제 달성 여부는 운영 데이터(Time to Resolution)로 측정합니다.
        </p>
      </section>

      <section className="block" id="decisions">
        <h2>3. 핵심 기획 판단</h2>
        <div className="grid4">
          {DECISIONS.map(([title, body]) => (
            <div className="card" key={title}>
              <h3>{title}</h3>
              <p className="small" style={{ margin: 0 }}>{body}</p>
            </div>
          ))}
        </div>
        <h3 style={{ marginTop: 24 }}>예외 처리: 자동 수정 조건</h3>
        <pre className="pre">{`Channel Analysis
 ├ L/R 정상                              → 그대로 진행
 ├ 한쪽 채널 이상 (근거 명확)
 │   · 한쪽이 사실상 무음 (≥20dB 차이, 무음 ≥90%)
 │   · 모노로 합치면 음성이 사라짐 (손실 ≥10dB, 음성 구간 절반 이하)
 │                                       → Channel Correction 제안
 └ 판단 불확실 (레벨 차이만 큼, 상관 낮음) → Review Required, 자동수정 없음`}</pre>
      </section>

      <section className="block" id="demo">
        <h2>4. 샘플로 체험하기</h2>
        <p className="muted">파일 없이 핵심 흐름을 확인할 수 있습니다. 수치는 합성 샘플을 실제 분석기로 측정한 값입니다.</p>
        <Demo />
      </section>

      <section className="block" id="requirements">
        <h2>5. 요구사항과 우선순위</h2>
        <p>
          P0/P1/P2를 나눈 논리 자체가 기획입니다. &ldquo;검사할 수 있는 것은 전부 검사한다&rdquo;가 아니라{" "}
          <b>&ldquo;사용자의 핵심 실패 원인부터 검사한다&rdquo;</b>.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>검사 항목</th><th>실제 Pain Point</th><th>제품적 목적</th><th>우선순위</th></tr>
            </thead>
            <tbody>
              {REQUIREMENTS.map(([a, b, c, d]) => (
                <tr key={a}><td>{a}</td><td>{b}</td><td>{c}</td><td><b>{d}</b></td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>
          * 테스트 중 발견: 레벨이 같은 역상 파일은 L/R 음량 비교로는 정상으로 보입니다. 모노 다운믹스 검사만 이를 잡아내서 P0로 올렸습니다.
          용량 한도는 서비스·계정별로 달라 하드코딩하지 않고 사용자가 입력합니다.
        </p>
      </section>

      <section className="block" id="verification">
        <h2>6. 검증: 가설을 재현하고 제품으로 확인</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>합성 샘플 (역상 stereo)</th><th>모노 다운믹스 음성 구간</th><th>AI Readiness</th><th>실제 경험과 비교</th></tr>
            </thead>
            <tbody>
              <tr><td>원본</td><td>0% (L/R 음량은 동일)</td><td><span className="badge fail">✕ NOT READY</span></td><td>SUCCESS인데 STT 0건</td></tr>
              <tr><td><code>-ac 1</code> 모노 변환</td><td>0%</td><td><span className="badge fail">✕ NOT READY</span></td><td>실패했던 방법과 일치</td></tr>
              <tr><td>FIX-001 정상 채널 복제 (<code>-c:v copy</code>)</td><td>80%</td><td><span className="badge ready">● READY</span></td><td>성공했던 방법과 일치</td></tr>
            </tbody>
          </table>
        </div>
        <p className="small" style={{ marginTop: 10 }}>
          정상 · 한쪽 무음 · 한쪽 약화(애매) · 무음 · 오디오 없음 · 손상 · 용량 초과 등 9종 합성 미디어로 PRD의 QA 기준(QA-001~012)을{" "}
          <b>자동화 테스트 23건</b>으로 검증했습니다. 실제 업무 영상은 사용하지 않았습니다.
        </p>
      </section>

      <section className="block" id="kpi">
        <h2>7. KPI</h2>
        <pre className="pre">{`North Star: First-Pass Processing Success Rate
  │  최초 업로드 후 수정·재업로드 없이 AI 분석 결과가 정상 생성된 비율
  ├─ Input Quality
  │    ├─ Media Readiness Detection Rate   실제 문제 중 사전 탐지 비율 (labeled set)
  │    └─ False Positive Rate              정상 파일을 문제로 판단한 비율
  ├─ Operational Efficiency
  │    ├─ Time to Diagnosis                ✓ 집계 중
  │    ├─ Time to Resolution               ✓ 집계 중
  │    └─ Re-upload / Reprocessing Rate
  └─ AI Output Quality
       ├─ Zero-Output Rate                 SUCCESS인데 STT 0건 (V3: API 연동 후)
       ├─ Verification Pass Rate           ✓ 집계 중
       └─ Manual Review Rate               ✓ 집계 중`}</pre>
        <p className="small muted" style={{ marginTop: 10 }}>
          Zero-Output Rate는 System Success와 Business Success의 차이를 직접 측정하는 지표입니다. 사람이 수정하지 않았다고 AI 결과가 정확하다는
          뜻은 아니므로 Human Correction Rate를 &lsquo;정확도&rsquo;와 동일시하지 않습니다.
        </p>
      </section>

      <section className="block" id="architecture">
        <h2>8. 아키텍처</h2>
        <pre className="pre">{`[Browser] ── Next.js (Vercel)
    │  REST/JSON                    ┌─ signed URL PUT/GET ─┐
    ▼                               ▼                      │
 FastAPI ── PostgreSQL (jobs, diagnostics, fix_jobs, events)
    │  enqueue
    ▼
 Queue ──▶ Media Worker ── ffprobe / ffmpeg / numpy signal analysis
                │
                ▼
       Object Storage  ← 원본·결과 분리, 24시간 후 삭제

 - - - - - - - - - - - Concept (V3+, 미구현) - - - - - - - - - - -
 Verified file ─▶ CLOVA Speech API ─▶ STT ─┬─▶ Zero-output 검증
                                           └─▶ Scene Analysis ─▶ Metadata ─▶ Human Review ─▶ Search / Reuse`}</pre>
        <ul className="small" style={{ marginTop: 12 }}>
          <li>웹 요청에서는 FFmpeg를 실행하지 않고, 모든 변환은 worker 작업으로 처리합니다.</li>
          <li>파일은 짧은 TTL의 서명된 URL로 업로드/다운로드하고, 원본과 결과를 분리 보관한 뒤 24시간 후 삭제합니다.</li>
          <li>진단 rule과 임계값은 한 곳(rule registry)에서 관리하고, 모든 결과에 측정값(raw metric)을 남겨 사람이 검증할 수 있게 했습니다.</li>
          <li>FFmpeg 인자는 허용된 값만 받고 argument array로 실행합니다(shell 문자열 결합 없음).</li>
        </ul>
      </section>

      <section className="block" id="roadmap">
        <h2>9. 로드맵과 역할</h2>
        <div className="table-scroll">
          <table>
            <thead><tr><th>단계</th><th>범위</th><th>상태</th></tr></thead>
            <tbody>
              <tr><td>V1</td><td>Preflight + Diagnosis (File / Audio / Channel / Speech)</td><td><span className="badge ready">구현</span></td></tr>
              <tr><td>V2</td><td>Auto Fix + Batch Processing + Verification</td><td><span className="badge ready">구현</span></td></tr>
              <tr><td>V3</td><td>CLOVA Speech API 연동, STT 결과 검증(Zero-output 탐지)</td><td><span className="badge neutral">계획</span></td></tr>
              <tr><td>V4</td><td>STT / Metadata / Search / Content Reuse</td><td><span className="badge neutral">계획</span></td></tr>
            </tbody>
          </table>
        </div>
        <div className="compare" style={{ marginTop: 16 }}>
          <div className="card">
            <h3>내가 한 일</h3>
            <ul className="small">
              <li>문제 정의, PRD·요구사항·우선순위, 예외 처리, KPI·로드맵 기획</li>
              <li>동작하는 MVP 구현: Next.js · FastAPI · PostgreSQL · FFmpeg/ffprobe · numpy 신호 분석 · 비동기 worker</li>
              <li>FFmpeg는 목적이 아니라 <b>문제 해결의 실행 수단</b>. 핵심은 입력 진단 → 자동 교정 → 재검증으로 이어지는 Product Workflow</li>
            </ul>
          </div>
          <div className="card">
            <h3>실제 경험으로 확인된 사실</h3>
            <ul className="small">
              <li><code>-ac 1</code>(모노 변환) 방식은 실패했다.</li>
              <li>Premiere의 Fill Left with Right 방식은 성공했다.</li>
              <li>FFmpeg <code>pan=stereo|c0=c0|c1=c0</code>로 같은 방향의 처리가 가능했다.</li>
              <li><code>-c:v copy</code>로 영상은 재인코딩하지 않았다.</li>
              <li>수정 파일은 CLOVA Speech에서 정상 STT 결과를 생성했다.</li>
            </ul>
          </div>
        </div>
        <div className="row" style={{ marginTop: 24 }}>
          <Link className="btn primary" href="/">직접 써보기</Link>
          <a className="btn" href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub ↗</a>
        </div>
      </section>
    </div>
  );
}
