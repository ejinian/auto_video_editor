/**
 * Readers for the beatcut folder. Nothing here changes an edit: every change goes
 * through `uv run beatcut.py …` (see jobs.ts) so the CLI, the chat and the buttons
 * never disagree. The only writes are the sound pointer, the post caption and the
 * probe/thumbnail caches, which mirror what ui.py did.
 */
import fs from "node:fs";
import fsp from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { hasChatAuth } from "./chatAuth";
import { CLIPS, FINAL, OUT, PROJECTS, ROOT, SOUND, VIDEO_EXT, rel } from "./paths";
import { POSTED_FILE, readPosted, unmarkPosted } from "./posted";
import type {
  ClipInfo,
  FolderInfo,
  Project,
  ProjectDetail,
  ProjectSummary,
  SlotRow,
  SoundInfo,
  SoundMeta,
} from "./types";

const execFileP = promisify(execFile);
const HDR_TRANSFERS = new Set(["smpte2084", "arib-std-b67"]);
export const CAPCUT_DRAFTS = path.join(os.homedir(), "Movies", "CapCut", "User Data", "Projects", "com.lveditor.draft");

// ------------------------------------------------------------------ helpers

export function naturalKey(s: string): Array<string | number> {
  return s.split(/(\d+)/).filter(Boolean).map((t) => (/^\d+$/.test(t) ? Number(t) : t.toLowerCase()));
}

export function naturalCompare(a: string, b: string): number {
  const ka = naturalKey(a), kb = naturalKey(b);
  for (let i = 0; i < Math.max(ka.length, kb.length); i++) {
    const x = ka[i], y = kb[i];
    if (x === undefined) return -1;
    if (y === undefined) return 1;
    if (typeof x === "number" && typeof y === "number") {
      if (x !== y) return x - y;
    } else if (String(x) !== String(y)) return String(x) < String(y) ? -1 : 1;
  }
  return 0;
}

export function exists(p: string): boolean {
  try { fs.accessSync(p); return true; } catch { return false; }
}

function stat(p: string): fs.Stats | null {
  try { return fs.statSync(p); } catch { return null; }
}

function readJson<T>(p: string): T | null {
  try { return JSON.parse(fs.readFileSync(p, "utf8")) as T; } catch { return null; }
}

export function isVideo(name: string): boolean {
  return !name.startsWith(".") && VIDEO_EXT.has(path.extname(name).toLowerCase());
}

/** `dayN_V` → `dayN`; `cle_1` → `cle`; `lisa_v1` → `lisa` (matches beatcut.py's out_dir). */
export function projectFolder(name: string): string | null {
  const m = name.match(/^(.+)_\d+$/);
  return m ? m[1] : null;
}

/** Where a project's files land: out/<folder>/ for `<folder>_V`, else out/. */
export function projectOut(name: string): string {
  const f = projectFolder(name);
  return f ? path.join(OUT, f) : OUT;
}

export function safeName(s: string): string {
  return s.replace(/[^A-Za-z0-9_.-]/g, "_");
}

/** A clip folder name the app will create or write into: one path segment, no leading dot. */
export function validFolderName(s: string): boolean {
  return /^[A-Za-z0-9_][A-Za-z0-9 _.-]{0,79}$/.test(s) && !s.includes("..") && s.trim() === s;
}

/** `dayN` with the first N no clip folder, plan or project uses yet. */
export function nextDayName(): string {
  const used = new Set<number>();
  const take = (s: string) => { const m = s.match(/^day(\d+)(?:[._]|$)/); if (m) used.add(Number(m[1])); };
  if (exists(CLIPS)) for (const d of fs.readdirSync(CLIPS)) take(d);
  if (exists(PROJECTS)) for (const f of fs.readdirSync(PROJECTS)) take(f);
  let n = 1;
  while (used.has(n)) n++;
  return `day${n}`;
}

// -------------------------------------------------------------------- clips

interface ProbeEntry { duration: number; w: number; h: number; hdr: boolean }

const probeCachePath = path.join(CLIPS, ".probe.json");
let probeCache: Record<string, ProbeEntry> | null = null;

function loadProbeCache(): Record<string, ProbeEntry> {
  if (!probeCache) probeCache = readJson<Record<string, ProbeEntry>>(probeCachePath) ?? {};
  return probeCache;
}

let probeSaveTimer: NodeJS.Timeout | null = null;
function saveProbeCacheSoon() {
  if (probeSaveTimer) return;
  probeSaveTimer = setTimeout(() => {
    probeSaveTimer = null;
    try {
      // Re-read and merge: beatcut.py writes the same file with the same key format.
      const onDisk = readJson<Record<string, ProbeEntry>>(probeCachePath) ?? {};
      fs.writeFileSync(probeCachePath, JSON.stringify({ ...onDisk, ...probeCache }, null, 1));
    } catch { /* cache only */ }
  }, 500);
}

/** ffprobe one clip (duration, oriented size, HDR flag), cached like beatcut.py does. */
export async function probe(p: string): Promise<ProbeEntry> {
  const st = stat(p);
  if (!st) return { duration: 0, w: 0, h: 0, hdr: false };
  const key = `${rel(p)}:${st.size}:${Math.floor(st.mtimeMs / 1000)}`;
  const cache = loadProbeCache();
  if (cache[key] && "hdr" in cache[key]) return cache[key];
  try {
    const { stdout } = await execFileP("ffprobe", [
      "-v", "error", "-select_streams", "v:0",
      "-show_entries", "stream=width,height,color_transfer:stream_side_data=rotation:format=duration",
      "-of", "json", p,
    ]);
    const j = JSON.parse(stdout);
    const s = j.streams?.[0] ?? {};
    let rot = 0;
    for (const sd of s.side_data_list ?? []) if ("rotation" in sd) rot = Math.trunc(Number(sd.rotation));
    let w = Number(s.width ?? 0), h = Number(s.height ?? 0);
    if (rot % 180) [w, h] = [h, w];
    const entry = { duration: Number(j.format?.duration ?? 0), w, h, hdr: HDR_TRANSFERS.has(s.color_transfer) };
    cache[key] = entry;
    saveProbeCacheSoon();
    return entry;
  } catch {
    return { duration: 0, w: 0, h: 0, hdr: false };
  }
}

/** Every folder under clips/ that holds video files, newest shoot first. */
export async function folders(): Promise<FolderInfo[]> {
  if (!exists(CLIPS)) return [];
  const names = (await fsp.readdir(CLIPS, { withFileTypes: true }))
    .filter((d) => d.isDirectory() && !d.name.startsWith("."))
    .map((d) => d.name);
  const projs = await projects();
  const out: FolderInfo[] = [];
  for (const name of names) {
    const clips = await folderClips(name);
    if (!clips.length) continue;
    const st = stat(path.join(CLIPS, name));
    out.push({
      name,
      clipCount: clips.length,
      footage: clips.reduce((a, c) => a + c.duration, 0),
      projects: projs.filter((p) => p.folder === name).map((p) => p.name),
      plan: exists(path.join(PROJECTS, `${name}.plan.md`)) ? `projects/${name}.plan.md` : null,
      isDay: /^day\d+$/.test(name),
      mtime: st?.mtimeMs ?? 0,
    });
  }
  // day folders by number, then the rest alphabetically; newest day on top
  out.sort((a, b) => (a.isDay !== b.isDay ? (a.isDay ? -1 : 1) : a.isDay ? naturalCompare(b.name, a.name) : naturalCompare(a.name, b.name)));
  return out;
}

/** Plans without clips yet (tomorrow's shoot). */
export function pendingPlans(existingFolders: string[]): Array<{ folder: string; path: string }> {
  if (!exists(PROJECTS)) return [];
  return fs.readdirSync(PROJECTS)
    .filter((f) => f.endsWith(".plan.md"))
    .map((f) => f.slice(0, -".plan.md".length))
    .filter((folder) => !existingFolders.includes(folder))
    .sort(naturalCompare)
    .map((folder) => ({ folder, path: `projects/${folder}.plan.md` }));
}

export async function folderClips(folder: string): Promise<ClipInfo[]> {
  const dir = path.join(CLIPS, folder);
  if (!exists(dir)) return [];
  const names = (await fsp.readdir(dir)).filter(isVideo).sort(naturalCompare);
  const clips: ClipInfo[] = [];
  for (let i = 0; i < names.length; i++) {
    const p = path.join(dir, names[i]);
    const pr = await probe(p);
    clips.push({
      n: i + 1,
      name: names[i],
      stem: path.parse(names[i]).name,
      path: `clips/${folder}/${names[i]}`,
      folder,
      duration: pr.duration,
      w: pr.w,
      h: pr.h,
      hdr: pr.hdr,
      size: stat(p)?.size ?? 0,
    });
  }
  return clips;
}

export function readPlan(folder: string): string | null {
  const p = path.join(PROJECTS, `${folder}.plan.md`);
  return exists(p) ? fs.readFileSync(p, "utf8") : null;
}

export function readIdeas(): string {
  const p = path.join(PROJECTS, "ideas.md");
  return exists(p) ? fs.readFileSync(p, "utf8") : "";
}

// --------------------------------------------------------------- thumbnails

const thumbInflight = new Map<string, Promise<string | null>>();

/** One 360px-tall frame from 1 s in, cached in out/<folder>/.thumbs/ (same place ui.py used). */
export function thumbPath(folder: string, stem: string): string {
  return path.join(OUT, folder, ".thumbs", `${stem}.jpg`);
}

export async function thumb(folder: string, stem: string): Promise<string | null> {
  const t = thumbPath(folder, stem);
  if (exists(t)) return t;
  const key = `${folder}/${stem}`;
  const running = thumbInflight.get(key);
  if (running) return running;
  const job = (async () => {
    const clips = await folderClips(folder);
    const clip = clips.find((c) => c.stem === stem);
    if (!clip) return null;
    await fsp.mkdir(path.dirname(t), { recursive: true });
    const tmp = `${t}.${process.pid}.tmp.jpg`;
    try {
      await execFileP("ffmpeg", ["-v", "error", "-y", "-ss", clip.duration > 1.5 ? "1" : "0", "-i", path.join(ROOT, clip.path),
        "-frames:v", "1", "-vf", "scale=-2:360", tmp]);
      await fsp.rename(tmp, t);
      return t;
    } catch {
      try { await fsp.unlink(tmp); } catch { /* none */ }
      return null;
    } finally {
      thumbInflight.delete(key);
    }
  })();
  thumbInflight.set(key, job);
  return job;
}


/** Where a clip is read from for frames: the SDR proxy beatcut.py tone-mapped for an HDR
 *  clip (clips/<folder>/.sdr/<stem>.mov) when it exists, so colours match the render. */
export function frameSource(clipRel: string, hdr: boolean): string {
  const full = path.join(ROOT, clipRel);
  if (!hdr) return full;
  const proxy = path.join(path.dirname(full), ".sdr", `${path.parse(full).name}.mov`);
  return exists(proxy) ? proxy : full;
}

const frameInflight = new Map<string, Promise<string | null>>();

/** One 360px-tall frame of `src` at `t` seconds into `dest`, deduplicated while it runs. */
async function extractFrame(src: string, t: number, dest: string): Promise<string | null> {
  if (exists(dest)) return dest;
  const running = frameInflight.get(dest);
  if (running) return running;
  const job = (async () => {
    await fsp.mkdir(path.dirname(dest), { recursive: true });
    const tmp = `${dest}.${process.pid}.tmp.jpg`;
    try {
      await execFileP("ffmpeg", ["-v", "error", "-y", "-ss", Math.max(0, t).toFixed(3), "-i", src, "-frames:v", "1", "-vf", "scale=-2:360", tmp]);
      await fsp.rename(tmp, dest);
      return dest;
    } catch {
      try { await fsp.unlink(tmp); } catch { /* none */ }
      return null;
    } finally {
      frameInflight.delete(dest);
    }
  })();
  frameInflight.set(dest, job);
  return job;
}

/**
 * The frame the timeline shows for slot `n` (1-based) of a project: the clip at its
 * in-point plus half the slot's length, i.e. the same frame `board` picks. Cached in
 * out/<folder>/.slots/ under a name that holds the clip, in-point and length, so any
 * edit of the slot produces a new file (older files for the same slot are removed).
 */
export async function slotThumb(name: string, n: number): Promise<string | null> {
  const pr = loadProject(name);
  if (!pr || n < 1 || n > pr.slots.length) return null;
  const s = pr.slots[n - 1];
  const dur = pr.cuts[n] - pr.cuts[n - 1];
  const clipRel = pr.clips[s.clip - 1];
  if (!clipRel || !exists(path.join(ROOT, clipRel))) return null;
  const dir = path.join(projectOut(name), ".slots");
  const dest = path.join(dir, `${name}.s${n}.c${s.clip}.${s.in.toFixed(3)}.${dur.toFixed(3)}.jpg`);
  if (exists(dest)) return dest;
  const hdr = (await probe(path.join(ROOT, clipRel))).hdr;
  const got = await extractFrame(frameSource(clipRel, hdr), s.in + dur / 2, dest);
  if (got) {
    const prefix = `${name}.s${n}.`;
    for (const f of fs.readdirSync(dir)) {
      if (f.startsWith(prefix) && f.endsWith(".jpg") && path.join(dir, f) !== dest) { try { fs.rmSync(path.join(dir, f)); } catch { /* cache */ } }
    }
  }
  return got;
}

/** A frame of a clip at `t` seconds (rounded to 0.1 s), for scrubbing an in-point.
 *  Cached in out/<folder>/.frames/ next to the thumbnails. */
export async function clipFrame(folder: string, stem: string, t: number): Promise<string | null> {
  const clips = await folderClips(folder);
  const clip = clips.find((c) => c.stem === stem);
  if (!clip) return null;
  const tq = Math.max(0, Math.min(Math.round(t * 10) / 10, Math.max(0, clip.duration - 0.1)));
  const dest = path.join(OUT, folder, ".frames", `${stem}.${tq.toFixed(1)}.jpg`);
  return extractFrame(frameSource(clip.path, clip.hdr), tq, dest);
}

// ------------------------------------------------------------------- sounds

function soundMeta(mp3: string): SoundMeta {
  const src = mp3.replace(/\.mp3$/, ".source.json");
  const j = readJson<SoundMeta & { meta?: SoundMeta }>(src);
  if (!j) return {};
  return j.meta ?? j;
}

export async function sounds(): Promise<SoundInfo[]> {
  if (!exists(SOUND)) return [];
  const files = (await fsp.readdir(SOUND)).filter((f) => f.endsWith(".mp3") && !f.startsWith("."));
  const projs = await projects();
  const out: SoundInfo[] = [];
  for (const file of files) {
    const mp3 = path.join(SOUND, file);
    const meta = soundMeta(mp3);
    const beats = readJson<{ duration?: number; tempo?: number; drops?: Array<{ time: number }> }>(mp3.replace(/\.mp3$/, ".beats.json"));
    const relPath = `sound/${file}`;
    out.push({
      path: relPath,
      file,
      title: meta.title || path.parse(file).name,
      author: meta.author,
      source: meta.source,
      duration: beats?.duration ?? meta.duration,
      tempo: beats?.tempo,
      drops: (beats?.drops ?? []).map((d) => (typeof d === "number" ? d : d.time)),
      mtime: stat(mp3)?.mtimeMs ?? 0,
      usedBy: projs.filter((p) => p.soundPath === relPath).map((p) => p.name),
    });
  }
  out.sort((a, b) => b.mtime - a.mtime);
  return out;
}

export function soundByPath(relPath: string): SoundInfo | null {
  const mp3 = path.join(ROOT, relPath);
  if (!exists(mp3)) return null;
  const meta = soundMeta(mp3);
  const beats = readJson<{ duration?: number; tempo?: number; drops?: Array<{ time: number }> }>(mp3.replace(/\.mp3$/, ".beats.json"));
  return {
    path: relPath,
    file: path.basename(mp3),
    title: meta.title || path.parse(mp3).name,
    author: meta.author,
    source: meta.source,
    duration: beats?.duration ?? meta.duration,
    tempo: beats?.tempo,
    drops: (beats?.drops ?? []).map((d) => (typeof d === "number" ? d : d.time)),
    mtime: stat(mp3)?.mtimeMs ?? 0,
    usedBy: [],
  };
}

/**
 * Point a project at a sound already in sound/ by writing its pointer file.
 * Running `sound sound/x.mp3` would re-import the file onto itself and truncate it
 * (seen 2026-10-08), so the pointer is written directly, exactly as ui.py did.
 */
export function linkSound(project: string, mp3Rel: string): void {
  const mp3 = path.join(ROOT, mp3Rel);
  const beats = mp3.replace(/\.mp3$/, ".beats.json");
  if (!mp3Rel.startsWith("sound/") || !exists(mp3) || !exists(beats)) {
    throw new Error(`${mp3Rel} has no beat analysis next to it`);
  }
  const meta = soundMeta(mp3);
  fs.mkdirSync(PROJECTS, { recursive: true });
  fs.writeFileSync(
    path.join(PROJECTS, `${project}.sound.json`),
    JSON.stringify({ sound: `sound/${path.basename(mp3)}`, beats: `sound/${path.basename(beats)}`, meta: Object.keys(meta).length ? meta : { source: mp3Rel, title: path.parse(mp3).name } }, null, 1),
  );
}

export function projectSoundPointer(name: string): { sound: string; meta: SoundMeta } | null {
  return readJson<{ sound: string; meta?: SoundMeta }>(path.join(PROJECTS, `${name}.sound.json`)) as { sound: string; meta: SoundMeta } | null;
}

// ----------------------------------------------------------------- projects

export function loadProject(name: string): Project | null {
  if (name.endsWith(".sound") || !/^[A-Za-z0-9_.-]+$/.test(name)) return null;
  return readJson<Project>(path.join(PROJECTS, `${name}.json`));
}

export function soundTitle(name: string, project?: Project | null): string {
  const ptr = projectSoundPointer(name);
  const meta = ptr?.meta ?? {};
  const t = meta.title || path.parse(ptr?.sound ?? project?.sound ?? "").name;
  return meta.author ? `${t} — ${meta.author}` : t;
}

export async function projects(): Promise<Array<ProjectSummary & { soundPath: string }>> {
  if (!exists(PROJECTS)) return [];
  const files = (await fsp.readdir(PROJECTS)).filter((f) => f.endsWith(".json") && !f.endsWith(".sound.json"));
  const out: Array<ProjectSummary & { soundPath: string }> = [];
  const postedAll = readPosted();
  for (const f of files) {
    const name = f.slice(0, -5);
    const pj = path.join(PROJECTS, f);
    const data = readJson<Project>(pj);
    if (!data || !Array.isArray(data.slots)) continue;
    const mp4 = path.join(projectOut(name), `${name}.mp4`);
    const pst = stat(pj), mst = stat(mp4);
    out.push({
      name,
      folder: projectFolder(name),
      rendered: !!mst,
      stale: !!mst && !!pst && pst.mtimeMs > mst.mtimeMs + 1000,
      length: data.cuts?.length ? data.cuts[data.cuts.length - 1] - data.cuts[0] : data.length,
      slots: data.slots.length,
      caption: data.caption ?? null,
      sound: soundTitle(name, data),
      soundPath: data.sound,
      mp4: mst ? rel(mp4) : null,
      mtime: pst?.mtimeMs ?? 0,
      inFinal: exists(path.join(FINAL, `${name}.mp4`)),
      posted: postedAll[name] ?? null,
    });
  }
  out.sort((a, b) => b.mtime - a.mtime);
  return out;
}

export function nextProjectName(folder: string): string {
  if (!exists(PROJECTS)) return `${folder}_1`;
  const ns = fs.readdirSync(PROJECTS)
    .map((f) => f.match(new RegExp(`^${folder.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}_(\\d+)\\.json$`)))
    .filter((m): m is RegExpMatchArray => !!m)
    .map((m) => Number(m[1]));
  return `${folder}_${ns.length ? Math.max(...ns) + 1 : 1}`;
}

export function slotRows(pr: Project): SlotRow[] {
  const cuts = pr.cuts, a0 = cuts[0];
  const drops = (pr._drops ?? []).map((d) => (typeof d === "number" ? d : d.time));
  const uses = new Map<number, number>();
  for (const s of pr.slots) uses.set(s.clip, (uses.get(s.clip) ?? 0) + 1);
  return pr.slots.map((s, i) => ({
    n: i + 1,
    t0: cuts[i] - a0,
    t1: cuts[i + 1] - a0,
    dur: cuts[i + 1] - cuts[i],
    clip: s.clip,
    file: path.basename(pr.clips[s.clip - 1] ?? "?"),
    in: s.in,
    drop: drops.some((d) => Math.abs(d - cuts[i]) < 0.35),
    hero: pr.hero === s.clip,
    uses: uses.get(s.clip) ?? 1,
  }));
}

export function captionFilePath(name: string): string {
  return path.join(projectOut(name), `${name}.caption.txt`);
}

export function readPostCaption(name: string): string {
  const p = captionFilePath(name);
  return exists(p) ? fs.readFileSync(p, "utf8").trim() : "";
}

export function writePostCaption(name: string, text: string): void {
  const p = captionFilePath(name);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, text.trim() + "\n");
}

export async function projectDetail(name: string): Promise<ProjectDetail | null> {
  const pr = loadProject(name);
  if (!pr) return null;
  const od = projectOut(name);
  const mp4 = path.join(od, `${name}.mp4`);
  const board = path.join(od, `_${name}_board.jpg`);
  const pst = stat(path.join(PROJECTS, `${name}.json`)), mst = stat(mp4);
  const uses = new Map<number, number>();
  for (const s of pr.slots) uses.set(s.clip, (uses.get(s.clip) ?? 0) + 1);
  const clips: ProjectDetail["clips"] = [];
  for (let i = 0; i < pr.clips.length; i++) {
    const cp = pr.clips[i];
    const full = path.join(ROOT, cp);
    const m = cp.match(/^clips\/([^/]+)\/(.+)$/);
    const prb = await probe(full);
    const fname = path.basename(cp);
    clips.push({
      n: i + 1,
      name: fname,
      stem: path.parse(fname).name,
      path: cp,
      folder: m ? m[1] : "",
      duration: prb.duration,
      w: prb.w,
      h: prb.h,
      hdr: prb.hdr,
      size: stat(full)?.size ?? 0,
      excluded: (pr.excluded ?? []).includes(i + 1),
      uses: uses.get(i + 1) ?? 0,
      missing: !exists(full),
    });
  }
  const vdir = path.join(od, "versions");
  const versions = exists(vdir)
    ? fs.readdirSync(vdir)
        .filter((f) => f.startsWith(`${name}.v`) && f.endsWith(".mp4"))
        .sort(naturalCompare)
        .reverse()
        .map((f) => {
          const p = path.join(vdir, f);
          const s = stat(p);
          return { name: f, path: rel(p), size: s?.size ?? 0, mtime: s?.mtimeMs ?? 0 };
        })
    : [];
  const frameSheets = clips
    .map((c) => ({ clip: c.name, path: path.join(od, `_frames_${c.stem}.jpg`) }))
    .filter((f) => exists(f.path))
    .map((f) => ({ clip: f.clip, path: rel(f.path) }));
  const ptr = projectSoundPointer(name);
  const sound = soundByPath(ptr?.sound ?? pr.sound);
  return {
    name,
    project: pr,
    folder: projectFolder(name),
    outRel: rel(od),
    mp4: mst ? rel(mp4) : null,
    mp4Size: mst?.size ?? 0,
    rendered: !!mst,
    stale: !!mst && !!pst && pst.mtimeMs > mst.mtimeMs + 1000,
    board: exists(board) ? rel(board) : null,
    boardMtime: Math.round(stat(board)?.mtimeMs ?? 0),
    sound,
    slots: slotRows(pr),
    clips,
    captionFile: rel(captionFilePath(name)),
    postCaption: readPostCaption(name),
    versions,
    frameSheets,
    realLength: pr.cuts?.length ? pr.cuts[pr.cuts.length - 1] - pr.cuts[0] : pr.length,
    capcutDraft: exists(path.join(CAPCUT_DRAFTS, name)),
    inFinal: exists(path.join(FINAL, `${name}.mp4`)),
    posted: readPosted()[name] ?? null,
  };
}

/** Remove a project and everything it produced (the "keep only X" move). */
export function deleteProject(name: string): string[] {
  const removed: string[] = [];
  const od = projectOut(name);
  const targets = [
    path.join(PROJECTS, `${name}.json`),
    path.join(PROJECTS, `${name}.sound.json`),
    path.join(od, `${name}.mp4`),
    path.join(od, `_${name}_board.jpg`),
    path.join(od, `${name}.caption.txt`),
    path.join(od, `${name}.capcut.json`),
    path.join(FINAL, `${name}.mp4`),
  ];
  const vdir = path.join(od, "versions");
  if (exists(vdir)) for (const f of fs.readdirSync(vdir)) if (f.startsWith(`${name}.v`)) targets.push(path.join(vdir, f));
  const sdir = path.join(od, ".slots");
  if (exists(sdir)) for (const f of fs.readdirSync(sdir)) if (f.startsWith(`${name}.s`)) targets.push(path.join(sdir, f));
  for (const t of targets) {
    if (exists(t)) { fs.rmSync(t); removed.push(rel(t)); }
  }
  if (unmarkPosted(name)) removed.push(`${rel(POSTED_FILE)} (entry)`);
  return removed;
}

// ------------------------------------------------------------------- health

export async function health(): Promise<{ ffmpeg: boolean; uv: boolean; apiKey: boolean; root: string; capcutSeed: boolean }> {
  const which = async (bin: string) => { try { await execFileP("which", [bin]); return true; } catch { return false; } };
  return {
    ffmpeg: await which("ffmpeg"),
    uv: await which("uv"),
    apiKey: hasChatAuth(),   // an API key in .env.local or the Claude Code login on this Mac
    root: ROOT,
    capcutSeed: exists(CAPCUT_DRAFTS) && fs.readdirSync(CAPCUT_DRAFTS).some((d) => !d.startsWith(".")),
  };
}
