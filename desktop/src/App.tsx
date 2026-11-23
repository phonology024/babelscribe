import { Check, Moon, Plug, ShieldCheck, Sun } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { Button } from "./components/ui/button";
import { ConnectDialog } from "./components/ConnectDialog";
import { ConfirmDialog, DialogClose } from "./components/ui/dialog";
import { Logo } from "./components/logo";
import { useToast } from "./components/toast";
import { backend, inApp } from "./lib/backend";
import { engineCall, parseLlms, stateLabel, whenIdle, type AppRow, type Llm } from "./lib/ai";
import { chosenFormats, DEFAULT_OPTIONS, engineArgs, exited, newRun, parseFit, stagesFor, step as stepRun, type Fit, type Options as Opts, type Run } from "./lib/engine";
import { addRecent, loadRecent, saveRecent, type Recent } from "./lib/recent";
import { parseFile, parseText, subtitleSource, translatedSource, type Cue } from "./lib/subtitles";
import { applyTheme, savedTheme, saveTheme, systemDark, themeFromUrl, type Theme } from "./lib/theme";
import { cn, languageName, splitPath } from "./lib/utils";
import { ChooseFile } from "./screens/ChooseFile";
import { Options } from "./screens/Options";
import { Progress } from "./screens/Progress";
import { Result } from "./screens/Result";

type Step = 1 | 2 | 3 | 4;
const TITLES: Record<Step, string> = { 1: "Choose a file", 2: "Options", 3: "Working", 4: "Result" };

export default function App() {
  const toast = useToast();
  const [step, setStep] = useState<Step>(1);
  const [reached, setReached] = useState<Step>(1);
  const [file, setFile] = useState<{ path: string; size: number | null } | null>(null);
  const [opts, setOpts] = useState<Opts>(DEFAULT_OPTIONS);
  const [run, setRun] = useState<Run | null>(null);
  const [fit, setFit] = useState<Fit | null>(null);
  const [llms, setLlms] = useState<Llm[] | null>(null); // local models that can translate; null while looking
  const [scanning, setScanning] = useState(false);
  const [connectOpen, setConnectOpen] = useState(false);
  const [apps, setApps] = useState<AppRow[] | null>(null);
  const [ranWith, setRanWith] = useState<Opts>(DEFAULT_OPTIONS); // the options of the run on screen
  const [translated, setTranslated] = useState<Cue[] | null>(null);
  const [running, setRunning] = useState(false);
  const [cues, setCues] = useState<Cue[]>([]);
  const [recent, setRecent] = useState<Recent[]>(() => loadRecent());
  const [dragOver, setDragOver] = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [theme, setTheme] = useState<Theme | null>(() => themeFromUrl() ?? savedTheme());
  const [osDark, setOsDark] = useState(systemDark());
  const runId = useRef(0);
  const finished = useRef(0);
  const stepRef = useRef(step);
  stepRef.current = step;
  const runningRef = useRef(running);
  runningRef.current = running;

  const dark = theme ? theme === "dark" : osDark;

  useEffect(() => {
    applyTheme(theme);
    backend().then((b) => b.setTheme(theme)).catch(() => {});
  }, [theme]);
  useEffect(() => {
    const m = matchMedia("(prefers-color-scheme: dark)");
    const on = () => setOsDark(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  useEffect(() => saveRecent(recent), [recent]);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);

  const go = useCallback((n: Step) => {
    setStep(n);
    document.getElementById("content")?.scrollTo(0, 0);
  }, []);

  const scan = useCallback(async () => {
    if (runningRef.current) return;
    setScanning(true);
    const r = await engineCall(await backend(), ["llms", "--json"], 15000);
    setLlms(parseLlms(r.out) ?? []);
    setScanning(false);
  }, []);

  const openFile = useCallback(async (path: string) => {
    if (runningRef.current) return;
    const b = await backend();
    let size: number | null = null;
    try {
      const info = await b.fileInfo(path);
      if (!info.exists) {
        toast("File not found", path, "warn");
        return;
      }
      if (!info.isFile) {
        toast("Choose a file, not a folder", splitPath(path).name, "warn");
        return;
      }
      size = info.size;
    } catch {
      /* size is shown only when known */
    }
    const known = loadRecent().find((r) => r.path.toLowerCase() === path.toLowerCase());
    setFile({ path, size });
    setOpts((o) => ({
      ...o,
      lang: known?.lang ?? "auto",
      accurate: known?.lang === "th" || known?.lang === "hi" ? true : o.accurate,
      target: known?.lang === "th" || known?.lang === "hi" ? "en" : "th", // translate into something other than what is spoken
    }));
    setRecent((l) => addRecent(l, { path, when: Date.now() }));
    // which models fit this computer's free memory, and which local models can translate: the engine decides, this
    // only asks (never blocks the screen; a run waits for the answers, a second or two at most)
    engineCall(b, ["models", "--json"], 8000).then((r) => setFit(parseFit(r.out.join("\n"))));
    scan();
    setReached(2);
    go(2);
  }, [go, toast, scan]);

  const pick = useCallback(async () => {
    try {
      const path = await (await backend()).pickFile();
      if (path) await openFile(path);
    } catch (e) {
      toast("Could not open the file picker", String(e), "warn");
    }
  }, [openFile, toast]);

  // files dropped on the window (the app gets their paths from Tauri, not from the HTML drop event)
  useEffect(() => {
    let stop: (() => void) | null = null;
    let gone = false;
    backend().then((b) => b.onDrop((e) => {
      if (stepRef.current !== 1 || runningRef.current) return setDragOver(false);
      if (e.type === "over") setDragOver(true);
      else if (e.type === "leave") setDragOver(false);
      else {
        setDragOver(false);
        if (e.paths[0]) openFile(e.paths[0]);
      }
    })).then((un) => (gone ? un() : (stop = un))).catch(() => {});
    return () => {
      gone = true;
      stop?.();
    };
  }, [openFile]);

  const start = useCallback(async () => {
    if (!file) return;
    if (chosenFormats(opts).length === 0) {
      toast("Pick at least one output", "A subtitle file: .srt, .vtt or .txt.", "warn");
      return;
    }
    const id = ++runId.current;
    setRanWith(opts);
    setTranslated(null);
    setRun(newRun(Date.now(), stagesFor(file.path, opts)));
    setCues([]);
    setRunning(true);
    setReached(3);
    go(3);
    try {
      await whenIdle(); // the questions asked while choosing options are a second or two; the engine runs one thing at a time
      if (id !== runId.current) return; // Stop was pressed while waiting
      await (await backend()).run(
        engineArgs(file.path, opts),
        (stream, line) => id === runId.current && setRun((r) => r && stepRun(r, stream, line, Date.now())),
        (code) => {
          if (id !== runId.current) return;
          setRun((r) => r && exited(r, code));
          setRunning(false);
        },
      );
    } catch (e) {
      setRun((r) => r && { ...r, error: `babelscribe could not be started: ${e}` });
      setRunning(false);
    }
  }, [file, opts, go, toast]);

  // a finished run: read the lines back, then show the result
  useEffect(() => {
    if (running || !run?.result || run.error || finished.current === runId.current || !file) return;
    finished.current = runId.current;
    const result = run.result;
    (async () => {
      const target = ranWith.translate ? ranWith.target : undefined;
      const source = subtitleSource(result.files, target);
      let lines: Cue[] = [];
      try {
        if (source) lines = parseFile(source, await (await backend()).readText(source));
      } catch {
        lines = parseText(result.text ?? "");
      }
      setCues(lines);
      const other = target ? translatedSource(result.files, target) : null;
      if (other) {
        try {
          setTranslated(parseFile(other, await (await backend()).readText(other)));
        } catch {
          setTranslated(null); // the translated file is listed under Files written; its lines just are not shown here
        }
      }
      setRecent((l) => addRecent(l, { path: file.path, when: Date.now(), lang: result.lang }));
      setReached(4);
      go(4);
      toast("Subtitles ready", splitPath(file.path).name, "ok");
    })();
  }, [running, run, file, ranWith, go, toast]);

  const stop = useCallback(async () => {
    setConfirmStop(false);
    runId.current++; // whatever the stopped run still prints is ignored
    await (await backend()).cancel().catch(() => {});
    setRunning(false);
    setRun(null);
    setReached(2);
    go(2);
    toast("Stopped", "Nothing half-done was kept. Your file was not changed.", "warn");
  }, [go, toast]);

  const openPath = async (path: string) => {
    try {
      await (await backend()).openPath(path);
    } catch (e) {
      toast("Could not open it", String(e), "warn");
    }
  };
  const showInFolder = async (path: string) => {
    try {
      await (await backend()).showInFolder(path);
    } catch (e) {
      toast("Could not show the folder", String(e), "warn");
    }
  };

  // a plain browser (npm run dev): ?demo=2|3|4 opens the sample file, starts a fake run, shows the result
  const demoed = useRef(false);
  useEffect(() => {
    if (inApp() || demoed.current) return;
    demoed.current = true;
    const demo = Number(new URLSearchParams(location.search).get("demo") ?? 0);
    if (!demo) return;
    import("./lib/mock").then(async ({ SAMPLE }) => {
      const day = 86400000;
      const t = Date.now();
      setRecent([
        { path: "C:\\Users\\you\\Videos\\apollo11_landing_1969.mp4", lang: "en", when: t - 5 * day },
        { path: "C:\\Users\\you\\Downloads\\fleurs_th_sample_0042.wav", lang: "th", when: t - day },
        { path: SAMPLE, lang: "en", when: t },
      ].reverse());
      if (demo >= 2) await openFile(SAMPLE);
    });
  }, [openFile]);
  useEffect(() => {
    if (inApp()) return;
    const demo = Number(new URLSearchParams(location.search).get("demo") ?? 0);
    if (demo >= 3 && file && reached === 2 && runId.current === 0) start();
  }, [file, reached, start]);

  const can = (k: Step) => (running ? k === 3 : k <= reached && k !== 3);
  const browserDrop = inApp() ? undefined : (e: DragEvent) => {
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) openFile(`C:\\Users\\you\\Downloads\\${f.name}`);
  };

  return (
    <div className="flex h-full">
      <aside className="flex w-[232px] shrink-0 flex-col gap-3.5 border-r border-border bg-background px-2.5 py-3.5">
        <div className="flex items-center gap-2 px-2 pt-0.5 text-[12.5px]">
          <Logo />
          <span>babelscribe</span>
        </div>
        <div className="px-2 text-[10.5px] font-medium tracking-[.16em] text-muted-foreground uppercase">Steps</div>
        <nav className="flex flex-col gap-0.5">
          {([1, 2, 3, 4] as Step[]).map((k) => {
            const on = k === step;
            const done = !on && k < reached;
            return (
              <button
                key={k}
                disabled={!can(k)}
                onClick={() => go(k)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-md border-0 bg-transparent px-2 py-[7px] text-left hover:enabled:bg-accent disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                  on && "bg-accent font-medium disabled:opacity-100",
                )}
              >
                <span
                  className={cn(
                    "grid size-[22px] shrink-0 place-items-center rounded-full border border-border bg-background text-[11.5px]",
                    done && "text-muted-foreground",
                    on && "border-foreground bg-foreground text-background",
                  )}
                >
                  {done ? <Check className="size-3.5" /> : k}
                </span>
                <span>{TITLES[k]}</span>
              </button>
            );
          })}
        </nav>
        <div className="mt-auto flex flex-col gap-2.5">
          <div className="flex flex-col gap-1.5 rounded-lg border border-border bg-card p-2.5">
            <div className="flex items-center gap-2">
              <ShieldCheck className="size-4 shrink-0" aria-hidden />
              <b className="text-[12.5px] font-semibold">Runs on this computer</b>
            </div>
            <p className="text-[11.5px] text-muted-foreground">Nothing is uploaded.</p>
          </div>
          {apps && apps.some((a) => a.state === "connected") && (
            <div className="flex flex-col gap-1">
              {apps.map((a) => (
                <div key={a.app} className="flex items-center gap-2 text-[12.5px]">
                  <span className={cn("size-1.5 shrink-0 rounded-full bg-gold", a.state !== "connected" && "bg-muted-foreground/50")} aria-hidden />
                  <span className="min-w-0 flex-1 truncate">{a.name}</span>
                  <span className="text-[11.5px] text-muted-foreground">{stateLabel(a.state)}</span>
                </div>
              ))}
            </div>
          )}
          <Button variant="outline" onClick={() => setConnectOpen(true)}>
            <Plug aria-hidden />
            Connect to an AI app
          </Button>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-border px-5">
          <b className="truncate font-semibold">
            {TITLES[step]}
            {file && step > 1 ? ` · ${splitPath(file.path).name}` : ""}
          </b>
          <Button variant="outline" size="sm" className="ml-auto" onClick={() => setConnectOpen(true)}>
            <Plug aria-hidden />
            <span>
              Connect<span className="max-[760px]:hidden"> to AI app</span>
            </span>
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Toggle light or dark theme"
            title="Toggle theme"
            onClick={() => {
              const next: Theme = dark ? "light" : "dark";
              saveTheme(next);
              setTheme(next);
            }}
          >
            {dark ? <Sun aria-hidden /> : <Moon aria-hidden />}
          </Button>
        </div>

        <div id="content" className="flex-1 overflow-x-hidden overflow-y-auto p-7">
          <section key={step} className="mx-auto max-w-[860px] animate-fade">
            {step === 1 && (
              <ChooseFile
                recent={recent}
                dragOver={dragOver}
                onPick={pick}
                onOpen={openFile}
                onClear={() => {
                  setRecent([]);
                  toast("Recent list cleared");
                }}
                onBrowserDrop={browserDrop}
                onBrowserDrag={inApp() ? undefined : setDragOver}
              />
            )}
            {step === 2 && file && (
              <Options path={file.path} size={file.size} fit={fit} llms={llms} scanning={scanning} onRescan={scan} opts={opts} setOpts={setOpts} onChangeFile={() => go(1)} onStart={start} />
            )}
            {step === 3 && file && run && (
              <Progress
                path={file.path}
                run={run}
                formats={chosenFormats(ranWith)}
                opts={ranWith}
                now={now}
                onCancel={() => setConfirmStop(true)}
                onBack={() => {
                  setReached(2);
                  go(2);
                }}
              />
            )}
            {step === 4 && file && run?.result && (
              <Result
                result={run.result}
                detected={ranWith.lang === "auto"}
                cues={cues}
                translated={translated}
                targetName={languageName(ranWith.target)}
                onNew={() => {
                  setReached(2);
                  go(1);
                }}
                onOpen={openPath}
                onShow={showInFolder}
              />
            )}
          </section>
        </div>
      </main>

      <ConnectDialog open={connectOpen} onOpenChange={setConnectOpen} busy={running} onRows={setApps} toast={toast} />

      <ConfirmDialog
        open={confirmStop}
        onOpenChange={setConfirmStop}
        title="Stop this run?"
        description="Files that are already finished stay on disk. The half-done step is thrown away. The video itself is never changed."
      >
        <DialogClose asChild>
          <Button variant="outline">Keep going</Button>
        </DialogClose>
        <Button variant="destructive" onClick={stop}>
          Stop
        </Button>
      </ConfirmDialog>
    </div>
  );
}
