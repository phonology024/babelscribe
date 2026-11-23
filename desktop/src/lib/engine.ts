// Talking to the engine: babelscribe.exe (the Python CLI, bundled as a sidecar) run with --progress-json.
// The command line is the single source of truth; this file only builds its arguments and reads its events.

export type Format = "srt" | "vtt" | "txt";
export const FORMATS: Format[] = ["srt", "vtt", "txt"];

export interface Options {
  lang: string; // "auto" or a Whisper language code
  accurate: boolean;
  formats: Record<Format, boolean>;
  prompt: string; // names and terms to spell correctly
}

export const DEFAULT_OPTIONS: Options = {
  lang: "auto",
  accurate: false,
  formats: { srt: true, vtt: false, txt: true },
  prompt: "",
};

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
  args.push("--progress-json");
  return args;
}

function quote(arg: string): string {
  return /^[\w.,:\\/=-]+$/.test(arg) ? arg : `"${arg.replace(/"/g, '\\"')}"`;
}

/** The same run typed into a terminal, shown under Advanced. */
export function commandLine(path: string, o: Options): string {
  return ["babelscribe", ...engineArgs(path, o).filter((a) => a !== "--progress-json")].map(quote).join(" ");
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

export type Stage = "prepare" | "transcribe" | "save";
export const STAGES: Stage[] = ["prepare", "transcribe", "save"];

export interface Run {
  percent: number; // 0-100, never going back
  stage: Stage;
  activity: string; // the latest thing the engine said
  startedAt: number;
  transcribeAt: number | null; // when the first progress arrived
  log: string[]; // the last lines of stdout/stderr, shown when the run fails
  result: Extract<EngineEvent, { event: "done" }> | null;
  error: string | null;
}

export function newRun(now: number): Run {
  return { percent: 0, stage: "prepare", activity: "", startedAt: now, transcribeAt: null, log: [], result: null,
    error: null };
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
      if (ev.stage !== "transcribe") return run;
      const percent = Math.max(run.percent, Math.min(100, ev.percent));
      return { ...run, percent, stage: percent >= 100 ? "save" : "transcribe",
        transcribeAt: run.transcribeAt ?? now };
    }
    case "done":
      return { ...run, percent: 100, stage: "save", result: ev };
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
