import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Media Preflight",
  description: "AI 음성·영상 분석 전에 미디어 파일을 진단하고, 원인을 설명하고, 자동으로 수정한 뒤 재검증합니다.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <header className="topbar">
          <div className="wrap">
            <Link href="/" className="brand">
              Media Preflight <span>· AI Readiness Check</span>
            </Link>
            <Link href="/showcase" className="btn primary">
              프로젝트 보기 ↗
            </Link>
          </div>
        </header>
        <main className="wrap">{children}</main>
      </body>
    </html>
  );
}
