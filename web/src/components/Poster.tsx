"use client";

import { Clapperboard } from "lucide-react";
import { useState } from "react";

/** A 9:16 poster frame: the first source that loads wins, else a placeholder. */
export function Poster({ sources, alt = "", className = "" }: { sources: string[]; alt?: string; className?: string }) {
  const [i, setI] = useState(0);
  const src = sources[i];
  if (!src) {
    return <div className={`poster ph ${className}`} aria-label={alt}><Clapperboard size={22} /></div>;
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt} className={`poster ${className}`} loading="lazy" onError={() => setI((n) => n + 1)} />;
}
