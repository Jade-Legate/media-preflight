"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function HeaderAction() {
  const onShowcase = usePathname().startsWith("/showcase");
  return (
    <Link href={onShowcase ? "/" : "/showcase"} className="btn primary">
      {onShowcase ? "직접 써보기" : "내용 상세 확인하기"}
    </Link>
  );
}
