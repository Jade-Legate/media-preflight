"use client";

import { useState } from "react";
import demo from "@/lib/demo.json";
import type { Diagnostic } from "@/lib/api";
import { ChannelPanel, IssueList, READINESS_TEXT, StatusBadge, TechDetails, Verification, issuesOf } from "./Diagnosis";

// 실제 분석기로 합성 샘플(phase_inverted.mp4)을 돌려 얻은 결과. 수치는 만든 값이 아니라 측정값이다.
const asDiag = (x: object) => ({ ...x, diagnosticId: "demo", status: "DONE", errorCode: null }) as unknown as Diagnostic;
const before = asDiag(demo.before);
const after = asDiag(demo.after);
const naive = asDiag(demo.naiveMono);
const src = demo.fix.params.sourceChannel;

const STEPS = ["1. 기존 방식", "2. 진단", "3. Auto Fix", "4. 재검증"];

export default function Demo() {
  const [step, setStep] = useState(0);
  const [showNaive, setShowNaive] = useState(false);
  return (
    <div className="card stack">
      <div className="steps" role="tablist">
        {STEPS.map((s, i) => (
          <button key={s} className="btn" role="tab" aria-current={step === i ? "step" : undefined} aria-selected={step === i} onClick={() => setStep(i)}>
            {s}
          </button>
        ))}
      </div>

      {step === 0 && (
        <div className="stack">
          <h3>{demo.fileName} → AI 음성인식</h3>
          <pre className="pre">{`처리 상태    SUCCESS
추출 문장 수  0
실패 원인    (표시되지 않음)
해결 방법    (표시되지 않음)`}</pre>
          <p>
            시스템은 성공이라고 하지만 쓸 수 있는 결과는 없습니다. 사용자는 영상 문제인지, 오디오 문제인지, 서비스 문제인지 모른 채
            직접 원인을 찾아야 합니다.
          </p>
          <button className="btn primary" onClick={() => setStep(1)}>같은 파일을 Media Preflight로 진단하기 →</button>
        </div>
      )}

      {step === 1 && (
        <div className="stack">
          <div className="row spread">
            <h3 style={{ margin: 0 }}>{demo.fileName}</h3>
            <StatusBadge status={before.overallStatus!} />
          </div>
          <p>{READINESS_TEXT[before.overallStatus!]}</p>
          <IssueList results={issuesOf(before)} />
          <ChannelPanel metrics={before.metrics} />
          <p className="small muted">
            L/R 음량은 같아서 단순 레벨 비교로는 정상처럼 보입니다. 하지만 두 채널을 모노로 합치면 음성이 사라집니다. 이것이
            &lsquo;처리는 성공했는데 결과는 0건&rsquo;을 설명할 수 있는 측정 근거입니다.
          </p>
          <TechDetails diagnostic={before} />
          <button className="btn primary" onClick={() => setStep(2)}>자동으로 수정하기 →</button>
        </div>
      )}

      {step === 2 && (
        <div className="stack">
          <h3>FIX-001 Audio Channel Correction</h3>
          <p>진단이 정상으로 판단한 {src === 0 ? "L" : "R"} 채널을 양쪽에 복제합니다. 영상 stream은 재인코딩하지 않고 복사합니다.</p>
          <pre className="pre">{`ffmpeg -i ${demo.fileName} \\
  -map 0:v:0? -c:v copy \\
  -map 0:a:0 -af "pan=stereo|c0=c${src}|c1=c${src}" \\
  -c:a aac -b:a 192k lecture_01_fix-001.mp4`}</pre>
          <p className="small muted">
            실제 업무에서 검증한 해결 방향을 결정적(deterministic) 변환으로 제품화했습니다. 채널 판단이 불확실한 파일에는 이 버튼이
            나타나지 않습니다.
          </p>
          <label className="small">
            <input type="checkbox" checked={showNaive} onChange={(e) => setShowNaive(e.target.checked)} />
            비교: 단순 모노 변환(<code>-ac 1</code>)을 했다면?
          </label>
          {showNaive && (
            <div className="issue fail">
              <h4>-ac 1 결과: <StatusBadge status={naive.overallStatus!} /></h4>
              {issuesOf(naive).map((r) => (
                <div key={r.ruleId} className="small">✕ {r.title}: {r.message}</div>
              ))}
              <div className="small muted" style={{ marginTop: 6 }}>모노 다운믹스가 같은 상쇄를 재현합니다. 실제 경험에서도 이 방법은 실패했습니다.</div>
            </div>
          )}
          <button className="btn primary" onClick={() => setStep(3)}>재검증 결과 보기 →</button>
        </div>
      )}

      {step === 3 && (
        <div className="stack">
          <Verification before={before} after={after} checks={demo.fix.checks as never} />
          <b style={{ color: "var(--ready)" }}>● READY FOR SPEECH PROCESSING</b>
          <p className="small muted">수정 → 동일 진단 재실행 → 통과해야만 다운로드를 제공합니다. 검증에 실패한 결과물은 격리됩니다.</p>
        </div>
      )}
    </div>
  );
}
