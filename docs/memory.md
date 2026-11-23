# Memory (RAM): which model fits your computer

Whisper models are big. babelscribe looks at how much memory is free **before it downloads or loads anything**, and
does one of two things:

- **You did not choose a model** (no `-m`): if the default model, `turbo`, does not fit, it uses the largest model that
  does, and says so in one line:
  `low memory: 1.4 GB free, turbo needs about 2.4 GB; using small instead (it is less accurate, most of all for Thai and other languages than English). -m turbo keeps it.`
- **You chose a model** (`-m`, `--text-model`, `--accurate`, `--translate`, or `BABELSCRIBE_MODEL`): it is never
  changed. If it will not fit, you get one warning line and the run goes on.

If the free memory cannot be found out, nothing changes at all. Smaller models are less accurate; for Thai, Hindi and
other languages Whisper knows less well, the difference is large (see [benchmarks](benchmarks.md)).

`babelscribe models` lists what each model needs, `babelscribe doctor` shows the memory of this computer, and
`babelscribe models --json` is what the desktop app asks to mark what will not fit.

## What each model needs

Peak memory of one `whisper-cli` run (Windows 11, AMD Radeon RX 9070 XT, 20 threads, whisper.cpp from release v0.4.0, the
models as babelscribe downloads them), in MB, as the peak working set of the process, for a 2 minute recording:

| model | file on disk | RAM, CPU build | needs free (rule) | RAM, Vulkan build | card memory for the weights |
|---|---:|---:|---:|---:|---:|
| `tiny` | 75 MB | 309 | 821 | 420 | 77 |
| `base` | 142 MB | 418 | 930 | 534 | 147 |
| `small` | 466 MB | 887 | 1399 | 635 | 487 |
| `medium` | 1.5 GB | 2191 | 2703 | 683 | 1533 |
| `large-v3-turbo` (`turbo`) | 1.6 GB | 1939 | 2451 | 670 | 1624 |
| `large-v3` | 3.1 GB | 4046 | 4558 | 871 | 3094 |
| a fine-tune (`thai-pathumma`, ...) | 1.6 GB (`q8_0`) | 2665 | 3177 | 835 | 1656 |

"Needs free (rule)" is the CPU number plus the 512 MB margin described below, for a recording of 2 minutes or less.

How it was measured: each model transcribed the 11-second JFK sample (public domain, whisper.cpp's `samples/jfk.wav`) and
a 2 minute 9 second English clip made of 14 Google FLEURS utterances (CC BY 4.0), once with the CPU build and once with the
Vulkan build; the peak working set was read from the operating system while the process ran. The fine-tunes are not
measured one by one: they are `large-v3`-sized models stored as 8-bit (`q8_0`), so the row "a fine-tune" is `large-v3`
quantized to `q8_0` with `whisper-quantize`, which has the same tensors and the same size on disk.

What the numbers say:

- **CPU build:** the whole model is in RAM, plus about 0.2 to 1.0 GB of working memory. `large-v3` needs about 4 GB.
- **Vulkan build:** the weights go to the graphics card, so the RAM stays under 1 GB for every model, but the card
  needs room for the model (the last column, plus a few hundred MB of working memory). A card that shares the computer's memory (many
  laptops) uses RAM for that, so count it like the CPU build.
- **Length of the recording:** RAM grows with the length of the audio, because whisper-cli keeps the whole recording and its spectrogram in
  memory: `tiny` on the CPU went from 309 MB (2 minutes) to 576 MB (30 minutes), and `turbo` on Vulkan from 670 MB to
  971 MB. That is about 10 to 11 MB per minute, so a 3 hour recording needs about 2 GB more than the table says. The
  rule adds 11 MB for every minute beyond the first 2 (it reads the length with ffmpeg; if it cannot, it adds nothing).
- **Beam search** (`--accurate`, `-bs 5`) did not change the peak (`large-v3` 3925 MB with and without, `small` 770 MB
  with and without, on the 11 second clip).

## The rule

A model fits when its **CPU-build peak + 512 MB (+ 11 MB for each minute beyond 2)** is at most the memory the operating system calls *available* (Windows:
available physical memory; Linux: `MemAvailable`, or the room left under a container's memory limit when there is one;
macOS: free + inactive + speculative pages). The 512 MB margin is for the operating system, ffmpeg and the program itself.

The CPU column is the rule's default. **When a discrete graphics card will hold the weights, the Vulkan column is used
instead** (about 0.7 to 0.9 GB of RAM for every model), so a computer with a good card and little free RAM keeps `turbo`.
The card is looked for only when the CPU column says no, and it counts only when it is certain: the `whisper-cli` that
will run is a CUDA build, or a Vulkan build whose device says `uma: 0` (its own memory). An integrated GPU (`uma: 1`)
shares the computer's RAM, and Apple's Metal uses the same unified memory, so both use the CPU column; so does anything
that cannot be found out. The card's own memory is not checked (its size is not read), only that it exists.
Choosing the default model for you only happens when `turbo` does not fit by that rule, which, without a card, is below
about 2.4 GB of free memory.

## Not measured

- macOS and Linux were not measured; the table is from Windows. whisper.cpp uses the same weights there, and macOS with
  Metal keeps the weights in the computer's own (unified) memory, so the CPU numbers are the better guide.
- Other thread counts were not tried (all 20 threads of this computer were used).
