// 로그인이 없으므로 '내 처리 기록'은 이 브라우저에만 저장한다(다른 사람의 기록은 보이지 않는다).
const KEY = "jobHistory";

export function readHistory(): string[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}

export function rememberJob(jobId: string) {
  try {
    localStorage.setItem(KEY, JSON.stringify([jobId, ...readHistory().filter((id) => id !== jobId)].slice(0, 100)));
    localStorage.setItem("lastJobId", jobId);
  } catch {}
}

export function formatTime(iso: string) {
  return new Date(iso).toLocaleString("ko-KR", { year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
