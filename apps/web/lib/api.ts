// 비어 있으면 업로드 서버가 아직 연결되지 않은 상태(Showcase/데모만 동작)
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export type RuleStatus = "PASS" | "WARN" | "FAIL" | "NOT_APPLICABLE";
export type Overall = "READY" | "REVIEW_REQUIRED" | "NOT_READY";

export type RuleResult = {
  ruleId: string;
  title: string;
  category: string;
  status: RuleStatus;
  severity: string;
  metrics: Record<string, unknown>;
  message: string;
  impact: string;
  action: string;
  recommendedFix: string | null;
  errorCode: string | null;
};

export type ChannelStat = { channel: string; rmsDb: number; peakDb: number; silenceRatio: number; speechRatio: number };

export type Metrics = {
  sizeBytes: number;
  probe: { container: string; durationSec: number; streams: Record<string, unknown>[] } | null;
  audio?: {
    channels: number;
    analyzedSeconds: number;
    perChannel: ChannelStat[];
    stereo: null | {
      deltaDb: number;
      correlation: number | null;
      downmixRmsDb: number;
      downmixLossDb: number;
      downmixSilenceRatio: number;
      downmixSpeechRatio: number;
    };
  } | null;
  channelDecision?: { state: string; sourceChannel: number | null; reasons: string[] };
};

export type Diagnostic = {
  diagnosticId: string;
  status: "QUEUED" | "RUNNING" | "DONE" | "FAILED";
  overallStatus: Overall | null;
  results: RuleResult[];
  metrics: Metrics | null;
  errorCode: string | null;
};

export type Check = { ruleId: string; title: string; status: "PASS" | "FAIL"; message: string };

export type FileInfo = {
  fileId: string;
  name: string;
  sizeBytes: number | null;
  status: string;
  downloadable: boolean;
};

export type FixJob = {
  fixJobId: string;
  fixId: string;
  title: string;
  params: Record<string, unknown>;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "REJECTED" | "FAILED";
  errorCode: string | null;
  errorMessage: string | null;
  checks: Check[] | null;
  output: FileInfo | null;
  verification: Diagnostic | null;
};

export type JobFile = FileInfo & {
  // 수정본이 검증을 통과했다면 그 상태, 아니면 원본 진단 상태
  effectiveStatus: string;
  diagnostic: Diagnostic | null;
  fixes: FixJob[];
  // 일괄 다운로드 시 담기는 파일: 검증된 수정본이 있으면 수정본, 없으면 원본
  deliverable: { fileId: string; name: string; fixed: boolean } | null;
};

export type JobSummary = {
  jobId: string;
  createdAt: string;
  mode: "speech" | "video";
  fileCount: number;
  fixedCount: number;
  statusCounts: Record<string, number>;
};

export type Job = {
  jobId: string;
  mode: "speech" | "video";
  maxFileSizeMb: number | null;
  createdAt: string;
  status: "PROCESSING" | "COMPLETED";
  summary: Record<string, number>;
  files: JobFile[];
  fixCatalog: Record<string, { title: string; desc: string }>;
};

export class ApiError extends Error {
  constructor(public code: string, message: string, public details: Record<string, unknown> = {}) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("NETWORK_ERROR", "서버에 연결할 수 없습니다. 서버가 절전 상태였다면 깨어나는 데 1분 정도 걸리니 잠시 후 다시 시도하세요.");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = body.error ?? {};
    throw new ApiError(e.code ?? "HTTP_" + res.status, e.message ?? "요청에 실패했습니다.", e.details);
  }
  return body as T;
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const SUPPORTED = ["mp4", "mov", "avi", "wmv", "mkv", "flv", "mp3", "aac", "ac3", "ogg", "flac", "wav", "m4a"];
export const MAX_UPLOAD_BYTES = 2 * 1024 ** 3;

export function mb(bytes: number | null | undefined) {
  return bytes == null ? "-" : `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function pct(x: number | null | undefined) {
  return x == null ? "-" : `${Math.round(x * 100)}%`;
}
