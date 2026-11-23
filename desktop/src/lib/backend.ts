// What the screens need from the computer. In the app this is the Rust side (src-tauri/src/main.rs); in a plain
// browser (npm run dev) it is the stand-in in mock.ts, so the screens can be worked on without Rust or a GPU.
import { Channel, invoke, isTauri } from "@tauri-apps/api/core";
import { getCurrentWebview } from "@tauri-apps/api/webview";

export interface FileInfo {
  exists: boolean;
  isFile: boolean;
  size: number;
}

export type Line = (stream: "stdout" | "stderr", line: string) => void;
export type Exit = (code: number | null) => void;
export type Drop = (e: { type: "over" } | { type: "leave" } | { type: "drop"; paths: string[] }) => void;

export interface Backend {
  pickFile(): Promise<string | null>;
  fileInfo(path: string): Promise<FileInfo>;
  /** Starts babelscribe.exe with these arguments. Only one run at a time. */
  run(args: string[], onLine: Line, onExit: Exit): Promise<void>;
  /** Ends the run and every process it started (whisper-cli, ffmpeg). */
  cancel(): Promise<void>;
  readText(path: string): Promise<string>;
  openPath(path: string): Promise<void>;
  showInFolder(path: string): Promise<void>;
  setTheme(theme: "light" | "dark" | null): Promise<void>;
  onDrop(cb: Drop): Promise<() => void>;
}

type EngineMessage =
  | { kind: "stdout"; line: string }
  | { kind: "stderr"; line: string }
  | { kind: "exit"; code: number | null }
  | { kind: "error"; message: string };

const tauri: Backend = {
  pickFile: () => invoke<string | null>("pick_file"),
  fileInfo: (path) => invoke<FileInfo>("file_info", { path }),
  async run(args, onLine, onExit) {
    const channel = new Channel<EngineMessage>();
    channel.onmessage = (m) => {
      if (m.kind === "stdout" || m.kind === "stderr") onLine(m.kind, m.line);
      else if (m.kind === "error") onLine("stderr", m.message);
      else onExit(m.code);
    };
    await invoke("run_engine", { args, onEvent: channel });
  },
  cancel: () => invoke("cancel_engine"),
  readText: (path) => invoke<string>("read_text", { path }),
  openPath: (path) => invoke("open_path", { path }),
  showInFolder: (path) => invoke("show_in_folder", { path }),
  setTheme: (theme) => invoke("set_theme", { theme }),
  async onDrop(cb) {
    return getCurrentWebview().onDragDropEvent((e) => {
      const p = e.payload;
      if (p.type === "drop") cb({ type: "drop", paths: p.paths });
      else if (p.type === "leave") cb({ type: "leave" });
      else cb({ type: "over" });
    });
  },
};

let chosen: Backend | null = null;

export async function backend(): Promise<Backend> {
  if (!chosen) chosen = isTauri() ? tauri : (await import("./mock")).mock;
  return chosen;
}

export const inApp = () => isTauri();
