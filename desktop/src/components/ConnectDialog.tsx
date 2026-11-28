// "Connect to an AI app": put babelscribe into Claude Desktop, Claude Code, Codex CLI, Cursor, Gemini CLI or OpenCode, show
// exactly what was added, and take it out again. Every file and command is handled by the engine (`babelscribe connect`); this is the
// window for it.
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Check, Copy, Info, LoaderCircle, Plug, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  engineCall, parseOutcome, parsePlan, parseRows, stateLabel, TRY_ASKING, type AppRow, type Outcome, type Plan,
} from "../lib/ai";
import { backend } from "../lib/backend";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";

export function ConnectDialog(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  busy: boolean; // a transcription is running: the engine does one thing at a time
  onRows: (rows: AppRow[]) => void;
  toast: (title: string, text?: string, kind?: "ok" | "warn") => void;
}) {
  const { open, busy, onRows, toast } = props;
  const [rows, setRows] = useState<AppRow[] | null>(null);
  const [app, setApp] = useState<string | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [problem, setProblem] = useState<string | null>(null); // the engine could not answer, or refused
  const [working, setWorking] = useState(false);
  const [backup, setBackup] = useState(true);
  const [done, setDone] = useState<{ what: "added" | "removed"; outcome: Extract<Outcome, { ok: true }>; plan: Plan } | null>(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true; // again, not only at the start: React's development mode mounts, unmounts and mounts once more
    return () => void (alive.current = false);
  }, []);

  const loadRows = useCallback(async () => {
    const res = await engineCall(await backend(), ["connect", "status", "--json"]);
    const list = parseRows(res.out);
    if (!alive.current) return null;
    if (list) {
      setRows(list);
      onRows(list);
    } else setProblem("babelscribe could not look for AI apps. Nothing was changed.");
    return list;
  }, [onRows]);

  const loadPlan = useCallback(async (key: string) => {
    const res = await engineCall(await backend(), ["connect", "show", key, "--json"]);
    if (!alive.current) return;
    const p = parsePlan(res.out);
    setPlan(p);
    setProblem(p ? null : "babelscribe could not prepare this. Nothing was changed.");
  }, []);

  // opening the dialog: look at the apps, pick the first one that is on this computer
  useEffect(() => {
    if (!open || busy) return; // while a run has the engine there is nothing to ask it; the banner says so
    setDone(null);
    setProblem(null);
    setPlan(null);
    loadRows().then((list) => {
      if (!list || !alive.current) return;
      setApp((cur) => cur ?? (list.find((r) => r.installed) ?? list[0])?.app ?? null);
    });
  }, [open, busy, loadRows]);

  useEffect(() => {
    if (open && app && !busy) {
      setPlan(null);
      loadPlan(app);
    }
  }, [open, busy, app, loadPlan]);

  const act = async (what: "add" | "remove") => {
    if (!app || !plan || working || busy) return;
    setWorking(true);
    setProblem(null);
    const res = parseOutcome(
      await engineCall(await backend(), ["connect", what, app, "--json", ...(backup ? [] : ["--no-backup"])], 120000),
    );
    if (!alive.current) return;
    setWorking(false);
    if (!res.ok) {
      setProblem(res.error);
      return;
    }
    await loadRows();
    setDone({ what: what === "add" ? "added" : "removed", outcome: res, plan });
    toast(what === "add" ? `${plan.name} connected` : "Removed", res.message, "ok");
  };

  const copy = async () => {
    if (!plan) return;
    try {
      await navigator.clipboard.writeText(plan.text);
      toast("Copied", plan.kind === "command" ? "Paste it into a terminal." : "Add it to the file above yourself.");
    } catch {
      toast("Could not copy", "Select the text and copy it by hand.", "warn");
    }
  };

  const current = rows?.find((r) => r.app === app);
  const connected = current?.state === "connected";
  const present = connected || current?.state === "other";            // there is a babelscribe entry to take out
  const blocked = busy || working || !plan || !!plan.problem;
  // taking babelscribe out can work when connecting cannot (an old OpenCode, or one that is not installed any more)
  const cannotRemove = busy || working || !plan || !plan.can_remove;

  return (
    <DialogPrimitive.Root open={open} onOpenChange={props.onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px] animate-fade" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100vh-32px)] w-[calc(100%-32px)] max-w-[600px] -translate-x-1/2 -translate-y-1/2 flex-col gap-3.5 overflow-y-auto rounded-lg border border-border bg-background p-6 shadow-[0_24px_60px_-24px_hsl(var(--shadow)/.5)]"
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <DialogPrimitive.Title asChild>
                <h2>Connect to an AI app</h2>
              </DialogPrimitive.Title>
              <p className="mt-1 text-[12.5px] text-muted-foreground">Then ask it for subtitles in plain words.</p>
            </div>
            <DialogPrimitive.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Close">
                <X aria-hidden />
              </Button>
            </DialogPrimitive.Close>
          </div>

          {busy && (
            <div role="status" className="flex items-start gap-2 rounded-md border border-border bg-muted/50 px-2.5 py-2 text-[12.5px] text-muted-foreground">
              <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>A run is in progress. Connect an app when it has finished.</span>
            </div>
          )}

          {done ? (
            <div className="flex flex-col items-center gap-2 py-2.5 text-center">
              <Check className="size-[22px]" aria-hidden />
              <h2>{done.what === "added" ? `${done.plan.name} is connected` : `Removed from ${done.plan.name}`}</h2>
              <p className="text-[12.5px] text-muted-foreground">{done.what === "added" && done.outcome.changed ? done.plan.after : done.outcome.message}</p>
              {done.what === "added" && (
                <>
                  {done.outcome.changed && (
                    <div className="w-full text-left">
                      <p className="mb-1 text-[12.5px]">
                        {done.plan.kind === "command" ? "The command that was run" : "What was added"}
                        {done.outcome.path ? <>{done.plan.kind === "command" ? ", which changed " : " to "}<span className="font-mono [overflow-wrap:anywhere]">{done.outcome.path}</span></> : ""}:
                      </p>
                      <pre className="m-0 whitespace-pre-wrap break-words rounded-md border border-border bg-muted px-3 py-2.5 font-mono text-[12px] leading-normal [overflow-wrap:anywhere]">{done.plan.text}</pre>
                      {done.outcome.backup && (
                        <p className="mt-1 text-[11.5px] text-muted-foreground">
                          The old file was kept as <span className="font-mono [overflow-wrap:anywhere]">{done.outcome.backup}</span>.
                        </p>
                      )}
                    </div>
                  )}
                  <p className="text-[12.5px] text-muted-foreground">Try asking:</p>
                  <pre className="m-0 w-full whitespace-pre-wrap break-words rounded-md border border-border bg-muted px-3 py-2.5 text-left font-mono text-[12px]">{TRY_ASKING}</pre>
                </>
              )}
              <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
                {done.what === "added" && (
                  <Button variant="outline" size="sm" disabled={busy || working} onClick={() => void act("remove")}>
                    Remove again
                  </Button>
                )}
                <Button variant="outline" size="sm" onClick={() => setDone(null)}>
                  {done.what === "added" ? "Connect another app" : "Back"}
                </Button>
                <DialogPrimitive.Close asChild>
                  <Button variant="primary" size="sm">
                    Done
                  </Button>
                </DialogPrimitive.Close>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <div role="radiogroup" aria-label="AI app" className="grid grid-cols-3 gap-2 max-[760px]:grid-cols-1">
                {(rows ?? []).map((r) => (
                  <button
                    key={r.app}
                    type="button"
                    role="radio"
                    aria-checked={r.app === app}
                    onClick={() => {
                      setApp(r.app);
                      setProblem(null);
                    }}
                    className={cn(
                      "flex flex-col gap-1 rounded-lg border border-input bg-background p-2.5 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                      r.app === app && "border-foreground",
                    )}
                  >
                    <b className="text-[12.5px] font-semibold">{r.name}</b>
                    <span className="text-[11.5px] text-muted-foreground">{stateLabel(r.state)}</span>
                  </button>
                ))}
                {rows === null && !problem && (
                  <span className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
                    <LoaderCircle className="size-4 animate-spin" aria-hidden />
                    Looking for AI apps...
                  </span>
                )}
              </div>

              {plan && (
                <div className="flex flex-col gap-1.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[12.5px]">
                      {plan.kind !== "command" ? "Adds babelscribe to this file:" : plan.path ? "Runs a command for you that changes this file:" : "Runs this command for you:"}{" "}
                      {plan.path && <span className="font-mono [overflow-wrap:anywhere]">{plan.path}</span>}
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-secondary px-2 py-px text-[11.5px] font-medium whitespace-nowrap">
                      {plan.installed ? (
                        <>
                          <Check className="size-3.5" aria-hidden /> {plan.name} found
                        </>
                      ) : (
                        `${plan.name} not found on this computer`
                      )}
                    </span>
                  </div>
                  <pre className="m-0 max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-muted px-3 py-2.5 font-mono text-[12px] leading-normal [overflow-wrap:anywhere]">{plan.text}</pre>
                  <p className="text-[11.5px] text-muted-foreground">{plan.extra}</p>
                  {plan.state === "other" && (
                    <p className="text-[11.5px] text-muted-foreground">babelscribe is already in this app another way; Connect replaces only that entry.</p>
                  )}
                </div>
              )}

              {(plan?.problem || problem) && (
                <div role="alert" className="flex items-start gap-2 rounded-md border border-border bg-muted/50 px-2.5 py-2 text-[12.5px]">
                  <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
                  <span className="[overflow-wrap:anywhere]">{problem ?? plan?.problem}</span>
                </div>
              )}

              {plan?.backup && !plan.problem && (
                <label className="flex cursor-pointer items-center gap-2 text-[12.5px]">
                  <input type="checkbox" className="accent-gold" checked={backup} onChange={(e) => setBackup(e.target.checked)} />
                  <span>
                    Keep a copy of the old file first (<span className="font-mono">{plan.backup.split(/[\\/]/).pop()}</span>)
                  </span>
                </label>
              )}

              <div className="flex flex-wrap items-center justify-between gap-2">
                <Button variant="ghost" size="sm" disabled={!plan} onClick={() => void copy()}>
                  <Copy aria-hidden />
                  Copy instead, I&apos;ll add it myself
                </Button>
                <div className="flex items-center gap-2">
                  {present && (
                    <Button variant="outline" size="sm" disabled={cannotRemove} onClick={() => void act("remove")}>
                      Remove
                    </Button>
                  )}
                  <Button variant="primary" disabled={blocked} onClick={() => void act("add")}>
                    {working ? <LoaderCircle className="animate-spin" aria-hidden /> : <Plug aria-hidden />}
                    {working ? "Connecting..." : connected ? "Connect again" : `Connect ${plan?.name ?? ""}`.trim()}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
