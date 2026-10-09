# Contributing to babelscribe

Looking for something to pick up? See [ROADMAP.md](ROADMAP.md) (releases and a *Need help?* table) or the [`need help`](https://github.com/phonology024/babelscribe/labels/need%20help) label.

Thanks for helping! The most valuable contributions are small and concrete:

## 1. Make your language more accurate (best first PR)
Many languages have a community Whisper fine-tune on Hugging Face that beats plain Whisper. Adding one is a ~5-line PR:

1. Find a fine-tune (`whisper-large-v3` / `large-v2` based, Transformers format) for your language.
2. Add an entry to `FINETUNES` in `babelscribe/models.py` (repo, language code, `beam: 5`, a one-line note).
3. Measure it on FLEURS — slow is fine, it runs on your own GPU:
   ```bash
   python bench/fleurs.py fetch ./_fleurs --langs xx_yy --n 50
   python bench/fleurs.py run ./_fleurs --bin whisper-cli --model ggml-large-v3.bin --beam 5 --langs xx_yy --tag large-v3
   python bench/fleurs.py run ./_fleurs --bin whisper-cli --model <converted fine-tune> --beam 5 --langs xx_yy --tag my-finetune
   python bench/fleurs.py table ./_fleurs
   ```
4. If it wins, also add it to `ACCURATE` and paste the table in the PR. If it loses, a PR adding the result to the
   README's "measured and not used" line is just as useful.

## 2. Test on your hardware
Run `babelscribe devices` and transcribe one file, then open an issue with your OS, GPU and what happened
(template: *Hardware report*). NVIDIA, Intel Arc, Linux and macOS reports are especially wanted.

## 3. Code
`pip install -e .` then `python -m pytest`. Keep changes small, match the surrounding style, and say in the PR how you tested.
