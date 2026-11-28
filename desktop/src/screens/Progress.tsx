import { Check, LoaderCircle, X } from "lucide-react";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { formatLeft, secondsLeft, type Options, type Run, type Stage } from "../lib/engine";
import { cn, languageName, splitPath } from "../lib/utils";

const NAMES: Record<Stage, string> = {
  prepare: "Get ready",
  transcribe: "Transcribe",
  translate: "Translate",
  burn: "Burn subtitles",
  save: "Save the files",
};

function Bar({ percent }: { percent: number }) {
  return (
    <div className="h-1 overflow-hidden rounded-full bg-secondary" role="progressbar" aria-valuenow={Math.floor(percent)} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full bg-gold" style={{ width: `${percent}%` }} />
    </div>
  );
}

export function Progress(props: {
  path: string;
  run: Run;
  formats: string[];
  opts: Options;
  now: number;
  onCancel: () => void;
  onBack: () => void;
}) {
  const { run } = props;
  const notes: Record<Stage, string> = {
    prepare: "Finds whisper-cli, the model and your GPU. The first run downloads them.",
    transcribe: "Speech to text, on this computer.",
    translate: `Into ${languageName(props.opts.target)}, with a model on this computer.`,
    burn: `${props.opts.style} captions on a copy of the video.`,
    save: props.formats.map((f) => `.${f}`).join(", ") + " next to the file.",
  };
  const finished = run.result !== null;
  const at = run.stages.indexOf(run.stage);
  const left = secondsLeft(run, props.now);

  if (run.error) {
    return (
      <div className="flex flex-col gap-4">
        <Card className="flex flex-col gap-3 px-[18px] py-4">
          <div>
            <h2>That did not work</h2>
            <p className="text-[12.5px] text-muted-foreground">{splitPath(props.path).name}</p>
          </div>
          <p className="text-[13.5px]">{run.error}</p>
          {run.log.length > 0 && (
            <details>
              <summary className="cursor-pointer text-[12.5px] text-muted-foreground">Details</summary>
              <pre className="mt-2 max-h-[220px] overflow-y-auto whitespace-pre-wrap rounded-md border border-border bg-muted px-2.5 py-2 font-mono text-[12px] [overflow-wrap:anywhere]">
                {run.log.slice(-60).join("\n")}
              </pre>
            </details>
          )}
        </Card>
        <div className="flex justify-end">
          <Button variant="outline" onClick={props.onBack}>
            Back to options
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-3 px-[18px] py-4">
        <div>
          <h2>Working on it</h2>
          <p className="text-[12.5px] text-muted-foreground">{splitPath(props.path).name}</p>
        </div>
        <div className="flex items-center justify-between">
          <b className="text-[36px] leading-none font-medium tabular-nums">{Math.floor(run.percent)}%</b>
          {left !== null && (
            <span className="text-[12.5px] text-muted-foreground">
              {formatLeft(left)} <span className="ml-0.5 whitespace-nowrap">est.</span>
            </span>
          )}
        </div>
        <Bar percent={run.percent} />
      </Card>

      <Card>
        <ul className="m-0 list-none p-0">
          {run.stages.map((s, i) => {
            const state = finished || i < at ? "done" : i === at ? "run" : "wait";
            return (
              <li key={s} className="flex items-center gap-3 border-t border-border px-[18px] py-3 first:border-t-0">
                <span
                  className={cn(
                    "grid size-7 shrink-0 place-items-center rounded-full border border-border text-muted-foreground",
                    state === "run" && "border-foreground text-foreground",
                    state === "done" && "border-transparent",
                  )}
                >
                  {state === "done" ? <Check className="size-4" /> : state === "run" ? <LoaderCircle className="size-4 animate-spin" /> : <span className="text-[11.5px]">{i + 1}</span>}
                </span>
                <div className="min-w-0 flex-1">
                  <b className="text-[12.5px] font-semibold">{NAMES[s]}</b>
                  <div className="truncate text-[11.5px] text-muted-foreground">
                    {state === "run" && run.activity ? run.activity : notes[s]}
                  </div>
                  {state === "run" && s !== "prepare" && s !== "save" && (
                    <div className="mt-1.5">
                      <Bar percent={run.stagePercent[s] ?? 0} />
                    </div>
                  )}
                </div>
                {state === "run" && s !== "prepare" && s !== "save" ? (
                  <span className="font-mono text-[12.5px] tabular-nums">{Math.floor(run.stagePercent[s] ?? 0)}%</span>
                ) : (
                  <span className="text-[11.5px] text-muted-foreground">{state === "done" ? "done" : state === "wait" ? "waiting" : ""}</span>
                )}
              </li>
            );
          })}
        </ul>
      </Card>

      <div className="flex justify-end">
        <Button variant="outline" onClick={props.onCancel}>
          <X aria-hidden />
          Cancel
        </Button>
      </div>
    </div>
  );
}
