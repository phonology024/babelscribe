// Every screen renders with the new options and states (server-side render: no window needed), and says what it should.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BURN_COLOURS } from "../lib/ai";
import { DEFAULT_OPTIONS, newRun, stagesFor, step, type Options as Opts } from "../lib/engine";
import { Options } from "./Options";
import { Progress } from "./Progress";
import { Result } from "./Result";

const noop = () => {};
const video = "C:\\Videos\\talk.mp4";
const llms = [{ url: "http://127.0.0.1:11434/v1", kind: "Ollama", up: true, models: ["gemma3"] }];

function options(o: Partial<Opts>, path = video, extra: Partial<Parameters<typeof Options>[0]> = {}) {
  return renderToStaticMarkup(
    <Options path={path} size={1234567} fit={null} llms={llms} scanning={false} onRescan={noop} opts={{ ...DEFAULT_OPTIONS, ...o }}
      setOpts={noop} onChangeFile={noop} onStart={noop} {...extra} />,
  );
}

describe("Options", () => {
  it("shows the two new switches off and nothing under them by default", () => {
    const html = options({});
    expect(html).toContain("Translate the subtitles");
    expect(html).toContain("Burn subtitles into the video");
    expect(html).not.toContain("Local model");
    expect(html).not.toContain("Caption style");
  });
  it("shows the target, the local models found and the Check again button when translating", () => {
    const html = options({ translate: true, target: "th" });
    expect(html).toContain("Local model");
    expect(html).toContain("Ollama · 127.0.0.1:11434 · gemma3");
    expect(html).toContain("Check again");
    expect(html).toContain('<option value="th" selected');
    expect(html).not.toContain("No model is running");
  });
  it("says so when no local model answers, instead of leaving the choice empty", () => {
    const html = options({ translate: true }, video, { llms: [{ url: "http://127.0.0.1:8080/v1", kind: "llama-server", up: false, models: [] }] });
    expect(html).toContain("No model is running on this computer");
  });
  it("shows the three caption styles in the colours the engine draws them in", () => {
    const html = options({ burn: true, style: "karaoke" });
    expect(html).toContain("Caption style");
    for (const name of ["Plain", "Karaoke", "Shorts"]) expect(html).toContain(`>${name}<`);
    for (const colour of [BURN_COLOURS.karaoke, BURN_COLOURS.shorts]) expect(html.toLowerCase()).toContain(colour.toLowerCase());
    expect(html).toContain('aria-checked="true"');
  });
  it("lets translated subtitles be drawn only when translating", () => {
    expect(options({ burn: true })).toContain("disabled=\"\"><option value=\"orig\"");
    expect(options({ burn: true, translate: true })).not.toContain("disabled=\"\"><option value=\"orig\"");
  });
  it("turns burning off for an audio file and says why", () => {
    const html = options({ burn: true }, "C:\\Music\\talk.mp3");
    expect(html).toContain("Needs a video file.");
    expect(html).not.toContain("Caption style");
  });
  it("shows the whole run on the command line", () => {
    const html = options({ translate: true, target: "ja", burn: true, style: "plain" });
    expect(html).toContain("--translate-to ja --burn --style plain");
  });
  it("shows the engine's memory note when there is one", () => {
    const fit = { ram: null, default: "turbo", default_used: "small", default_note: "low memory: 1.2 GB free", accurate: {}, models: [] };
    expect(options({}, video, { fit })).toContain("low memory: 1.2 GB free");
  });
});

describe("Progress", () => {
  const all: Opts = { ...DEFAULT_OPTIONS, translate: true, target: "th", burn: true, style: "karaoke" };
  const render = (run: ReturnType<typeof newRun>, opts: Opts = all) =>
    renderToStaticMarkup(<Progress path={video} run={run} formats={["srt"]} opts={opts} now={5000} onCancel={noop} onBack={noop} />);

  it("lists the steps of what was asked for", () => {
    const html = render(newRun(0, stagesFor(video, all)));
    for (const name of ["Get ready", "Transcribe", "Translate", "Burn subtitles", "Save the files"]) expect(html).toContain(name);
    expect(html).toContain("Into Thai");
  });
  it("lists only three steps for a plain run", () => {
    const html = render(newRun(0, stagesFor(video, DEFAULT_OPTIONS)), DEFAULT_OPTIONS);
    expect(html).not.toContain("Translate");
    expect(html).not.toContain("Burn subtitles");
  });
  it("shows the step that is running with its own percentage", () => {
    let r = newRun(0, stagesFor(video, all));
    for (const [stage, percent] of [["transcribe", 100], ["translate", 40]] as const) {
      r = step(r, "stdout", JSON.stringify({ event: "progress", stage, percent }), 1000);
    }
    const html = render(r);
    expect(html).toContain(">40%<");
    expect(html).toContain('aria-valuenow="40"');
  });
  it("shows the error with Back to options", () => {
    const r = { ...newRun(0, stagesFor(video, all)), error: "no local LLM answered" };
    const html = render(r);
    expect(html).toContain("no local LLM answered");
    expect(html).toContain("Back to options");
  });
});

describe("Result", () => {
  const result = { event: "done" as const, files: ["C:\\Videos\\talk.srt", "C:\\Videos\\talk.th.srt", "C:\\Videos\\talk.th.subbed.mp4"], lang: "en", segments: 2 };
  const cue = (text: string) => ({ start: 0, end: 1, text });
  const render = (translated: ReturnType<typeof cue>[] | null) =>
    renderToStaticMarkup(
      <Result result={result} detected cues={[cue("hello")]} translated={translated} targetName="Thai" onNew={noop} onOpen={noop} onShow={noop} />,
    );

  it("has a tab for the translated lines only when the run translated", () => {
    expect(render(null)).not.toContain('role="tab"');
    const html = render([cue("สวัสดี")]);
    expect(html).toContain('role="tab"');
    expect(html).toContain(">Thai<");
    expect(html).toContain("hello");
  });
  it("lists every file written, the translated one and the video included", () => {
    const html = render([cue("x")]);
    for (const f of ["talk.srt", "talk.th.srt", "talk.th.subbed.mp4"]) expect(html).toContain(f);
  });
});
