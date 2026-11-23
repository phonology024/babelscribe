# babelscribe desktop: third-party software

The desktop app is MIT licensed, like the rest of babelscribe (see `LICENSE`). It is built from, and its installer
contains, the following software, each under its own licence.

| Component | Licence | Where |
|---|---|---|
| Tauri, its plugins (shell, dialog, opener) and their Rust dependencies | MIT / Apache-2.0 | https://tauri.app |
| React, React DOM | MIT | https://react.dev |
| Radix UI primitives (dialog, switch) | MIT | https://www.radix-ui.com |
| shadcn/ui: the button, card, badge, switch and dialog components are adapted from it | MIT | https://ui.shadcn.com |
| Tailwind CSS (build time; its generated CSS is in the app) | MIT | https://tailwindcss.com |
| lucide-react icons | ISC | https://lucide.dev |
| class-variance-authority | Apache-2.0 | https://github.com/joe-bell/cva |
| clsx | MIT | https://github.com/lukeed/clsx |
| tailwind-merge | MIT | https://github.com/dcastil/tailwind-merge |
| Poppins font (latin and latin-ext, weights 400/500/600, from the @fontsource/poppins package), bundled so the app needs no network | SIL Open Font License 1.1, `src/assets/fonts/OFL.txt` | https://github.com/itfoundry/Poppins |
| The babelscribe logo's "b": outlines of the Poppins SemiBold glyph (artwork made with the font) | SIL Open Font License 1.1 | as above |
| The installer script `src-tauri/installer/installer.nsi`, adapted from Tauri's NSIS template | MIT / Apache-2.0 | https://github.com/tauri-apps/tauri |
| Vite, TypeScript, Vitest (build and test tools only, not shipped) | MIT / Apache-2.0 | |

The engine, `babelscribe-engine.exe` and its `_internal` folder, is the standalone babelscribe build
(`packaging/standalone`); what it contains is listed in `packaging/standalone/THIRD-PARTY.txt`, which the installer
puts in its `licenses` folder together with this file, `LICENSE` and the Poppins licence.
