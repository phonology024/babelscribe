# Speaker labels (diarization): options and measured cost

Research for [#9](https://github.com/phonology024/babelscribe/issues/9). Everything below was run on an Apple M4 Pro
(48 GB, Metal) on 30 Oct 2026 with `babelscribe` 0.3.2, so the numbers are reproducible, not estimates. Nothing here is
implemented yet.

**The question:** is there a light, offline, no-account way to label speakers that works on non-NVIDIA GPUs and keeps
the install small?

**Short answer:** yes — `sherpa-onnx` (2 wheels, 11.6 MB, no CUDA) with a 45 MB pair of ONNX models. It runs on the CPU,
so it works identically on AMD, Intel, Apple and NVIDIA. Measured at **6.4×–23× realtime**, i.e. a 5-minute interview
costs 47 s on top of the transcription. Two caveats: it needs a threshold that adapts to the recording, and the numbers
below come from synthetic voices, so real recordings are still unmeasured.

---

## What already ships in whisper.cpp, and why neither option is enough

whisper-cli has two relevant flags. Both were tested rather than read about.

### `-di` — stereo channel diarization

It does not find voices. It reports which *channel* is louder, which only works if each speaker was recorded on their
own track (a two-mic podcast, a phone call). Measured:

| Input | Correct answer | `-di` output |
|---|---|---|
| Two different voices, one per channel, sequential | speakers A, B | `speaker 0`, `speaker 1` ✅ |
| The **same** voice on both channels, sequential | one speaker | `speaker 0`, `speaker 1` ❌ invents a second speaker |
| The mono file babelscribe actually produces | — | `speaker ?` on every segment ❌ |

The third row is the important one. `transcribe.to_wav16k` converts to `-ac 1` before whisper-cli runs, so the stereo
difference is destroyed and `-di` cannot work at all in the current pipeline. Enabling the flag alone would change
nothing. It would also only ever help the minority of files that were recorded on separate tracks.

### `-tdrz` — tinydiarize

Adds a `speaker_turn_next` boolean to each segment (it does appear in the `-ojf` JSON). Two problems, both measured:

- **It requires a tdrz model.** With `large-v3-turbo` it silently produces `false` on everything. On a 3-voice file with
  three real speaker changes it flagged **0 of 3**. On a 63-second single-speaker file it correctly flagged 0 of 16,
  so it is not wrong so much as always answering "no".
- **No tdrz model is distributed for the models babelscribe uses.** `ggml-small.en-tdrz.bin` returns **404** on
  `huggingface.co/ggerganov/whisper.cpp`, and it is English-only, which is useless for the Thai and Hindi users this
  project targets.

So `-tdrz` would mean maintaining our own converted models, English-only, to get turn *boundaries* rather than speaker
identities. Not worth it.

---

## The viable option: sherpa-onnx

A C++/ONNX runtime speaker-diarization pipeline with Python bindings. No PyTorch, no CUDA, no account, no network at
inference time.

### Install cost

| Piece | Size |
|---|---|
| `sherpa-onnx` wheel (macOS arm64) | 2.0 MB |
| `sherpa-onnx-core` wheel | 9.1 MB |
| Dependencies | **none** (only `sherpa-onnx` and `sherpa-onnx-core`) |
| Installed site-packages | 37 MB |
| Segmentation model (`sherpa-onnx-pyannote-segmentation-3-0`) | 7.2 MB |
| Embedding model (`3dspeaker_eres2net_base`, 16 kHz) | 38 MB |
| **Total** | **≈ 107 MB** |

For comparison, the Whisper model babelscribe already downloads is 1.6 GB, so this is ~7% on top and is a lazy
download like the models. No CUDA toolkit, no PyTorch (which would be ~2 GB and would pull a GPU stack that does not
work on AMD without ROCm).

### Accuracy, measured

| Test | Correct answer | Result |
|---|---|---|
| 2 voices, one per channel, sequential | 2 speakers, turns in the right places | ✅ 2 speakers, both turns correct |
| **Same voice both channels** (false-positive check) | 1 speaker | ✅ 1 speaker — no invented speaker, unlike `-di` |
| 3 voices (Samantha, Daniel, Karen), sequential | 3 speakers | ✅ 3 speakers, all three turns correct |

Getting the three-voice case right needed `threshold=0.4`. The library default of `0.5` merges Samantha and Karen into
one speaker. A sweep on the same file:

| threshold | speakers found |
|---|---|
| 0.3 | 3 ✅ |
| 0.4 | 3 ✅ |
| 0.5 (default) | 2 ❌ |
| 0.6–0.8 | 2 ❌ |

On the two-voice file every threshold from 0.3 to 0.8 gave the correct 2, so 0.4 is safe there too. **This is the main
risk:** the right threshold depends on the recording, and a fixed default will sometimes merge two similar voices.
A future implementation should expose it, and probably default to 0.4 rather than the library's 0.5.

### Speed, measured

Single-threaded CPU, no GPU used:

| Audio | Diarization time | Realtime factor |
|---|---|---|
| 13 s | 0.56 s | 23× |
| 20 s | 1.6 s | 12.6× |
| 63 s | 8.6 s | 7.2× |
| 100 s | 12.8 s | 7.8× |
| 300 s | 47.0 s | 6.4× |

It scales roughly linearly at ~6–7× realtime on longer files. On the same machine whisper.cpp transcribes at ~23×
realtime, so **diarization costs about 3–4× the transcription time**. For a 5-minute interview: ~13 s to transcribe,
~47 s for speaker labels. Worth it when the user asks for it, too slow to run unconditionally.

### Merging with the transcript

The transcript and the speaker turns are separate timelines, so each whisper segment is assigned to whichever
diarization turn it overlaps most. Demonstrated end to end on the 3-voice file:

```
[Speaker 1] So the main thing I wanted to raise today is the release schedule, because we are already behind on the migration.
[Speaker 0] Right. And I think the blocker there is the database change that nobody has had time to look at properly.
[Speaker 2] I can take that one. I have been working with the same schema in my own project for a few months now.
```

All three segments attributed correctly. Note the speaker numbers are arbitrary cluster ids (1, 0, 2 in time order);
they need renumbering by first appearance before they are shown to a user.

---

## Options considered and rejected

| Option | Why not |
|---|---|
| **pyannote.audio** | The reference implementation and the most accurate, but it needs PyTorch (~2 GB), a Hugging Face account and accepting a gated model licence — directly against "no-account" and "keep install small". |
| **WhisperX** | Wraps pyannote, so it inherits both problems, plus it re-runs its own ASR and would duplicate the pipeline. |
| **NeMo** | Same PyTorch weight, plus it is tuned for NVIDIA. |
| **`-di`** | Only works on separate tracks; cannot work on the mono file babelscribe produces. |
| **`-tdrz`** | English-only, no model for the models we ship; silently returns nothing otherwise. |
| **Cloud APIs** | Against the project's whole premise — offline, nothing uploaded. |

---

## Recommendation

1. **Implement with sherpa-onnx**, as an opt-in flag (`--speakers` / a `diarize: true` MCP argument) rather than a
   default, because it adds 3–4× the transcription time and a 45 MB model download.
2. **Default `threshold=0.4`**, expose it, and document that two similar voices can merge.
3. **Plain-language output** — `Speaker 1:` prefixes in `txt`/`srt`, a `speaker` key per segment in `json`. Keep the
   `json` addition optional so the pinned output keys in `API_STABILITY.md` are untouched.
4. **Do not advertise speaker *identification*** — this labels "who spoke when", not "this is Anna". Naming speakers
   would need enrolment samples, a much bigger feature.

## What is still unknown

Every measurement above used synthetic macOS `say` voices, which are unusually clean and well separated. Real
meetings — crosstalk, background noise, similar-sounding people, more than three speakers — are **unmeasured** and are
where diarization usually degrades. Before implementing, it is worth running this on one real interview with known
speakers. That is the only number here I would not trust yet.