"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

export default function HeaderAction() {
  const pathname = usePathname();
  const [lastJobId, setLastJobId] = useState<string | null>(null);

  useEffect(() => {
    try {
      setLastJobId(localStorage.getItem("lastJobId"));
    } catch {}
  }, [pathname]);

  if (pathname.startsWith("/showcase"))
    return lastJobId ? (
      <Link href={`/jobs/${lastJobId}`} className="btn primary">← 처리 화면으로 돌아가기</Link>
    ) : (
      <Link href="/" className="btn primary">직접 써보기</Link>
    );

  // 처리 중인 화면(업로드·진단)을 잃지 않도록 설명 페이지는 새 탭으로 연다.
  return (
    <Link href="/showcase" target="_blank" className="btn primary">
      프로젝트 설명 확인하기 ↗
    </Link>
  );
}
