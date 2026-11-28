# Privacy Policy
babelscribe runs entirely on your own computer. Last updated 2026-11-10.

- **Data collection:** none. babelscribe has no telemetry, analytics, accounts or crash reporting, and never uploads your
  audio, video, transcripts or file names anywhere.
- **What it processes and where:** the media file you choose is converted and transcribed locally; subtitles and text are
  written to your disk (next to the file, or the folder you choose). Through MCP, the transcript text is returned to the AI
  app that called the tool — what that app does with it is governed by that app's own privacy policy.
- **Optional translation (`--translate-to`, off unless you ask):** the subtitle text is sent to the LLM endpoint you
  run, which must be on this computer (`127.0.0.1` / `localhost`). It goes to another machine only if you pass
  `--allow-remote` yourself (for the MCP server: `BABELSCRIBE_LLM_ALLOW_REMOTE=1` in its settings; an AI app cannot
  switch it on). Audio and video are never sent.
- **Network access (downloads only):** on first use it downloads the `whisper-cli` program from this project's GitHub
  releases, speech models from Hugging Face (`huggingface.co/ggerganov/whisper.cpp`, and for `--accurate` Thai/Hindi the
  fine-tune's own repository, with the converter script from `ggml-org/whisper.cpp` and one data file from
  `openai/whisper` on GitHub), and Python packages from PyPI when installed with pip/uv. These are plain downloads;
  no personal data is sent. GitHub, Hugging Face and PyPI see a normal download request (IP address, user agent) under
  their own privacy policies.
- **Storage and retention:** downloaded programs and models are cached in `~/.babelscribe` (or `BABELSCRIBE_HOME` /
  `BABELSCRIBE_MODELS`) until you delete that folder. Outputs stay wherever they were written until you delete them.
  babelscribe keeps no other data.
- **Third-party sharing:** none.
- **Contact:** open an issue at https://github.com/phonology024/babelscribe/issues
