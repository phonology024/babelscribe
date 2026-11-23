import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** A Windows path ("C:\Users\you\a.mp4", "\\server\share\a.mp4"): drive letter or UNC, and no case in file names. */
export function isWindowsPath(path: string): boolean {
  return /^[A-Za-z]:[\\/]/.test(path) || path.startsWith("\\\\");
}

/** "C:\Videos\talk.mp4" -> { name: "talk.mp4", folder: "C:\Videos" }. Windows accepts both separators; on macOS and
 * Linux a backslash is an ordinary character in a file name. */
export function splitPath(path: string): { name: string; folder: string } {
  const i = isWindowsPath(path) ? Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/")) : path.lastIndexOf("/");
  return i < 0 ? { name: path, folder: "" } : { name: path.slice(i + 1), folder: path.slice(0, i) || path.slice(0, 1) };
}

export const AUDIO = ["mp3", "wav", "m4a", "aac", "flac", "ogg", "opus", "wma"];
export const VIDEO = ["mp4", "mkv", "mov", "avi", "webm", "m4v"];

export function isAudio(path: string): boolean {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return AUDIO.includes(ext);
}

export function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(0.1, bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes < 1024 ** 3) return `${Math.round(bytes / 1024 / 1024)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

/** English name of a language code ("th" -> "Thai"), the code itself when the runtime does not know it. */
export function languageName(code: string): string {
  try {
    const name = new Intl.DisplayNames(["en"], { type: "language" }).of(code);
    if (name && name !== code) return name;
  } catch {
    /* not a valid code */
  }
  return code;
}
