from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

import uvicorn
from fastapi import FastAPI

from rawcd.api import create_app


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the RawCD local engine API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    runner: Callable[[FastAPI, str, int, str], None] = uvicorn.run,
) -> None:
    args = parse_args(argv)
    runner(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
