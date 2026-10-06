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
| NVIDIA on Windows (alternative) | CUDA | `windows-x64-cuda` (`--flavor cuda`) |
| AMD / NVIDIA / Intel GPU on Linux | Vulkan | `linux-x64-vulkan` |
| Apple Silicon | Metal | `macos-arm64-metal` |
| No usable GPU | CPU | `*-cpu` (`--flavor cpu`) |

Measured on an AMD Radeon RX 9070 XT (Vulkan): 90 s of English in 5.4 s, 105 s of Thai in 9.8 s, a 14-minute talk in ~75 s
with `large-v3-turbo`.

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
with one line in `babelscribe/models.py` (Thai is the first: *Thonburian Whisper*). PRs adding fine-tunes for other
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
- **Outputs** — `srt`, `vtt`, `txt`, `json` (segments with token timings).

## Usage
```bash
babelscribe talk.mp4 -f srt,vtt,txt,json          # all formats
babelscribe podcast.mp3 -l en -m large-v3          # pick language and model
babelscribe vo.wav -l th --text-model thai-thonburian   # hybrid: Thai fine-tune text + turbo timing
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
ภาษาไทยแนะนำ `babelscribe ไฟล์.mp4 -l th --text-model thai-thonburian` — ข้อความจาก Thonburian Whisper ที่สะกดไทยแม่นที่สุด + เวลาจาก large-v3-turbo

## Credits & licence
MIT. Built on [whisper.cpp](https://github.com/ggml-org/whisper.cpp) (MIT) and OpenAI Whisper models (MIT).
Fine-tunes belong to their authors — e.g. [Thonburian Whisper](https://huggingface.co/biodatlab/whisper-th-large-v3-combined) by biodatlab.
