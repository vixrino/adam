import hashlib
from pathlib import Path

from adam_core.utils.hashing import sha256_bytes, sha256_file


def test_sha256_bytes_matches_hashlib() -> None:
    data = b"adam-ingestion-pdf"
    assert sha256_bytes(data) == hashlib.sha256(data).hexdigest()


def test_sha256_bytes_length_is_64() -> None:
    assert len(sha256_bytes(b"")) == 64


def test_sha256_file_matches_bytes(tmp_path: Path) -> None:
    content = b"%PDF-1.4 fake pdf content"
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(content)
    assert sha256_file(pdf) == sha256_bytes(content)
