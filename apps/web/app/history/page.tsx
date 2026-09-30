"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, api, type JobSummary } from "@/lib/api";
import { formatTime, readHistory } from "@/lib/history";

const IN_PROGRESS = ["UPLOADING", "QUEUED", "ANALYZING", "FIXING", "VERIFYING"];

export default function History() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ids = readHistory();
    if (!ids.length) return setJobs([]);
    api<JobSummary[]>(`/api/v1/jobs?ids=${ids.join(",")}`)
      .then(setJobs)
      .catch((e) => setError(e instanceof ApiError ? e.message : "기록을 불러오지 못했습니다."));
  }, []);

  return (
    <div className="stack">
      <div>
        <h1>내 처리 기록</h1>
        <p className="muted small">이 브라우저에서 요청한 작업만 보여요. 업로드한 파일은 24시간 후 삭제됩니다.</p>
      </div>
      {error && <div className="error">{error}</div>}
      {jobs === null && !error && <p className="muted">불러오는 중…</p>}
      {jobs?.length === 0 && (
        <div className="card">
          아직 처리한 기록이 없어요. <Link href="/">파일 진단하러 가기</Link>
        </div>
      )}
      {jobs?.map((j) => {
        const c = j.statusCounts;
        const inProgress = IN_PROGRESS.reduce((n, k) => n + (c[k] ?? 0), 0);
        return (
          <Link key={j.jobId} href={`/jobs/${j.jobId}`} className="card history-item">
            <div className="row spread">
              <div>
                <b>{formatTime(j.createdAt)} 처리 요청</b>
                <div className="muted small">
                  파일 {j.fileCount}개{j.fixedCount > 0 && ` · 수정 ${j.fixedCount}개`} · {j.mode === "speech" ? "Speech-only" : "Video analysis"}
                </div>
              </div>
              <div className="row small">
                {inProgress > 0 && <span className="badge neutral">⏳ 진행 중 {inProgress}</span>}
                {c.READY > 0 && <span className="badge ready">● Ready {c.READY}</span>}
                {c.REVIEW_REQUIRED > 0 && <span className="badge review">▲ Review {c.REVIEW_REQUIRED}</span>}
                {c.NOT_READY > 0 && <span className="badge fail">✕ Not ready {c.NOT_READY}</span>}
                <span className="muted">›</span>
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
