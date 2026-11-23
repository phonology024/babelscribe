// Small toasts in the corner, like the mockup's (sonner-like look, written here).
import { AlertTriangle, Check, Info } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Kind = "ok" | "warn" | "info";
interface Toast { id: number; title: string; text?: string; kind: Kind }

const Ctx = createContext<(title: string, text?: string, kind?: Kind) => void>(() => {});
export const useToast = () => useContext(Ctx);

let next = 1;

export function Toasts({ children }: { children: ReactNode }) {
  const [list, setList] = useState<Toast[]>([]);
  const toast = useCallback((title: string, text?: string, kind: Kind = "info") => {
    const id = next++;
    setList((l) => [...l, { id, title, text, kind }]);
    setTimeout(() => setList((l) => l.filter((t) => t.id !== id)), 3600);
  }, []);
  return (
    <Ctx.Provider value={toast}>
      {children}
      <div className="fixed right-4 bottom-4 z-60 flex w-[min(360px,calc(100vw-32px))] flex-col gap-2" aria-live="polite">
        {list.map((t) => (
          <div key={t.id} className="flex animate-toast items-start gap-2.5 rounded-lg border border-border bg-popover px-3.5 py-3 shadow-[0_12px_32px_-16px_hsl(var(--shadow)/.4)]">
            <span className={t.kind === "warn" ? "mt-px text-destructive" : "mt-px text-foreground"}>
              {t.kind === "ok" ? <Check className="size-4" /> : t.kind === "warn" ? <AlertTriangle className="size-4" /> : <Info className="size-4" />}
            </span>
            <div>
              <b className="block text-[13px] font-semibold">{t.title}</b>
              {t.text && <span className="text-[12.5px] text-muted-foreground">{t.text}</span>}
            </div>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
