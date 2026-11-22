"""`--translate-to` / `babelscribe translate` (#49): subtitles translated by a local LLM, timing kept."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from babelscribe import api, cli, llm_translate as lt, writers

SEGS = [
    {"start": 0.5, "end": 3.0, "text": "Hello there.", "words": [[" Hello", 0.5, 1.5], [" there.", 1.5, 3.0]]},
    {"start": 3.2, "end": 9.9, "text": "This one is long enough that it has to be wrapped onto more lines.",
     "words": []},
    {"start": 10.0, "end": 11.0, "text": "Bye.", "words": [[" Bye.", 10.0, 11.0]]},
]
THAI = {"Hello there.": "สวัสดีครับ", "Bye.": "ลาก่อน",
        "This one is long enough that it has to be wrapped onto more lines.":
            "ประโยคนี้ยาวพอที่จะต้องถูกตัดขึ้นบรรทัดใหม่หลายบรรทัดเพื่อให้อ่านได้สบายตา"}


def fake_translation(text: str) -> str:
    return THAI.get(text, f"<{text}>")


class FakeLLM(BaseHTTPRequestHandler):
    """An OpenAI-compatible endpoint that 'translates' numbered lines, with switches for the ways models misbehave."""
    mode = "good"
    requests: list = []

    def log_message(self, *a):
        pass

    def _send(self, code: int, body: dict):
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200, {"data": [{"id": "fake-model"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        cls = type(self)
        cls.requests.append(body)
        if cls.mode == "strict" and "reasoning_effort" in body:
            return self._send(400, {"error": {"message": "unknown field reasoning_effort"}})
        user = body["messages"][-1]["content"] if body["messages"][-1]["role"] == "user" else ""
        first = next(m["content"] for m in body["messages"] if m["role"] == "user")
        lines = re.findall(r"^(\d+)\t(.*)$", first, re.MULTILINE)
        if not lines:                                           # the one-line-at-a-time fallback
            reply = fake_translation(user)
        else:
            out = [f"{n}\t{fake_translation(t)}" for n, t in lines]
            if cls.mode == "merges" or (cls.mode == "merges-once" and len(body["messages"]) == 2):
                out = out[:-2] + [out[-2] + " " + out[-1].split("\t", 1)[1]]      # two lines became one
            reply = "<think>let me see</think>\n" + "\n".join(out) if cls.mode == "thinks" else "\n".join(out)
        self._send(200, {"choices": [{"message": {"role": "assistant", "content": reply}}]})


@pytest.fixture
def llm(monkeypatch):
    FakeLLM.mode, FakeLLM.requests = "good", []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeLLM)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.delenv("BABELSCRIBE_LLM", raising=False)
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()


@pytest.fixture
def talk(tmp_path):
    writers.write(json.loads(json.dumps(SEGS)), tmp_path / "talk", ["json", "srt"], {"lang": "en", "model": "turbo"})
    return tmp_path / "talk.json"


def cues(path: Path) -> list[tuple[str, str, str]]:
    out = []
    for block in path.read_text(encoding="utf-8").strip().split("\n\n"):
        _, stamp, *text = block.split("\n")
        out.append((*stamp.split(" --> "), "\n".join(text)))
    return out


# ---------------------------------------------------------------- one line in, one line out

@pytest.mark.parametrize("mode", ["good", "thinks", "merges-once", "merges", "strict"])
def test_every_subtitle_comes_back_once_and_in_order_whatever_the_model_does(llm, mode):
    FakeLLM.mode = mode
    said: list[str] = []
    texts = [s["text"] for s in SEGS]
    out = lt.translate_texts(texts, "th", lt.chat_fn(llm, "fake-model"), "en", said.append)
    assert out == [THAI[t] for t in texts]
    if mode == "merges":
        assert any("one at a time" in m for m in said), "said that it fell back"
    if mode == "strict":
        assert "reasoning_effort" in FakeLLM.requests[0] and "reasoning_effort" not in FakeLLM.requests[-1]


def test_a_line_the_model_never_answers_keeps_its_text():
    replies = iter(["nonsense", "more nonsense", "สวัสดี", ""])
    out = lt.translate_texts(["Hello.", "Bye."], "th", lambda messages: next(replies), log=lambda m: None)
    assert out == ["สวัสดี", "Bye."]


def test_batches_carry_the_lines_before_them_as_context():
    seen = []

    def call(messages):
        seen.append(messages[-1]["content"])
        return "\n".join(f"{n}\tT{n}" for n in re.findall(r"^(\d+)\t", messages[-1]["content"], re.MULTILINE))

    out = lt.translate_texts([f"line {i}" for i in range(1, 6)], "ja", call, log=lambda m: None, batch=2)
    assert len(out) == 5 and len(seen) == 3
    assert "context only" not in seen[0] and "line 2  =>  T2" in seen[1] and "into Japanese" in seen[1]


# ---------------------------------------------------------------- the files

def test_translated_files_keep_the_timing_and_wrap_for_the_target_language(llm, talk):
    before = talk.with_suffix(".srt").read_text(encoding="utf-8")
    r = lt.translate_file(talk, "th", llm, formats=["srt", "json"], log=lambda m: None)
    assert [Path(f).name for f in r["files"]] == ["talk.th.srt", "talk.th.json"]
    assert r["segments"] == 3 and r["lang"] == "th" and r["model"] == "fake-model"
    assert talk.with_suffix(".srt").read_text(encoding="utf-8") == before, "the original is never touched"

    data = json.loads((talk.parent / "talk.th.json").read_text(encoding="utf-8"))
    assert [(s["start"], s["end"]) for s in data["segments"]] == [(s["start"], s["end"]) for s in SEGS]
    assert [s["text"] for s in data["segments"]] == [THAI[s["text"]] for s in SEGS]
    assert data["meta"]["lang"] == "th" and data["meta"]["translated_from"] == "en"

    got = cues(talk.parent / "talk.th.srt")
    assert got[0] == ("00:00:00,500", "00:00:03,000", "สวัสดีครับ") and got[-1][:2] == ("00:00:10,000", "00:00:11,000")
    middle = got[1:-1]
    assert len(middle) > 1, "the long line became several subtitles"
    assert middle[0][0] == "00:00:03,200" and middle[-1][1] == "00:00:09,900", "inside its own segment's time"
    for _, _, text in got:
        assert all(len(line) <= writers.CJK_THAI_MAX_LINE_CHARS for line in text.split("\n")), text
        assert text[0] not in lt._JOINS_BACK, "no line starts with a vowel or tone mark cut from its consonant"
    assert "".join(t.replace("\n", "") for _, _, t in middle) == THAI[SEGS[1]["text"]]


def test_an_srt_can_be_translated_cue_for_cue(llm, talk):
    srt = talk.with_suffix(".srt")
    r = lt.translate_file(srt, "Japanese", llm, log=lambda m: None)
    assert Path(r["files"][0]).name == "talk.ja.srt" and r["segments"] == len(cues(srt))
    assert cues(Path(r["files"][0]))[0][:2] == cues(srt)[0][:2]


def test_the_output_cannot_be_the_input(llm, talk):
    with pytest.raises(ValueError, match="overwrite"):
        lt.translate_file(talk, "th", llm, formats=["json"], out=talk.with_suffix(""), log=lambda m: None)


# ---------------------------------------------------------------- the endpoint

def test_language_names_and_codes():
    assert lt.language("th") == ("th", "Thai") and lt.language("Thai") == ("th", "Thai")
    assert lt.language("Chinese") == ("zh", "Chinese (Simplified)")
    assert lt.language("Swiss German") == ("swiss-german", "Swiss German"), "unknown: passed on as written"
    with pytest.raises(ValueError):
        lt.language(" ")


@pytest.mark.parametrize("url,local", [
    ("http://127.0.0.1:8080/v1", True), ("http://localhost:11434/v1", True), ("http://[::1]:1234/v1", True),
    ("http://192.168.1.20:8080/v1", False), ("https://api.example.com/v1", False),
    ("http://127.0.0.1.example.com/v1", False), ("http://localhost.example.com/v1", False)])
def test_only_this_computer_counts_as_local(url, local):
    assert lt.is_local(url) is local


def test_a_remote_endpoint_is_refused_unless_allowed(llm, monkeypatch):
    with pytest.raises(SystemExit, match="not on this computer.*--allow-remote"):
        lt.find_endpoint("https://api.example.com/v1")
    monkeypatch.setattr(lt, "is_local", lambda url: False)          # the fake server, treated as a remote one
    with pytest.raises(SystemExit, match="--allow-remote"):
        lt.find_endpoint(llm)
    assert lt.find_endpoint(llm, allow_remote=True) == (llm, ["fake-model"])


def test_no_llm_running_says_how_to_start_one(monkeypatch):
    monkeypatch.delenv("BABELSCRIBE_LLM", raising=False)
    monkeypatch.setattr(lt, "DEFAULT_ENDPOINTS", ("http://127.0.0.1:9/v1",))
    with pytest.raises(SystemExit, match="(?s)no local LLM answered.*ollama serve.*--llm"):
        lt.find_endpoint()


def test_the_endpoint_can_come_from_the_environment(llm, monkeypatch):
    monkeypatch.setenv("BABELSCRIBE_LLM", llm)
    assert lt.find_endpoint()[0] == llm


# ---------------------------------------------------------------- the command line and MCP

def test_translate_to_flag_checks_the_llm_before_transcribing(tmp_path, monkeypatch):
    audio = tmp_path / "talk.wav"; audio.touch()
    monkeypatch.delenv("BABELSCRIBE_LLM", raising=False)
    monkeypatch.setattr(lt, "DEFAULT_ENDPOINTS", ("http://127.0.0.1:9/v1",))
    monkeypatch.setattr(api, "transcribe_file", lambda **kw: pytest.fail("transcribed without an LLM to translate"))
    with pytest.raises(SystemExit, match="no local LLM answered"):
        cli.main([str(audio), "--translate-to", "th"])


def test_translate_to_flag_writes_the_translation_next_to_the_subtitles(llm, talk, monkeypatch, capsys):
    seen = {}

    def fake_transcribe(src, formats, out, **kw):
        seen["formats"] = formats
        return {"files": [str(talk.with_suffix(".srt")), str(talk)]}

    monkeypatch.setattr(api, "transcribe_file", fake_transcribe)
    (talk.parent / "talk.wav").touch()
    cli.main([str(talk.parent / "talk.wav"), "-f", "srt", "--translate-to", "th", "--llm", llm])
    assert seen["formats"] == ["srt", "json"]
    assert cues(talk.parent / "talk.th.srt")[0][2] == "สวัสดีครับ"
    assert not (talk.parent / "talk.th.json").exists(), "only the formats that were asked for"


def test_translate_command(llm, talk, capsys):
    cli.main(["translate", str(talk), "--to", "th", "--llm", llm, "-f", "vtt"])
    assert (talk.parent / "talk.th.vtt").read_text(encoding="utf-8").startswith("WEBVTT")
    with pytest.raises(SystemExit, match="no such file"):
        cli.main(["translate", str(talk.parent / "nope.json"), "--to", "th", "--llm", llm])


def test_mcp_tool_translates_and_cannot_be_pointed_at_another_machine(llm, talk, monkeypatch):
    pytest.importorskip("mcp.server.mcpserver")
    import anyio
    from babelscribe import mcp_server
    srv = mcp_server.build()

    async def call(args):
        return await srv.call_tool("translate_subtitles", args)

    out = anyio.run(call, {"path": str(talk), "target": "th", "llm_url": llm})
    assert "talk.th.srt" in str(out) and (talk.parent / "talk.th.srt").is_file()
    monkeypatch.delenv("BABELSCRIBE_LLM_ALLOW_REMOTE", raising=False)
    with pytest.raises(Exception, match="not on this computer"):
        anyio.run(call, {"path": str(talk), "target": "th", "llm_url": "https://api.example.com/v1"})
