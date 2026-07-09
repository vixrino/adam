import hashlib
from pathlib import Path

import pytest

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


def test_sha256_bytes_empty() -> None:
    assert sha256_bytes(b"") == hashlib.sha256(b"").hexdigest()


def test_sha256_file_with_string_path(tmp_path: Path) -> None:
    content = b"test string path"
    f = tmp_path / "file.bin"
    f.write_bytes(content)
    assert sha256_file(str(f)) == sha256_bytes(content)


def test_sha256_file_empty(tmp_path: Path) -> None:
    f = tmp_path / "empty.bin"
    f.write_bytes(b"")
    assert sha256_file(f) == sha256_bytes(b"")


def test_sha256_file_multipart(tmp_path: Path) -> None:
    content = b"x" * (1024 * 1024 + 1)
    f = tmp_path / "big.bin"
    f.write_bytes(content)
    assert sha256_file(f) == hashlib.sha256(content).hexdigest()


def test_sha256_file_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        sha256_file(tmp_path / "does-not-exist.bin")
