import { describe, expect, it } from "vitest";
import type { Backend } from "./backend";
import { engineCall, inLine, lastJson, llmChoices, parseLlms, parseOutcome, parsePlan, parseRows, stateLabel, whenIdle } from "./ai";

/** A backend whose run() answers each command with the given stdout lines (or never answers, or fails to start). */
function fake(answer: (args: string[]) => string[] | "never" | "fail", log: string[] = []): Backend {
  return {
    async run(args: string[], onLine: (s: string, l: string) => void, onExit: (c: number | null) => void) {
      log.push(args.join(" "));
      const a = answer(args);
      if (a === "fail") throw new Error("could not start");
      if (a === "never") return;
      a.forEach((l) => onLine("stdout", l));
      onLine("stderr", "noise on stderr");
      queueMicrotask(() => onExit(0));
    },
    async cancel() {
      log.push("cancel");
    },
  } as unknown as Backend;
}

describe("lastJson", () => {
  it("takes the last JSON object or list and skips anything else", () => {
    expect(lastJson(["hello", '{"a": 1}', "bye"])).toEqual({ a: 1 });
    expect(lastJson(['{"a": 1}', "[2]"])).toEqual([2]);
    expect(lastJson(["{broken", "nothing"])).toBeNull();
    expect(lastJson([])).toBeNull();
  });
});

describe("local models", () => {
  const llms = [
    { url: "http://127.0.0.1:8080/v1", kind: "llama-server", up: false, models: [] },
    { url: "http://127.0.0.1:11434/v1", kind: "Ollama", up: true, models: ["gemma3", "qwen3"] },
    { url: "http://127.0.0.1:1234/v1", kind: "LM Studio", up: true, models: [] },
  ];
  it("lists one entry per model on each server that answers, never the ones that do not", () => {
    const c = llmChoices(llms);
    expect(c.map((x) => x.label)).toEqual(["Ollama · 127.0.0.1:11434 · gemma3", "Ollama · 127.0.0.1:11434 · qwen3", "LM Studio · 127.0.0.1:1234"]);
    expect(c[0]).toMatchObject({ url: "http://127.0.0.1:11434/v1", model: "gemma3" });
    expect(c[2]).toMatchObject({ url: "http://127.0.0.1:1234/v1", model: "" });   // a server that lists no model: the engine picks
    expect(llmChoices(null)).toEqual([]);
  });
  it("reads the engine's answer and refuses anything else", () => {
    expect(parseLlms([JSON.stringify(llms)])).toEqual(llms);
    expect(parseLlms(['{"no": "list"}'])).toBeNull();
    expect(parseLlms([])).toBeNull();
    expect(parseLlms(['[{"url": 1}, 5, null]'])).toEqual([]);
  });
});

describe("AI apps", () => {
  it("reads the app list and a plan", () => {
    expect(parseRows(['[{"app": "cursor"}]'])).toEqual([{ app: "cursor" }]);
    expect(parseRows(["{}"])).toBeNull();
    expect(parsePlan(['{"text": "x", "app": "cursor"}'])?.app).toBe("cursor");
    expect(parsePlan(['{"app": "cursor"}'])).toBeNull();
    expect(parsePlan(["nothing"])).toBeNull();
  });
  it("trusts a success only when the engine said ok and exited 0", () => {
    const ok = { ok: true, changed: true, message: "done", path: "p", backup: null };
    expect(parseOutcome({ code: 0, out: [JSON.stringify(ok)] })).toEqual(ok);
    expect(parseOutcome({ code: 1, out: [JSON.stringify(ok)] }).ok).toBe(false);          // said ok but crashed
    expect(parseOutcome({ code: null, out: [JSON.stringify(ok)] }).ok).toBe(false);
    expect(parseOutcome({ code: 1, out: ['{"ok": false, "error": "left it exactly as it is"}'] })).toEqual({ ok: false, error: "left it exactly as it is" });
  });
  it("never reports success for an answer that did not come", () => {
    for (const res of [{ code: 0, out: [] }, { code: 0, out: ["garbage"] }, { code: null, out: [] }]) {
      const r = parseOutcome(res);
      expect(r.ok).toBe(false);
      expect(r.ok === false && r.error).toContain("Nothing was changed");
    }
  });
  it("says in words where an app stands", () => {
    expect(stateLabel("connected")).toBe("connected");
    expect(stateLabel("not-connected")).toBe("not yet");
    expect(stateLabel("other")).toBe("set up another way");
    expect(stateLabel("unknown")).toBe("cannot check");
  });
});

describe("asking the engine", () => {
  it("returns the stdout lines and the exit code, and never the stderr", async () => {
    const got = await engineCall(fake(() => ['{"a": 1}']), ["llms", "--json"]);
    expect(got).toEqual({ code: 0, out: ['{"a": 1}'] });
  });
  it("answers a command that cannot start with no code and no lines instead of throwing", async () => {
    expect(await engineCall(fake(() => "fail"), ["llms"])).toEqual({ code: null, out: [] });
  });
  it("gives up on an engine that never answers, ends it, and lets the next question go", async () => {
    const log: string[] = [];
    const b = fake((args) => (args[0] === "slow" ? "never" : ["[]"]), log);
    const slow = engineCall(b, ["slow"], 20);
    const next = engineCall(b, ["fast"]);
    expect((await slow).code).toBeNull();
    expect((await next).code).toBe(0);
    expect(log).toEqual(["slow", "cancel", "fast"]);
  });
  it("asks one question at a time, in the order they were asked", async () => {
    const log: string[] = [];
    const order: string[] = [];
    let busy = 0;
    const b = {
      async run(args: string[], _onLine: unknown, onExit: (c: number | null) => void) {
        busy++;
        expect(busy).toBe(1);
        order.push(args[0]);
        setTimeout(() => {
          busy--;
          onExit(0);
        }, 5);
      },
      async cancel() {},
    } as unknown as Backend;
    await Promise.all([engineCall(b, ["a"]), engineCall(b, ["b"]), engineCall(b, ["c"])]);
    expect(order).toEqual(["a", "b", "c"]);
    expect(log).toEqual([]);
  });
  it("a run that waits for every question asked before it", async () => {
    const done: string[] = [];
    const slow = inLine(async () => {
      await new Promise((r) => setTimeout(r, 10));
      done.push("question");
    });
    await whenIdle();
    done.push("run");
    await slow;
    expect(done).toEqual(["question", "run"]);
  });
  it("keeps going after a question that threw", async () => {
    await inLine(async () => {
      throw new Error("boom");
    }).catch(() => {});
    expect(await inLine(async () => 7)).toBe(7);
  });
});
