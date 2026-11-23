// Reading back what the engine wrote, to list the subtitle lines on the result screen.

export interface Cue {
  start: number | null; // seconds; null for plain text (.txt)
  end: number | null;
  text: string;
}

function seconds(stamp: string): number | null {
  const m = /^(?:(\d+):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})$/.exec(stamp.trim());
  if (!m) return null;
  const [, h, min, s, ms] = m;
  return (Number(h ?? 0) * 3600) + Number(min) * 60 + Number(s) + Number(ms.padEnd(3, "0")) / 1000;
}

/** SRT and WebVTT: blocks with a "start --> end" line; numbers, headers and NOTE blocks are skipped. */
export function parseCues(text: string): Cue[] {
  const cues: Cue[] = [];
  const blocks = text.replace(/^﻿/, "").replace(/\r\n?/g, "\n").split(/\n\s*\n/);
  for (const block of blocks) {
    const lines = block.split("\n");
    const at = lines.findIndex((l) => l.includes("-->"));
    if (at < 0) continue;
    const [a, b] = lines[at].split("-->");
    const start = seconds(a);
    const end = seconds(b.trim().split(/\s+/)[0] ?? "");
    const body = lines.slice(at + 1).join("\n").replace(/<[^>]+>/g, "").trim();
    if (start === null || end === null || !body) continue;
    cues.push({ start, end, text: body });
  }
  return cues;
}

export function parseText(text: string): Cue[] {
  return text.replace(/\r\n?/g, "\n").split("\n").map((l) => l.trim()).filter(Boolean)
    .map((t) => ({ start: null, end: null, text: t }));
}

const TIMED_FIRST = [".srt", ".vtt", ".txt"];

/** NAME.th.srt: what the translation of a run into Thai writes. */
function isTranslation(file: string, target: string): boolean {
  const f = file.toLowerCase();
  return TIMED_FIRST.some((ext) => f.endsWith(`.${target.toLowerCase()}${ext}`));
}

/** Which written file to read the lines from: timed formats first. With `target`, the translated files are not it. */
export function subtitleSource(files: string[], target?: string): string | null {
  for (const ext of TIMED_FIRST) {
    const f = files.find((x) => x.toLowerCase().endsWith(ext) && !(target && isTranslation(x, target)));
    if (f) return f;
  }
  return null;
}

/** The translated subtitles a run wrote (NAME.LANG.srt, .vtt or .txt), or null. */
export function translatedSource(files: string[], target: string): string | null {
  for (const ext of TIMED_FIRST) {
    const f = files.find((x) => x.toLowerCase().endsWith(`.${target.toLowerCase()}${ext}`));
    if (f) return f;
  }
  return null;
}

export function parseFile(path: string, text: string): Cue[] {
  return path.toLowerCase().endsWith(".txt") ? parseText(text) : parseCues(text);
}

/** 4.6 -> "0:04.600" */
export function stamp(t: number): string {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s < 10 ? "0" : ""}${s.toFixed(3)}`;
}
