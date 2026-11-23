import { FileText, FolderOpen, Plus } from "lucide-react";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import type { EngineEvent } from "../lib/engine";
import { stamp, type Cue } from "../lib/subtitles";
import { languageName, splitPath } from "../lib/utils";

type Done = Extract<EngineEvent, { event: "done" }>;

export function Result(props: {
  result: Done;
  detected: boolean;
  cues: Cue[];
  onNew: () => void;
  onOpen: (path: string) => void;
  onShow: (path: string) => void;
}) {
  const { result } = props;
  const n = result.segments ?? props.cues.length;
  const summary = [
    `${n} subtitle${n === 1 ? "" : "s"}`,
    result.lang && `${languageName(result.lang)}${props.detected ? " (detected)" : ""}`,
    result.seconds !== undefined && `took ${Math.round(result.seconds)} s`,
  ].filter(Boolean).join(" · ");
  const first = result.files[0];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h2>Done</h2>
          <p className="text-[12.5px] text-muted-foreground">{summary}</p>
        </div>
        <Button variant="outline" size="sm" onClick={props.onNew}>
          <Plus aria-hidden />
          New file
        </Button>
      </div>

      <div className="grid grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] items-start gap-4">
        <Card>
          <div className="px-[18px] pt-4 pb-2.5">
            <h3>Subtitles</h3>
          </div>
          <div className="max-h-[430px] overflow-y-auto">
            {props.cues.length === 0 && (
              <p className="border-t border-border px-3.5 py-2.5 text-[12.5px] text-muted-foreground">No lines to show.</p>
            )}
            {props.cues.map((c, i) => (
              <div key={i} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2.5 gap-y-1 border-t border-border px-3.5 py-2.5">
                <span className="grid size-[22px] place-items-center rounded-[5px] bg-secondary text-[11px]">{i + 1}</span>
                <div className="flex flex-col gap-0.5">
                  {c.start !== null && c.end !== null && (
                    <span className="font-mono text-[12px] text-muted-foreground">
                      {stamp(c.start)} <span aria-hidden>&rarr;</span> {stamp(c.end)}
                    </span>
                  )}
                  <span className="whitespace-pre-line leading-[1.4]">{c.text}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="flex flex-col gap-2 px-[18px] py-4">
          <h3>Files written</h3>
          <ul className="m-0 list-none p-0">
            {result.files.map((f) => (
              <li key={f} className="flex items-center gap-2.5 border-t border-border py-2 first:border-t-0">
                <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]" title={f}>{splitPath(f).name}</span>
                <Button variant="ghost" size="sm" onClick={() => props.onOpen(f)}>
                  Open
                </Button>
              </li>
            ))}
          </ul>
          {first && (
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2">
              <span className="min-w-0 flex-1 truncate text-[11.5px] text-muted-foreground" title={splitPath(first).folder}>
                in {splitPath(first).folder}
              </span>
              <Button variant="ghost" size="sm" onClick={() => props.onShow(first)}>
                <FolderOpen aria-hidden />
                Show in folder
              </Button>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
