"use client";

import Link from "next/link";
import { Plus } from "lucide-react";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Shoots" },
  { href: "/videos", label: "Videos" },
  { href: "/sounds", label: "Sounds" },
  { href: "/jobs", label: "Jobs" },
  { href: "/howto", label: "How to" },
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="flex items-center gap-5 px-4 py-2.5 border-b border-line bg-card sticky top-0 z-30">
      <Link href="/" className="font-bold tracking-wide text-fg no-underline hover:no-underline">beatcut</Link>
      {LINKS.map((l) => {
        const active = l.href === "/" ? path === "/" || path.startsWith("/shoot") : path.startsWith(l.href) || (l.href === "/videos" && path.startsWith("/video/"));
        return (
          <Link key={l.href} href={l.href} className={`text-sm no-underline hover:text-fg hover:no-underline ${active ? "text-fg" : "text-muted"}`}>{l.label}</Link>
        );
      })}
      <Link href="/new" className={`btn sm ml-auto no-underline hover:no-underline ${path === "/new" ? "" : "sec"}`}><Plus size={14} /> New video</Link>
      <span className="text-[11.5px] text-muted hidden md:inline">Young Vibas · one post a day</span>
    </nav>
  );
}
