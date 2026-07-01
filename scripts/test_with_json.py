"""
Usage: python scripts/test_with_json.py mon_fichier.json

Simule le flux complet (ingestion -> lecture typee) sur un fichier JSON reel,
sans besoin de serveur ni de base de donnees.

NOTE: le champ racine attendu par SmartdocDocument est "format_version".
Si le fichier source utilise un autre nom de cle pour la version
(n'importe quelle cle racine finissant par "_version"), elle est
detectee et mappee automatiquement.
"""
import json
import sys

sys.path.insert(0, "src")

from adam_core.schemas.interface_contract import SmartdocDocument
from adam_core.utils.field_parser import parse_field_value


def main(json_path: str) -> None:
    with open(json_path, encoding="utf-8") as f:
        raw_json = json.load(f)

    # Detecte automatiquement toute cle racine "*_version" si "format_version" est absent
    if "format_version" not in raw_json:
        for key in raw_json:
            if key.endswith("_version"):
                raw_json["format_version"] = raw_json[key]
                break

    doc = SmartdocDocument.model_validate(raw_json)
    specs = doc.extract_field_specs()
    kv_by_key = {kv.field_key: kv for _, _, kv in doc.iter_kv_pairs()}

    print(f"{'field_key':15s} {'value_type':10s} {'stocke (brut)':25s} {'sortie API (typee)'}")
    print("-" * 90)
    for spec in specs:
        key = spec["field_key"]
        kv = kv_by_key[key]
        stored = kv.extracted_value  # ce qui serait stocke en base (string)
        parsed = parse_field_value(stored, spec["value_type"])
        print(f"{key:15s} {spec['value_type']:10s} {stored!r:25s} {parsed!r} ({type(parsed).__name__})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/test_with_json.py mon_fichier.json")
        sys.exit(1)
    main(sys.argv[1])
