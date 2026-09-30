import type { Metadata } from "next";
import Link from "next/link";
import HeaderAction from "@/components/HeaderAction";
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
            <nav className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
              <Link href="/history" className="btn">내 처리 기록</Link>
              <HeaderAction />
            </nav>
          </div>
        </header>
        <main className="wrap">{children}</main>
      </body>
    </html>
  );
}
