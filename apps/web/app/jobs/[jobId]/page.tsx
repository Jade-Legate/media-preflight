"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, mb, post, type Job, type JobFile, type RuleResult } from "@/lib/api";
import { IssueList, OptimizeControls, READINESS_TEXT, StatusBadge, TechDetails, Verification, issuesOf } from "@/components/Diagnosis";

const FAILURE_TEXT: Record<string, string> = {
  STORAGE_ERROR: "일시적인 저장소 오류입니다. 다시 시도하세요.",
  WORKER_TIMEOUT: "처리 시간이 초과되었습니다. 다시 시도하세요.",
  AUDIO_DECODE_FAILED: "오디오를 디코드하지 못했습니다.",
  FIX_FAILED: "파일 변환에 실패했습니다. 원본은 그대로 보존됩니다.",
  VERIFY_FAILED: "수정 결과가 재검증을 통과하지 못해 다운로드를 제공하지 않습니다.",
};

export default function JobPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setJob(await api<Job>(`/api/v1/jobs/${jobId}`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "작업을 불러오지 못했습니다.");
    }
  }, [jobId]);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (job?.status !== "PROCESSING") return;
    const t = setTimeout(load, 1500);
    return () => clearTimeout(t);
  }, [job, load]);

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "요청에 실패했습니다.");
    }
    load();
  };

  if (!job) return error ? <div className="error">{error}</div> : <p className="muted">불러오는 중…</p>;
  const s = job.summary;

  return (
    <div className="stack">
      <div className="row spread">
        <div>
          <Link href="/" className="small">← 새 파일 진단</Link>
          <h1 style={{ marginTop: 6 }}>Diagnosis</h1>
          <div className="muted small">
            {job.mode === "speech" ? "Speech-only" : "Video analysis"} · 용량 제한 {job.maxFileSizeMb ? `${job.maxFileSizeMb} MB` : "없음"}
          </div>
        </div>
        {job.status === "PROCESSING" && <span className="badge neutral">⏳ 처리 중</span>}
      </div>

      <div className="summary-grid">
        <div className="stat"><b>{job.files.length}</b>전체 파일</div>
        <div className="stat"><b>{s.READY}</b>● Ready</div>
        <div className="stat"><b>{s.REVIEW_REQUIRED}</b>▲ Review required</div>
        <div className="stat"><b>{s.NOT_READY}</b>✕ Not ready</div>
        <div className="stat"><b>{s.OPTIMIZATION_REQUIRED}</b>용량 최적화 필요</div>
        {s.FAILED > 0 && <div className="stat"><b>{s.FAILED}</b>분석 실패</div>}
        {s.IN_PROGRESS > 0 && <div className="stat"><b>{s.IN_PROGRESS}</b>⏳ 진행 중</div>}
      </div>

      {error && <div className="error" role="alert">{error}</div>}

      {s.OPTIMIZATION_REQUIRED > 1 && <BatchBar job={job} act={act} />}

      {job.files.map((f) => (
        <FileCard key={f.fileId} file={f} job={job} act={act} />
      ))}
    </div>
  );
}

function BatchBar({ job, act }: { job: Job; act: (fn: () => Promise<unknown>) => void }) {
  const targets = job.files.filter((f) => f.diagnostic?.results.some((r) => r.ruleId === "FILE-003" && r.status === "WARN"));
  const before = targets.reduce((n, f) => n + (f.sizeBytes ?? 0), 0);
  const running = targets.some((f) => f.fixes.some((x) => x.status === "QUEUED" || x.status === "RUNNING"));
  return (
    <div className="card">
      <h3>Batch Media Optimizer</h3>
      <p className="muted small">
        용량 초과 {targets.length}개 · 합계 {mb(before)}. 파일마다 독립 작업으로 처리되며 한 파일이 실패해도 나머지는 계속됩니다.
        채널 이상이 확인된 파일은 채널 교정을 함께 적용합니다.
      </p>
      <OptimizeControls
        recommended={job.mode === "speech" ? "FIX-002" : "FIX-006"}
        channelFix={null}
        disabled={running}
        onRun={(fixId, params) =>
          act(() => post("/api/v1/batch/optimize", { jobId: job.jobId, fileIds: targets.map((f) => f.fileId), fixId, params, applyChannelCorrection: true }))
        }
      />
    </div>
  );
}

function FileCard({ file, job, act }: { file: JobFile; job: Job; act: (fn: () => Promise<unknown>) => void }) {
  const d = file.diagnostic;
  const decision = d?.metrics?.channelDecision;
  const channelFix = decision?.state === "ONE_SIDED" && decision.sourceChannel != null ? { source: decision.sourceChannel } : null;
  const fixing = file.fixes.some((x) => x.status === "QUEUED" || x.status === "RUNNING");
  const fix = (fixId: string, params: Record<string, unknown>) => act(() => post(`/api/v1/files/${file.fileId}/fix`, { fixId, params }));

  const action = (r: RuleResult) => {
    if (r.recommendedFix === "FIX-001" && channelFix)
      return (
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn primary" disabled={fixing} onClick={() => fix("FIX-001", { sourceChannel: channelFix.source })}>
            자동으로 수정하기
          </button>
          <span className="muted small">
            정상 채널({channelFix.source === 0 ? "L" : "R"})을 L/R에 복제 · 영상은 재인코딩 없이 복사 · 수정 후 자동 재검증
          </span>
        </div>
      );
    if (r.ruleId === "FILE-003" && r.recommendedFix)
      return <OptimizeControls recommended={r.recommendedFix} channelFix={channelFix} disabled={fixing} onRun={fix} />;
    if (r.recommendedFix === "FIX-003" || r.recommendedFix === "FIX-004")
      return (
        <button className="btn" style={{ marginTop: 10 }} disabled={fixing} onClick={() => fix(r.recommendedFix!, {})}>
          {job.fixCatalog[r.recommendedFix].title}
        </button>
      );
    return null;
  };

  return (
    <article className="card stack" aria-label={file.name}>
      <div className="row spread">
        <div>
          <h2 style={{ marginBottom: 2, wordBreak: "break-all" }}>{file.name}</h2>
          <span className="muted small mono">{mb(file.sizeBytes)}</span>
        </div>
        <StatusBadge status={file.status} />
      </div>

      {d?.status === "DONE" && d.overallStatus && <p style={{ margin: 0 }}>{READINESS_TEXT[d.overallStatus]}</p>}
      {d?.status === "FAILED" && (
        <div className="row">
          <div className="error">{FAILURE_TEXT[d.errorCode ?? ""] ?? "분석에 실패했습니다."}</div>
          <button className="btn" onClick={() => act(() => post(`/api/v1/files/${file.fileId}/diagnose`))}>다시 진단</button>
        </div>
      )}

      {d?.status === "DONE" && (
        <>
          <div>
            <h3>{issuesOf(d).length ? `${issuesOf(d).length}개 문제 발견` : "문제 없음"}</h3>
            <IssueList results={issuesOf(d)} renderAction={action} />
          </div>

          {file.fixes.map((x) => (
            <div key={x.fixJobId} className="card stack" style={{ background: "var(--surface-2)" }}>
              <div className="row spread">
                <h3 style={{ margin: 0 }}>
                  {x.title} <span className="muted small mono">{x.fixId}</span>
                </h3>
                <StatusBadge status={x.status} />
              </div>
              {x.errorCode && <div className="error">{FAILURE_TEXT[x.errorCode] ?? x.errorMessage ?? "처리에 실패했습니다."}</div>}
              {x.verification?.status === "DONE" && <Verification before={d} after={x.verification} checks={x.checks} />}
              {x.output && x.status === "SUCCEEDED" && (
                <div className="row spread">
                  <div>
                    {x.output.status === "READY" ? (
                      <b style={{ color: "var(--ready)" }}>● READY FOR SPEECH PROCESSING</b>
                    ) : (
                      <span>수정은 검증됐지만 남은 문제가 있습니다: <StatusBadge status={x.output.status} /></span>
                    )}
                    <div className="muted small">{x.output.name} · {mb(x.output.sizeBytes)}</div>
                  </div>
                  <DownloadButton fileId={x.output.fileId} />
                </div>
              )}
            </div>
          ))}

          <TechDetails diagnostic={d} />
        </>
      )}
    </article>
  );
}

function DownloadButton({ fileId }: { fileId: string }) {
  const [err, setErr] = useState<string | null>(null);
  return (
    <span className="row">
      <button
        className="btn primary"
        onClick={async () => {
          try {
            // signed URL은 짧게 만료되므로 클릭 시점에 발급받는다.
            const { url } = await api<{ url: string }>(`/api/v1/files/${fileId}/download`);
            window.location.href = url;
          } catch (e) {
            setErr(e instanceof ApiError ? e.message : "다운로드 링크를 만들지 못했습니다.");
          }
        }}
      >
        수정 파일 다운로드
      </button>
      {err && <span className="error small">{err}</span>}
    </span>
  );
}
