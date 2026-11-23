import { Folder, Music, Upload, Video } from "lucide-react";
import type { DragEvent } from "react";
import { Badge, Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import type { Recent } from "../lib/recent";
import { whenLabel } from "../lib/recent";
import { cn, isAudio, languageName, splitPath } from "../lib/utils";

export function ChooseFile(props: {
  recent: Recent[];
  dragOver: boolean;
  onPick: () => void;
  onOpen: (path: string) => void;
  onClear: () => void;
  onBrowserDrop?: (e: DragEvent) => void; // only in a plain browser; the app gets drops from Tauri
  onBrowserDrag?: (over: boolean) => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <h1>Make subtitles</h1>
      <div
        tabIndex={0}
        aria-label="Drop a file here or choose one"
        className={cn(
          "flex flex-col items-center gap-2.5 rounded-lg border border-dashed border-input bg-card px-5 py-14 text-center transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
          props.dragOver && "border-solid border-foreground bg-accent",
        )}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            props.onPick();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          props.onBrowserDrag?.(true);
        }}
        onDragLeave={() => props.onBrowserDrag?.(false)}
        onDrop={(e) => {
          e.preventDefault();
          props.onBrowserDrop?.(e);
        }}
      >
        <Upload className="size-6 text-muted-foreground" aria-hidden />
        <h2>Drop a video or audio file here</h2>
        <p className="text-[12.5px] text-muted-foreground">Video or audio. Subtitles are saved next to it.</p>
        <div className="mt-1.5 flex justify-center">
          <Button variant="primary" onClick={props.onPick}>
            <Folder aria-hidden />
            Choose file
          </Button>
        </div>
      </div>

      <Card>
        <div className="flex items-center justify-between px-[18px] pt-4 pb-3">
          <h3>Recent</h3>
          {props.recent.length > 0 && (
            <Button variant="ghost" size="sm" onClick={props.onClear}>
              Clear
            </Button>
          )}
        </div>
        <ul className="m-0 list-none p-0">
          {props.recent.length === 0 && (
            <li className="border-t border-border px-[18px] py-2.5 text-[12.5px] text-muted-foreground">No recent files.</li>
          )}
          {props.recent.map((r) => {
            const { name, folder } = splitPath(r.path);
            const Icon = isAudio(r.path) ? Music : Video;
            return (
              <li
                key={r.path}
                tabIndex={0}
                className="flex cursor-pointer items-center gap-3 border-t border-border px-[18px] py-2.5 hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                onClick={() => props.onOpen(r.path)}
                onKeyDown={(e) => e.key === "Enter" && props.onOpen(r.path)}
              >
                <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{name}</div>
                  <div className="truncate text-[11.5px] text-muted-foreground">{folder}</div>
                </div>
                {r.lang && <Badge soft>{languageName(r.lang)}</Badge>}
                <span className="whitespace-nowrap text-[11.5px] text-muted-foreground">{whenLabel(r.when)}</span>
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}
