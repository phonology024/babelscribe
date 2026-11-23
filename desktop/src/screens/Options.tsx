import { ChevronLeft, Clock, Music, Play, Video } from "lucide-react";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Switch } from "../components/ui/switch";
import { commandLine, FORMATS, type Options as Opts } from "../lib/engine";
import { formatSize, isAudio, splitPath } from "../lib/utils";

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

function accurateNote(lang: string): string {
  if (lang === "th") return "Thai model for the text. Slower.";
  if (lang === "hi") return "Hindi model for the text. Slower.";
  return "About 2x slower.";
}

export function Options(props: {
  path: string;
  size: number | null;
  opts: Opts;
  setOpts: (o: Opts) => void;
  onChangeFile: () => void;
  onStart: () => void;
}) {
  const { opts, setOpts } = props;
  const { name, folder } = splitPath(props.path);
  const Icon = isAudio(props.path) ? Music : Video;
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

        <div className="flex flex-col gap-2 px-[22px] py-5">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0 flex-1">
              <h3>Accurate mode</h3>
              <p className="mt-0.5 text-[12.5px] text-muted-foreground">Slower, fewer errors. Best for Thai and Hindi.</p>
            </div>
            <Switch
              aria-label="Accurate mode"
              checked={opts.accurate}
              onCheckedChange={(v) => setOpts({ ...opts, accurate: v })}
            />
          </div>
          {opts.accurate && (
            <div className="flex items-start gap-2 rounded-md border border-border bg-muted/50 px-2.5 py-2 text-[12.5px] text-muted-foreground">
              <Clock className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>{accurateNote(opts.lang)}</span>
            </div>
          )}
        </div>

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
