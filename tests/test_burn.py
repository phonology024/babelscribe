"""`--burn` / `babelscribe burn` (#58): the video with the subtitles drawn on it."""
import json
import subprocess
from pathlib import Path

import pytest

from babelscribe import api, burn, cli, writers

WIDE = """Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'C:\\clips\\my talk.mp4':
  Duration: 00:01:02.50, start: 0.000000, bitrate: 3206 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(tv, progressive), 1920x1080 [SAR 1:1 DAR 16:9], 3068 kb/s, 30 fps
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 48000 Hz, stereo, fltp, 128 kb/s
"""
PHONE = """  Duration: 00:00:11.00, start: 0.000000, bitrate: 900 kb/s
  Stream #0:0[0x1](und): Video: hevc (Main) (hvc1 / 0x31637668), yuv420p(tv, bt709), 1920x1080, 800 kb/s, 30 fps
    Side data:
      displaymatrix: rotation of -90.00 degrees
"""
AUDIO = """  Duration: 00:00:11.00, start: 0.000000, bitrate: 256 kb/s
  Stream #0:0: Audio: pcm_s16le ([1][0][0][0] / 0x0001), 16000 Hz, mono, s16, 256 kb/s
"""


def words(text: str, start: float = 0.0, each: float = 0.4) -> list:
    import re
    return [[tok, round(start + i * each, 3), round(start + (i + 1) * each, 3)]
            for i, tok in enumerate(re.findall(r"\s*\S+", " " + text))]


def segment(text: str, start: float = 0.0) -> dict:
    w = words(text, start)
    return {"start": w[0][1], "end": w[-1][2], "text": text, "words": w}


def style_line(doc: str) -> list[str]:
    return next(x for x in doc.splitlines() if x.startswith("Style:")).split(",")


def events(doc: str) -> list[str]:
    return [x.split(",,", 1)[1].split(",,", 1)[-1] for x in doc.splitlines() if x.startswith("Dialogue:")]


# ---------------------------------------------------------------- the video

def test_size_is_read_as_the_video_is_shown():
    assert burn.parse_size(WIDE) == (1920, 1080)
    assert burn.parse_size(PHONE) == (1080, 1920), "a phone video stored sideways is a vertical video"
    assert burn.parse_duration(WIDE) == 62.5 and burn.parse_duration("no length here") == 0.0


def test_an_audio_file_is_refused_with_the_reason():
    with pytest.raises(SystemExit, match="no video to draw subtitles on"):
        burn.parse_size(AUDIO, "talk.wav")


# ---------------------------------------------------------------- the filter string

@pytest.mark.parametrize("video", [r"C:\Users\me\My Clips\it's a [clip], 50% done.mp4", "/home/me/my clip: part 1.mp4"])
def test_the_filter_never_contains_the_users_path(video):
    """Drive-letter colons, spaces, quotes, commas and brackets all mean something inside an ffmpeg filter.
    The subtitle file is copied to a fixed name in a temp folder and ffmpeg runs there, so none can appear."""
    cmd = burn.burn_command("ffmpeg", Path(video), Path(video).with_suffix(".subbed.mp4"), "subs.ass", burn.SOFTWARE)
    assert cmd[cmd.index("-vf") + 1] == "ass=subs.ass"
    assert cmd[cmd.index("-i") + 1] == str(Path(video)) and cmd[-1] == str(Path(video).with_suffix(".subbed.mp4"))
    assert cmd[cmd.index("-c:a") + 1] == "copy", "audio is copied, not encoded again"


# ---------------------------------------------------------------- preset -> ASS style

def test_each_look_becomes_its_ass_style():
    segs = [segment("And so my fellow Americans ask not what your country can do for you")]
    docs = {s: burn.ass_document(segs, {"lang": "en"}, s, 1080, 1920, font="Arial") for s in burn.STYLES}
    for doc in docs.values():
        assert "PlayResX: 1080\nPlayResY: 1920\n" in doc, "sizes are in the video's own pixels"
    plain, karaoke, shorts = (style_line(docs[s]) for s in burn.STYLES)
    assert plain[1] == "Arial" and int(shorts[2]) > int(plain[2]), "shorts is the big one"
    assert shorts[7] == "-1" and plain[7] == "0", "and bold"
    assert int(shorts[21]) > int(plain[21]) > 0, "and sits higher, above the app's buttons"
    assert plain[3] == burn.WHITE and karaoke[3] == burn.AMBER and shorts[3] == burn.YELLOW
    assert "\\k" not in "".join(events(docs["plain"])) and "\\k" in events(docs["karaoke"])[0]
    assert all(len(e.replace("\\N", " ").split("}")) - 1 <= 3 for e in events(docs["shorts"])), "three words at most"
    assert len(events(docs["shorts"])) >= 5 > len(events(docs["plain"]))


def test_text_size_follows_the_picture():
    small = burn.layout("plain", 640, 360, "latin", "en")
    big = burn.layout("plain", 3840, 2160, "latin", "en")
    assert big["size"] == 6 * small["size"] and abs(big["bottom"] - 6 * small["bottom"]) <= 3
    tall, wide = burn.layout("shorts", 1080, 1920, "latin"), burn.layout("shorts", 1920, 1080, "latin")
    assert tall["bottom"] / 1920 > wide["bottom"] / 1080, "a vertical video keeps the bottom third clear"
    with pytest.raises(SystemExit, match="unknown style"):
        burn.layout("neon", 1920, 1080, "latin")


def test_shorts_cuts_at_a_sentence_end_and_at_a_pause():
    seg = segment("Yes. We can do")
    seg["words"][3][1] += 2.0; seg["words"][3][2] += 2.0       # a two-second pause before "do"
    assert [c["text"] for c in burn.short_cues([seg], 40)] == ["Yes.", "We can", "do"]
    no_words = {"start": 0.0, "end": 2.0, "text": "kept whole", "words": []}
    assert [c["text"] for c in burn.short_cues([no_words], 40)] == ["kept whole"]


def test_thai_is_never_cut_between_a_consonant_and_its_vowel_or_tone_mark(monkeypatch):
    monkeypatch.setattr(burn.align, "_word_breaks", lambda text: set())      # as when pythainlp is not installed
    toks = [[t, i * 0.1, i * 0.1 + 0.1] for i, t in enumerate(["ต", "่", "อ", "เ", "ท", "ี", "่", "ยว"])]
    seg = {"start": 0.0, "end": 0.8, "text": "ต่อเที่ยว", "words": toks}
    texts = [c["text"] for c in burn.short_cues([seg], 2, script="thai")]
    assert "".join(texts) == "ต่อเที่ยว"
    for t in texts:
        assert t[0] not in burn._THAI_JOINS_BACK and t[-1] not in burn._THAI_JOINS_NEXT, texts


def test_thai_words_stay_whole_when_the_word_list_is_there(monkeypatch):
    text = "ลงทะเบียนเรียน"
    monkeypatch.setattr(burn.align, "_word_breaks", lambda t: {9})          # ลงทะเบียน | เรียน
    toks = [[ch, i * 0.1, i * 0.1 + 0.1] for i, ch in enumerate(text)]
    units = burn._units(toks, "thai")
    assert [u[0][0] for u in units] == ["ลงทะเบียน", "เรียน"]
    assert units[0][0][1] == 0.0 and round(units[1][0][2], 3) == 1.4, "each word keeps the time of its letters"


# ---------------------------------------------------------------- fonts

def test_the_script_is_read_from_the_text():
    assert burn.script_of("Hello there") == "latin"
    assert burn.script_of("สวัสดีครับ hello") == "thai"
    assert burn.script_of("こんにちは世界") == "japanese" and burn.script_of("你好世界") == "chinese"
    assert burn.script_of("世界", "ja") == "japanese"
    assert burn.script_of("안녕하세요") == "korean" and burn.script_of("नमस्ते") == "devanagari"
    assert burn.script_of("مرحبا") == "arabic"


def test_a_font_that_has_the_letters_is_picked_or_named():
    assert burn.pick_font("thai", {"arial", "leelawadee ui bold", "tahoma"}) == "Leelawadee UI"
    assert burn.pick_font("thai", {"dejavu sans", "noto sans thai"}) == "Noto Sans Thai"
    assert burn.pick_font("latin", {"something else"}) == "Arial"
    with pytest.raises(SystemExit, match="no font for thai.*Noto Sans Thai.*--font"):
        burn.pick_font("thai", {"dejavu sans", "arial"})
    # the list of fonts is unknown (macOS without fontconfig): the font the system ships with
    assert burn.pick_font("thai", set(), system="Darwin") == "Thonburi"
    assert burn.pick_font("japanese", set(), system="Windows") == "Yu Gothic"


# ---------------------------------------------------------------- subtitle files

def test_an_srt_is_read_back_as_cues(tmp_path):
    p = tmp_path / "a.srt"
    p.write_text("1\n00:00:01,000 --> 00:00:02,500\nHello <i>there</i>\nfriend\n\n2\n01:00:00,000 --> 01:00:01,000\nBye\n",
                 encoding="utf-8")
    assert burn.read_srt(p) == [{"start": 1.0, "end": 2.5, "text": "Hello there friend", "words": []},
                                {"start": 3600.0, "end": 3601.0, "text": "Bye", "words": []}]


def test_the_subtitles_next_to_the_video_are_found_json_first(tmp_path):
    video = tmp_path / "clip.mp4"; video.touch()
    with pytest.raises(SystemExit, match="no subtitles found next to clip.mp4"):
        burn.find_subtitles(video)
    (tmp_path / "clip.srt").touch()
    assert burn.find_subtitles(video).name == "clip.srt"
    (tmp_path / "clip.json").touch()
    assert burn.find_subtitles(video).name == "clip.json"


def test_a_folder_run_does_not_pick_up_burned_videos(tmp_path):
    for name in ("clip.mp4", "clip.subbed.mp4", "talk.SUBBED.mp4", "other.mp3"):
        (tmp_path / name).touch()
    assert [p.name for p, _ in api.collect_media([tmp_path])] == ["clip.mp4", "other.mp3"]
    assert [p.name for p, _ in api.collect_media([tmp_path / "clip.subbed.mp4"])] == ["clip.subbed.mp4"], "named: taken"


# ---------------------------------------------------------------- the command line

def test_burn_flag_transcribes_then_burns_from_the_json(tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"; video.touch()
    seen = {}

    def fake_transcribe(src, formats, out, **kw):
        seen["formats"] = formats
        return {"files": [str(tmp_path / "clip.srt"), str(tmp_path / "clip.json")]}

    monkeypatch.setattr(api, "transcribe_file", fake_transcribe)
    monkeypatch.setattr(burn, "burn_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(burn, "video_size", lambda path, ffmpeg=None: (1080, 1920))
    monkeypatch.setattr(burn, "burn_file", lambda *a, **kw: seen.update(burn=a))
    cli.main([str(video), "-f", "srt", "--burn", "--style", "shorts"])
    assert seen["formats"] == ["srt", "json"], "the JSON is what the looks are drawn from"
    assert seen["burn"][:4] == (video, str(tmp_path / "clip.json"), "shorts", str(tmp_path / "clip.subbed.mp4"))


def test_burn_flag_refuses_an_audio_file_before_transcribing_it(tmp_path, monkeypatch):
    audio = tmp_path / "talk.wav"; audio.touch()
    monkeypatch.setattr(burn, "burn_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(burn, "probe", lambda path, ffmpeg=None: AUDIO)
    monkeypatch.setattr(api, "transcribe_file", lambda **kw: pytest.fail("transcribed anyway"))
    with pytest.raises(SystemExit, match="no video to draw subtitles on"):
        cli.main([str(audio), "--burn"])


def test_an_ffmpeg_without_libass_is_reported_with_what_to_install(monkeypatch):
    monkeypatch.setattr(burn.transcribe, "ffmpeg", lambda: "/opt/thin/ffmpeg")
    monkeypatch.setattr(burn, "has_libass", lambda exe: False)
    with pytest.raises(SystemExit, match="(?s)built without libass.*brew install ffmpeg"):
        burn.burn_ffmpeg()


# ---------------------------------------------------------------- for real

@pytest.fixture(scope="module")
def ffmpeg():
    try:
        return burn.burn_ffmpeg()
    except SystemExit as e:
        pytest.skip(f"no ffmpeg with libass here: {e}")


def frame(ffmpeg: str, video: Path, at: float, crop: str) -> bytes:
    """Raw grey pixels of one region of one frame."""
    return subprocess.run([ffmpeg, "-v", "error", "-ss", str(at), "-i", str(video), "-frames:v", "1",
                           "-vf", f"crop={crop},format=gray", "-f", "rawvideo", "-"],
                          capture_output=True, check=True).stdout


@pytest.mark.parametrize("style", burn.STYLES)
def test_real_burn_draws_the_words_and_leaves_the_input_alone(ffmpeg, tmp_path, style):
    folder = tmp_path / "my clips, it's [1]"       # every character that breaks a naive subtitles= filter
    folder.mkdir()
    video = folder / "a clip.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=black:size=360x640:rate=10:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(video)], check=True, capture_output=True)
    before = video.read_bytes()
    writers.write([segment("Hello there my friend", 0.5)], folder / "a clip", ["json"], {"lang": "en"})

    seen: list[float] = []
    r = burn.burn_file(video, style=style, log=lambda m: None, progress=seen.append)

    out = Path(r["file"])
    assert out == folder / "a clip.subbed.mp4" and out.stat().st_size > 1000
    assert r["size"] == "360x640" and r["style"] == style and r["subtitles"].endswith("a clip.json")
    assert video.read_bytes() == before, "the input video is never changed"
    assert seen and seen[-1] == 100.0 and seen == sorted(seen)
    info = burn.probe(out, ffmpeg)
    assert burn.parse_size(info) == (360, 640) and "Audio:" in info and abs(burn.parse_duration(info) - 3) < 0.5
    lower = "360:400:0:240"
    assert max(frame(ffmpeg, out, 1.0, lower)) > 200, "white text on the black picture while the words are spoken"
    assert max(frame(ffmpeg, out, 2.8, lower)) < 60, "and nothing after the last word"
    assert max(frame(ffmpeg, video, 1.0, lower)) < 60


def test_real_burn_of_an_edited_ass_and_of_an_srt(ffmpeg, tmp_path):
    video = tmp_path / "clip.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=black:size=320x240:rate=10:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True, capture_output=True)
    writers.write([segment("Hello there", 0.2)], tmp_path / "clip", ["ass", "srt"], {"lang": "en"})
    for subs, used in ((tmp_path / "clip.ass", "as written in the .ass"), (tmp_path / "clip.srt", "plain")):
        said: list[str] = []
        r = burn.burn_file(video, subs, style="karaoke", out=tmp_path / f"out{subs.suffix}.mp4", log=said.append)
        assert r["style"] == used and max(frame(ffmpeg, Path(r["file"]), 0.6, "320:240:0:0")) > 200
    assert any("no word timings" in m for m in said), "an .srt can only be drawn plain, and says so"
    with pytest.raises(SystemExit, match="overwrite the input"):
        burn.burn_file(video, tmp_path / "clip.srt", out=video)
