# Diagnostic des migrations alembic de nota : lecture seule, rien n'est modifie.
# A lancer depuis la racine de nota-back. La sortie est copiee dans le
# presse-papiers : il suffit ensuite de la coller (Ctrl+V).
#
#   powershell -ExecutionPolicy Bypass -File scripts\diag_migrations.ps1

& {
  "== branche"
  git branch --show-current
  "== migrations (revision / down_revision), les 16 dernieres lignes"
  Select-String -Path src\nota_core\migrations\versions\*.py -Pattern '^(down_)?revision' | Select-Object -Last 16
  "== fichiers qui citent f2a3b4c5d6e7, e1f2a3b4c5d6 ou d0e1f2a3b4c5"
  Select-String -Path src\nota_core\migrations\versions\*.py -Pattern 'f2a3b4c5d6e7|e1f2a3b4c5d6|d0e1f2a3b4c5' | ForEach-Object { "$($_.Filename): $($_.Line.Trim())" }
  "== heads"
  uv run --all-extras alembic -c src\nota_core\alembic.ini heads
} 2>&1 | Out-String | Tee-Object -Variable sortie
$sortie | Set-Clipboard
"--- sortie copiee dans le presse-papiers ---"
