from pathlib import Path

from babelscribe import align, backend, writers


def test_asset_name_is_known_flavour():
    name = backend.asset_name()
    assert name.startswith("whisper-cli-") and name.endswith(".zip")


def test_pick_device_prefers_discrete():
    found = [{"backend": "vulkan", "id": 0, "name": "Intel UHD", "detail": "uma: 1"},
             {"backend": "vulkan", "id": 1, "name": "Radeon", "detail": "uma: 0"}]
    assert backend.pick_device(found) == 1


def test_hybrid_keeps_accurate_text_and_timing():
    timing = [{"start": 0.0, "end": 2.0, "text": "helo wrld", "words": [["helo", 0.0, 1.0], [" wrld", 1.0, 2.0]]},
              {"start": 2.0, "end": 4.0, "text": "how ar you", "words": [["how", 2.0, 2.6], [" ar", 2.6, 3.2], [" you", 3.2, 4.0]]}]
    text = [{"start": 0, "end": 4, "text": "hello world how are you", "words": []}]
    out = align.hybrid(text, timing)
    assert " ".join(s["text"] for s in out) == "hello world how are you"
    assert out[0]["start"] < 0.2 and out[-1]["end"] == 4.0
    assert [s["text"] for s in out] == ["hello world", "how are you"]   # cut on the timing model segment boundary


def test_hybrid_thai_no_spaces():
    timing = [{"start": 0.0, "end": 3.0, "text": "สวัสดีครับ", "words": [["สวัสดี", 0.0, 1.5], ["ครับ", 1.5, 3.0]]}]
    out = align.hybrid([{"start": 0, "end": 3, "text": "สวัสดีครับ", "words": []}], timing)
    assert out[0]["text"] == "สวัสดีครับ"


def test_writers(tmp_path: Path):
    segs = [{"start": 0.0, "end": 1.5, "text": "hi", "words": []}]
    files = writers.write(segs, tmp_path / "x", ["srt", "vtt", "txt", "json"], {})
    assert (tmp_path / "x.srt").read_text(encoding="utf-8").startswith("1\n00:00:00,000 --> 00:00:01,500\nhi")
    assert len(files) == 4


def test_accurate_models_resolve():
    from babelscribe import cli, models  # noqa: F401  (import catches syntax errors in every module)
    for lang, name in models.ACCURATE.items():
        _, ft = models.resolve(name)
        assert ft and ft["lang"] == lang
