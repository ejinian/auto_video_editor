"use client";

import Link from "next/link";
import { Activity, BookOpen, Clapperboard, Music, Plus, Scissors, Video } from "lucide-react";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Shoots", Icon: Clapperboard },
  { href: "/videos", label: "Videos", Icon: Video },
  { href: "/sounds", label: "Sounds", Icon: Music },
  { href: "/jobs", label: "Jobs", Icon: Activity },
  { href: "/howto", label: "How to", Icon: BookOpen },
];

/** The sidebar: brand, the one primary action, the sections. */
export function Nav() {
  const path = usePathname();
  return (
    <nav className="sb" aria-label="main">
      <Link href="/" className="brand"><span className="mark"><Scissors size={14} strokeWidth={2.5} /></span><span>beatcut</span></Link>
      <Link href="/new" className={`btn new ${path === "/new" ? "" : ""}`}><Plus size={16} /><span>New video</span></Link>
      {LINKS.map(({ href, label, Icon }) => {
        const active = href === "/" ? path === "/" || path.startsWith("/shoot") : path.startsWith(href) || (href === "/videos" && path.startsWith("/video/"));
        return (
          <Link key={href} href={href} className={`item ${active ? "on" : ""}`} title={label}><Icon size={17} strokeWidth={1.9} /><span>{label}</span></Link>
        );
      })}
      <div className="foot">Young Vibas<br />one post a day</div>
    </nav>
  );
}
