# Usage

Everything the command line, Python, Docker and the MCP server can do. Back to the [README](../README.md).

## How it works
babelscribe is a thin, friendly layer on top of [whisper.cpp](https://github.com/ggml-org/whisper.cpp). It exists because
getting fast Whisper on a non-NVIDIA card (e.g. an AMD Radeon on Windows) still means building whisper.cpp with the
Vulkan SDK yourself. babelscribe downloads a prebuilt `whisper-cli` for your system and handles the rest.

| Your hardware | Backend used | Prebuilt asset |
|---|---|---|
| AMD / NVIDIA / Intel GPU on Windows | Vulkan | `windows-x64-vulkan` |
| NVIDIA on Windows | Vulkan (same build) | `windows-x64-vulkan` |
| NVIDIA on Linux (alternative) | CUDA | `linux-x64-cuda` (`--flavor cuda`) |
| AMD / NVIDIA / Intel GPU on Linux | Vulkan | `linux-x64-vulkan` |
| Apple Silicon | Metal | `macos-arm64-metal` |
| No usable GPU | CPU | `*-cpu` (`--flavor cpu`; chosen by itself where the Vulkan library is missing) |

## Features
- **Any input** — mp4, mkv, mov, mp3, wav, m4a… (ffmpeg is bundled through `imageio-ffmpeg`).
- **Any language** — `-l auto` detects it; or pass `-l th`, `-l ja`, `-l es`…
- **Picks the right GPU** — prefers a discrete card over an integrated one; `babelscribe devices` lists them, `--device N` overrides.
- **Long files that don't loop** — runs whisper with `--max-context 0`, which stops the classic "same sentence repeated forever" hallucination on long recordings.
- **Hybrid mode for better spelling in your language** — community fine-tunes (e.g. Thai *Thonburian Whisper*) spell far better but often lose timestamps. `--text-model` takes the text from the fine-tune and the timing from `large-v3-turbo`, aligned character by character (works for languages without spaces), cut only at word boundaries, with the timing model filling any words the fine-tune skipped.
- **`--accurate`** — slower, fewest errors: large-v3 with beam search, or for Thai and Hindi the best community fine-tune (hybrid). Chosen per language from the [FLEURS benchmark](benchmarks.md#benchmark-16-languages-on-fleurs). The Thai and Hindi fine-tunes are converted on your computer once, which needs `pip install "babelscribe[finetune]"`. Without it (the desktop app and the Claude Desktop bundle cannot convert) and with no model converted earlier, `--accurate` uses large-v3, which is less accurate for those two, and says so. A model converted once is used by every babelscribe that shares the models folder.
- **Custom vocabulary** — `--prompt "Pitakpong, babelscribe"` gives whisper an initial prompt that biases the spelling of names and jargon. In the MCP `transcribe` tool the same thing is the `vocabulary` argument. While a prompt is set, `--max-context 0` is not passed (whisper.cpp ignores the prompt otherwise).
- **Translate to English** — `--translate` writes the transcript translated to English (whisper's translate task, any source language). It uses `large-v3` because turbo was not trained to translate, and cannot be combined with `--text-model`. In the MCP `transcribe` tool it is the `translate` argument.
- **Progress** — in a terminal the CLI draws a progress bar per file (`--no-progress` turns it off; it is never drawn into a pipe or a log). MCP clients get a notification every 5 seconds with the real percentage (`progress` of `total` 100 for one file; files done plus the fraction of the current one for a folder). From Python: `transcribe_file(..., progress=callback)`, called with 0 to 100. For a program that runs the command, `--progress-json` prints one JSON object per line on stdout instead (`progress`, `log`, then `done` with the files written, or `error`); everything else goes to stderr. `--exit-when-stdin-closes` is for a program that keeps babelscribe's standard input open (and never writes to it): when that program ends, however it ends, babelscribe stops whisper-cli and ffmpeg and exits. The desktop app uses it, so killing the app never leaves a transcription running on the GPU.
- **Outputs** — `srt`, `vtt`, `txt`, `json` (segments with token timings), `ass` (karaoke: each word highlights
  as it is spoken, from the token timings — for short-form video and players that read ASS).

## Command line
```bash
babelscribe talk.mp4 -f srt,vtt,txt,json          # all formats
babelscribe a.mp4 b.mp3 c.wav                      # several files in one run
babelscribe ./recordings                           # every audio/video file in a folder (-r: sub-folders too)
babelscribe ./recordings -o ./subs --skip-existing # write into a folder; leave files that are already done
babelscribe reel.mp4 -f ass                        # karaoke subtitles, one highlight per word
babelscribe podcast.mp3 -l en -m large-v3          # pick language and model
babelscribe talk.mp4 -l hi --accurate              # slower, fewest errors (best model per language)
babelscribe vo.wav -l th --text-model thai-thonburian   # hybrid: pick a Thai fine-tune yourself
babelscribe talk.mp4 --prompt "Pitakpong, babelscribe"   # bias the spelling of names and terms
babelscribe talk.mp4 --translate                   # subtitles translated to English
babelscribe talk.mp4 --translate-to th             # also talk.th.srt: any language, through your local LLM
babelscribe convert talk.json -f srt,ass --max-line-chars 20   # re-wrap / re-export, no transcription
babelscribe clip.mp4 --burn --style shorts         # also clip.subbed.mp4: the video with the captions drawn on
babelscribe devices                                # GPUs whisper.cpp can see
babelscribe models                                 # models and fine-tunes
babelscribe talk.mp4 --bin /path/to/whisper-cli    # use your own whisper.cpp build
```
With several files or a folder, a file that fails does not stop the rest: the run ends with a summary line
(`12 done, 0 skipped, 1 failed`) and a non-zero exit code if anything failed. `-o` is then an output folder, and
two files that would share a subtitle name (`talk.mp4` and `talk.mp3`) keep their full name.

**Fix and re-export.** Transcribing is the slow part; how the subtitles look is the part you redo. Keep the JSON
and the rest takes no time:
```bash
babelscribe talk.mp4 -f json,srt                 # once
# correct names or words in the "text" fields of talk.json, then:
babelscribe convert talk.json -f srt,vtt,ass     # every format gets the corrected text, with its timing
```
`convert` also takes `--max-line-chars`, `--max-lines 1`, and three reading-speed rules that are off unless asked
for: `--max-duration 7` (cut subtitles that stay up longer), `--min-duration 1` and `--max-cps 17` (keep short or
fast subtitles up longer, never into the next one). In MCP it is the `convert_subtitles` tool, which is why the
MCP tools now write a `.json` by default.

**Translate into any language, with your own LLM.** `--translate` is whisper's own translator and only writes
English. For any other direction (English to Thai, Japanese to Spanish, ...) babelscribe can hand the finished
subtitles to an LLM running on your computer: Ollama, LM Studio, llama-server, colibri, or anything else with an
OpenAI-compatible API. babelscribe downloads no model for this; it uses the one you already run.
```bash
babelscribe talk.mp4 --translate-to th                      # talk.srt as usual, plus talk.th.srt
babelscribe translate talk.json --to ja -f srt,vtt          # later, from the saved JSON (or from any .srt / .vtt)
babelscribe talk.mp4 --translate-to es --llm http://127.0.0.1:11434/v1 --llm-model gemma3
```
Only the text is translated: every sentence keeps its own start and end time, and the lines are wrapped again by
the rules of the target language (shorter lines for Thai, Japanese and Chinese). The original files are not
changed. Without `--llm`, the usual local ports are tried (llama-server 8080, localllm 9931, Ollama 11434, LM Studio
1234, colibri 8000; on 8000, a port many programs use, only one that lists a model counts), or set `BABELSCRIBE_LLM`. If nothing answers, babelscribe says so before it starts transcribing. The endpoint must
be on this computer; `--allow-remote` is the explicit switch for sending the text to another machine.

Measured: a 3 min 18 s English recording into Thai with Gemma (26B, Q4) in llama-server on a Radeon RX 9070 XT:
17 s to transcribe, 38 s to translate. Translation quality is the model's: a small model translates fast and
loosely, so read the result before you publish it. In MCP it is `translate_to` on `transcribe`, and the
`translate_subtitles` tool.

**Burn the subtitles into the video.** For TikTok, Reels and Shorts the result you post is the video with the
captions on it, not an `.srt`:
```bash
babelscribe clip.mp4 --burn                   # clip.subbed.mp4, white subtitles at the bottom
babelscribe clip.mp4 --burn --style karaoke   # each word lights up as it is spoken
babelscribe clip.mp4 --burn --style shorts    # big, two or three words at a time, placed for vertical video
babelscribe burn clip.mp4                     # again from the saved clip.json (after fixing words, or another style)
babelscribe burn clip.mp4 clip.ass            # an .ass you styled yourself is drawn exactly as it is
```
| `babelscribe jfk.mp4 --burn --style karaoke` | `babelscribe clip.mp4 -l th --burn --style shorts` |
|---|---|
| ![English clip with karaoke subtitles](https://raw.githubusercontent.com/phonology024/babelscribe/main/docs/img/burn-karaoke-en.jpg) | ![Vertical Thai clip with shorts captions](https://raw.githubusercontent.com/phonology024/babelscribe/main/docs/img/burn-shorts-th.jpg) |

Frames from real runs (speech: JFK's 1961 inaugural address, public domain; a Thai sentence from Google FLEURS, CC BY 4.0).

The input video is never changed and its audio is copied as it is. Text size and position follow the picture
(a phone video counts as vertical), and the font is one that has the letters of the language: Thai, Japanese,
Chinese, Korean, Arabic and Devanagari are looked up among the fonts on your computer, and if none has them
babelscribe says which to install instead of drawing empty boxes (`--font "Name"` to choose yourself). The video is
encoded on the GPU when it can be (NVIDIA, AMD, Intel, Apple), otherwise with x264. An `.srt` or `.vtt` can be
burned too, plain only, since it has no word timings. For Thai in the shorts look, `pip install "babelscribe[thai]"`
keeps words whole. In MCP it is the `burn_subtitles` tool.

From Python:
```python
from babelscribe.api import transcribe_file
r = transcribe_file("talk.mp4", lang="auto", formats=["srt", "txt"])   # or accurate=True, prompt="names, terms"
print(r["lang"], r["device"], r["files"]); print(r["text"][:200])

from babelscribe.api import transcribe_many
done = transcribe_many(["a.mp4", "./recordings"], recursive=True, formats=["srt"])   # other options as above
print(done["succeeded"], done["failed"])
```
A download that is interrupted (a dropped connection, Ctrl+C, *Cancel*) continues where it stopped, the next time you
run babelscribe if it has to give up. The finished file is checked against its sha256 before it is used
([troubleshooting.md](troubleshooting.md)).

Models download on first use to `~/.babelscribe/models` (`BABELSCRIBE_MODELS` to change). Hybrid fine-tunes are converted on your
machine from their original Hugging Face repo — install `pip install "babelscribe[finetune]"` once. Only one weights file and
the few files the converter reads are downloaded (about 3 GB; 6 GB for Hindi). Converted weights are never
redistributed, so each fine-tune keeps its own licence. Thai word boundaries: `pip install "babelscribe[thai]"`.
A computer with little free memory gets a smaller model than `turbo` when you do not name one, and a warning when you name one
that will not fit; what each model needs is in [memory.md](memory.md).

## Connect to an AI app from a terminal
`babelscribe connect status` lists Claude Desktop, Claude Code, Codex CLI, Cursor, Gemini CLI and OpenCode (version 2)
and whether babelscribe is in each; `babelscribe connect show cursor` prints exactly what would be added; `babelscribe connect add cursor` does it
(`--no-backup` skips the `.bak` copy) and `babelscribe connect remove cursor` undoes it (`remove --all` takes it out of every app that has it set up with this program). Other servers and settings in the
app's file are kept, and a file with a syntax error is refused and left as it is. `babelscribe llms` lists the local models
that can translate. `--burn-translated` (with `--burn` and `--translate-to`) draws the translated subtitles
(`NAME.LANG.subbed.mp4`). The desktop app does the same through its *Connect to an AI app* window
([desktop-app.md](desktop-app.md)).

## MCP tools
Setup for each app is in the [README](../README.md#use-it-from-an-ai-app-mcp--no-terminal-needed).

Tools: `transcribe` (file → subtitles + text), `transcribe_folder` (every audio/video in a folder, one summary
back), `convert_subtitles` (re-wrap or re-export from the saved JSON, no transcription), `burn_subtitles` (the video with
the subtitles drawn on it), `translate_subtitles` (into any language, through an LLM on your computer), `find_media` (newest audio/video in Downloads, Videos, Desktop, …), `list_devices`,
`list_languages_and_models`.

`transcribe_folder` goes on after a file fails and lists the failure in the summary. Subtitles land next to each
file, or under `output_dir` with the same sub-folders. Two files that would share a subtitle name (`talk.mp4` and
`talk.mp3`) keep their full name: `talk.mp4.srt`, `talk.mp3.srt`.

The MCP tools use the `turbo` model (1.6 GB), or a smaller one when the computer has too little free memory for it
(see [memory.md](memory.md)). To choose yourself, set `BABELSCRIBE_MODEL` in the server's environment, e.g.
`"env": {"BABELSCRIBE_MODEL": "small"}` in the JSON above.

## Docker
No Python, ffmpeg or whisper.cpp on the host — the image has them, and the model is cached in a volume. There is no
published image yet, so build it from a checkout, then run it on the folder that holds your media:
```bash
docker build -t babelscribe -f docker/Dockerfile .
docker run --rm -v "$PWD:/media" -v babelscribe-models:/models babelscribe talk.mp4   # writes talk.srt next to the input
```
CPU by default, linux/amd64; a Vulkan image for GPU hosts is one `--build-arg` away. Details: [docker/README.md](../docker/README.md).

## Prebuilt binaries
`.github/workflows/build-binaries.yml` builds `whisper-cli` + `whisper-quantize` for every row of the table in [How it works](#how-it-works) and attaches
them to each `v*` release, with a `SHA256SUMS` file.

Each babelscribe version downloads the binaries of one fixed release (`BINARY_TAG` in `babelscribe/backend.py`), not
"latest", and checks the zip's sha256 before unpacking it. A download that does not match is deleted and nothing is
run. `babelscribe doctor` shows which release the cached binary came from and whether its files changed since.
Point `BABELSCRIBE_RELEASES` at another URL to self-host: a mirror of the official zips is checked the same way; a
mirror with your own builds needs `BABELSCRIBE_SKIP_VERIFY=1`.
