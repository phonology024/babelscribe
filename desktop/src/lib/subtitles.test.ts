import { describe, expect, it } from "vitest";
import { parseCues, parseFile, stamp, subtitleSource } from "./subtitles";

describe("parseCues", () => {
  it("reads SRT, including CRLF, a BOM and two-line subtitles", () => {
    const srt = "﻿1\r\n00:00:00,400 --> 00:00:04,600\r\nWe observe today\r\nnot a victory of party,\r\n\r\n" +
      "2\r\n00:00:04,600 --> 00:00:08,200\r\nbut a celebration of freedom,\r\n";
    expect(parseCues(srt)).toEqual([
      { start: 0.4, end: 4.6, text: "We observe today\nnot a victory of party," },
      { start: 4.6, end: 8.2, text: "but a celebration of freedom," },
    ]);
  });
  it("reads WebVTT with cue settings, tags and a NOTE", () => {
    const vtt = "WEBVTT\n\nNOTE made by babelscribe\n\n01:02.500 --> 01:04.000 align:center\n<c>ask not</c> what\n";
    expect(parseCues(vtt)).toEqual([{ start: 62.5, end: 64, text: "ask not what" }]);
  });
  it("skips blocks it cannot read", () => {
    expect(parseCues("1\nnot a time\nhello\n\n2\n00:00:01,000 --> 00:00:02,000\n\n")).toEqual([]);
  });
});

describe("which file is shown", () => {
  it("prefers timed formats", () => {
    expect(subtitleSource(["a.txt", "a.vtt", "a.srt"])).toBe("a.srt");
    expect(subtitleSource(["a.TXT", "a.vtt"])).toBe("a.vtt");
    expect(subtitleSource(["a.txt"])).toBe("a.txt");
    expect(subtitleSource(["a.subbed.mp4"])).toBeNull();
  });
  it("reads .txt as untimed lines", () => {
    expect(parseFile("a.txt", "one\r\n\r\ntwo\n")).toEqual([
      { start: null, end: null, text: "one" },
      { start: null, end: null, text: "two" },
    ]);
  });
});

it("formats times as m:ss.mmm", () => {
  expect(stamp(4.6)).toBe("0:04.600");
  expect(stamp(62.5)).toBe("1:02.500");
});
