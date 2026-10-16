"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { slotThumbUrl } from "@/lib/format";
import type { SlotRow } from "@/lib/types";

const MIN_W = 44;   // px: a 0.3 s shot still shows a frame and takes a click
const NARROW = 60;  // px: under this the length label is dropped (the tooltip and the card have it)
const H = 104;      // px: tile height

type Zone = "before" | "after" | "swap";
interface Drag { from: number; x: number; y: number; over: number | null; zone: Zone | null; moved: boolean }

/** Tile widths: proportional to length, never under MIN_W, and the strip fills its
 *  container when it can (the long shots give up what the short ones need). */
function layout(slots: SlotRow[], width: number): number[] {
  if (!width || !slots.length) return slots.map(() => MIN_W);
  const total = slots.reduce((a, s) => a + s.dur, 0);
  let pps = width / total;
  for (let k = 0; k < 6; k++) {
    const fixed = slots.filter((s) => s.dur * pps < MIN_W);
    const free = total - fixed.reduce((a, s) => a + s.dur, 0);
    if (!free || fixed.length === slots.length) break;
    pps = (width - fixed.length * MIN_W) / free;
  }
  return slots.map((s) => Math.max(MIN_W, s.dur * pps));
}

export function Timeline({ name, slots, selected, time, hasVideo, busy, onSelect, onMove, onSwap }: {
  name: string;
  slots: SlotRow[];
  selected: number | null;
  /** current video time in seconds (from the start of the video) */
  time: number;
  hasVideo: boolean;
  busy: boolean;
  onSelect: (slot: number) => void;
  /** move slot `from` so it lands at position `to` (both 1-based) */
  onMove: (from: number, to: number) => void;
  onSwap: (a: number, b: number) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const tiles = useRef<Array<HTMLDivElement | null>>([]);
  const [width, setWidth] = useState(0);
  const [drag, setDrag] = useState<Drag | null>(null);

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);  // fires once on observe, so the first layout has a width
    return () => ro.disconnect();
  }, []);

  const widths = layout(slots, width);
  const lefts: number[] = [];
  let acc = 0;
  for (const w of widths) { lefts.push(acc); acc += w; }
  const cur = slots.findIndex((s) => time >= s.t0 && time < s.t1);
  const playX = cur >= 0 ? lefts[cur] + ((time - slots[cur].t0) / slots[cur].dur) * widths[cur] : time >= (slots.at(-1)?.t1 ?? 0) ? acc : 0;

  // keep the selected tile in view when the strip scrolls
  useEffect(() => {
    if (selected == null) return;
    tiles.current[selected - 1]?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [selected]);

  const hit = useCallback((x: number, from: number): { over: number; zone: Zone } | null => {
    const els = tiles.current;
    for (let i = 0; i < els.length; i++) {
      const el = els[i];
      if (!el || i + 1 === from) continue;
      const r = el.getBoundingClientRect();
      if (x >= r.left && x <= r.right) {
        const rel = (x - r.left) / r.width;
        return { over: i + 1, zone: rel < 0.25 ? "before" : rel > 0.75 ? "after" : "swap" };
      }
    }
    const first = els.find(Boolean), last = [...els].reverse().find(Boolean);
    if (first && x < first.getBoundingClientRect().left) return from === 1 ? null : { over: 1, zone: "before" };
    if (last && x > last.getBoundingClientRect().right) return from === els.length ? null : { over: els.length, zone: "after" };
    return null;
  }, []);

  const down = (e: React.PointerEvent<HTMLDivElement>, n: number) => {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    setDrag({ from: n, x: e.clientX, y: e.clientY, over: null, zone: null, moved: false });
  };
  const move = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const moved = drag.moved || Math.abs(e.clientX - drag.x) > 6 || Math.abs(e.clientY - drag.y) > 6;
    if (!moved) return;
    const h = busy ? null : hit(e.clientX, drag.from);
    setDrag({ ...drag, moved: true, x: e.clientX, y: e.clientY, over: h?.over ?? null, zone: h?.zone ?? null });
  };
  const up = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    e.currentTarget.releasePointerCapture(e.pointerId);
    const d = drag;
    setDrag(null);
    if (!d.moved) { onSelect(d.from); return; }
    if (d.over == null || d.zone == null || busy) return;
    if (d.zone === "swap") { onSwap(d.from, d.over); return; }
    // `move a b` pops a and inserts at b: the position the tile ends up at, 1-based
    const a = d.from, j = d.over;
    const to = d.zone === "before" ? (j < a ? j : j - 1) : (j < a ? j + 1 : j);
    if (to !== a) onMove(a, to);
  };

  const hint = drag?.moved
    ? drag.over == null ? "drop on a shot to swap, or at its edge to move"
      : drag.zone === "swap" ? `swap with shot ${drag.over}` : `move ${drag.zone} shot ${drag.over}`
    : null;

  return (
    <div className="tl" ref={box}>
      <div className="tl-strip" style={{ height: H, width: Math.max(acc, width) }}>
        {slots.map((s, i) => {
          const n = i + 1;
          const isSel = selected === n, isCur = cur === i, isDrag = drag?.moved && drag.from === n;
          const over = drag?.moved && drag.over === n ? drag.zone : null;
          return (
            <div
              key={n}
              ref={(el) => { tiles.current[i] = el; }}
              className={`tl-tile ${isSel ? "sel" : ""} ${isCur && hasVideo ? "cur" : ""} ${isDrag ? "dragging" : ""} ${over === "swap" ? "over-swap" : ""} ${over === "before" ? "over-before" : ""} ${over === "after" ? "over-after" : ""}`}
              style={{ left: lefts[i], width: widths[i], height: H }}
              title={`shot ${n}: clip ${s.clip} (${s.file}) ${s.in.toFixed(2)} s in · ${s.dur.toFixed(2)} s · ${s.t0.toFixed(2)}–${s.t1.toFixed(2)} s`}
              onPointerDown={(e) => down(e, n)}
              onPointerMove={move}
              onPointerUp={up}
              onPointerCancel={() => setDrag(null)}
              role="button"
              aria-pressed={isSel}
              aria-label={`shot ${n}, clip ${s.clip}, ${s.dur.toFixed(1)} seconds`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={slotThumbUrl(name, n, `${s.clip}-${s.in.toFixed(3)}-${s.dur.toFixed(3)}`)} alt="" draggable={false} loading="lazy" />
              <span className="tl-n">{n}</span>
              {widths[i] >= NARROW && <span className="tl-len">{s.dur.toFixed(1)}s</span>}
              <span className="tl-clip">{widths[i] >= 96 ? `clip ${s.clip}` : `c${s.clip}`}</span>
              {s.drop && <span className="tl-drop" style={widths[i] < NARROW ? { top: 24, bottom: "auto" } : undefined}>DROP</span>}
              {s.hero && <span className="tl-hero" style={s.drop ? { bottom: 24 } : undefined}>★{widths[i] >= 96 ? " hero" : ""}</span>}
            </div>
          );
        })}
        {hasVideo && <div className="tl-play" style={{ left: playX, height: H }} />}
      </div>
      {hint && <div className="tl-hint" style={{ left: (drag?.x ?? 0) + 14, top: (drag?.y ?? 0) + 14 }}>{hint}</div>}
    </div>
  );
}
