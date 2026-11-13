"""Comprueba acceso de solo lectura a un índice de Pinecone.

Uso:
    python scripts/pinecone_smoke.py
    python scripts/pinecone_smoke.py --index incident-knowledge-cloud

La credencial y los valores predeterminados se leen desde ``.env`` o desde las
variables ``PINECONE_API_KEY``, ``PINECONE_INDEX_NAME`` y
``PINECONE_NAMESPACE``. El script no crea índices, no inserta vectores y no
imprime secretos.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any


def _load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _index_names(client: Any) -> set[str]:
    catalog = getattr(client, "indexes", None)
    rows = catalog.list() if catalog is not None else client.list_indexes()
    names: set[str] = set()
    for row in rows:
        name = row.get("name") if isinstance(row, dict) else getattr(row, "name", None)
        if name:
            names.add(str(name))
    return names


def _open_index(client: Any, name: str) -> Any:
    factory = getattr(client, "index", None)
    return factory(name) if callable(factory) else client.Index(name)


def _read_field(payload: Any, field: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(field, default)
    return getattr(payload, field, default)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Valida credenciales y consulta estadísticas de Pinecone sin modificar datos."
    )
    parser.add_argument("--index", help="Índice; por defecto usa PINECONE_INDEX_NAME.")
    parser.add_argument(
        "--namespace",
        help="Namespace; por defecto usa PINECONE_NAMESPACE.",
    )
    return parser


def main() -> None:
    _load_environment()
    args = _parser().parse_args()
    api_key = os.getenv("PINECONE_API_KEY", "").strip()
    index_name = (args.index or os.getenv("PINECONE_INDEX_NAME", "")).strip()
    namespace = (args.namespace or os.getenv("PINECONE_NAMESPACE", "")).strip()

    if not api_key:
        raise SystemExit("Falta la variable PINECONE_API_KEY.")
    if not index_name:
        raise SystemExit("Indica --index o configura PINECONE_INDEX_NAME.")

    try:
        from pinecone import Pinecone
    except ImportError as exc:
        raise SystemExit("Instala la dependencia 'pinecone'.") from exc

    client = Pinecone(api_key=api_key)
    available = _index_names(client)
    if index_name not in available:
        raise SystemExit(f"El índice '{index_name}' no existe en la cuenta configurada.")

    stats = _open_index(client, index_name).describe_index_stats()
    namespaces = _read_field(stats, "namespaces", {}) or {}
    namespace_stats = namespaces.get(namespace, {}) if namespace else {}
    result = {
        "status": "ok",
        "index": index_name,
        "namespace": namespace or None,
        "dimension": _read_field(stats, "dimension"),
        "total_vector_count": _read_field(stats, "total_vector_count", 0),
        "namespace_vector_count": _read_field(namespace_stats, "vector_count", 0),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
