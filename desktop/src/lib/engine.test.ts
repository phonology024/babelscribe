import { describe, expect, it } from "vitest";
import { commandLine, DEFAULT_OPTIONS, engineArgs, exited, formatLeft, memoryNote, newRun, parseEvent, parseFit, secondsLeft, step, type Run } from "./engine";

const path = "C:\\Users\\you\\My Videos\\talk.mp4";

describe("engineArgs", () => {
  it("passes the file, the formats and --progress-json; auto language is the CLI default", () => {
    expect(engineArgs(path, DEFAULT_OPTIONS)).toEqual([path, "-f", "srt,txt", "--progress-json"]);
  });
  it("adds language, accurate mode and the vocabulary prompt", () => {
    const o = { ...DEFAULT_OPTIONS, lang: "th", accurate: true, prompt: "  Kennedy, Eisenhower ",
      formats: { srt: true, vtt: true, txt: false } };
    expect(engineArgs(path, o)).toEqual([path, "-l", "th", "--accurate", "-f", "srt,vtt", "--prompt",
      "Kennedy, Eisenhower", "--progress-json"]);
  });
  it("shows the same run as a command line, quoted where needed", () => {
    expect(commandLine(path, { ...DEFAULT_OPTIONS, prompt: 'say "hi"' })).toBe(
      'babelscribe "C:\\Users\\you\\My Videos\\talk.mp4" -f srt,txt --prompt "say \\"hi\\""');
  });
  it("quotes a macOS or Linux path for a POSIX shell: $, backticks and quotes stay literal", () => {
    expect(commandLine("/home/you/talk.mp4", DEFAULT_OPTIONS)).toBe("babelscribe /home/you/talk.mp4 -f srt,txt");
    expect(commandLine("/home/you/My Videos/$HOME `x`.mp4", { ...DEFAULT_OPTIONS, prompt: "it's" })).toBe(
      "babelscribe '/home/you/My Videos/$HOME `x`.mp4' -f srt,txt --prompt 'it'\\''s'");
  });
});

describe("parseEvent", () => {
  it("reads the JSON lines of babelscribe --progress-json", () => {
    expect(parseEvent('{"event": "progress", "stage": "transcribe", "percent": 12.3}\r')).toEqual(
      { event: "progress", stage: "transcribe", percent: 12.3 });
    expect(parseEvent('{"event": "done", "files": ["a.srt"], "text": "\\u0e2a"}')).toMatchObject({ text: "ส" });
  });
  it("ignores anything else", () => {
    for (const s of ["", "downloading model turbo ...", "{not json", '{"no": "event"}', "[1, 2]"]) {
      expect(parseEvent(s)).toBeNull();
    }
  });
});

function feed(lines: [("stdout" | "stderr"), string, number][], run: Run = newRun(0)): Run {
  return lines.reduce((r, [s, l, t]) => step(r, s, l, t), run);
}

describe("a run", () => {
  it("goes get ready -> transcribe -> save, and the percentage never goes back", () => {
    let r = feed([
      ["stderr", "downloading model turbo (large-v3-turbo) ...", 100],
      ["stdout", '{"event": "log", "message": "language: en"}', 200],
    ]);
    expect(r.stage).toBe("prepare");
    expect(r.activity).toBe("language: en");
    r = feed([
      ["stdout", '{"event": "progress", "stage": "transcribe", "percent": 0.0}', 1000],
      ["stdout", '{"event": "progress", "stage": "transcribe", "percent": 40}', 5000],
      ["stdout", '{"event": "progress", "stage": "transcribe", "percent": 30}', 6000],
      ["stdout", '{"event": "progress", "stage": "burn", "percent": 90}', 6500],
    ], r);
    expect(r.stage).toBe("transcribe");
    expect(r.percent).toBe(40);
    expect(r.transcribeAt).toBe(1000);
    r = feed([["stdout", '{"event": "progress", "stage": "transcribe", "percent": 100}', 9000]], r);
    expect(r.stage).toBe("save");
    r = feed([["stdout", '{"event": "done", "files": ["C:/a.srt"], "lang": "en", "segments": 8}', 9100]], r);
    expect(r.result?.files).toEqual(["C:/a.srt"]);
    expect(exited(r, 0).error).toBeNull();
  });

  it("is a failure on an error event, a non-zero exit or no result", () => {
    const err = feed([["stdout", '{"event": "error", "message": "no such file: a.mp4"}', 1]]);
    expect(exited(err, 1).error).toBe("no such file: a.mp4");
    const crashed = feed([["stderr", "Traceback (most recent call last):", 1], ["stderr", "KeyError: 'x'", 2]]);
    expect(exited(crashed, 1).error).toContain("KeyError: 'x'");
    expect(exited(newRun(0), 0).error).toContain("without a result");
    const done = feed([["stdout", '{"event": "done", "files": []}', 1]]);
    expect(exited(done, null).error).not.toBeNull(); // killed after it was done: not a clean exit
  });

  it("keeps only the last lines of output", () => {
    const lines = Array.from({ length: 500 }, (_, i) => ["stderr", `line ${i}`, i] as ["stderr", string, number]);
    const r = feed(lines);
    expect(r.log.length).toBe(200);
    expect(r.log[199]).toBe("line 499");
  });

  it("estimates the time left from the speed so far", () => {
    const r = feed([
      ["stdout", '{"event": "progress", "stage": "transcribe", "percent": 0}', 0],
      ["stdout", '{"event": "progress", "stage": "transcribe", "percent": 25}', 10000],
    ]);
    expect(secondsLeft(r, 10000)).toBe(30);
    expect(secondsLeft(r, 1000)).toBeNull(); // too early to say
    expect(formatLeft(30)).toBe("about 30 s left");
    expect(formatLeft(150)).toBe("about 3 min left");
  });
});

describe("what fits this computer", () => {
  const model = (name: string, warning: string | null) => ({ name, kind: "general" as const, ram_mb: 1, gpu_ram_mb: 1,
    fits: warning === null, warning });
  const fit = {
    ram: { total_mb: 4096, available_mb: 1500 }, default: "turbo", default_used: "small",
    default_note: "low memory: 1.5 GB free, turbo needs about 2.3 GB; using small instead.",
    accurate: { th: "thai-pathumma", "*": "large-v3" },
    models: [model("large-v3", "large-v3 needs about 4.4 GB"), model("thai-pathumma", "thai-pathumma needs about 3.0 GB"),
      model("tiny", null)],
  };
  it("reads the engine's answer and nothing else", () => {
    expect(parseFit(JSON.stringify(fit))).toEqual(fit);
    for (const s of ["", "downloading ...", '{"event": "log"}', "[1]", '{"models": 3}']) expect(parseFit(s)).toBeNull();
  });
  it("shows the engine's own line for the default model when it was replaced", () => {
    expect(memoryNote(fit, { lang: "en", accurate: false })).toBe(fit.default_note);
  });
  it("shows the warning of the model Accurate mode adds for the chosen language", () => {
    expect(memoryNote(fit, { lang: "th", accurate: true })).toBe("thai-pathumma needs about 3.0 GB");
    expect(memoryNote(fit, { lang: "auto", accurate: true })).toBe("large-v3 needs about 4.4 GB");
    expect(memoryNote(fit, { lang: "de", accurate: true })).toBe("large-v3 needs about 4.4 GB");
  });
  it("says nothing when it fits, when the engine did not answer, or when the model is not listed", () => {
    expect(memoryNote({ ...fit, default_note: null }, { lang: "en", accurate: false })).toBeNull();
    expect(memoryNote(null, { lang: "en", accurate: true })).toBeNull();
    expect(memoryNote({ ...fit, models: [] }, { lang: "th", accurate: true })).toBeNull();
  });
});
