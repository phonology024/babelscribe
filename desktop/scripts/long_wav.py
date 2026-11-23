"""A long recording for the CI check that stopping the engine ends whisper-cli too.

    python desktop/scripts/long_wav.py jfk.wav long.wav 60

Writes `long.wav`: the sample repeated 60 times (about 11 minutes), so that whisper-cli is still working when the
check stops the engine. Standard library only."""
from __future__ import annotations

import sys
import wave


def main() -> None:
    source, target, times = sys.argv[1], sys.argv[2], int(sys.argv[3])
    with wave.open(source, "rb") as r:
        params, frames = r.getparams(), r.readframes(r.getnframes())
    with wave.open(target, "wb") as w:
        w.setparams(params)
        for _ in range(times):
            w.writeframes(frames)
    print(f"{target}: {times} x {params.nframes / params.framerate:.1f} s")


if __name__ == "__main__":
    main()
