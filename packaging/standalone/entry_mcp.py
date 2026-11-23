"""babelscribe-mcp (babelscribe-mcp.exe on Windows) of the standalone build: the MCP server, for AI apps to launch."""
import frozen_env

frozen_env.install()

from babelscribe.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()
