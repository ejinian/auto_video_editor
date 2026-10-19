/** The edit, as beatcut.py writes it to projects/<name>.json. */
export interface Project {
  name: string;
  clips: string[];
  sound: string;
  beats: string;
  audio_start: number;
  length: number;
  density: Record<string, number>;
  preset?: string;
  sync?: boolean;
  excluded: number[];
  hero: number | null;
  first?: number | null;
  story?: number[] | null;
  random?: boolean;
  seed?: number | null;
  caption: string | null;
  /** Set by `remix`: the video this one was cut from, and which recipe (hook / sound / reorder / long). */
  remix_of?: string | null;
  remix?: string | null;
  /** A reformat (set by `reformat`): the posted video kept as is, plus one framing. */
  kind?: "reformat";
  reformat?: "hook" | "narrated" | "reply";
  source?: string;
  hook?: string | null;
  lines?: string[];
  voice?: string;
  comment?: { text: string; user?: string | null } | null;
  cuts: number[];
  _drops?: Array<{ time: number } | number>;
  slots: Array<{ clip: number; in: number; reused?: boolean }>;
}

export interface SoundMeta {
  source?: string;
  title?: string;
  author?: string;
  platform?: string;
  duration?: number;
  music_id?: string;
}

export interface SoundInfo {
  /** `sound/<file>.mp3`, the value a project's `sound` field holds. */
  path: string;
  file: string;
  title: string;
  author?: string;
  source?: string;
  duration?: number;
  tempo?: number;
  drops: number[];
  mtime: number;
  usedBy: string[];
}

export interface ClipInfo {
  /** 1-based number in the folder's natural order (what the edit buttons use). */
  n: number;
  name: string;
  stem: string;
  /** `clips/<folder>/<name>` */
  path: string;
  folder: string;
  duration: number;
  w: number;
  h: number;
  hdr: boolean;
  size: number;
}

export interface FolderInfo {
  name: string;
  clipCount: number;
  footage: number;
  projects: string[];
  plan: string | null;
  isDay: boolean;
  mtime: number;
}

/** One entry of out/.app/posted.json: the user's note that the video went up. */
export interface PostedInfo {
  postedAt: string;
  platform?: "tiktok" | "instagram" | "both";
  url?: string;
}

export interface ProjectSummary {
  name: string;
  folder: string | null;
  rendered: boolean;
  stale: boolean;
  length: number;
  slots: number;
  caption: string | null;
  sound: string;
  mp4: string | null;
  mtime: number;
  inFinal: boolean;
  posted: PostedInfo | null;
  remixOf: string | null;
  remix: string | null;
  reformat: string | null;
}

export interface SlotRow {
  n: number;
  t0: number;
  t1: number;
  dur: number;
  clip: number;
  file: string;
  in: number;
  drop: boolean;
  hero: boolean;
  uses: number;
}

export interface ProjectDetail {
  name: string;
  project: Project;
  folder: string | null;
  outRel: string;
  mp4: string | null;
  mp4Size: number;
  rendered: boolean;
  stale: boolean;
  board: string | null;
  boardMtime: number;
  sound: SoundInfo | null;
  slots: SlotRow[];
  clips: Array<ClipInfo & { excluded: boolean; uses: number; missing: boolean }>;
  captionFile: string;
  postCaption: string;
  versions: Array<{ name: string; path: string; size: number; mtime: number }>;
  frameSheets: Array<{ clip: string; path: string }>;
  realLength: number;
  capcutDraft: boolean;
  inFinal: boolean;
  posted: PostedInfo | null;
  /** The video this one was remixed from, and the remixes cut from this one. */
  remixOf: string | null;
  remix: string | null;
  remixes: ProjectSummary[];
  /** For a reformat: the other reformats of the same posted video (this one included). */
  reformats: ProjectSummary[];
}

export interface JobInfo {
  id: string;
  title: string;
  cmds: string[][];
  /** The project the commands work on (`-p <name>`), null for a bare `sound <link>`. */
  project?: string | null;
  /** The beatcut subcommand of each command, in order: `sound`, `plan`, `board`, `render`… */
  steps?: string[];
  log: string;
  done: boolean;
  ok: boolean;
  then: string | null;
  startedAt: number;
  endedAt: number | null;
}

/** What /api/jobs lists: the job with the log cut short and the running step's index. */
export interface JobSummary extends JobInfo {
  project: string | null;
  steps: string[];
  step: number;
}
