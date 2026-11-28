"""Which local LLMs answer (`babelscribe llms`), for the desktop app's list of translators."""
import json

from babelscribe import cli, llm_translate


def fake(up):
    def get(url, payload=None, timeout=600, key=None):
        base = url.rsplit("/models", 1)[0]
        if base not in up:
            raise OSError("connection refused")
        return {"data": [{"id": m} for m in up[base]] + [{"no": "id"}, "junk"]}
    return get


def test_scan_lists_every_usual_port_and_says_which_answer(monkeypatch):
    monkeypatch.setattr(llm_translate, "_get_json", fake({"http://127.0.0.1:11434/v1": ["gemma3", "qwen3"]}))
    got = llm_translate.scan()
    assert [g["url"] for g in got] == list(llm_translate.DEFAULT_ENDPOINTS)
    by = {g["kind"]: g for g in got}
    assert by["Ollama"]["up"] and by["Ollama"]["models"] == ["gemma3", "qwen3"]
    assert not by["LM Studio"]["up"] and by["LM Studio"]["models"] == []
    assert set(by) == {"llama-server", "localllm", "Ollama", "LM Studio"}


def test_a_server_that_answers_with_something_else_is_not_up(monkeypatch):
    def get(*a, **k):
        raise ValueError("not json")
    monkeypatch.setattr(llm_translate, "_get_json", get)
    assert not any(g["up"] for g in llm_translate.scan())


def test_llms_command_prints_json_and_plain_text(monkeypatch, capsys):
    monkeypatch.setattr(llm_translate, "_get_json", fake({"http://127.0.0.1:8080/v1": ["m"]}))
    cli.main(["llms", "--json", "--exit-when-stdin-closes"])
    got = json.loads(capsys.readouterr().out)
    assert got[0]["up"] and got[0]["models"] == ["m"] and len(got) == 4
    cli.main(["llms"])
    out = capsys.readouterr().out
    assert "llama-server" in out and "not running" in out
