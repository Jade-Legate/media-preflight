"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { API_URL, ApiError, MAX_UPLOAD_BYTES, SUPPORTED, mb, post } from "@/lib/api";

type Picked = { file: File; problem: string | null; progress: number };

function check(f: File): string | null {
  const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
  if (!SUPPORTED.includes(ext)) return "지원하지 않는 형식";
  if (f.size === 0) return "빈 파일(0 byte)";
  if (f.size > MAX_UPLOAD_BYTES) return `업로드 한도(${mb(MAX_UPLOAD_BYTES)}) 초과`;
  return null;
}

function putWithProgress(url: string, file: File, onProgress: (p: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error(`upload ${xhr.status}`)));
    xhr.onerror = () => reject(new Error("network"));
    xhr.send(file);
  });
}

export default function Home() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<Picked[]>([]);
  const [over, setOver] = useState(false);
  const [limitOn, setLimitOn] = useState(false);
  const [limit, setLimit] = useState(500);
  const [mode, setMode] = useState<"speech" | "video">("speech");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const add = (list: FileList | null) => {
    if (!list) return;
    setFiles((prev) => [...prev, ...Array.from(list).map((file) => ({ file, problem: check(file), progress: 0 }))]);
  };
  const valid = files.filter((f) => !f.problem);

  // 무료 서버는 절전될 수 있어 페이지를 여는 순간 미리 깨운다.
  useEffect(() => {
    if (API_URL) fetch(API_URL + "/api/v1/health").catch(() => {});
  }, []);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const job = await post<{ jobId: string; files: { fileId: string; uploadUrl: string }[] }>("/api/v1/jobs", {
        files: valid.map((f) => ({ name: f.file.name, sizeBytes: f.file.size })),
        mode,
        maxFileSizeMb: limitOn ? limit : null,
      });
      // 파일은 서버를 거치지 않고 object storage로 직접 올린다(signed URL).
      await Promise.all(
        job.files.map(async (target, i) => {
          const picked = valid[i];
          for (let attempt = 0; ; attempt++) {
            try {
              await putWithProgress(target.uploadUrl, picked.file, (p) =>
                setFiles((prev) => prev.map((x) => (x === picked ? { ...x, progress: p } : x))),
              );
              break;
            } catch (e) {
              if (attempt >= 1) throw new ApiError("UPLOAD_FAILED", `${picked.file.name} 업로드에 실패했습니다. 다시 시도하세요.`);
            }
          }
          await post(`/api/v1/jobs/${job.jobId}/files/complete`, { fileId: target.fileId });
          await post(`/api/v1/files/${target.fileId}/diagnose`);
        }),
      );
      router.push(`/jobs/${job.jobId}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "알 수 없는 오류가 발생했습니다.");
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div>
        <h1>AI 분석 전에, 파일을 먼저 진단하세요.</h1>
        <p className="muted">
          STT·영상 AI에 넣기 전에 입력 파일이 실제로 처리 가능한 상태인지 확인합니다.{" "}
          <b>Diagnose → Explain → Fix → Verify</b>
        </p>
      </div>

      {!API_URL && (
        <div className="card" role="status">
          <b>실제 파일 업로드 서버를 준비 중입니다.</b>{" "}
          <span className="muted">진단 → 자동 수정 → 재검증의 전체 흐름은 </span>
          <Link href="/showcase#demo">인터랙티브 데모</Link>
          <span className="muted">에서 바로 확인할 수 있어요.</span>
        </div>
      )}

      <div
        className={`drop ${over ? "over" : ""}`}
        role="button"
        tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          add(e.dataTransfer.files);
        }}
      >
        <b>파일을 여기로 끌어다 놓거나 클릭해서 선택하세요</b>
        <div className="muted small">여러 파일 가능 · {SUPPORTED.map((s) => s.toUpperCase()).join(", ")}</div>
        <input ref={input} type="file" multiple hidden accept={SUPPORTED.map((s) => "." + s).join(",")} onChange={(e) => add(e.target.files)} />
      </div>

      {files.length > 0 && (
        <div className="card">
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>파일</th><th>크기</th><th>상태</th><th></th></tr>
              </thead>
              <tbody>
                {files.map((f, i) => (
                  <tr key={i}>
                    <td style={{ wordBreak: "break-all" }}>{f.file.name}</td>
                    <td className="mono">{mb(f.file.size)}</td>
                    <td>
                      {f.problem ? (
                        <span className="badge fail">✕ {f.problem}</span>
                      ) : busy ? (
                        <div className="meter" aria-label="업로드 진행률"><i style={{ width: `${f.progress * 100}%` }} /></div>
                      ) : (
                        <span className="badge neutral">대기</span>
                      )}
                    </td>
                    <td>
                      {!busy && (
                        <button className="btn small" onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label={`${f.file.name} 제거`}>
                          제거
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card stack">
        <div className="row">
          <label>
            <input type="checkbox" checked={limitOn} onChange={(e) => setLimitOn(e.target.checked)} />
            파일 용량 제한 검사
          </label>
          <input type="number" min={1} value={limit} disabled={!limitOn} onChange={(e) => setLimit(Math.max(1, Number(e.target.value)))} aria-label="용량 제한 MB" />
          <span>MB</span>
        </div>
        <p className="muted small" style={{ margin: 0 }}>
          사용하는 AI 서비스·계정의 실제 입력 제한값을 입력하세요. 500MB는 예시값이며 CLOVA Speech의 공식 한도가 아닙니다.
        </p>
        <fieldset className="row" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="small muted" style={{ marginBottom: 6 }}>분석 목적</legend>
          <label><input type="radio" name="mode" checked={mode === "speech"} onChange={() => setMode("speech")} /> Speech-only (STT만 필요 · MP3 변환 가능)</label>
          <label><input type="radio" name="mode" checked={mode === "video"} onChange={() => setMode("video")} /> Video analysis (영상 유지 · MP4 압축)</label>
        </fieldset>
      </div>

      {error && <div className="error" role="alert">{error}</div>}

      <div className="row spread">
        <span className="muted small">업로드 파일은 24시간 후 자동 삭제됩니다.</span>
        <button className="btn primary" disabled={!API_URL || !valid.length || busy} onClick={run}>
          {busy ? "업로드 중…" : `진단 시작 (${valid.length}개)`}
        </button>
      </div>
    </div>
  );
}
