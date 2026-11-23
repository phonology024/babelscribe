"""Free memory (#18): detection on each OS from canned system output, the fit rule, and what transcribe_file does with it."""
import json

import pytest

from babelscribe import api, cli, hybrid, models, ram, transcribe

GB = 1024


def machine(free_gb, total_gb=16):
    return {"total_mb": int(total_gb * GB), "available_mb": int(free_gb * GB)}


def free_for(name):
    """Just enough free memory for `name` (and not for anything that needs more)."""
    return {"total_mb": 64 * GB, "available_mb": ram.need_mb(name)}


# ------------------------------------------------------------------------------------------------- the table

def test_every_model_has_a_measured_need_and_bigger_models_need_more():
    for name in list(models.GENERAL) + list(models.FINETUNES):
        r = models.RAM_MB[name]
        assert r["cpu"] > 0 and r["gpu"] > 0, name
        assert r["gpu"] <= r["cpu"] + 512, name              # a card's own memory takes the weights off the RAM
    cpu = lambda n: models.RAM_MB[n]["cpu"]                   # noqa: E731
    assert cpu("tiny") < cpu("base") < cpu("small") < cpu("medium")
    assert cpu("large-v3-turbo") < cpu("large-v3")


# ------------------------------------------------------------------------------------------------- detection

MEMINFO = """MemTotal:       16318524 kB
MemFree:         1203292 kB
MemAvailable:    9876544 kB
Buffers:          102400 kB
Cached:          4000000 kB
"""


def test_linux_meminfo():
    assert ram.parse_meminfo(MEMINFO) == {"total_mb": 16318524 // 1024, "available_mb": 9876544 // 1024}


def test_linux_meminfo_of_an_old_kernel_without_memavailable():
    old = "MemTotal: 2048000 kB\nMemFree: 100000 kB\nBuffers: 50000 kB\nCached: 350000 kB\n"
    assert ram.parse_meminfo(old) == {"total_mb": 2000, "available_mb": 500000 // 1024}


@pytest.mark.parametrize("text", ["", "garbage\n", "MemFree: 5 kB\n"])
def test_linux_meminfo_that_cannot_be_read_is_unknown(text):
    assert ram.parse_meminfo(text) is None


VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               20000.
Pages active:                            300000.
Pages inactive:                          100000.
Pages speculative:                        10000.
Pages purgeable:                           5000.
"""


def test_macos_vm_stat():
    got = ram.parse_vm_stat(VM_STAT, 16 * GB * 1024 * 1024)
    assert got == {"total_mb": 16 * GB, "available_mb": (20000 + 100000 + 10000) * 16384 // (1024 * 1024)}


def test_macos_output_that_cannot_be_read_is_unknown():
    assert ram.parse_vm_stat("nothing useful", 8 << 30) is None
    assert ram.parse_vm_stat(VM_STAT, 0) is None


def test_a_container_limit_wins_over_the_hosts_free_memory():
    files = {"/proc/meminfo": MEMINFO, "/sys/fs/cgroup/memory.max": "2147483648\n",
             "/sys/fs/cgroup/memory.current": "1073741824\n"}
    assert ram._linux(files.get) == {"total_mb": 16318524 // 1024, "available_mb": 1024}


@pytest.mark.parametrize("files", [
    {"/sys/fs/cgroup/memory.max": "max\n", "/sys/fs/cgroup/memory.current": "123\n"},               # cgroup v2, no limit
    {"/sys/fs/cgroup/memory/memory.limit_in_bytes": "9223372036854771712\n",
     "/sys/fs/cgroup/memory/memory.usage_in_bytes": "123\n"},                                        # cgroup v1, no limit
    {}])                                                                                              # not in a cgroup
def test_no_container_limit_means_the_hosts_numbers_stand(files):
    assert ram.container_limit_mb(files.get) is None
    assert ram._linux({"/proc/meminfo": MEMINFO, **files}.get)["available_mb"] == 9876544 // 1024


def test_container_limit_v1_counts_down_to_zero_and_not_below():
    files = {"/sys/fs/cgroup/memory/memory.limit_in_bytes": "1048576\n",
             "/sys/fs/cgroup/memory/memory.usage_in_bytes": "9999999\n"}
    assert ram.container_limit_mb(files.get) == 0


def test_detect_calls_the_one_for_this_os_and_returns_its_numbers(monkeypatch):
    monkeypatch.setattr(ram, "_linux", lambda: machine(3))
    monkeypatch.setattr(ram.sys, "platform", "linux")
    assert ram.detect() == machine(3)


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux", "freebsd13"])
def test_detect_gives_up_quietly(monkeypatch, platform):
    def boom(*a, **k):
        raise OSError("no /proc here")
    for fn in ("_windows", "_macos", "_linux"):
        monkeypatch.setattr(ram, fn, boom)
    monkeypatch.setattr(ram.sys, "platform", platform)
    assert ram.detect() is None


@pytest.mark.parametrize("bad", [{"total_mb": 0, "available_mb": 0}, {"total_mb": 8, "available_mb": -1}, {}])
def test_detect_refuses_numbers_that_cannot_be_true(monkeypatch, bad):
    monkeypatch.setattr(ram, "_linux", lambda: bad)
    monkeypatch.setattr(ram.sys, "platform", "linux")
    assert ram.detect() is None


def test_detect_on_this_computer_is_either_unknown_or_sane():
    got = ram.detect()
    assert got is None or 0 < got["available_mb"] <= got["total_mb"]


# ------------------------------------------------------------------------------------------------- the rule

def test_default_turbo_stays_when_it_fits():
    assert ram.choose_default("turbo", machine(16)) == ("turbo", None)
    assert ram.choose_default("turbo", free_for("turbo")) == ("turbo", None)


def test_nothing_is_changed_when_memory_is_unknown():
    assert ram.choose_default("turbo", None) == ("turbo", None)
    assert ram.warning("large-v3", None) is None


def test_default_that_does_not_fit_becomes_the_largest_that_does_with_one_line():
    for want in ("small", "base", "tiny"):
        got, say = ram.choose_default("turbo", free_for(want))
        assert got == want
        assert "\n" not in say and "turbo" in say and want in say and "-m turbo" in say


def test_default_picks_the_largest_not_the_first_that_fits():
    ten_below_turbo = {"total_mb": 64 * GB, "available_mb": ram.need_mb("turbo") - 1}
    got, _ = ram.choose_default("turbo", ten_below_turbo)
    assert got == "small" if ram.fits("small", ten_below_turbo) else got in ("base", "tiny")
    assert ram.fits(got, ten_below_turbo)


def test_when_even_tiny_does_not_fit_tiny_is_used_and_the_line_says_so():
    got, say = ram.choose_default("turbo", machine(0.3, 4))
    assert got == "tiny" and "even tiny" in say


def test_warning_names_the_model_the_numbers_and_a_smaller_one_that_fits():
    say = ram.warning("large-v3", free_for("small"))
    assert "large-v3" in say and "-m small" in say and "free" in say and "\n" not in say
    assert ram.warning("large-v3", machine(32)) is None


def test_warning_for_the_smallest_model_has_no_smaller_one_to_offer():
    say = ram.warning("tiny", machine(0.2, 4))
    assert "-m" not in say and "Close other programs" in say


def test_a_discrete_gpu_figure_is_mentioned_only_when_it_would_fit():
    low = {"total_mb": 8 * GB, "available_mb": ram.need_mb("large-v3") - 1}      # CPU run does not fit, a GPU run does
    assert "graphics card" in ram.warning("large-v3", low)
    assert "graphics card" not in ram.warning("large-v3", machine(0.3, 4))


def test_every_fine_tune_is_judged_like_a_large_model():
    for name in models.FINETUNES:
        assert ram.warning(name, machine(0.5, 4)) and ram.warning(name, machine(32)) is None


def test_report_for_programs_lists_every_model_with_the_engines_own_words():
    r = ram.report(free_for("small"))
    by = {m["name"]: m for m in r["models"]}
    assert set(by) == set(models.GENERAL) | set(models.FINETUNES)
    assert by["small"]["fits"] is True and by["small"]["warning"] is None
    assert by["large-v3"]["fits"] is False and "large-v3" in by["large-v3"]["warning"]
    assert r["default"] == "turbo" and r["default_used"] == "small" and "small" in r["default_note"]
    assert r["accurate"]["th"] == "thai-pathumma" and r["accurate"]["*"] == "large-v3"
    json.dumps(r, ensure_ascii=True)


def test_report_when_memory_is_unknown_marks_nothing():
    r = ram.report(None)
    assert r["ram"] is None and r["default_used"] == "turbo" and r["default_note"] is None
    assert all(m["fits"] is None and m["warning"] is None for m in r["models"])


def test_models_json_prints_the_report_and_plain_models_is_unchanged(monkeypatch, capsys):
    monkeypatch.setattr(ram, "detect", lambda: machine(1.5, 8))
    cli.main(["models", "--json"])
    out = capsys.readouterr().out
    assert json.loads(out)["ram"] == machine(1.5, 8) and out.isascii()
    cli.main(["models"])
    assert "general (99 languages)" in capsys.readouterr().out


# ------------------------------------------------------------------------------------------------- transcribe_file

def _run(monkeypatch, tmp_path, free, **kw):
    """transcribe_file with a computer that has `free` GB free; returns (model setup was asked for, log lines)."""
    asked, said = [], []
    monkeypatch.setattr(ram, "detect", lambda: None if free is None else machine(free))
    monkeypatch.setattr(api, "_told", set())
    monkeypatch.setattr(api, "setup", lambda model, *a, **k: asked.append(model) or (
        tmp_path / "whisper-cli", tmp_path / "m.bin", [{"id": 0, "backend": "cpu", "name": "CPU"}]))
    monkeypatch.setattr(models, "ensure", lambda *a, **k: tmp_path / "m.bin")
    monkeypatch.setattr(transcribe, "run", lambda *a, **k: [{"start": 0.0, "end": 1.0, "text": "hi", "words": []}])
    monkeypatch.setattr(hybrid, "run", lambda *a, **k: [{"start": 0.0, "end": 1.0, "text": "hi", "words": []}])
    (tmp_path / "a.wav").write_bytes(b"x")
    r = api.transcribe_file(tmp_path / "a.wav", lang="en", formats=["srt"], log=said.append, **kw)
    return asked, said, r


def test_no_model_named_and_not_enough_memory_uses_a_smaller_one_and_says_so(monkeypatch, tmp_path):
    asked, said, r = _run(monkeypatch, tmp_path, 1.5)
    assert asked[0] in ("small", "base", "tiny") and r["model"] == asked[0]
    assert sum("low memory" in s for s in said) == 1


def test_no_model_named_and_enough_memory_changes_nothing_and_says_nothing(monkeypatch, tmp_path):
    asked, said, r = _run(monkeypatch, tmp_path, 16)
    assert asked == ["turbo"] and r["model"] == "turbo" and not any(("low memory" in s or "needs about" in s) for s in said)


def test_unknown_memory_behaves_exactly_as_before(monkeypatch, tmp_path):
    asked, said, r = _run(monkeypatch, tmp_path, None)
    assert asked == ["turbo"] and not any(("low memory" in s or "needs about" in s) for s in said)


@pytest.mark.parametrize("named", ["turbo", "large-v3", "medium"])
def test_a_model_the_user_named_is_never_changed_only_warned_about(monkeypatch, tmp_path, named):
    asked, said, r = _run(monkeypatch, tmp_path, 0.9, model=named)
    assert asked == [named] and r["model"] == named
    assert sum(named in s and "needs about" in s for s in said) == 1


def test_naming_the_default_by_hand_is_a_choice_too(monkeypatch, tmp_path):
    asked, said, _ = _run(monkeypatch, tmp_path, 0.9, model="turbo")        # a plain "turbo", not api.UNCHOSEN
    assert asked == ["turbo"] and any("needs about" in s for s in said)


def test_the_model_from_BABELSCRIBE_MODEL_is_a_choice(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "DEFAULT_MODEL", "large-v3")                    # what the environment variable gives
    asked, said, _ = _run(monkeypatch, tmp_path, 0.9, model=api.DEFAULT_MODEL)
    assert asked == ["large-v3"]


def test_a_text_model_accurate_or_translate_are_choices_and_keep_the_model(monkeypatch, tmp_path):
    for extra in ({"text_model": "thai-thonburian"}, {"accurate": True}, {"translate": True}):
        asked, said, _ = _run(monkeypatch, tmp_path, 0.9, **extra)
        assert asked[0] in ("turbo", "large-v3"), extra                       # never a smaller model than asked for
        assert not any("using" in s and "instead" in s for s in said), extra


def test_text_model_that_does_not_fit_is_warned_about(monkeypatch, tmp_path):
    _, said, _ = _run(monkeypatch, tmp_path, 0.9, text_model="thai-thonburian")
    assert any("thai-thonburian" in s and "needs about" in s for s in said)


def test_accurate_warns_for_the_model_it_switches_to(monkeypatch, tmp_path):
    _, said, _ = _run(monkeypatch, tmp_path, 3.0, accurate=True)
    assert any("large-v3" in s and "needs about" in s for s in said)


def test_the_same_line_is_said_once_for_a_whole_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(ram, "detect", lambda: machine(0.9))
    monkeypatch.setattr(api, "_told", set())
    said = []
    for _ in range(3):
        api._memory(api.UNCHOSEN, None, False, False, said.append)
    assert len(said) == 1


def test_cli_without_m_hands_over_the_unchosen_default_and_with_m_a_plain_name(monkeypatch):
    seen = {}
    monkeypatch.setattr(api, "transcribe_file", lambda *a, **k: seen.update(k) or {"files": []})
    for argv, chosen in (([], False), (["-m", "turbo"], True)):
        seen.clear()
        try:
            cli.main(["x.wav", *argv, "--no-progress"])
        except SystemExit:
            pass
        assert isinstance(seen["model"], api._Unchosen) is (not chosen)
        assert seen["model"] == "turbo"


# ------------------------------------------------------------------------------------------------- long recordings

def test_a_short_recording_adds_nothing_and_a_long_one_adds_about_11_mb_a_minute():
    assert ram.extra_mb(None) == 0 and ram.extra_mb(0) == 0 and ram.extra_mb(2) == 0 and ram.extra_mb(1.5) == 0
    assert ram.extra_mb(32) == 330 and ram.extra_mb(182) == 1980
    assert ram.need_mb("small", minutes=182) == ram.need_mb("small") + 1980


def test_a_model_that_fits_a_short_file_may_not_fit_a_three_hour_one():
    free = free_for("turbo")
    assert ram.choose_default("turbo", free) == ("turbo", None)
    room = {"total_mb": 64 * GB, "available_mb": ram.need_mb("small", minutes=180)}
    pick, say = ram.choose_default("turbo", room, minutes=180)
    assert pick == "small" and "180 minute recording" in say
    assert "180 minute" in ram.warning("turbo", room, 180) and ram.warning("turbo", room) is None


def test_media_minutes_reads_ffmpegs_duration_line(monkeypatch):
    class Done:
        stderr = "Input #0, wav, from 'a.wav':\n  Duration: 01:02:03.50, start: 0.000000, bitrate: 256 kb/s\n"
    monkeypatch.setattr(ram.subprocess, "run", lambda *a, **k: Done)
    assert ram.media_minutes("a.wav") == pytest.approx(62.058, abs=0.01)
    Done.stderr = "Duration: N/A, bitrate: N/A"
    assert ram.media_minutes("a.wav") is None


def test_media_minutes_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("ffmpeg vanished")
    monkeypatch.setattr(ram.subprocess, "run", boom)
    assert ram.media_minutes("a.wav") is None
    monkeypatch.undo()
    assert ram.media_minutes("C:/no/such/file.wav") is None


def test_transcribe_file_counts_the_length_of_the_recording(monkeypatch, tmp_path):
    monkeypatch.setattr(ram, "media_minutes", lambda p: 240.0)
    asked, said, r = _run(monkeypatch, tmp_path, ram.need_mb("turbo") / GB + 0.2)    # fits turbo for a short file only
    assert asked[0] != "turbo" and any("240 minute recording" in s for s in said)
