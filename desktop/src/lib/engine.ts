// Talking to the engine: babelscribe-engine (the Python CLI, bundled with the app) run with --progress-json.
// The command line is the single source of truth; this file only builds its arguments and reads its events.
import { isAudio, isWindowsPath } from "./utils";

export type Format = "srt" | "vtt" | "txt";
export const FORMATS: Format[] = ["srt", "vtt", "txt"];

export type Style = "plain" | "karaoke" | "shorts";
export const STYLES: Style[] = ["plain", "karaoke", "shorts"];

export interface Options {
  lang: string; // "auto" or a Whisper language code
  accurate: boolean;
  formats: Record<Format, boolean>;
  prompt: string; // names and terms to spell correctly
  translate: boolean; // also write NAME.LANG.srt, translated by a local model
  target: string; // language code to translate into
  llm: string; // "" = the engine looks at the usual local ports; else the endpoint URL
  llmModel: string; // "" = the first model the endpoint lists
  burn: boolean; // also write a video with the subtitles drawn on it
  style: Style;
  burnTranslated: boolean; // draw the translated subtitles instead of the original ones
}

export const DEFAULT_OPTIONS: Options = {
  lang: "auto",
  accurate: false,
  formats: { srt: true, vtt: false, txt: true },
  prompt: "",
  translate: false,
  target: "en",
  llm: "",
  llmModel: "",
  burn: false,
  style: "karaoke",
  burnTranslated: false,
};

/** Is burning in on for this file? An audio file has no picture to draw on. */
export function burning(path: string, o: Options): boolean {
  return o.burn && !isAudio(path);
}

export function chosenFormats(o: Options): Format[] {
  return FORMATS.filter((f) => o.formats[f]);
}

/** The arguments the desktop app passes to babelscribe.exe for one file. */
export function engineArgs(path: string, o: Options): string[] {
  const args = [path];
  if (o.lang !== "auto") args.push("-l", o.lang);
  if (o.accurate) args.push("--accurate");
  args.push("-f", chosenFormats(o).join(","));
  if (o.prompt.trim()) args.push("--prompt", o.prompt.trim());
  if (o.translate) {
    args.push("--translate-to", o.target);
    if (o.llm) args.push("--llm", o.llm);
    if (o.llmModel) args.push("--llm-model", o.llmModel);
  }
  if (burning(path, o)) {
    args.push("--burn", "--style", o.style);
    if (o.translate && o.burnTranslated) args.push("--burn-translated");
  }
  args.push("--progress-json");
  return args;
}

/** Quoted for cmd.exe / PowerShell (Windows paths) ... */
function quote(arg: string): string {
  return /^[\w.,:\\/=-]+$/.test(arg) ? arg : `"${arg.replace(/"/g, '\\"')}"`;
}

/** ... or for a POSIX shell: single quotes keep $, backticks and backslashes as they are. */
function quotePosix(arg: string): string {
  return /^[\w.,:/=@%+-]+$/.test(arg) ? arg : `'${arg.replace(/'/g, "'\\''")}'`;
}

/** The same run typed into a terminal, shown under Advanced. */
export function commandLine(path: string, o: Options): string {
  return ["babelscribe", ...engineArgs(path, o).filter((a) => a !== "--progress-json")]
    .map(isWindowsPath(path) ? quote : quotePosix)
    .join(" ");
}

export type EngineEvent =
  | { event: "log"; message: string }
  | { event: "progress"; stage: string; percent: number }
  | { event: "done"; files: string[]; lang?: string; segments?: number; seconds?: number; text?: string;
      model?: string; device?: string }
  | { event: "error"; message: string };

/** One line of the engine's stdout -> an event, or null for anything that is not one. */
export function parseEvent(line: string): EngineEvent | null {
  const s = line.trim();
  if (!s.startsWith("{")) return null;
  try {
    const v = JSON.parse(s);
    if (v && typeof v === "object" && typeof v.event === "string") return v as EngineEvent;
  } catch {
    /* not JSON */
  }
  return null;
}

export type Stage = "prepare" | "transcribe" | "translate" | "burn" | "save";
export const STAGES: Stage[] = ["prepare", "transcribe", "save"];

/** The steps a run goes through for these options, in order. */
export function stagesFor(path: string, o: Options): Stage[] {
  return ["prepare", "transcribe", ...(o.translate ? (["translate"] as Stage[]) : []),
    ...(burning(path, o) ? (["burn"] as Stage[]) : []), "save"];
}

// How much of the whole run each step is, for the one percentage on screen (transcribing is the long part).
const WEIGHT: Partial<Record<Stage, number>> = { transcribe: 100, translate: 35, burn: 25 };

function working(stages: Stage[]): Stage[] {
  return stages.filter((s) => s !== "prepare" && s !== "save");
}

/** The whole run's percentage from each step's own. */
export function overall(stages: Stage[], pct: Partial<Record<Stage, number>>): number {
  const w = working(stages);
  const total = w.reduce((a, s) => a + (WEIGHT[s] ?? 0), 0);
  if (total === 0) return 0;
  return Math.min(100, w.reduce((a, s) => a + ((WEIGHT[s] ?? 0) * (pct[s] ?? 0)) / 100, 0) / total * 100);
}

export interface Run {
  stages: Stage[];
  stagePercent: Partial<Record<Stage, number>>; // each step's own 0-100, never going back
  percent: number; // 0-100, never going back
  stage: Stage;
  activity: string; // the latest thing the engine said
  startedAt: number;
  transcribeAt: number | null; // when the first progress arrived
  log: string[]; // the last lines of stdout/stderr, shown when the run fails
  result: Extract<EngineEvent, { event: "done" }> | null;
  error: string | null;
}

export function newRun(now: number, stages: Stage[] = STAGES): Run {
  return { stages, stagePercent: {}, percent: 0, stage: "prepare", activity: "", startedAt: now, transcribeAt: null, log: [],
    result: null, error: null };
}

const KEEP = 200;

function remember(run: Run, line: string): string[] {
  const log = run.log.length >= KEEP ? run.log.slice(run.log.length - KEEP + 1) : run.log.slice();
  log.push(line);
  return log;
}

/** The run after one line from the engine. stream "stderr" carries downloads, warnings and tracebacks. */
export function step(run: Run, stream: "stdout" | "stderr", line: string, now: number): Run {
  const text = line.replace(/\s+$/, "");
  if (!text) return run;
  const ev = stream === "stdout" ? parseEvent(text) : null;
  if (!ev) return { ...run, log: remember(run, text), activity: stream === "stderr" ? text.trim() : run.activity };
  switch (ev.event) {
    case "log":
      return { ...run, log: remember(run, ev.message), activity: ev.message };
    case "progress": {
      const s = ev.stage as Stage;
      if (!working(run.stages).includes(s)) return run;
      const stagePercent = { ...run.stagePercent, [s]: Math.max(run.stagePercent[s] ?? 0, Math.min(100, ev.percent)) };
      const next = working(run.stages).find((w) => (stagePercent[w] ?? 0) < 100);
      return { ...run, stagePercent, percent: Math.max(run.percent, overall(run.stages, stagePercent)),
        stage: next ?? "save", transcribeAt: run.transcribeAt ?? (s === "transcribe" ? now : null) };
    }
    case "done":
      return { ...run, percent: 100, stage: "save", result: ev,
        stagePercent: Object.fromEntries(working(run.stages).map((s) => [s, 100])) };
    case "error":
      return { ...run, error: ev.message, log: remember(run, ev.message) };
  }
  return run;
}

/** The run after the engine exited. A missing result or a non-zero code is a failure. */
export function exited(run: Run, code: number | null): Run {
  if (run.result && code === 0) return run;
  if (run.error) return run;
  const tail = run.log.slice(-1)[0];
  return { ...run, error: tail ? `babelscribe stopped (exit code ${code ?? "none"}): ${tail}`
    : `babelscribe stopped without a result (exit code ${code ?? "none"}).` };
}

/** Seconds left, from how fast the transcription has gone so far; null until there is enough to go on. */
export function secondsLeft(run: Run, now: number): number | null {
  if (run.transcribeAt === null || run.percent < 3 || run.percent >= 100) return null;
  const spent = (now - run.transcribeAt) / 1000;
  if (spent < 3) return null;
  return Math.max(1, Math.round((spent * (100 - run.percent)) / run.percent));
}

export function formatLeft(s: number): string {
  if (s < 60) return `about ${s} s left`;
  const m = Math.round(s / 60);
  return `about ${m} min left`;
}

// What fits this computer. The rule and its words live in the engine (babelscribe/ram.py); the app only asks
// `babelscribe models --json` and shows what comes back.
export interface FitModel {
  name: string;
  kind: "general" | "finetune";
  ram_mb: number; // peak memory of a CPU run, with a margin
  gpu_ram_mb: number;
  fits: boolean | null; // null: the engine could not find out how much memory is free
  warning: string | null;
}

export interface Fit {
  ram: { total_mb: number; available_mb: number } | null;
  default: string;
  default_used: string; // what a run with no model chosen will use
  default_note: string | null; // the engine's one line when that is not the default
  accurate: Record<string, string>; // language code -> the model Accurate mode adds; "*" for every other language
  models: FitModel[];
}

/** The engine's answer to `models --json` (its stdout lines joined), or null for anything else. */
export function parseFit(text: string): Fit | null {
  try {
    const v = JSON.parse(text);
    if (v && typeof v === "object" && Array.isArray(v.models) && typeof v.default_used === "string" && v.accurate) {
      return v as Fit;
    }
  } catch {
    /* not JSON */
  }
  return null;
}

/** The one thing to tell the person about memory for these options, in the engine's own words, or null. */
export function memoryNote(fit: Fit | null, o: Pick<Options, "lang" | "accurate">): string | null {
  if (!fit) return null;
  if (o.accurate) {
    const name = fit.accurate[o.lang] ?? fit.accurate["*"];
    return fit.models.find((m) => m.name === name)?.warning ?? null;
  }
  return fit.default_note;
}
