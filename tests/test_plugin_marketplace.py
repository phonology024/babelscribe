"""The Claude Code plugin and the marketplace it is published through.

`plugin/.claude-plugin/marketplace.json` is what lets someone run
`/plugin install babelscribe --marketplace phonology024/babelscribe`, so it has to keep listing the plugin
under the same name as `plugin.json`; a mismatch fails at install time with "Plugin ... not found in marketplace".
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugin"
MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
MARKETPLACE = PLUGIN / ".claude-plugin" / "marketplace.json"


def test_the_plugin_manifest_is_valid_json():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["name"] == "babelscribe"
    for field in ("displayName", "description", "version", "license", "homepage", "repository"):
        assert data.get(field), f"plugin.json is missing {field}"


def test_the_marketplace_lists_the_plugin_under_the_same_name():
    plugin = json.loads(MANIFEST.read_text(encoding="utf-8"))
    market = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    names = [p["name"] for p in market["plugins"]]
    assert plugin["name"] in names, f"marketplace lists {names}, plugin.json says {plugin['name']!r}"


def test_the_marketplace_entry_points_at_the_plugin_root():
    """The plugin lives at the repository's plugin/ root, so its source is './' — not '../' or a subfolder."""
    market = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    entry = next(p for p in market["plugins"] if p["name"] == "babelscribe")
    assert entry["source"] == "./"
    assert MARKETPLACE.parent.parent.joinpath(".mcp.json").is_file()


def test_the_marketplace_has_the_fields_claude_code_requires():
    market = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    assert market["name"] and market["owner"]["name"] and isinstance(market["plugins"], list)


def test_the_plugin_version_matches_the_package():
    from babelscribe import __version__
    assert json.loads(MANIFEST.read_text(encoding="utf-8"))["version"] == __version__


def test_the_pinned_mcp_command_matches_the_plugin_version():
    """The plugin starts `uvx babelscribe==<version> mcp`; a stale pin would run an older package."""
    from babelscribe import __version__
    cfg = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
    args = cfg["mcpServers"]["babelscribe"]["args"]
    assert args[0] == f"babelscribe=={__version__}"
    assert args[1] == "mcp"


def test_the_icon_is_a_square_png_that_claude_code_accepts():
    """The validator wants .claude-plugin/icon.png, 512-2048 px a side; a missing icon is a directory warning."""
    icon = PLUGIN / ".claude-plugin" / "icon.png"
    assert icon.is_file(), "plugin/.claude-plugin/icon.png is missing"
    head = icon.read_bytes()[:33]
    assert head.startswith(b"\x89PNG\r\n\x1a\n"), "icon is not a PNG"
    width = int.from_bytes(head[16:20], "big")
    height = int.from_bytes(head[20:24], "big")
    assert width == height and 512 <= width <= 2048, f"icon is {width}x{height}"
    assert icon.stat().st_size < 2 * 1024 * 1024


def test_the_readme_documents_the_one_line_install():
    readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
    assert "/plugin install babelscribe --marketplace phonology024/babelscribe" in readme