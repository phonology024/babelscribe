---
name: make-subtitles
description: Make subtitles or a transcript from an audio or video file on the user's computer. Use when the user asks to transcribe, caption or subtitle a video, recording, podcast, interview or voice note, wants an .srt/.vtt file, or asks what was said in a local media file.
---

Use the babelscribe tools; everything runs on the user's own computer and GPU.

1. **Find the file.** If the user gave a full path, use it. Otherwise call `find_media` (optionally with `name_contains`
   or `folder`) and confirm which file they mean when more than one fits.
2. **Pick the mode.**
   - Default: `transcribe` with `language` = the spoken language's ISO code if the user said it (e.g. `th`, `en`, `ja`),
     otherwise `auto`.
   - Set `accurate: true` when the user wants the fewest mistakes, for subtitles they will publish, or whenever the
     language is Thai or Hindi — it is several times slower but roughly halves errors for those two.
   - `formats` defaults to `srt,txt`; add `vtt` for web players or `json` for word timings.
3. **Tell the user what to expect** before a long run: the first use downloads the speech model (~1.6 GB) and can take
   a few minutes; after that, about 20x real time on a modern GPU (a 10-minute video in ~30 s), slower with `accurate`.
4. **Report back** the files written and the device used, and show a short excerpt — not the whole transcript.
5. **Offer the follow-ups this enables:** fix misspelled names or terms in the .srt (keep every timestamp line
   unchanged), translate the subtitles into another language as a new file, or summarise the content.

If the tools are missing, the user needs [uv](https://docs.astral.sh/uv/) installed (the plugin starts the server with
`uvx`). If `list_devices` shows only `cpu`, transcription still works, just slower.
