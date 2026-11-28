"""The caption preview in the desktop app uses the colours the engine really draws (desktop/src/lib/ai.ts BURN_COLOURS)."""
import re
from pathlib import Path

from babelscribe import burn

TS = Path(__file__).resolve().parents[1] / "desktop" / "src" / "lib" / "ai.ts"


def rgb(ass: str) -> str:
    """ASS &HAABBGGRR -> #RRGGBB"""
    bb, gg, rr = ass[4:6], ass[6:8], ass[8:10]
    return f"#{rr}{gg}{bb}".upper()


def test_the_preview_colours_are_the_burn_colours():
    text = TS.read_text(encoding="utf-8")
    found = dict(re.findall(r'(\w+): "(#[0-9A-Fa-f]{6})"', re.search(r"BURN_COLOURS = \{(.*?)\}", text, re.S).group(1)))
    assert found["white"].upper() == rgb(burn.WHITE)
    assert found["karaoke"].upper() == rgb(burn.AMBER), "karaoke lights each spoken word in this colour"
    assert found["shorts"].upper() == rgb(burn.YELLOW), "shorts lights the spoken word in this colour"
    assert found["outline"].upper() == "#000000"


def test_the_style_names_in_the_app_are_the_engines():
    text = (TS.parent / "engine.ts").read_text(encoding="utf-8")
    listed = re.search(r"STYLES: Style\[\] = \[(.*?)\]", text).group(1)
    assert tuple(re.findall(r'"(\w+)"', listed)) == burn.STYLES
