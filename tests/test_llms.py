"""Which local LLMs answer (`babelscribe llms`), for the desktop app's list of translators."""
import http.client
import json

import pytest

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
    assert set(by) == {"llama-server", "localllm", "Ollama", "LM Studio", "colibri"}


def test_a_server_that_answers_with_something_else_is_not_up(monkeypatch):
    def get(*a, **k):
        raise ValueError("not json")
    monkeypatch.setattr(llm_translate, "_get_json", get)
    assert not any(g["up"] for g in llm_translate.scan())


def test_llms_command_prints_json_and_plain_text(monkeypatch, capsys):
    monkeypatch.setattr(llm_translate, "_get_json", fake({"http://127.0.0.1:8080/v1": ["m"]}))
    cli.main(["llms", "--json", "--exit-when-stdin-closes"])
    got = json.loads(capsys.readouterr().out)
    assert got[0]["up"] and got[0]["models"] == ["m"] and len(got) == 5
    cli.main(["llms"])
    out = capsys.readouterr().out
    assert "llama-server" in out and "not running" in out


COLIBRI = "http://127.0.0.1:8000/v1"


def serves(monkeypatch, replies):
    """replies: base -> what GET base/models returns, or the exception it raises."""
    def get(url, payload=None, timeout=600, key=None):
        reply = replies.get(url.rsplit("/models", 1)[0], OSError("connection refused"))
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.delenv("BABELSCRIBE_LLM", raising=False)
    monkeypatch.setattr(llm_translate, "_get_json", get)


def at_8000():
    return next(g for g in llm_translate.scan() if g["url"] == COLIBRI)


def test_colibri_is_recognised_by_what_its_model_list_says(monkeypatch):
    assert at_8000()["kind"] == "colibri"
    serves(monkeypatch, {COLIBRI: {"object": "list", "data": [{"id": "glm", "object": "model", "owned_by": "colibri"}]}})
    assert at_8000() == {"url": COLIBRI, "kind": "colibri", "up": True, "models": ["glm"]}
    assert llm_translate.find_endpoint() == (COLIBRI, ["glm"])
    serves(monkeypatch, {COLIBRI: {"data": [{"id": "m", "owned_by": "vllm"}]}})
    assert at_8000() == {"url": COLIBRI, "kind": "local server", "up": True, "models": ["m"]}


def test_the_ports_people_already_use_come_first(monkeypatch):
    serves(monkeypatch, {COLIBRI: {"data": [{"id": "c"}]}, "http://127.0.0.1:1234/v1": {"data": [{"id": "lm"}]}})
    assert llm_translate.find_endpoint() == ("http://127.0.0.1:1234/v1", ["lm"])


@pytest.mark.parametrize("reply", [{"detail": "Not Found"}, {"data": []}, {"data": "yes"}, ["a", "b"], "text", 7, None,
                                   http.client.BadStatusLine("SSH-2.0"), ValueError("<html>"), OSError("HTTP 404")],
                         ids=lambda r: str(r)[:20])
def test_something_else_on_the_shared_port_is_neither_a_crash_nor_a_translator(monkeypatch, reply):
    serves(monkeypatch, {COLIBRI: reply})
    assert not at_8000()["up"]
    with pytest.raises(SystemExit, match="no local LLM answered"):
        llm_translate.find_endpoint()


@pytest.mark.parametrize("reply", [["a"], "text", {"data": 3}, http.client.BadStatusLine("x")], ids=lambda r: str(r)[:20])
def test_a_strange_answer_on_any_port_or_url_is_passed_over(monkeypatch, reply):
    serves(monkeypatch, {"http://127.0.0.1:8080/v1": reply})
    assert not any(g["up"] for g in llm_translate.scan())
    with pytest.raises(SystemExit):
        llm_translate.find_endpoint("http://127.0.0.1:8080/v1")


def test_ollama_with_no_model_yet_still_counts_and_a_url_given_by_hand_is_trusted(monkeypatch):
    serves(monkeypatch, {"http://127.0.0.1:11434/v1": {"object": "list", "data": None}, COLIBRI: {"data": []}})
    by = {g["kind"]: g for g in llm_translate.scan()}
    assert by["Ollama"]["up"] and by["Ollama"]["models"] == []
    assert llm_translate.find_endpoint() == ("http://127.0.0.1:11434/v1", [])
    assert llm_translate.find_endpoint(COLIBRI) == (COLIBRI, [])
