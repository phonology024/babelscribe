# PyInstaller spec for the standalone Windows build (#59): one folder holding babelscribe.exe and
# babelscribe-mcp.exe, with Python and every library inside it. Nothing to install, no admin rights.
#
#   pip install . pyinstaller
#   pyinstaller --noconfirm --distpath dist --workpath build packaging/standalone/babelscribe.spec
#
# whisper-cli and the speech models are not in here: they download on first run, as with pip.
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

datas, binaries, hidden = [], [], collect_submodules("babelscribe")
d, b, h = collect_all("imageio_ffmpeg")            # carries ffmpeg.exe as package data
datas += d; binaries += b; hidden += h
# the server imports parts of the mcp SDK by name at run time; mcp.cli is the SDK's own command line (needs typer)
hidden += collect_submodules("mcp", filter=lambda name: not name.startswith("mcp.cli"))
for package in ("mcp", "mcp-types", "anyio", "pydantic", "imageio-ffmpeg"):   # read at run time through importlib.metadata
    try:
        datas += copy_metadata(package)
    except Exception:                              # a package split differently in another mcp version
        pass
hidden += ["anyio._backends._asyncio"]

# Not needed to transcribe. The fine-tune converter (torch, transformers) stays a pip-only feature.
excludes = ["torch", "transformers", "numpy", "huggingface_hub", "tkinter", "pytest", "setuptools", "pip"]


def program(script: str, name: str):
    a = Analysis([script], pathex=[], datas=datas, binaries=binaries, hiddenimports=hidden, excludes=excludes,
                 noarchive=False)
    pyz = PYZ(a.pure)
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=name, console=True, upx=False,
              icon=None)
    return a, exe


cli, cli_exe = program("entry_cli.py", "babelscribe")
mcp, mcp_exe = program("entry_mcp.py", "babelscribe-mcp")

COLLECT(cli_exe, cli.binaries, cli.datas, mcp_exe, mcp.binaries, mcp.datas, name="babelscribe", upx=False)
