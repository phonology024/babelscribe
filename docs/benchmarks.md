# Benchmarks

All numbers below were measured with the scripts in `bench/`. Back to the [README](../README.md).

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
