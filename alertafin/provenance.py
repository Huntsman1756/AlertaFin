"""Provenancia: bytes inmutables identificados por SHA-256 + eventos de retrieval.

- Cada retrieval produce su PROPIO evento, aunque los bytes sean identicos a
  uno anterior. Nunca se sobrescribe metadata historica.
- El ByteStore es append-only e inmutable: si un fichero existe con otro
  contenido (corrupcion) se eleva error.
"""

import hashlib
import json
import uuid
from pathlib import Path


class ByteStore:
    """Almacen de objetos de bytes inmutables identificados por SHA-256."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, sha: str) -> Path:
        return self.root / sha[:2] / f"{sha}.bin"

    def put(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        path = self._path(sha)
        if path.exists():
            if path.read_bytes() != data:
                raise RuntimeError(
                    f"byte store corruption: {path} content != sha256 {sha}"
                )
            return sha
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return sha

    def get(self, sha: str) -> bytes:
        return self._path(sha).read_bytes()

    def has(self, sha: str) -> bool:
        return self._path(sha).exists()

    def path_of(self, sha: str) -> Path:
        return self._path(sha)


class RetrievalLog:
    """Registro append-only de eventos de retrieval (JSONL)."""

    def __init__(self, path):
        self.path = Path(path)

    def append(
        self,
        source_url: str,
        query_params: dict,
        retrieved_at: str,
        http_status,
        source_sha256: str,
        size: int,
        note: str = "",
        **extra,
    ) -> dict:
        event = {
            "retrieval_id": uuid.uuid4().hex,
            "source_url": source_url,
            "query_params": query_params,
            "retrieved_at": retrieved_at,
            "http_status": http_status,
            "source_sha256": source_sha256,
            "size": size,
            "note": note,
        }
        event.update(extra)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=False) + "\n")
        return event

    def events(self) -> list:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
