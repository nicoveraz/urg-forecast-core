"""Console entry point that launches the reference FastAPI server.

Equivalent to ``uvicorn urgencias_core.server.app:app`` but installed as the
``urgencias-server`` command. The server reads ``urg-forecast-core.toml`` from the
current directory if present, otherwise serves the bundled synthetic fixture.

Run with::

    urgencias-server                    # after: pip install "urg-forecast-core[server]"
    urgencias-server --port 9000 --reload
"""

from __future__ import annotations

import argparse

from urgencias_core._logging import setup_logging
from urgencias_core._optional import missing_extra_error


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Launch the urg-forecast-core reference server.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000).")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (development).")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - exercised via the core-only install
        raise missing_extra_error("server", "The reference server") from exc

    uvicorn.run(
        "urgencias_core.server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
