import type { Metadata } from "next";
import Link from "next/link";
import Demo from "@/components/Demo";

export const metadata: Metadata = {
  title: "Media Preflight · 프로젝트 상세",
  description: "AI가 성공했다고 했는데, 왜 결과는 0개일까? — AI 처리 성공과 실제 업무 성공 사이의 gap을 줄이는 제품 기획·구현.",
};

const GITHUB_URL = process.env.NEXT_PUBLIC_GITHUB_URL ?? "https://github.com/Jade-Legate/media-preflight";

const DECISIONS: [string, string][] = [
  ["실패 원인부터 검사한다", "영상 화질까지 다 검사하지 않고, 실제 실패 원인이었던 음성 채널을 V1의 핵심(P0)으로 뒀습니다. 영상 품질은 P2 이후."],
  ["채널 수는 오류가 아니다", "stereo는 정상입니다. 채널 수가 아니라 채널 간 이상(한쪽 무음, 모노로 합치면 음성이 사라짐)을 봅니다."],
  ["근거가 명확할 때만 자동 수정", "애매한 파일은 억지로 고치지 않고 Review Required로 사람에게 넘깁니다. 정상 stereo를 망치지 않기 위해서입니다."],
  ["사실과 가설을 구분한다", "당시 측정값이 없으므로 원인을 '위상 상쇄'로 단정하지 않고, 제품도 '가능성 + 측정 근거'로 설명합니다."],
];

export default function Showcase() {
  return (
    <div>
      <section className="hero">
        <p className="muted small">AI 영상 프로덕트 기획 포트폴리오 · Jisun Kim</p>
        <h1>AI가 성공했다고 했는데, 왜 결과는 0개일까?</h1>
        <p className="lead">
          실제 업무에서 겪은 AI 음성인식 실패를, <b>진단 → 설명 → 자동 수정 → 재검증</b>하는 제품으로 만들었습니다.
        </p>
        <div className="row" style={{ marginTop: 16 }}>
          <Link className="btn primary" href="/">직접 써보기</Link>
          <a className="btn" href="#demo">샘플로 체험하기</a>
          <a className="btn" href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub ↗</a>
        </div>
      </section>

      <section className="block" id="problem">
        <h2>1. 문제</h2>
        <p>
          교육 영상을 CLOVA Speech로 STT 처리했더니 상태는 <b>SUCCESS</b>인데 문장은 <b>0개</b>였습니다. 시스템은 이유를 알려주지 않았고,
          원인을 찾아 고치는 데 <b>약 2시간</b>이 걸렸습니다.
        </p>
        <div className="quote">
          핵심 Pain Point는 실패 자체가 아니라 <b>&ldquo;실패했는데 실패라고 알려주지 않는 것&rdquo;</b>입니다.
          <br />
          <span className="muted small">System Success(처리 완료) ≠ Business Success(쓸 수 있는 결과)</span>
        </div>
      </section>

      <section className="block" id="solution">
        <h2>2. 해결</h2>
        <div className="flow">
          <span>파일 업로드</span><i>→</i><span>진단</span><i>→</i><span>원인·조치 설명</span><i>→</i><span>자동 수정</span><i>→</i><span>재검증 후 다운로드</span>
        </div>
        <p style={{ marginTop: 14 }}>
          파일 형식·오디오 track 같은 기본 검사에 더해, <b>채널별 음량·무음 비율·음성 활동</b>과 <b>모노로 합쳤을 때 음성이 사라지는지</b>를 측정합니다.
          결과는 <span className="badge ready">● READY</span> <span className="badge review">▲ REVIEW</span> <span className="badge fail">✕ NOT READY</span>로 보여주고,
          용량이 큰 파일은 MP3 추출·MP4 압축으로 여러 개를 한 번에 줄일 수 있습니다.
        </p>
      </section>

      <section className="block" id="demo">
        <h2>3. 샘플로 체험하기</h2>
        <p className="muted">실제 장애와 같은 증상의 합성 파일을 분석기로 측정한 결과입니다.</p>
        <Demo />
      </section>

      <section className="block" id="decisions">
        <h2>4. 핵심 기획 판단</h2>
        <div className="grid4">
          {DECISIONS.map(([title, body], i) => (
            <div className="card" key={title}>
              <h3>{i + 1}. {title}</h3>
              <p className="small muted" style={{ margin: 0 }}>{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="block" id="result">
        <h2>5. 검증과 다음 단계</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>같은 문제 파일에 적용한 방법</th><th>결과</th><th>실제 경험</th></tr>
            </thead>
            <tbody>
              <tr><td>그대로 사용</td><td><span className="badge fail">✕ NOT READY</span></td><td>SUCCESS인데 0건</td></tr>
              <tr><td>단순 모노 변환 (<code>-ac 1</code>)</td><td><span className="badge fail">✕ NOT READY</span></td><td>실패했던 방법</td></tr>
              <tr><td>정상 채널 복제 (제품의 자동 수정)</td><td><span className="badge ready">● READY</span></td><td>성공했던 방법</td></tr>
            </tbody>
          </table>
        </div>
        <ul className="small" style={{ marginTop: 14 }}>
          <li><b>성과 지표:</b> 최초 업로드로 쓸 수 있는 결과를 얻은 비율(North Star), 문제 해결까지 걸린 시간, &lsquo;성공인데 0건&rsquo; 비율</li>
          <li><b>로드맵:</b> V1 진단 · V2 자동 수정/일괄 처리 (완료) → V3 CLOVA Speech API 연동 → V4 검색·재활용</li>
          <li><b>역할:</b> 문제 정의, 요구사항·우선순위, 예외 처리, KPI 설계, 동작하는 MVP 구현 (Next.js · FastAPI · FFmpeg)</li>
        </ul>
        <div className="row" style={{ marginTop: 20 }}>
          <Link className="btn primary" href="/">직접 써보기</Link>
          <a className="btn" href={GITHUB_URL} target="_blank" rel="noreferrer">요구사항·아키텍처 자세히 (GitHub) ↗</a>
        </div>
      </section>
    </div>
  );
}
