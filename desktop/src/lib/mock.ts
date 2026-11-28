// Stand-in for the Rust side in a plain browser (npm run dev): a fake engine that prints the same JSON lines
// as `babelscribe --progress-json`. Nothing is read or run. The sample text is from J. F. Kennedy's 1961
// inaugural address (public domain).
import type { Backend, Exit, Line } from "./backend";

export const SAMPLE = "C:\\Users\\you\\Videos\\jfk_inaugural_1961.mp4";

const LINES: [number, number, string][] = [
  [0.4, 4.6, "We observe today not a victory of party,"],
  [4.6, 8.2, "but a celebration of freedom,"],
  [8.2, 12.4, "symbolizing an end, as well as a beginning."],
  [13.0, 17.0, "Let the word go forth from this time and place,"],
  [17.0, 19.8, "to friend and foe alike."],
  [21.0, 23.6, "And so, my fellow Americans:"],
  [23.6, 26.6, "ask not what your country can do for you,"],
  [26.6, 30.0, "ask what you can do for your country."],
];

function t(s: number, sep: string): string {
  const p = (n: number, w = 2) => String(n).padStart(w, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(Math.floor(s % 60))}${sep}${p(Math.round((s % 1) * 1000), 3)}`;
}

const THAI = ["วันนี้เราไม่ได้ฉลองชัยชนะของพรรคใด", "แต่ฉลองเสรีภาพ", "ซึ่งเป็นทั้งจุดจบ และจุดเริ่มต้น",
  "ขอให้ถ้อยคำนี้ ส่งออกไปจากที่นี่ และเวลานี้", "ถึงทั้งมิตร และศัตรู", "ดังนั้น เพื่อนชาวอเมริกันทั้งหลาย",
  "อย่าถามว่า ประเทศจะทำอะไร ให้คุณได้", "จงถามว่า คุณจะทำอะไร ให้ประเทศได้"];

function file(path: string): string {
  if (/\.th\.srt$/.test(path)) {
    return LINES.map(([a, b], i) => `${i + 1}\n${t(a, ",")} --> ${t(b, ",")}\n${THAI[i]}`).join("\n\n") + "\n";
  }
  if (path.endsWith(".txt")) return LINES.map((l) => l[2]).join("\n") + "\n";
  if (path.endsWith(".vtt")) return "WEBVTT\n\n" + LINES.map(([a, b, x]) => `${t(a, ".")} --> ${t(b, ".")}\n${x}`).join("\n\n") + "\n";
  return LINES.map(([a, b, x], i) => `${i + 1}\n${t(a, ",")} --> ${t(b, ",")}\n${x}`).join("\n\n") + "\n";
}

const params = () => new URLSearchParams(typeof location === "undefined" ? "" : location.search);
let timers: number[] = [];

// Fake AI apps for `npm run dev`: what `babelscribe connect` would answer, kept in memory (nothing is written anywhere).
const APPS_MOCK: Record<string, { name: string; installed: boolean; path: string | null; kind: string }> = {
  "claude-desktop": { name: "Claude Desktop", installed: true, path: "C:\\Users\\you\\AppData\\Roaming\\Claude\\claude_desktop_config.json", kind: "json" },
  "claude-code": { name: "Claude Code", installed: true, path: null, kind: "command" },
  codex: { name: "Codex CLI", installed: false, path: "C:\\Users\\you\\.codex\\config.toml", kind: "toml" },
  cursor: { name: "Cursor", installed: true, path: "C:\\Users\\you\\.cursor\\mcp.json", kind: "json" },
  gemini: { name: "Gemini CLI", installed: false, path: "C:\\Users\\you\\.gemini\\settings.json", kind: "json" },
};
const SERVER = "C:\\Users\\you\\AppData\\Local\\babelscribe\\babelscribe-mcp.exe";
const connected = new Set<string>();

function connectAnswer(args: string[]): unknown {
  const [, action, app] = args;
  if (action === "status") {
    return Object.entries(APPS_MOCK).map(([k, a]) => ({ app: k, name: a.name, installed: a.installed, path: a.path, problem: null,
      state: connected.has(k) ? "connected" : "not-connected" }));
  }
  const a = APPS_MOCK[app];
  if (action === "show") {
    const text = a.kind === "command" ? `claude mcp add --scope user babelscribe -- ${SERVER}`
      : a.kind === "toml" ? `[mcp_servers.babelscribe]\ncommand = ${JSON.stringify(SERVER)}\nargs = []\ntool_timeout_sec = 3600\nstartup_timeout_sec = 120\n`
      : JSON.stringify({ mcpServers: { babelscribe: { command: SERVER, args: [], timeout: 3600000 } } }, null, 2);
    return { app, name: a.name, kind: a.kind, installed: a.installed, state: connected.has(app) ? "connected" : "not-connected",
      path: a.path, text, backup: a.path ? `${a.path}.bak` : null, problem: params().get("broken") === app
        ? `${a.path} has a mistake in it (Expecting ',' delimiter, line 3, column 5), so babelscribe left it exactly as it is. Fix that line, or use Copy and add babelscribe yourself.` : null,
      extra: a.kind === "command" ? "Claude Code keeps this in its own user settings (`--scope user`), so it works in every project." : "Other servers already in the file are kept.",
      after: `Start ${a.name} again and look for babelscribe.`, server: SERVER };
  }
  if (action === "add") connected.add(app);
  else connected.delete(app);
  return { ok: true, changed: true, path: a.path, backup: a.path ? `${a.path}.bak` : null,
    message: action === "add" ? `${a.name} is connected. Start ${a.name} again and look for babelscribe.` : `babelscribe was taken out of ${a.name}'s settings.` };
}

export const mock: Backend = {
  async pickFile() {
    return SAMPLE;
  },
  async fileInfo() {
    return { exists: true, isFile: true, size: 48 * 1024 * 1024 };
  },
  async run(args: string[], onLine: Line, onExit: Exit) {
    if (args[0] === "llms" || args[0] === "connect") {
      const answer = args[0] === "connect" ? connectAnswer(args) : [
        { url: "http://127.0.0.1:8080/v1", kind: "llama-server", up: false, models: [] },
        { url: "http://127.0.0.1:11434/v1", kind: "Ollama", up: params().get("llm") !== "none", models: ["gemma3", "qwen3"] },
        { url: "http://127.0.0.1:1234/v1", kind: "LM Studio", up: false, models: [] },
      ];
      timers.push(window.setTimeout(() => { onLine("stdout", JSON.stringify(answer)); onExit(0); }, 120));
      return;
    }
    if (args[0] === "models") {
      // ?ram=1.5 pretends this computer has 1.5 GB free, for screenshots of the low-memory notes
      const free = Number(params().get("ram") ?? 16) * 1024;
      const need = (mb: number) => mb + 512;
      const one = (name: string, kind: string, mb: number) => {
        const fits = need(mb) <= free;
        return { name, kind, ram_mb: need(mb), gpu_ram_mb: 1200, fits,
          warning: fits ? null : `${name} needs about ${(need(mb) / 1024).toFixed(1)} GB of free memory and this computer has ${(free / 1024).toFixed(1)} GB free: it may run very slowly or stop.` };
      };
      const list = [one("tiny", "general", 309), one("small", "general", 887), one("large-v3-turbo", "general", 1939),
        one("large-v3", "general", 4000), one("thai-pathumma", "finetune", 2600)];
      const used = list.find((m) => m.name === "large-v3-turbo")?.fits ? "turbo" : "small";
      const note = used === "small" ? `low memory: ${(free / 1024).toFixed(1)} GB free, turbo needs about ${(need(1939) / 1024).toFixed(1)} GB; using small instead (it is less accurate, most of all for Thai and other languages than English). -m turbo keeps it.` : null;
      const report = { ram: { total_mb: 16384, available_mb: free }, margin_mb: 512, default: "turbo", default_used: used,
        default_note: note, accurate: { th: "thai-pathumma", "*": "large-v3" }, models: list };
      timers.push(window.setTimeout(() => { onLine("stdout", JSON.stringify(report)); onExit(0); }, 150));
      return;
    }
    const src = args[0];
    const formats = (args[args.indexOf("-f") + 1] || "srt").split(",");
    const base = src.replace(/\.[^.\\/]+$/, "");
    const hold = Number(params().get("hold") ?? 101); // ?hold=42 stops the fake run there, for screenshots
    const say = (ms: number, line: string, stream: "stdout" | "stderr" = "stdout") =>
      timers.push(window.setTimeout(() => onLine(stream, line), ms));
    const ev = (o: object) => JSON.stringify(o);
    let ms = 200;
    if (!args.includes("-l")) say(ms += 300, ev({ event: "log", message: "language: en" }));
    say(ms += 200, ev({ event: "log", message: "transcribing with turbo on vulkan GPU 0 ..." }));
    const target = args.includes("--translate-to") ? args[args.indexOf("--translate-to") + 1] : null;
    const stages = ["transcribe", ...(target ? ["translate"] : []), ...(args.includes("--burn") ? ["burn"] : [])];
    for (const stage of stages) {
      for (let p = 0; p <= 100; p += 6) {
        if ((stages.indexOf(stage) * 100 + p) / stages.length > hold) return;
        say(ms += 180, ev({ event: "progress", stage, percent: p }));
      }
      say(ms += 120, ev({ event: "progress", stage, percent: 100 }));
    }
    if (hold <= 100) return;
    const files = [...formats.map((f) => `${base}.${f}`), ...(target ? [`${base}.${target}.srt`] : []),
      ...(args.includes("--burn") ? [`${base}${args.includes("--burn-translated") && target ? `.${target}` : ""}.subbed.mp4`] : [])];
    say(ms += 200, ev({ event: "done", files, lang: "en", segments: LINES.length, seconds: 6.1, model: "turbo",
      device: "vulkan GPU 0", text: LINES.map((l) => l[2]).join("\n") }));
    timers.push(window.setTimeout(() => onExit(0), ms + 50));
  },
  async cancel() {
    timers.forEach(clearTimeout);
    timers = [];
  },
  async readText(path: string) {
    return file(path);
  },
  async openPath() {},
  async showInFolder() {},
  async setTheme() {},
  async onDrop() {
    return () => {};
  },
};
