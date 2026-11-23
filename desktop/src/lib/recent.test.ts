import { describe, expect, it } from "vitest";
import { addRecent, loadRecent, saveRecent, whenLabel } from "./recent";
import { formatSize, splitPath } from "./utils";

describe("recent files", () => {
  it("puts the newest on top, once, keeping a known language", () => {
    let l = addRecent([], { path: "C:\\a.mp4", when: 1, lang: "th" });
    l = addRecent(l, { path: "C:\\b.mp4", when: 2 });
    l = addRecent(l, { path: "c:\\A.MP4", when: 3 });
    expect(l.map((r) => [r.path, r.lang])).toEqual([["c:\\A.MP4", "th"], ["C:\\b.mp4", undefined]]);
  });
  it("keeps at most 8", () => {
    let l: ReturnType<typeof loadRecent> = [];
    for (let i = 0; i < 12; i++) l = addRecent(l, { path: `C:\\${i}.mp4`, when: i });
    expect(l.length).toBe(8);
    expect(l[0].path).toBe("C:\\11.mp4");
  });
  it("survives broken or missing storage", () => {
    const store = new Map<string, string>();
    const s = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
    saveRecent([{ path: "C:\\a.mp4", when: 1 }], s);
    expect(loadRecent(s)).toEqual([{ path: "C:\\a.mp4", when: 1 }]);
    store.set("bs-recent", "{broken");
    expect(loadRecent(s)).toEqual([]);
    expect(loadRecent(null)).toEqual([]);
    expect(() => saveRecent([], { setItem: () => { throw new Error("full"); } })).not.toThrow();
  });
  it("labels the day", () => {
    const now = new Date(2026, 10, 23, 10).getTime();
    expect(whenLabel(new Date(2026, 10, 23, 1).getTime(), now)).toBe("Today");
    expect(whenLabel(new Date(2026, 10, 22, 23).getTime(), now)).toBe("Yesterday");
    expect(whenLabel(new Date(2026, 10, 18, 12).getTime(), now)).toBe("Nov 18");
  });
});

describe("paths and sizes", () => {
  it("splits Windows and POSIX paths", () => {
    expect(splitPath("C:\\Users\\you\\Videos\\jfk.mp4")).toEqual({ name: "jfk.mp4", folder: "C:\\Users\\you\\Videos" });
    expect(splitPath("/home/you/jfk.mp4")).toEqual({ name: "jfk.mp4", folder: "/home/you" });
    expect(splitPath("jfk.mp4")).toEqual({ name: "jfk.mp4", folder: "" });
  });
  it("formats file sizes", () => {
    expect(formatSize(48 * 1024 * 1024)).toBe("48 MB");
    expect(formatSize(400 * 1024)).toBe("0.4 MB");
    expect(formatSize(3.2 * 1024 ** 3)).toBe("3.2 GB");
  });
});
