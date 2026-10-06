# babelscribe

**Transcribe any audio or video, in any of Whisper's 99 languages, on any GPU — AMD, NVIDIA, Intel or Apple — or just the CPU.**
One command, no CUDA required, subtitles out.

```bash
pip install babelscribe          # Python 3.9+
babelscribe interview.mp4                 # auto-detects language, picks your best GPU -> interview.srt + interview.json
```

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
| No usable GPU | CPU | `*-cpu` (`--flavor cpu`) |

A 19-minute English TED talk transcribes in 48 seconds on an AMD Radeon RX 9070 XT with 1.5% word error — see the benchmark below.

## Benchmark: real talks, human captions as the answer key
Four TED / TEDx talks, scored against the **human-made captions in the spoken language** (`bench/bench.py`, reproducible).
Error = word error rate (WER) for space-separated languages, character error rate (CER) for Japanese and Thai.
GPU: AMD Radeon RX 9070 XT via Vulkan. *default* = `large-v3-turbo`; *accurate* = `--accurate` (see the FLEURS section).

| Language | Talk | Length | default: time / error | `--accurate`: time / error |
|---|---|---|---|---|
| English | [Matt Walker — Sleep Is Your Superpower (TED)](https://youtu.be/5MuIMqhT8DM) | 19.3 min | 48 s (24x) · WER **1.5%** | 107 s (11x) · WER **1.5%** |
| Japanese | [Kazunari Taguchi (TEDxHimi)](https://youtu.be/cjtmDEG-B7U) | 16.2 min | 47 s (20x) · CER 4.7% | 115 s (8x) · CER **4.2%** |
| Spanish | [Adrià Solà Pastor — Cómo hablar (TEDxESIC University)](https://youtu.be/XUqrvbsTfck) | 19.9 min | 56 s (21x) · WER 13.8% | 134 s (9x) · WER 13.5% |
| Thai | [นิติ ชัยชิตาทร — โปรดเรียกฉันด้วยนามอันแท้จริง (TEDxBangkok)](https://youtu.be/48A9SU6_bQ8) | 14.1 min | 74 s (12x) · CER 22.7% | 565 s (2x) · CER **16.4%** |

How to read it: TED captions are edited for reading (fillers dropped, light rewording), so these numbers are an upper bound —
most of the Spanish "errors" are the speaker's actual words versus the tidied caption. Thai is genuinely harder: fast,
casual speech with slang; `--accurate` (Pathumma Whisper text + turbo timing) cuts its error by more than a quarter.
Talks are used only to measure accuracy; their transcripts are not redistributed (TED content is CC BY-NC-ND).

## Benchmark: 16 languages on FLEURS
[Google FLEURS](https://huggingface.co/datasets/google/fleurs) test set, 50 utterances per language, human-verified
verbatim transcripts (`bench/fleurs.py`, reproducible). Same normaliser for every language (Whisper's rule: lower-case,
drop punctuation and non-spacing marks, numbers spelled out). WER for space-separated languages, CER for ja / zh / ko / th.

| Language | default (turbo) | `--accurate` | model `--accurate` uses | `--accurate`, edge-trimmed* |
|---|---|---|---|---|
| English | 6.1% | 5.7% | large-v3, beam 5 | 5.6% |
| Spanish | 4.1% | 4.2% | large-v3, beam 5 | **2.6%** |
| French | 7.4% | 7.3% | large-v3, beam 5 | 7.2% |
| German | 4.3% | 4.0% | large-v3, beam 5 | **3.3%** |
| Portuguese | 8.5% | 7.7% | large-v3, beam 5 | 5.3% |
| Italian | 6.7% | 6.5% | large-v3, beam 5 | **3.8%** |
| Russian | 6.8% | 5.8% | large-v3, beam 5 | 5.6% |
| Arabic | 11.0% | 10.6% | large-v3, beam 5 | 9.7% |
| Hindi | 28.4% | **12.6%** | [vasista22/whisper-hindi-large-v2](https://huggingface.co/vasista22/whisper-hindi-large-v2) + turbo timing | 11.1% |
| Indonesian | 9.8% | 7.8% | large-v3, beam 5 | 5.6% |
| Vietnamese | 10.8% | 9.1% | large-v3, beam 5 | 9.1% |
| Turkish | 6.2% | 6.7% | large-v3, beam 5 | 5.8% |
| Japanese (CER) | 6.4% | 5.7% | large-v3, beam 5 | **4.6%** |
| Chinese (CER) | 6.3% | 5.3% | large-v3, beam 5 | **4.8%** |
| Korean (CER) | 4.1% | 3.9% | large-v3, beam 5 | **3.1%** |
| Thai (CER) | 15.9% | **8.9%** | [Pathumma Whisper](https://huggingface.co/nectec/Pathumma-whisper-th-large-v3) (NECTEC) + turbo timing | 8.8% |

\* Some FLEURS clips contain more speech than their reference transcript, so a correct model is charged for words the
reference leaves out. *Edge-trimmed* ignores extra words before the first / after the last reference word; both numbers
are stored by `bench/fleurs.py`. 50 utterances per language means differences under ~0.5 points are noise.

Also measured and **not** used, because large-v3 was as good or better: large-v2 (all languages),
PhoWhisper-large (vi 19.0%), whisper-large-v3 dialectal / code-switching Arabic fine-tunes (12.2% / 15.2%),
Typhoon Whisper (th 11.9%), Thonburian Whisper (th 9.1% — kept as an option), Vaani Hindi (16.5%).

## Why babelscribe (vs. what already exists)
| | GPU on AMD / Intel | Windows, no build step | Video in, subtitles out | Long files don't loop | Better text for your language |
|---|---|---|---|---|---|
| **babelscribe** | ✅ Vulkan | ✅ prebuilt `whisper-cli` downloaded for you | ✅ ffmpeg bundled | ✅ `--max-context 0` by default | ✅ hybrid fine-tune text + turbo timing |
| whisper.cpp (raw) | ✅ Vulkan — if you compile it | ❌ official releases ship no Windows Vulkan build | ❌ WAV 16 kHz only | ⚠️ you must know the flag | ❌ |
| faster-whisper / WhisperX | ❌ GPU = NVIDIA CUDA only | ✅ pip | ✅ | ⚠️ | ⚠️ manual |
| Cloud APIs | n/a (cloud) | ✅ | ✅ | ✅ | ❌ — and your audio leaves your machine, paid per minute |

babelscribe does **not** replace those projects — it stands on whisper.cpp and simply removes the hard parts:
compiling for your GPU, converting media, picking the right device, avoiding the long-file repeat bug, and combining
a language-specific fine-tune with accurate timestamps.

## Languages
All 99 languages Whisper was trained on, auto-detected or forced with `-l`:
af am ar as az ba be bg bn bo br bs ca cs cy da de el en es et eu fa fi fo fr gl gu ha haw he hi hr ht hu hy id is it ja jw ka kk km kn ko la lb ln lo lt lv mg mi mk ml mn mr ms mt my ne nl nn no oc pa pl ps pt ro ru sa sd si sk sl sn so sq sr su sv sw ta te tg th tk tl tr tt uk ur uz vi yi yo yue zh

Accuracy follows Whisper's own training data: excellent for high-resource languages (English, Spanish, Japanese, …),
weaker for low-resource ones. That is what hybrid mode is for — a community fine-tune for one language can be plugged in
with one line in `babelscribe/models.py` (Thai and Hindi so far). PRs adding fine-tunes for other
languages are the most valuable contribution.

## Limitations (honest)
- Tested end to end so far on an AMD Radeon RX 9070 XT (Windows, Vulkan). CUDA, Linux and macOS builds are produced by CI; reports from those machines are welcome.
- Hybrid mode runs two models, so it is slower (≈1 min per minute of audio with a large fine-tune on that GPU).
- Proper nouns can still be misspelled — check names before publishing subtitles.

## Features
- **Any input** — mp4, mkv, mov, mp3, wav, m4a… (ffmpeg is bundled through `imageio-ffmpeg`).
- **Any language** — `-l auto` detects it; or pass `-l th`, `-l ja`, `-l es`…
- **Picks the right GPU** — prefers a discrete card over an integrated one; `babelscribe devices` lists them, `--device N` overrides.
- **Long files that don't loop** — runs whisper with `--max-context 0`, which stops the classic "same sentence repeated forever" hallucination on long recordings.
- **Hybrid mode for better spelling in your language** — community fine-tunes (e.g. Thai *Thonburian Whisper*) spell far better but often lose timestamps. `--text-model` takes the text from the fine-tune and the timing from `large-v3-turbo`, aligned character by character (works for languages without spaces), cut only at word boundaries, with the timing model filling any words the fine-tune skipped.
- **`--accurate`** — slower, fewest errors: large-v3 with beam search, or for Thai and Hindi the best community fine-tune (hybrid). Chosen per language from the FLEURS benchmark above.
- **Outputs** — `srt`, `vtt`, `txt`, `json` (segments with token timings).

## Usage
```bash
babelscribe talk.mp4 -f srt,vtt,txt,json          # all formats
babelscribe podcast.mp3 -l en -m large-v3          # pick language and model
babelscribe talk.mp4 -l hi --accurate              # slower, fewest errors (best model per language)
babelscribe vo.wav -l th --text-model thai-thonburian   # hybrid: pick a Thai fine-tune yourself
babelscribe devices                                # GPUs whisper.cpp can see
babelscribe models                                 # models and fine-tunes
babelscribe talk.mp4 --bin /path/to/whisper-cli    # use your own whisper.cpp build
```
Models download on first use to `~/.babelscribe/models` (`BABELSCRIBE_MODELS` to change). Hybrid fine-tunes are converted on your
machine from their original Hugging Face repo — install `pip install "babelscribe[finetune]"` once; converted weights are never
redistributed, so each fine-tune keeps its own licence. Thai word boundaries: `pip install "babelscribe[thai]"`.

## Add a language fine-tune
Add one entry to `FINETUNES` in `babelscribe/models.py` (Hugging Face repo, language code, whether it needs beam search) and open a PR.

## Prebuilt binaries
`.github/workflows/build-binaries.yml` builds `whisper-cli` + `whisper-quantize` for every row of the table above and attaches
them to each `v*` release. Point `BABELSCRIBE_RELEASES` at another URL to self-host.

## ภาษาไทย
ถอดเสียงจากไฟล์เสียงหรือวิดีโอได้ทุกภาษา บนการ์ดจอทุกยี่ห้อ (AMD / NVIDIA / Intel ผ่าน Vulkan, Apple ผ่าน Metal) หรือ CPU
ภาษาไทยแนะนำ `babelscribe ไฟล์.mp4 -l th --accurate` — ข้อความจาก Pathumma Whisper (NECTEC) ที่ผิดน้อยที่สุดใน FLEURS (CER 8.9% เทียบ turbo 15.9%) + เวลาจาก large-v3-turbo
หรือเลือก Thonburian Whisper เอง: `--text-model thai-thonburian`

## Credits & licence
MIT. Built on [whisper.cpp](https://github.com/ggml-org/whisper.cpp) (MIT) and OpenAI Whisper models (MIT).
Fine-tunes belong to their authors: [Pathumma Whisper](https://huggingface.co/nectec/Pathumma-whisper-th-large-v3) by NECTEC,
[Thonburian Whisper](https://huggingface.co/biodatlab/whisper-th-large-v3-combined) by biodatlab,
[whisper-hindi-large-v2](https://huggingface.co/vasista22/whisper-hindi-large-v2) by vasista22 (Speech Lab, IIT Madras).
