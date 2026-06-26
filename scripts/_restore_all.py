#!/usr/bin/env python3
"""Restore missing adam artifacts from transcription reports."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACTED = ROOT / "_extracted"


def strip_numbered_lines(code: str) -> str:
    lines: list[str] = []
    for line in code.splitlines():
        if re.match(r"^\s*\d+\s*$", line):
            continue
        m = re.match(r"^\s*\d+\s*[:|]\s?(.*)$", line)
        if m:
            text = m.group(1).rstrip()
            if text.startswith("//"):
                continue
            lines.append(text)
            continue
        m2 = re.match(r"^(\d+) (.*)$", line.lstrip())
        if m2:
            text = m2.group(2)
            if len(m2.group(1)) >= 3 and text.startswith(" ") and not text.startswith("    "):
                text = " " + text
            lines.append(text.rstrip())
            continue
        if re.match(r"^\s*\d+[A-Za-z_#\"']", line):
            lines.append(re.sub(r"^\s*\d+", "", line).rstrip())
            continue
        if re.match(r"^\s*\d+[,}\]]", line):
            lines.append(re.sub(r"^\s*\d+", "", line).rstrip())
            continue
        if re.match(r"^\s*\d+\)", line):
            lines.append(re.sub(r"^\s*\d+", "", line).rstrip())
            continue
        if not re.match(r"^\s*//", line):
            lines.append(line.rstrip())
    return "\n".join(lines).strip()


def extract_codeblock(text: str, start_marker: str, end_marker: str | None = None) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    sub = text[start:]
    if end_marker:
        end = sub.find(end_marker, len(start_marker))
        if end >= 0:
            sub = sub[:end]
    m = re.search(r"```(?:json|python)?\n(.*?)```", sub, re.DOTALL)
    return m.group(1) if m else ""


def extract_all_json_blocks(text: str, section: str) -> list[str]:
    idx = text.find(section)
    if idx < 0:
        return []
    sub = text[idx:]
    blocks: list[str] = []
    for m in re.finditer(r"```json\n(.*?)```", sub, re.DOTALL):
        blocks.append(m.group(1))
    return blocks


def extract_pds2_line_map(text: str) -> dict[int, str]:
    """Map line numbers to JSON lines from Pds2 page sections."""
    idx = text.find("## Pages 37")
    if idx < 0:
        return {}
    sub = text[idx:]
    line_map: dict[int, str] = {}
    sections = re.split(r"### Page \d+ \(lines (\d+)[–-](\d+)\)", sub)
    # sections: [prefix, start1, end1, content1, start2, end2, content2, ...]
    i = 1
    while i + 2 < len(sections):
        start_line = int(sections[i])
        end_line = int(sections[i + 1])
        body = sections[i + 2]
        m = re.search(r"```json\n(.*?)```", body, re.DOTALL)
        if m:
            block_lines = [ln.rstrip() for ln in m.group(1).splitlines()]
            span = end_line - start_line + 1
            if block_lines:
                # Align block to end of range (screenshots show bottom of window)
                offset = max(0, span - len(block_lines))
                for j, ln in enumerate(block_lines):
                    line_map[start_line + offset + j] = ln
        i += 3
    return line_map


def extract_pds1_line_map(text: str) -> dict[int, str]:
    start = text.find("466:")
    end = text.find("## File 2:")
    if start < 0:
        return {}
    block = text[start:end]
    line_map: dict[int, str] = {}
    for raw in block.splitlines():
        m = re.match(r"^\s*(\d+)\s*[:|]\s?(.*)$", raw)
        if not m:
            continue
        num = int(m.group(1))
        content = m.group(2).rstrip()
        if content.startswith("//"):
            continue
        line_map[num] = content
    return line_map


def build_form_from_line_maps(p2_map: dict[int, str], p1_map: dict[int, str]) -> str:
    merged: dict[int, str] = {}
    merged.update(p2_map)
    merged.update(p1_map)
    if not merged:
        return ""
    max_line = max(merged)
    lines = [merged[n] for n in range(1, max_line + 1) if n in merged]
    text = "\n".join(lines)
    return repair_json_structure(text)


def trim_incomplete_tail(lines: list[str]) -> list[str]:
    """Drop trailing lines from a truncated screenshot page."""
    while lines:
        stripped = lines[-1].strip()
        if not stripped:
            lines.pop()
            continue
        if stripped.endswith((",", "{", "[", "},", "],", "}", "]")):
            break
        if re.match(r'^"[^"]+"\s*:\s*"[^"]*"$', stripped):
            lines.pop()
            continue
        if re.match(r'^"[^"]+"\s*:\s*$', stripped):
            lines.pop()
            continue
        if stripped == "{" or stripped.endswith('"id": "eligibilite.ei_non"'):
            lines.pop()
            continue
        break
    return lines


def _line_key(line: str) -> str:
    return line.strip()


def merge_overlapping_chunks(chunks: list[str]) -> str:
    if not chunks:
        return ""
    result_lines = chunks[0].strip().splitlines()
    for chunk in chunks[1:]:
        chunk_lines = chunk.strip().splitlines()
        best = 0
        max_ov = min(len(result_lines), len(chunk_lines))
        for i in range(max_ov, 0, -1):
            if [_line_key(x) for x in result_lines[-i:]] == [_line_key(x) for x in chunk_lines[:i]]:
                best = i
                break
        if best == 0:
            result_lines = trim_incomplete_tail(result_lines)
            if chunk_lines and chunk_lines[0].strip() == "{":
                while result_lines and not result_lines[-1].strip().endswith("},"):
                    result_lines.pop()
            if (
                len(chunk_lines) >= 2
                and chunk_lines[0].strip() == '"value": {'
                and chunk_lines[1].strip().startswith('"type"')
            ):
                while result_lines and result_lines[-1].strip() != '"value": {':
                    result_lines.pop()
            tail = "\n".join(result_lines[-8:])
            if re.search(r'"page_number": 3,\s*\n\s*"width": 0,\s*\n\s*"height": 0,\s*,?\s*$', tail):
                while result_lines and result_lines[-1].strip() != "],":
                    result_lines.pop()
                if result_lines and result_lines[-1].strip() == "],":
                    result_lines.pop()
                joined = "\n".join(chunk_lines)
                restart = joined.rfind('{\n  "page_number": 3,')
                if restart < 0:
                    restart = joined.rfind('"page_number": 3,')
                    if restart >= 0:
                        brace = joined.rfind("{", 0, restart)
                        if brace >= 0:
                            restart = brace
                if restart >= 0:
                    chunk_lines = joined[restart:].splitlines()
                    best = 0
        result_lines = result_lines + chunk_lines[best:]
    return "\n".join(result_lines)


def normalize_group_ids(text: str) -> str:
    return (
        text.replace('"Demandeur"', '"demandeur"')
        .replace('"Co-Demandeur"', '"co_demandeur"')
        .replace('"Co-demandeur"', '"co_demandeur"')
    )


def repair_json_structure(text: str) -> str:
    text = normalize_group_ids(text)
    text = re.sub(r",\s*//[^\n]*", "", text)
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"\.\.\.\s*\n", "", text)
    text = re.sub(
        r'\{\s*"id": "coordonnees_personnelles",\s*"label": "Coordonnées personnelles",\s*"kv_pairs": \[\s*\{\s*"confidence": 1\.0.*?\}\s*\]\s*\},\s*',
        "",
        text,
        count=1,
        flags=re.DOTALL,
    )
    text = re.sub(
        r'(\n\s*\}\s*)\],\s*\{\s*"page_number": 3,\s*"width": 0,\s*"height": 0,\s*\}\s*\n\s*\]\s*\n\s*\}\s*\n\s*\]\s*\n\s*\},\s*',
        r"\1\n    ]\n  },\n",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r'(\n\s*\}\s*)\],\s*\{\s*"page_number": 3,\s*"width": 0,\s*"height": 0,\s*,\s*',
        r'\1\n    ]\n  },\n  {\n    "page_number": 3,\n    "width": 0,\n    "height": 0,\n',
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r"(\n\s*\}\s*)\n\{\s*\n\s*\"page_number\": 3,",
        r'\1\n    ]\n  },\n  {\n    "page_number": 3,',
        text,
        count=1,
    )
    text = re.sub(
        r'"polygon": \[0,0,0,0,0,0,0,0\],\s*\n\s+"confidence": 1\.0\s*\n\s+\}\s*\n\s+\},',
        '"polygon": [0,0,0,0,0,0,0,0],\n              "confidence": 1.0\n            }\n          },',
        text,
    )
    text = re.sub(
        r'(\s+"confidence": 1\.0\s+\}\s+\})\s+\]\s*\}\s*\},\s*\{\s*"group_id": "autre_2"[^\}]+\}\s+\}\s+\],',
        r"\1,\n",
        text,
        count=1,
        flags=re.DOTALL,
    )
    text = text.replace(
        '"type": "boolean",\n"value": {',
        '"type": "boolean",\n            "value": false,\n            "polygon": [0,0,0,0,0,0,0,0],\n            "confidence": 1.0\n          }\n        },\n        REMOVED_DUP_VALUE',
    )
    text = text.replace("REMOVED_DUP_VALUE", "")
    text = re.sub(r'("text": "[^"]+"),?\s*\n(\s*"polygon")', r'\1,\n\2', text)
    text = re.sub(
        r'("polygon": \[0,0,0,0,0,0,0,0\],)\s*\n\s+"confidence": 1\.0\s*\n\s+\}\s*\n\s+\},',
        r'\1\n                            "confidence": 1.0\n                        }\n                    },',
        text,
    )
    text = re.sub(
        r'^\s*"id": "situation_logement_demandeur2",',
        '          "id": "situation_logement_demandeur2",',
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r'"type": "boolean",\s*\n\s*"value": \{\s*\n\s*"type": "boolean",',
        '"type": "boolean",',
        text,
    )
    return text


PAGE3_LOGEMENT_TAIL = """
    },
    {
      "id": "situation_logement",
      "label": "Situation logement",
      "kv_pairs": [
        {
          "group_id": "demandeur",
          "id": "situation_logement.locataire",
          "label": "Locataire",
          "value": {
            "type": "boolean",
            "value": true,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "group_id": "demandeur",
          "id": "situation_logement.procedure_expulsion",
          "label": "Procédure d'expulsion",
          "value": {
            "type": "boolean",
            "value": true,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "group_id": "co_demandeur",
          "id": "situation_logement.locataire",
          "label": "Locataire",
          "value": {
            "type": "boolean",
            "value": true,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "group_id": "co_demandeur",
          "id": "situation_logement.procedure_expulsion",
          "label": "Procédure d'expulsion",
          "value": {
            "type": "boolean",
            "value": true,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        }
      ]
    },
    {
"""


def build_form_json() -> str:
    p2 = (EXTRACTED / "Pds2-report.md").read_text(encoding="utf-8")
    p1 = (EXTRACTED / "Pds1-report.md").read_text(encoding="utf-8")

    head_blocks = extract_all_json_blocks(p2, "## Pages 37")
    # Pages 37-49 only (through personnes_domicile) — pages 50-51 overlap is unreliable in OCR
    head = merge_overlapping_chunks(head_blocks[:13])
    head = strip_numbered_lines(head)
    head = repair_json_structure(head).rstrip()
    if head.endswith("]"):
        head += PAGE3_LOGEMENT_TAIL.strip()

    start = p1.find("466:")
    end = p1.find("## File 2:")
    p1_map = extract_pds1_line_map(p1)
    if p1_map:
        tail = "\n".join(p1_map[n] for n in sorted(n for n in p1_map if n >= 466))
        if tail.lstrip().startswith('"id": "situation_logement_demandeur2"'):
            tail = "      " + tail.lstrip()
    else:
        tail = strip_numbered_lines(p1[start:end]) if start >= 0 else ""

    merged = head.rstrip().rstrip(",") + "\n" + tail.strip() if tail else head
    merged = repair_json_structure(merged)
    merged = re.sub(r'("(?:text|raw_text)": "[^"]+")\s*\n(\s*"polygon")', r"\1,\n\2", merged)

    if not merged.strip().endswith("}"):
        merged = merged.rstrip().rstrip(",") + "\n    }\n  ]\n}\n"

    parsed = json.loads(merged)
    return json.dumps(parsed, ensure_ascii=False, indent=4) + "\n"


def build_seed_py() -> str:
    p1 = (EXTRACTED / "Pds1-report.md").read_text(encoding="utf-8")
    block = extract_codeblock(p1, "## File 5:", "## File 6:")
    code = strip_numbered_lines(block)
    # Transcription typo: 8-tuple unpack with 6-tuple data
    code = code.replace(
        "for i, (sec_id, sec_label, key, label, ftype, page, required, polygon) in enumerate(HARDCODED_FIELD_SPECS):",
        "for i, (sec_id, sec_label, key, label, ftype, page) in enumerate(HARDCODED_FIELD_SPECS):",
    )
    code = code.replace(
        "        fs = FieldSpec(\n"
        "            schema_id=schema.id, page=page,\n"
        "            section_id=sec_id, section_label=sec_label,\n"
        "            field_key=key, display_label=label,\n"
        "            value_type=ftype, required=required,\n"
        "            display_order=i, polygon=polygon,\n"
        "        )",
        "        fs = FieldSpec(\n"
        "            schema_id=schema.id, name=key, page=page,\n"
        "            section_id=sec_id, section_label=sec_label,\n"
        "            field_key=key, display_label=label,\n"
        "            value_type=ftype, required=False,\n"
        "            display_order=i,\n"
        "        )",
    )
    code = code.replace(
        "        fs = FieldSpec(\n"
        "            schema_id=schema.id,\n"
        "            page=spec[\"page\"],",
        "        fs = FieldSpec(\n"
        "            schema_id=schema.id,\n"
        "            name=spec[\"field_key\"],\n"
        "            page=spec[\"page\"],",
    )
    if "async_sessionmaker" not in code:
        code = code.replace(
            "from sqlalchemy.ext.asyncio import AsyncSession",
            "from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker",
        )
    code = code.replace('\n """\n', '\n"""\n')
    return code + "\n"


MIGRATION_3DA97F = '''\
"""add updated_at deleted_at to organisation user doc_schema field_spec file user_project"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3da97f0d0b1d"
down_revision: Union[str, None] = "db8ff43496ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "doc_schema",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column(
        "field_spec",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column(
        "file",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column("organisation", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "user",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column("user", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "user_project",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("user_project", "updated_at")
    op.drop_column("user", "deleted_at")
    op.drop_column("user", "updated_at")
    op.drop_column("organisation", "deleted_at")
    op.drop_column("file", "updated_at")
    op.drop_column("field_spec", "updated_at")
    op.drop_column("doc_schema", "updated_at")
'''

MIGRATION_42E721 = '''\
"""add updated_at to organisation"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "42e721054714"
down_revision: Union[str, None] = "3da97f0d0b1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organisation",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("organisation", "updated_at")
'''

MIGRATION_65A5FD = '''\
"""update DocumentStatus"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "65a5fd7b662f"
down_revision: Union[str, None] = "6452f2c7b5b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "field_spec",
        "polygon",
        existing_type=postgresql.ARRAY(sa.DOUBLE_PRECISION(precision=53)),
        comment="4 points (x1,y1,x2,y2,x3,y3,x4,y4). 8 floats si non null",
        existing_comment="4 points (x1,y1,x2,y2,x3,y3,x4,y4) - 8 floats si non null",
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "field_spec",
        "polygon",
        existing_type=postgresql.ARRAY(sa.DOUBLE_PRECISION(precision=53)),
        comment="4 points (x1,y1,x2,y2,x3,y3,x4,y4) - 8 floats si non null",
        existing_comment="4 points (x1,y1,x2,y2,x3,y3,x4,y4). 8 floats si non null",
        existing_nullable=True,
    )
'''

TEST_EXCEPTIONS = '''\
"""Tests unitaires - adam_core/utils/exceptions.py"""
import pytest
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient

from adam_core.utils.exceptions import (
    _name,
    raise_not_found,
    raise_already_archived,
    raise_not_archived,
    raise_already_exists,
    raise_conflict,
    raise_unprocessable,
    http_exception_handler,
    NOT_FOUND,
    ALREADY_ARCHIVED,
    NOT_ARCHIVED,
    ALREADY_EXISTS,
)


class FakeModel:
    __tablename__ = "organisation"


class FakeModelNoTablename:
    __name__ = "Project"


class TestName:
    def test_uses_tablename_when_present(self) -> None:
        assert _name(FakeModel) == "Organisation"

    def test_falls_back_to_class_name(self) -> None:
        assert _name(FakeModelNoTablename) == "Project"

    def test_capitalizes_result(self) -> None:
        class Lower:
            __tablename__ = "user_project"

        assert _name(Lower) == "User_project"


class TestRaiseNotFound:
    def test_raises_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found(FakeModel)
        assert exc_info.value.status_code == 404
        assert NOT_FOUND.format("Organisation") in str(exc_info.value.detail)


class TestRaiseAlreadyArchived:
    def test_raises_409(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_already_archived(FakeModel)
        assert exc_info.value.status_code == 409
        assert ALREADY_ARCHIVED.format("Organisation") in str(exc_info.value.detail)


class TestHttpExceptionHandler:
    def test_handler_returns_json(self) -> None:
        app = FastAPI()
        app.add_exception_handler(HTTPException, http_exception_handler)
        client = TestClient(app)

        @app.get("/boom")
        def boom() -> None:
            raise HTTPException(status_code=418, detail="teapot")

        response = client.get("/boom")
        assert response.status_code == 418
        assert response.json()["detail"] == "teapot"
'''


def download_swagger() -> None:
    version = "5.17.14"
    base = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{version}"
    out = ROOT / "src/adam_api/static"
    out.mkdir(parents=True, exist_ok=True)
    for name in ("swagger-ui-bundle.js", "swagger-ui.css"):
        url = f"{base}/{name}"
        dest = out / name
        print(f"  GET {url}")
        urllib.request.urlretrieve(url, dest)


def write_file(rel: str, content: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {rel} ({len(content.splitlines())} lines)")


def cleanup_scratch() -> None:
    targets = [
        ROOT / "_bootstrap_parts",
        ROOT / "_build_adam.py",
        ROOT / "_make_build_script.py",
        ROOT / "_form_merged.json",
        ROOT / "scripts/form_merge_debug.json",
        ROOT / "scripts/form_demo_v0.3.json.raw",
    ]
    for path in targets:
        if path.is_dir():
            shutil.rmtree(path)
            print(f"  removed dir {path.name}/")
        elif path.exists():
            path.unlink()
            print(f"  removed {path.name}")


def main() -> None:
    print("1/7 form demo JSON")
    write_file("scripts/form_demo_v0.3.json", build_form_json())

    print("2/7 seed.py")
    write_file("scripts/seed.py", build_seed_py())

    print("3/7 migrations")
    write_file(
        "src/adam_core/migrations/versions/20240529_1346_3da97f0d0b1d_add_updated_at_deleted_at_to_organisation_user_doc_schema_field_spec_file_user_project.py",
        MIGRATION_3DA97F,
    )
    write_file(
        "src/adam_core/migrations/versions/20240529_1404_42e721054714_add_updated_at_to_organisation.py",
        MIGRATION_42E721,
    )
    write_file(
        "src/adam_core/migrations/versions/20240612_1601_65a5fd7b662f_update_documentstatus.py",
        MIGRATION_65A5FD,
    )

    print("4/7 swagger assets")
    download_swagger()

    print("5/7 tests")
    write_file("tests/unit/test_exceptions.py", TEST_EXCEPTIONS)

    print("6/7 validate")
    form_demo = json.loads((ROOT / "scripts/form_demo_v0.3.json").read_text(encoding="utf-8"))
    print(f"  form demo: {form_demo['page_count']} pages, {len(form_demo['pages'])} page objects")

    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(ROOT / "src"), str(ROOT / "scripts/seed.py")],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr)
        raise SystemExit(1)
    print("  compileall OK")

    print("7/7 cleanup")
    cleanup_scratch()
    print("Done.")


if __name__ == "__main__":
    main()
