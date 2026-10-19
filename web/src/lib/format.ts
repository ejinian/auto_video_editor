export function secs(s: number, digits = 1): string {
  return `${s.toFixed(digits)} s`;
}

export function mmss(s: number): string {
  const m = Math.floor(s / 60), r = Math.round(s - m * 60);
  return m ? `${m}:${String(r).padStart(2, "0")}` : `${r}s`;
}

export function mb(bytes: number): string {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(2)} GB` : `${(bytes / 1e6).toFixed(1)} MB`;
}

export function ago(ms: number): string {
  const d = Date.now() - ms;
  if (d < 60_000) return "just now";
  if (d < 3_600_000) return `${Math.floor(d / 60_000)} min ago`;
  if (d < 86_400_000) return `${Math.floor(d / 3_600_000)} h ago`;
  return `${Math.floor(d / 86_400_000)} d ago`;
}

/** `/api/media/out/day3/x.mp4` for a ROOT-relative path. */
export function mediaUrl(relPath: string, download = false): string {
  return "/api/media/" + relPath.split("/").map(encodeURIComponent).join("/") + (download ? "?download" : "");
}

export function thumbUrl(folder: string, stem: string): string {
  return `/api/thumb/${encodeURIComponent(folder)}/${encodeURIComponent(stem)}`;
}

/** The timeline's frame for a slot; the key makes the browser refetch after an edit. */
export function slotThumbUrl(name: string, slot: number, key: string): string {
  return `/api/slot-thumb/${encodeURIComponent(name)}/${slot}?k=${encodeURIComponent(key)}`;
}

export function clipFrameUrl(folder: string, stem: string, t: number): string {
  return `/api/clip-frame/${encodeURIComponent(folder)}/${encodeURIComponent(stem)}?t=${t.toFixed(1)}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** `Oct 19` for an ISO date, the same on the server and in the browser (no locale). */
export function shortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}
