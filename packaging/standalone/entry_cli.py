"""babelscribe (babelscribe.exe on Windows) of the standalone build."""
import frozen_env

frozen_env.install()

from babelscribe.cli import main  # noqa: E402  (after install: every program it starts gets the right library path)

if __name__ == "__main__":
    main()
