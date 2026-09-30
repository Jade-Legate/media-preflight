"use client";

import { useState } from "react";
import type { Check, Diagnostic, Metrics, RuleResult } from "@/lib/api";
import { mb, pct } from "@/lib/api";

const LABEL: Record<string, [string, string, string]> = {
  READY: ["ready", "●", "READY"],
  REVIEW_REQUIRED: ["review", "▲", "REVIEW REQUIRED"],
  NOT_READY: ["fail", "✕", "NOT READY"],
  FAILED: ["fail", "✕", "FAILED"],
  EXPIRED: ["neutral", "–", "EXPIRED"],
  SUCCEEDED: ["ready", "✓", "VERIFIED"],
  REJECTED: ["fail", "✕", "VERIFY FAILED"],
  PASS: ["ready", "✓", "PASS"],
  WARN: ["review", "▲", "WARN"],
  FAIL: ["fail", "✕", "FAIL"],
  NOT_APPLICABLE: ["neutral", "–", "N/A"],
};

const PROGRESS: Record<string, string> = {
  UPLOADING: "업로드 중",
  QUEUED: "대기 중",
  ANALYZING: "미디어 상태를 분석하는 중",
  FIXING: "파일을 수정하는 중",
  VERIFYING: "수정 결과를 다시 확인하는 중",
  RUNNING: "처리 중",
};

export function StatusBadge({ status }: { status: string }) {
  if (PROGRESS[status]) return <span className="badge neutral">⏳ {PROGRESS[status]}</span>;
  const [cls, icon, text] = LABEL[status] ?? ["neutral", "", status];
  return <span className={`badge ${cls}`}>{icon} {text}</span>;
}

export const READINESS_TEXT: Record<string, string> = {
  READY: "AI 분석 가능: 필수 검사를 모두 통과했습니다.",
  REVIEW_REQUIRED: "분석은 가능하지만 결과 품질이 떨어질 수 있습니다. 표시된 항목을 확인하세요.",
  NOT_READY: "이대로 넣으면 AI 처리가 실패하거나 결과가 비어 있을 수 있습니다. 수정 후 다시 확인하세요.",
};

export function issuesOf(d: Diagnostic | null) {
  return (d?.results ?? []).filter((r) => r.status === "WARN" || r.status === "FAIL").sort((a, b) => (a.status === "FAIL" ? -1 : 1) - (b.status === "FAIL" ? -1 : 1));
}

export function IssueList({ results, renderAction }: { results: RuleResult[]; renderAction?: (r: RuleResult) => React.ReactNode }) {
  if (!results.length) return <p className="muted">발견된 문제가 없습니다.</p>;
  return (
    <div className="stack">
      {results.map((r) => (
        <div key={r.ruleId} className={`issue ${r.status === "FAIL" ? "fail" : "warn"}`}>
          <div className="row spread">
            <h4>
              {r.status === "FAIL" ? "✕" : "▲"} {r.title} <span className="muted small mono">{r.ruleId}</span>
            </h4>
            <StatusBadge status={r.status} />
          </div>
          <div>{r.message}</div>
          <dl>
            <dt>예상 영향</dt>
            <dd>{r.impact}</dd>
            <dt>권장 조치</dt>
            <dd>{r.action}</dd>
            {!r.recommendedFix && r.errorCode === "CHANNEL_UNCERTAIN" && (
              <>
                <dt>자동 수정</dt>
                <dd>판단 근거가 충분하지 않아 자동 수정을 제공하지 않습니다(수동 검토).</dd>
              </>
            )}
          </dl>
          {renderAction?.(r)}
        </div>
      ))}
    </div>
  );
}

export function ChannelPanel({ metrics }: { metrics: Metrics | null | undefined }) {
  const a = metrics?.audio;
  if (!a) return null;
  const st = a.stereo;
  return (
    <div className="stack">
      <div className="channels">
        {a.perChannel.slice(0, 2).map((c) => (
          <div className="chan" key={c.channel}>
            <b>{c.channel} channel</b>
            <div className="mono">RMS {c.rmsDb} dB · peak {c.peakDb} dB</div>
            <div>무음 비율 {pct(c.silenceRatio)} · 음성 활동 {pct(c.speechRatio)}</div>
          </div>
        ))}
      </div>
      {st && (
        <div className="chan">
          <b>L+R 모노 다운믹스</b>
          <div className="mono">
            상관계수 {st.correlation ?? "N/A"} · 다운믹스 손실 {st.downmixLossDb} dB
          </div>
          <div>다운믹스 후 음성 활동 {pct(st.downmixSpeechRatio)} · 무음 {pct(st.downmixSilenceRatio)}</div>
        </div>
      )}
    </div>
  );
}

export function TechDetails({ diagnostic }: { diagnostic: Diagnostic }) {
  const p = diagnostic.metrics?.probe;
  return (
    <details>
      <summary>Technical details</summary>
      <div className="stack">
        {p && (
          <p className="small mono">
            container {p.container} · {p.durationSec}s · {mb(diagnostic.metrics?.sizeBytes)} · ruleset {diagnostic.results.length} rules
          </p>
        )}
        <ChannelPanel metrics={diagnostic.metrics} />
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Rule</th><th>Check</th><th>결과</th><th>근거(metrics)</th></tr>
            </thead>
            <tbody>
              {diagnostic.results.map((r) => (
                <tr key={r.ruleId}>
                  <td className="mono">{r.ruleId}</td>
                  <td>{r.title}<div className="muted small">{r.message}</div></td>
                  <td><StatusBadge status={r.status} /></td>
                  <td className="mono small" style={{ wordBreak: "break-all" }}>{JSON.stringify(r.metrics)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </details>
  );
}

const COMPARE_RULES = ["FILE-002", "AUDIO-001", "AUDIO-005", "AUDIO-006", "AUDIO-008", "FILE-003"];

export function Verification({ before, after, checks }: { before: Diagnostic; after: Diagnostic; checks: Check[] | null }) {
  const b = Object.fromEntries(before.results.map((r) => [r.ruleId, r]));
  const a = Object.fromEntries(after.results.map((r) => [r.ruleId, r]));
  const ch = (d: Diagnostic) => {
    const x = d.metrics?.audio;
    return x ? `${x.channels}ch${x.stereo ? ` · 다운믹스 음성 ${pct(x.stereo.downmixSpeechRatio)}` : ""}` : "-";
  };
  return (
    <div className="stack">
      <div className="table-scroll">
        <table>
          <thead>
            <tr><th></th><th>Original</th><th>Fixed</th></tr>
          </thead>
          <tbody>
            <tr><td>크기</td><td className="mono">{mb(before.metrics?.sizeBytes)}</td><td className="mono">{mb(after.metrics?.sizeBytes)}</td></tr>
            <tr><td>오디오</td><td>{ch(before)}</td><td>{ch(after)}</td></tr>
            {COMPARE_RULES.filter((id) => b[id] || a[id]).map((id) => (
              <tr key={id}>
                <td>{(a[id] ?? b[id]).title}</td>
                <td>{b[id] ? <StatusBadge status={b[id].status} /> : "-"}</td>
                <td>{a[id] ? <StatusBadge status={a[id].status} /> : "-"}</td>
              </tr>
            ))}
            <tr>
              <td><b>AI Readiness</b></td>
              <td><StatusBadge status={before.overallStatus ?? "-"} /></td>
              <td><StatusBadge status={after.overallStatus ?? "-"} /></td>
            </tr>
          </tbody>
        </table>
      </div>
      {checks && (
        <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
          {checks.map((c) => (
            <li key={c.ruleId}>
              {c.status === "PASS" ? "✓" : "✕"} <span className="mono">{c.ruleId}</span> {c.title}: {c.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** FILE-003 용량 초과 시 모드와 무관하게 두 가지 최적화를 모두 제안한다. 권장안은 모드 기준. */
export function OptimizeControls({
  recommended,
  channelFix,
  disabled,
  onRun,
}: {
  recommended: string;
  channelFix: { source: number } | null;
  disabled?: boolean;
  onRun: (fixId: string, params: Record<string, unknown>) => void;
}) {
  const [bitrate, setBitrate] = useState(128);
  const [crf, setCrf] = useState(28);
  const [withChannel, setWithChannel] = useState(true);
  const ch = channelFix && withChannel ? { sourceChannel: channelFix.source } : {};
  return (
    <div className="stack" style={{ marginTop: 10 }}>
      {channelFix && (
        <label className="small">
          <input type="checkbox" checked={withChannel} onChange={(e) => setWithChannel(e.target.checked)} />
          채널 교정({channelFix.source === 0 ? "L" : "R"} → L/R)을 함께 적용
        </label>
      )}
      <div className="row">
        <select value={bitrate} onChange={(e) => setBitrate(Number(e.target.value))} aria-label="MP3 bitrate">
          {[64, 96, 128, 192].map((b) => <option key={b} value={b}>{b} kbps</option>)}
        </select>
        <button className={`btn ${recommended === "FIX-002" ? "primary" : ""}`} disabled={disabled} onClick={() => onRun("FIX-002", { bitrateKbps: bitrate, ...ch })}>
          MP3로 변환 (Speech-only){recommended === "FIX-002" ? " · 권장" : ""}
        </button>
      </div>
      <div className="row">
        <select value={crf} onChange={(e) => setCrf(Number(e.target.value))} aria-label="압축 강도">
          <option value={23}>화질 우선 (CRF 23)</option>
          <option value={28}>균형 (CRF 28)</option>
          <option value={32}>용량 우선 (CRF 32)</option>
        </select>
        <button className={`btn ${recommended === "FIX-006" ? "primary" : ""}`} disabled={disabled} onClick={() => onRun("FIX-006", { crf, maxHeight: 720, ...ch })}>
          MP4 압축 (영상 유지){recommended === "FIX-006" ? " · 권장" : ""}
        </button>
      </div>
    </div>
  );
}
