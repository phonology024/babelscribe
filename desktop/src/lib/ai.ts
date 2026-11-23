// What the engine says about local translation models (`babelscribe llms --json`) and about AI apps
// (`babelscribe connect ... --json`). The rules, the files and the words live in the engine; this only asks and shows.
import type { Backend } from "./backend";

/** The colours the engine draws captions in (babelscribe/burn.py WHITE, AMBER, YELLOW; a Python test compares them). */
export const BURN_COLOURS = { white: "#FFFFFF", karaoke: "#FFD700", shorts: "#FFFF00", outline: "#000000" } as const;

// The engine runs one thing at a time, so every short question to it waits for the one before it.
let line: Promise<unknown> = Promise.resolve();
export function inLine<T>(fn: () => Promise<T>): Promise<T> {
  const next = line.then(fn, fn);
  line = next.catch(() => {});
  return next;
}
/** Resolves when every question asked so far has been answered (a run waits for this before it starts). */
export const whenIdle = () => inLine(async () => {});

/** Run an engine command to its end and hand back what it printed on stdout, line by line. */
export function engineCall(b: Backend, args: string[], giveUpMs = 60000): Promise<{ code: number | null; out: string[] }> {
  return inLine(() => new Promise((resolve) => {
    const out: string[] = [];
    let ended = false;
    const end = (code: number | null) => {
      if (ended) return;
      ended = true;
      clearTimeout(timer);
      resolve({ code, out });
    };
    // an engine that never answers must not leave the screen waiting (and holding the one slot) for ever
    const timer = setTimeout(() => {
      b.cancel().catch(() => {}).then(() => end(null));
    }, giveUpMs);
    b.run(args, (stream, text) => stream === "stdout" && out.push(text), end).catch(() => end(null));
  }));
}

/** The last line that is a JSON object or list, parsed; null when there is none. */
export function lastJson(lines: string[]): unknown | null {
  for (let i = lines.length - 1; i >= 0; i--) {
    const s = lines[i].trim();
    if (s.startsWith("{") || s.startsWith("[")) {
      try {
        return JSON.parse(s);
      } catch {
        return null;
      }
    }
  }
  return null;
}

// ---------------------------------------------------------------------------------------------- translators

export interface Llm {
  url: string;
  kind: string;
  up: boolean;
  models: string[];
}

export function parseLlms(lines: string[]): Llm[] | null {
  const v = lastJson(lines);
  if (!Array.isArray(v)) return null;
  return v.filter((x): x is Llm => !!x && typeof x.url === "string" && typeof x.kind === "string" && Array.isArray(x.models));
}

export interface LlmChoice {
  value: string; // "url|model"
  url: string;
  model: string;
  label: string;
}

/** One entry per model on every server that answers: "Ollama · 127.0.0.1:11434 · gemma3". */
export function llmChoices(llms: Llm[] | null): LlmChoice[] {
  const out: LlmChoice[] = [];
  for (const l of llms ?? []) {
    if (!l.up) continue;
    const host = l.url.replace(/^https?:\/\//, "").replace(/\/v1\/?$/, "");
    for (const model of l.models.length ? l.models : [""]) {
      out.push({ value: `${l.url}|${model}`, url: l.url, model, label: `${l.kind} · ${host}${model ? ` · ${model}` : ""}` });
    }
  }
  return out;
}

// ---------------------------------------------------------------------------------------------- AI apps

export interface AppRow {
  app: string;
  name: string;
  installed: boolean;
  state: "not-connected" | "connected" | "other" | "unknown";
  path: string | null;
  problem: string | null;
}

export interface Plan extends AppRow {
  kind: "json" | "toml" | "command";
  text: string; // exactly what will be added (or the command that will be run)
  backup: string | null; // where the old file would be copied to, when there is one
  extra: string;
  after: string;
}

export type Outcome =
  | { ok: true; changed: boolean; message: string; path: string | null; backup: string | null }
  | { ok: false; error: string };

export function parseRows(lines: string[]): AppRow[] | null {
  const v = lastJson(lines);
  return Array.isArray(v) ? (v as AppRow[]) : null;
}

export function parsePlan(lines: string[]): Plan | null {
  const v = lastJson(lines) as Plan | null;
  return v && typeof v === "object" && typeof (v as Plan).text === "string" ? v : null;
}

/** What `connect add` / `connect remove` answered; a missing answer is reported as a failure, never as success. */
export function parseOutcome(res: { code: number | null; out: string[] }): Outcome {
  const v = lastJson(res.out) as Record<string, unknown> | null;
  if (v && v.ok === true && res.code === 0) return v as unknown as Outcome;
  if (v && v.ok === false && typeof v.error === "string") return { ok: false, error: v.error };
  return { ok: false, error: "babelscribe did not answer. Nothing was changed; try again." };
}

/** Short status for the sidebar and the app list. */
export function stateLabel(s: AppRow["state"]): string {
  return s === "connected" ? "connected" : s === "other" ? "set up another way" : s === "unknown" ? "cannot check" : "not yet";
}

export const TRY_ASKING = "make Thai subtitles for the newest video in my Downloads";
