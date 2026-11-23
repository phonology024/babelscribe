// The recent files on screen 1. Kept in this computer's WebView storage only; losing it loses nothing else.
import { isWindowsPath } from "./utils";

export interface Recent {
  path: string;
  lang?: string; // the language of the last run, when known
  when: number; // ms since epoch
}

const KEY = "bs-recent";
const MAX = 8;

export function loadRecent(store: Pick<Storage, "getItem"> | null = safeStorage()): Recent[] {
  try {
    const v = JSON.parse(store?.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((r) => r && typeof r.path === "string" && typeof r.when === "number") : [];
  } catch {
    return [];
  }
}

export function saveRecent(list: Recent[], store: Pick<Storage, "setItem"> | null = safeStorage()): void {
  try {
    store?.setItem(KEY, JSON.stringify(list));
  } catch {
    /* storage full or blocked: the list is a convenience */
  }
}

/** The list with this file on top (once). Windows paths compare without case, as Windows does; on macOS and Linux
 * "A.mp4" and "a.mp4" can be two files. */
export function addRecent(list: Recent[], item: Recent): Recent[] {
  const same = (r: Recent) =>
    isWindowsPath(item.path) || isWindowsPath(r.path)
      ? r.path.toLowerCase() === item.path.toLowerCase()
      : r.path === item.path;
  const old = list.find(same);
  return [{ ...old, ...item, lang: item.lang ?? old?.lang }, ...list.filter((r) => !same(r))].slice(0, MAX);
}

/** "Today", "Yesterday", or a short date such as "Nov 18". */
export function whenLabel(when: number, now: number = Date.now()): string {
  const day = (t: number) => {
    const d = new Date(t);
    return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  };
  const days = Math.round((day(now) - day(when)) / 86400000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  return new Date(when).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function safeStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}
