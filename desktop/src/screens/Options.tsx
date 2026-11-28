import { ChevronLeft, Clock, Info, Music, Play, RefreshCw, TriangleAlert, Video } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Switch } from "../components/ui/switch";
import { BURN_COLOURS, llmChoices, type Llm } from "../lib/ai";
import { burning, commandLine, FORMATS, memoryNote, STYLES, type Fit, type Options as Opts, type Style } from "../lib/engine";
import { cn, formatSize, isAudio, splitPath } from "../lib/utils";

export const LANGUAGES: [string, string][] = [
  ["auto", "Auto detect"],
  ["en", "English (en)"],
  ["th", "Thai (th)"],
  ["hi", "Hindi (hi)"],
  ["ja", "Japanese (ja)"],
  ["es", "Spanish (es)"],
  ["zh", "Chinese (zh)"],
  ["fr", "French (fr)"],
  ["de", "German (de)"],
];

/** Languages the subtitles can be translated into (codes the engine knows). */
export const TARGETS: [string, string][] = [
  ["th", "Thai (th)"],
  ["en", "English (en)"],
  ["ja", "Japanese (ja)"],
  ["es", "Spanish (es)"],
  ["hi", "Hindi (hi)"],
  ["zh", "Chinese, Simplified (zh)"],
  ["vi", "Vietnamese (vi)"],
  ["id", "Indonesian (id)"],
  ["fr", "French (fr)"],
];

function accurateNote(lang: string): string {
  if (lang === "th") return "Thai model for the text. Slower.";
  if (lang === "hi") return "Hindi model for the text. Slower.";
  return "About 2x slower.";
}

const OUTLINE = `0 0 2px ${BURN_COLOURS.outline}, 0 0 2px ${BURN_COLOURS.outline}, 0 1px 3px ${BURN_COLOURS.outline}`;

/** A small frame with the caption drawn the way `--style` draws it: the same colours as the burned video. */
function StyleThumb({ style }: { style: Style }) {
  const cap = { color: BURN_COLOURS.white, textShadow: OUTLINE };
  const lit = (text: string, colour: string): ReactNode => <span style={{ color: colour }}>{text}</span>;
  if (style === "shorts") {
    return (
      <div className="flex aspect-video justify-center overflow-hidden rounded-md bg-[#0a0a0a]">
        <div className="relative aspect-[9/16] h-full bg-gradient-to-b from-[#1c1c20] to-[#0b0b0c]">
          <div className="absolute inset-x-[6%] bottom-[30%] text-center text-[clamp(10px,1.6vw,15px)] leading-tight font-black" style={cap}>
            {lit("Ask", BURN_COLOURS.shorts)} not
            <br />
            what
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="relative flex aspect-video justify-center overflow-hidden rounded-md bg-gradient-to-br from-[#1c1c20] to-[#0b0b0c]">
      <div className="absolute inset-x-[6%] bottom-[8%] text-center text-[clamp(8px,1.1vw,11px)] leading-tight font-semibold" style={cap}>
        {style === "karaoke" ? lit("Ask not what", BURN_COLOURS.karaoke) : "Ask not what"} your country
        <br />
        can do for you
      </div>
    </div>
  );
}

const STYLE_NAMES: Record<Style, string> = { plain: "Plain", karaoke: "Karaoke", shorts: "Shorts" };

function Row(props: { title: string; note?: ReactNode; control?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 px-[22px] py-5">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h3>{props.title}</h3>
          {props.note && <p className="mt-0.5 text-[12.5px] text-muted-foreground">{props.note}</p>}
        </div>
        {props.control}
      </div>
      {props.children}
    </div>
  );
}

function Callout(props: { icon: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-border bg-muted/50 px-2.5 py-2 text-[12.5px] text-muted-foreground">
      <span className="mt-0.5 shrink-0 [&_svg]:size-4">{props.icon}</span>
      <span>{props.children}</span>
    </div>
  );
}

export function Options(props: {
  path: string;
  size: number | null;
  fit: Fit | null;
  llms: Llm[] | null; // null: still looking
  scanning: boolean;
  onRescan: () => void;
  opts: Opts;
  setOpts: (o: Opts) => void;
  onChangeFile: () => void;
  onStart: () => void;
}) {
  const { opts, setOpts } = props;
  const { name, folder } = splitPath(props.path);
  const audio = isAudio(props.path);
  const Icon = audio ? Music : Video;
  const memory = memoryNote(props.fit, opts);
  const choices = llmChoices(props.llms);
  const picked = choices.find((c) => c.url === opts.llm && c.model === opts.llmModel)?.value ?? "";
  const drawing = burning(props.path, opts);
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex items-center justify-between gap-2 px-[18px] py-4">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <div className="min-w-0 flex-1">
              <b className="block truncate font-semibold">{name}</b>
              <span className="block truncate text-[11.5px] text-muted-foreground">
                {folder}
                {props.size !== null && ` · ${formatSize(props.size)}`}
              </span>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={props.onChangeFile}>
            Change file
          </Button>
        </div>
      </Card>

      {memory && (
        <div role="status">
          <Callout icon={<Info aria-hidden />}>{memory}</Callout>
        </div>
      )}

      <Card className="divide-y divide-border">
        <div className="flex items-center justify-between gap-4 px-[22px] py-5">
          <h3>Spoken language</h3>
          <select
            className="select"
            aria-label="Spoken language"
            value={opts.lang}
            onChange={(e) => setOpts({ ...opts, lang: e.target.value })}
          >
            {LANGUAGES.map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
        </div>

        <Row
          title="Accurate mode"
          note="Slower, fewer errors. Best for Thai and Hindi."
          control={<Switch aria-label="Accurate mode" checked={opts.accurate} onCheckedChange={(v) => setOpts({ ...opts, accurate: v })} />}
        >
          {opts.accurate && <Callout icon={<Clock aria-hidden />}>{accurateNote(opts.lang)}</Callout>}
        </Row>

        <Row
          title="Translate the subtitles"
          note="With a model on this computer."
          control={<Switch aria-label="Translate the subtitles" checked={opts.translate} onCheckedChange={(v) => setOpts({ ...opts, translate: v, burnTranslated: v ? opts.burnTranslated : false })} />}
        >
          {opts.translate && (
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <label className="w-[84px] text-[12.5px] text-muted-foreground" htmlFor="target">
                  Into
                </label>
                <select id="target" className="select" value={opts.target} onChange={(e) => setOpts({ ...opts, target: e.target.value })}>
                  {TARGETS.map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="w-[84px] text-[12.5px] text-muted-foreground" htmlFor="llm">
                  Local model
                </label>
                <select
                  id="llm"
                  className="select min-w-0 max-w-[340px] flex-1"
                  value={picked}
                  disabled={props.llms === null}
                  onChange={(e) => {
                    const c = choices.find((x) => x.value === e.target.value);
                    setOpts({ ...opts, llm: c?.url ?? "", llmModel: c?.model ?? "" });
                  }}
                >
                  <option value="">{props.llms === null ? "Looking..." : "Automatic (the first one that answers)"}</option>
                  {choices.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
                <Button variant="ghost" size="sm" disabled={props.scanning} onClick={props.onRescan}>
                  <RefreshCw className={cn(props.scanning && "animate-spin")} aria-hidden />
                  Check again
                </Button>
              </div>
              {props.llms !== null && choices.length === 0 && (
                <Callout icon={<TriangleAlert aria-hidden />}>
                  No model is running on this computer. Start Ollama, LM Studio or llama-server, then press Check again. Making subtitles
                  will stop at the start and say so if none answers.
                </Callout>
              )}
            </div>
          )}
        </Row>

        <Row
          title="Burn subtitles into the video"
          note={audio ? "Needs a video file." : "Saves a copy with captions on it."}
          control={
            <Switch aria-label="Burn subtitles into the video" disabled={audio} checked={drawing} onCheckedChange={(v) => setOpts({ ...opts, burn: v })} />
          }
        >
          {drawing && (
            <div className="flex flex-col gap-3">
              <div role="radiogroup" aria-label="Caption style" className="grid grid-cols-3 gap-2.5">
                {STYLES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    role="radio"
                    aria-checked={opts.style === s}
                    onClick={() => setOpts({ ...opts, style: s })}
                    className={cn(
                      "flex flex-col gap-2 rounded-lg border border-input bg-background p-2 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                      opts.style === s && "border-foreground",
                    )}
                  >
                    <StyleThumb style={s} />
                    <b className="text-[12.5px] font-semibold">{STYLE_NAMES[s]}</b>
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="w-[84px] text-[12.5px] text-muted-foreground" htmlFor="draw">
                  Draw
                </label>
                <select
                  id="draw"
                  className="select"
                  disabled={!opts.translate}
                  value={opts.translate && opts.burnTranslated ? "tr" : "orig"}
                  onChange={(e) => setOpts({ ...opts, burnTranslated: e.target.value === "tr" })}
                >
                  <option value="orig">Original subtitles</option>
                  <option value="tr">Translated subtitles</option>
                </select>
              </div>
            </div>
          )}
        </Row>

        <div className="flex flex-col gap-2 px-[22px] py-5">
          <h3>Subtitle files</h3>
          <div className="flex flex-wrap items-center gap-2">
            {FORMATS.map((f) => (
              <label
                key={f}
                className="inline-flex cursor-pointer select-none items-center gap-2 rounded-md border border-input px-2.5 py-1.5 has-[:checked]:border-foreground/70 has-[:checked]:bg-accent has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring"
              >
                <input
                  type="checkbox"
                  className="m-0 size-[15px] accent-foreground"
                  checked={opts.formats[f]}
                  onChange={(e) => setOpts({ ...opts, formats: { ...opts.formats, [f]: e.target.checked } })}
                />
                <span className="font-mono text-[12.5px]">.{f}</span>
              </label>
            ))}
          </div>
          {(drawing || opts.translate) && (
            <p className="text-[11.5px] text-muted-foreground">
              A <span className="font-mono">.json</span> with word timings is kept too: burning and translating are made from it.
            </p>
          )}
        </div>
      </Card>

      <Card>
        <details>
          <summary className="cursor-pointer list-none px-[18px] py-4 [&::-webkit-details-marker]:hidden">
            <div className="flex items-center justify-between">
              <b className="font-semibold">Advanced</b>
              <span className="text-[11.5px] text-muted-foreground">vocabulary, command line</span>
            </div>
          </summary>
          <div className="flex flex-col gap-3 px-[18px] pb-4">
            <label className="flex flex-col gap-1.5">
              <span className="text-[12.5px]">
                Names and terms to spell correctly <span className="text-muted-foreground">(optional)</span>
              </span>
              <input
                className="input"
                placeholder="e.g. Kennedy, Eisenhower"
                value={opts.prompt}
                onChange={(e) => setOpts({ ...opts, prompt: e.target.value })}
              />
            </label>
            <div className="flex flex-col gap-1.5">
              <span className="text-[12.5px]">The same run on the command line</span>
              <pre className="m-0 whitespace-pre-wrap break-words rounded-md border border-border bg-muted px-3 py-2.5 font-mono text-[12px] leading-normal [overflow-wrap:anywhere]">
                {commandLine(props.path, opts)}
              </pre>
            </div>
          </div>
        </details>
      </Card>

      <div className="flex items-center justify-between gap-2">
        <Button variant="ghost" onClick={props.onChangeFile}>
          <ChevronLeft aria-hidden />
          Back
        </Button>
        <Button variant="primary" onClick={props.onStart}>
          <Play aria-hidden />
          Make subtitles
        </Button>
      </div>
    </div>
  );
}
