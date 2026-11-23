// Light or dark: follows Windows until the toggle is used, then remembers the choice.
export type Theme = "light" | "dark";
const KEY = "bs-theme";

export function savedTheme(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

export function systemDark(): boolean {
  return typeof matchMedia !== "undefined" && matchMedia("(prefers-color-scheme: dark)").matches;
}

export function applyTheme(theme: Theme | null): void {
  const root = document.documentElement;
  if (theme) root.setAttribute("data-theme", theme);
  else root.removeAttribute("data-theme");
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* not kept: the next start follows Windows again */
  }
}

/** ?theme=dark|light in a plain browser, for screenshots of both looks. */
export function themeFromUrl(): Theme | null {
  const v = new URLSearchParams(location.search).get("theme");
  return v === "light" || v === "dark" ? v : null;
}
