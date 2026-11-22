"""Translate finished subtitles into any language through a local LLM (Ollama, LM Studio, llama-server, localllm:
anything that speaks the OpenAI chat API). Optional: babelscribe downloads no model for this and adds no dependency.

  babelscribe talk.mp4 --translate-to th                 # transcribe, then also write talk.th.srt
  babelscribe translate talk.json --to ja                # from a finished transcription (or an .srt / .vtt)

Only the text is translated. Every segment keeps its own start and end time, so the translated subtitles stay in
sync, and the lines are wrapped again by the rules of the target language. The original files are never changed.
The endpoint must be on this computer unless --allow-remote is given: transcripts do not leave it by accident."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from . import align, convert, writers

# Where local servers listen by default: llama-server / localllm, Ollama, LM Studio.
DEFAULT_ENDPOINTS = ("http://127.0.0.1:8080/v1", "http://127.0.0.1:9931/v1", "http://127.0.0.1:11434/v1",
                     "http://127.0.0.1:1234/v1")
BATCH = 20          # subtitle lines per request
CONTEXT = 3         # lines before the batch that are shown again, already translated, so the wording carries on
TIMEOUT = 600       # seconds for one request; a big model on a CPU is slow

LANGUAGES = {
    "ar": "Arabic", "bn": "Bengali", "cs": "Czech", "da": "Danish", "de": "German", "el": "Greek", "en": "English",
    "es": "Spanish", "fa": "Persian", "fi": "Finnish", "fr": "French", "he": "Hebrew", "hi": "Hindi",
    "hu": "Hungarian", "id": "Indonesian", "it": "Italian", "ja": "Japanese", "km": "Khmer", "ko": "Korean",
    "lo": "Lao", "ms": "Malay", "my": "Burmese", "nl": "Dutch", "no": "Norwegian", "pl": "Polish",
    "pt": "Portuguese", "ro": "Romanian", "ru": "Russian", "sv": "Swedish", "ta": "Tamil", "te": "Telugu",
    "th": "Thai", "tl": "Filipino", "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu", "vi": "Vietnamese",
    "zh": "Chinese (Simplified)", "zh-tw": "Chinese (Traditional)",
}
NO_SPACES = {"th", "ja", "zh", "zh-tw", "lo", "km", "my"}      # written without spaces between words


def language(target: str) -> tuple[str, str]:
    """('th', 'Thai') from 'th', 'TH' or 'Thai'. A language not in the table is passed to the model as written."""
    t = target.strip()
    if not t:
        raise ValueError("no target language given (e.g. th, ja, es)")
    if t.lower() in LANGUAGES:
        return t.lower(), LANGUAGES[t.lower()]
    for code, name in LANGUAGES.items():
        if t.lower() == name.lower() or t.lower() == name.split(" (")[0].lower():
            return code, name
    return re.sub(r"[^a-z0-9-]+", "-", t.lower()).strip("-") or "xx", t


def is_local(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host in ("localhost", "host.docker.internal") or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _get_json(url: str, payload: dict | None = None, timeout: float = TIMEOUT, key: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def find_endpoint(url: str | None = None, allow_remote: bool = False) -> tuple[str, list[str]]:
    """(base URL, model names it offers). url: --llm, else BABELSCRIBE_LLM, else the usual local ports are tried."""
    url = url or os.environ.get("BABELSCRIBE_LLM") or None
    candidates = [url.rstrip("/")] if url else list(DEFAULT_ENDPOINTS)
    for base in candidates:
        if not re.match(r"https?://", base):
            raise SystemExit(f"--llm needs a full URL such as http://127.0.0.1:8080/v1 (got '{base}')")
        if not is_local(base) and not allow_remote:
            raise SystemExit(f"{base} is not on this computer. babelscribe keeps your transcripts local, so it only "
                             f"sends them to another machine when you say so: add --allow-remote.")
        try:
            listing = _get_json(base + "/models", timeout=5, key=os.environ.get("BABELSCRIBE_LLM_KEY"))
        except (OSError, ValueError):
            continue
        names = [m.get("id", "") for m in listing.get("data", []) if isinstance(m, dict)]
        return base, [n for n in names if n]
    tried = ", ".join(candidates)
    raise SystemExit(
        f"no local LLM answered ({tried}). Translation needs one running on this computer, for example:\n"
        f"  ollama serve      (then: ollama pull gemma3)      or      llama-server -m model.gguf --port 8080\n"
        f"then run again, or point at yours with --llm http://127.0.0.1:PORT/v1")


def chat_fn(base: str, model: str | None = None) -> Callable[[list[dict]], str]:
    """A function that sends chat messages to the endpoint and returns the reply text.

    Reasoning is switched off (reasoning_effort "none"): a model that thinks before each answer took 18 s for one
    subtitle line instead of 1 s in the test run, for the same translation. A server that does not know the
    setting and refuses the request is asked again without it, and not sent it any more."""
    quiet = [True]

    def post(body: dict) -> dict:
        return _get_json(base + "/chat/completions", body, key=os.environ.get("BABELSCRIBE_LLM_KEY"))

    def call(messages: list[dict]) -> str:
        body = {"messages": messages, "temperature": 0.2, "stream": False}
        if model:
            body["model"] = model
        try:
            try:
                reply = post({**body, "reasoning_effort": "none"} if quiet[0] else body)
            except urllib.error.HTTPError as e:
                if not quiet[0] or e.code not in (400, 422):
                    raise
                quiet[0] = False
                reply = post(body)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"the LLM at {base} answered HTTP {e.code}: {detail}") from None
        except OSError as e:
            raise RuntimeError(f"the LLM at {base} stopped answering: {e}") from None
        try:
            return reply["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise RuntimeError(f"the LLM at {base} sent a reply babelscribe cannot read: {str(reply)[:200]}") from None
    return call


def _clean(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)          # reasoning models think out loud
    return text.strip()


def _system(name: str, source: str | None) -> str:
    from_ = f" from {source}" if source else ""
    return (f"You translate subtitles{from_} into {name}. You get numbered lines, one subtitle per line. "
            f"Reply with every line translated, in the same order, each as: number, a tab, the translation. "
            f"One input line is one output line: never merge, split, drop or add lines, and never leave a line "
            f"untranslated. Write natural spoken {name}, as short as the original allows. Keep names, numbers and "
            f"units correct. No notes, no explanations, nothing but the numbered lines.")


def _parse(reply: str, count: int) -> list[str] | None:
    """The translations by number, or None when the reply is not exactly lines 1..count."""
    found: dict[int, str] = {}
    for line in _clean(reply).splitlines():
        m = re.match(r"\s*\[?(\d+)\]?\s*[\t.:)|\-]?\s*(.*\S)\s*$", line)
        if m and int(m.group(1)) not in found:
            found[int(m.group(1))] = m.group(2).strip()
    if set(found) != set(range(1, count + 1)):
        return None
    return [found[i] for i in range(1, count + 1)]


def translate_texts(
    texts: list[str],
    target: str,
    call: Callable[[list[dict]], str],
    source: str | None = None,
    log: Callable[[str], None] = print,
    progress: Callable[[float], None] | None = None,
    batch: int = BATCH,
) -> list[str]:
    """Translate subtitle texts, one output per input, in order. Always returns len(texts) strings.

    Lines go out in batches, with the last few already-translated lines as context. A reply that does not have
    exactly the lines asked for is asked for once more; after that the batch is done one line at a time, and a
    line the model still does not answer keeps its original text (so a subtitle is never lost or shifted)."""
    _, name = language(target)
    src_name = language(source)[1] if source and source != "auto" else None
    out: list[str] = []
    for start in range(0, len(texts), batch):
        part = [" ".join(t.split()) for t in texts[start:start + batch]]
        numbered = "\n".join(f"{i}\t{t}" for i, t in enumerate(part, 1))
        user = f"Translate into {name}:\n{numbered}"
        if out:
            before = "\n".join(f"- {a}  =>  {b}" for a, b in
                               zip(texts[max(0, start - CONTEXT):start], out[-CONTEXT:]))
            user = f"The lines just before these, already translated (context only, do not repeat them):\n{before}\n\n{user}"
        messages = [{"role": "system", "content": _system(name, src_name)}, {"role": "user", "content": user}]
        reply = call(messages)
        done = _parse(reply, len(part))
        if done is None:                       # ask once more, showing the model what it sent
            done = _parse(call(messages + [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"That was not {len(part)} numbered lines. Reply again with exactly "
                                            f"lines 1 to {len(part)}, each as: number, tab, translation."}]),
                          len(part))
        if done is None:
            log(f"  lines {start + 1}-{start + len(part)}: the model did not keep the lines apart; one at a time ...")
            done = []
            for t in part:
                one = _clean(call([
                    {"role": "system", "content": f"Translate the subtitle line into {name}. Reply with the "
                                                  f"translation only, on one line."},
                    {"role": "user", "content": t}]))
                one = " ".join(one.split())
                done.append(re.sub(r"^1\s*[\t.:)]\s*", "", one) or t)
        out += done
        if progress:
            progress(min(100.0, 100.0 * len(out) / max(1, len(texts))))
        log(f"  translated {len(out)}/{len(texts)}")
    return out


def _timed_words(text: str, start: float, end: float, code: str) -> list:
    """Word timings for a translated line: its pieces share the segment's time by length. They are what lets the
    writers wrap a long translation into lines, and split it into several subtitles, without leaving its time."""
    if code in NO_SPACES:
        breaks = sorted(x for x in align._word_breaks(text) if 0 < x < len(text))
        if code != "th" or not any(not text[x].isspace() and not text[x - 1].isspace() for x in breaks):
            breaks = [i for i in range(1, len(text))                      # any letter may end a line, except that
                      if text[i] not in _JOINS_BACK and text[i - 1] not in _JOINS_NEXT    # marks stay with theirs
                      and not (text[i].isascii() and text[i - 1].isascii() and text[i].isalnum() and text[i - 1].isalnum())]
        edges = [0] + breaks + [len(text)]
        pieces = [text[a:b] for a, b in zip(edges, edges[1:])]
    else:
        pieces = re.findall(r"\s*\S+", text)
    pieces = [p for p in pieces if p]
    spans = convert._spread(start, end, [max(1, len(p.strip())) for p in pieces])
    return [[p, round(a, 3), round(b, 3)] for p, (a, b) in zip(pieces, spans)]


_JOINS_BACK = set("ะัาำิีึืฺุูๅๆ็่้"
                  "๊๋์ํ๎、。，！？」』）,.!?)")
_JOINS_NEXT = set("เแโใไ「『（(")


def load_segments(path: Path) -> tuple[list[dict], dict]:
    """Segments and meta from a babelscribe .json, or from the cues of an .srt / .vtt."""
    if path.suffix.lower() == ".json":
        data = convert.load(path)
        return [s for s in data["segments"] if str(s["text"]).strip()], dict(data.get("meta") or {})
    if path.suffix.lower() in (".srt", ".vtt"):
        from .burn import read_srt
        if not path.is_file():
            raise FileNotFoundError(f"no such file: {path}")
        return read_srt(path), {}
    raise ValueError(f"{path.name}: translate reads a babelscribe .json, an .srt or a .vtt")


def translate_file(
    path: str | Path,
    target: str,
    llm: str | None = None,
    model: str | None = None,
    formats: list[str] | None = None,
    out: str | Path | None = None,
    allow_remote: bool = False,
    max_line_chars: int | None = None,
    log: Callable[[str], None] = print,
    progress: Callable[[float], None] | None = None,
    call: Callable[[list[dict]], str] | None = None,
) -> dict:
    """Write NAME.<lang>.srt (and the other formats asked for) next to a finished transcription.

    path: a babelscribe .json (best), or an .srt / .vtt. Returns {"files", "segments", "lang", "model", "endpoint"}.
    Each segment keeps its start and end; the translated text is wrapped by the target language's rules."""
    src = Path(path).expanduser()
    code, name = language(target)
    segs, meta = load_segments(src)
    if not segs:
        raise ValueError(f"{src} has no subtitles in it")
    formats = formats or ["srt"]
    stem = src.name[:-len(src.suffix)]
    base = Path(out).expanduser() if out else src.with_name(f"{stem}.{code}")
    clash = [f for f in formats if (base.parent / f"{base.name}.{f}").resolve() == src.resolve()]
    if clash:
        raise ValueError(f"the translation would overwrite {src.name}; give another output with -o")
    endpoint, used = "", model
    if call is None:
        endpoint, offered = find_endpoint(llm, allow_remote)
        used = model or (offered[0] if offered else None)
        call = chat_fn(endpoint, used)
        log(f"translating {len(segs)} subtitles into {name} with {used or 'the model'} at {endpoint} ...")
    texts = translate_texts([s["text"].strip() for s in segs], target, call, meta.get("lang"), log, progress)
    done = []
    for s, t in zip(segs, texts):
        done.append({"start": s["start"], "end": s["end"], "text": t,
                     "words": _timed_words(t, s["start"], s["end"], code)})
    new_meta = {**meta, "lang": code, "translated_from": meta.get("lang") or "", "translated_by": used or ""}
    new_meta.pop("translate", None)
    base.parent.mkdir(parents=True, exist_ok=True)
    files = writers.write(done, base, formats, new_meta, max_line_chars=max_line_chars)
    log(f"{name}: " + ", ".join(str(f) for f in files))
    return {"files": [str(f) for f in files], "segments": len(done), "lang": code, "model": used or "",
            "endpoint": endpoint}


def main(argv: list[str]) -> None:
    """babelscribe translate talk.json --to th"""
    import argparse
    ap = argparse.ArgumentParser(
        prog="babelscribe translate",
        description="Translate finished subtitles into another language through a local LLM (Ollama, LM Studio, "
                    "llama-server, ...). Writes NAME.<lang>.srt next to the input; the timing is kept.")
    ap.add_argument("subtitles", nargs="+", help="babelscribe .json (best), .srt or .vtt")
    ap.add_argument("--to", required=True, metavar="LANG", help="target language: th, ja, es, ... or its name")
    add_llm_flags(ap)
    ap.add_argument("-f", "--formats", default="srt", help="comma list: srt,vtt,txt,json,ass (default: srt)")
    ap.add_argument("-o", "--out", help="output base path (default: NAME.<lang> next to the input; one input only)")
    ap.add_argument("--max-line-chars", type=int, help="maximum characters per subtitle line")
    a = ap.parse_args(argv)
    if a.out and len(a.subtitles) > 1:
        raise SystemExit("-o names one output; translate one file at a time with it")
    for path in a.subtitles:
        try:
            translate_file(path, a.to, a.llm, a.llm_model, [f.strip() for f in a.formats.split(",") if f.strip()],
                           a.out, a.allow_remote, a.max_line_chars)
        except (FileNotFoundError, ValueError, RuntimeError) as e:
            raise SystemExit(str(e))


def add_llm_flags(ap) -> None:
    ap.add_argument("--llm", metavar="URL", help="OpenAI-compatible endpoint, e.g. http://127.0.0.1:8080/v1 "
                    "(default: BABELSCRIBE_LLM, else llama-server, Ollama and LM Studio on their usual ports)")
    ap.add_argument("--llm-model", metavar="NAME", help="model to ask for (default: the first one the endpoint lists)")
    ap.add_argument("--allow-remote", action="store_true",
                    help="let --llm point at another computer (the transcript text is sent there)")
