// The babelscribe mark: the same outline as src-tauri/icons/logo.svg (made by scripts/make_icons.py), drawn in the
// window's colours like the mockup's .logo: a foreground-coloured square with the "b" cut out in the background colour.
import { cn } from "../lib/utils";

const B =
  "M392 563Q463 563 520.5 528.0Q578 493 611.5 428.5Q645 364 645 279Q645 194 611.5 128.5Q578 63 520.5 27.0Q463 -9 392 -9Q330 -9 283.5 15.5Q237 40 209 79V0H69V740H209V473Q236 513 283.5 538.0Q331 563 392 563ZM355 440Q317 440 283.5 420.5Q250 401 229.5 364.0Q209 327 209 277Q209 227 229.5 190.0Q250 153 283.5 133.5Q317 114 355 114Q394 114 427.5 134.0Q461 154 481.5 191.0Q502 228 502 279Q502 329 481.5 365.5Q461 402 427.5 421.0Q394 440 355 440Z";

export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" aria-hidden className={cn("size-[18px] shrink-0", className)}>
      <rect width="1024" height="1024" rx="284.4" className="fill-foreground" />
      <path d={B} className="fill-background" transform="translate(288.60 740.72) scale(0.625778 -0.625778)" />
    </svg>
  );
}
