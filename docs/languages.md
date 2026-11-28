# Languages

Back to the [README](../README.md).

All 99 languages Whisper was trained on, auto-detected or forced with `-l`:
af am ar as az ba be bg bn bo br bs ca cs cy da de el en es et eu fa fi fo fr gl gu ha haw he hi hr ht hu hy id is it ja jw ka kk km kn ko la lb ln lo lt lv mg mi mk ml mn mr ms mt my ne nl nn no oc pa pl ps pt ro ru sa sd si sk sl sn so sq sr su sv sw ta te tg th tk tl tr tt uk ur uz vi yi yo yue zh

Accuracy follows Whisper's own training data: excellent for high-resource languages (English, Spanish, Japanese, …),
weaker for low-resource ones. That is what hybrid mode is for — a community fine-tune for one language can be plugged in
with one line in `babelscribe/models.py` (Thai and Hindi so far). PRs adding fine-tunes for other
languages are the most valuable contribution.

## Add a language fine-tune
Add one entry to `FINETUNES` in `babelscribe/models.py` (Hugging Face repo, the full commit id of the version you tested as
`revision`, language code, whether it needs beam search) and open a PR. Only that commit is downloaded: some weights are
pickle files, which can run code when they are loaded.
