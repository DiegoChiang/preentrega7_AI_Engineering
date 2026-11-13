"""Arranque local de la API."""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="API multi-agente de produccion")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run(
        "multi_agent_orchestrator.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
