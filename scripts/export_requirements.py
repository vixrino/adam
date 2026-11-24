"""
Exporte les dépendances épinglées de pyproject.toml vers requirements*.txt.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
HEADER = (
    "# Auto-generated from pyproject.toml by scripts/export_requirements.py. Do not edit by hand.\n"
)


def main() -> None:
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)

    deps = data["project"]["dependencies"]
    dev_deps = data["dependency-groups"]["dev"]

    (ROOT / "requirements.txt").write_text(
        HEADER
        + "\n".join(deps)
        + "\n\n# -r requirements.dev.txt\n"
        + "# Packages used development\n"
        + "\n".join(dev_deps)
        + "\n",
        encoding="utf-8",
    )

    (ROOT / "requirements.dev.txt").write_text(
        HEADER + "\n".join(dev_deps) + "\n", encoding="utf-8"
    )

    print(f"requirements.txt: {len(deps) + len(dev_deps)} packages")
    print(f"requirements.dev.txt: {len(dev_deps)} packages")

if __name__ == "__main__":
    main()