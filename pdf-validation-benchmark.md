# ADAM — Analyse : validation des PDF ingérés

**Contexte :** `looks_like_pdf` (`src/adam_api/services/ingestion.py`) valide un fichier uploadé avant écriture sur le PVC. Après un premier fix retirant les critères falsifiables (`content_type`, extension de nom de fichier) au profit des seuls magic bytes (`%PDF-`), la question suivante s'est posée : est-ce suffisant, ou faut-il une vraie validation structurelle du PDF, et à quel coût CPU ?

---

## Limite du check magic bytes

Vérifier que le fichier commence par `%PDF-` confirme uniquement la signature d'en-tête. Ça ne garantit pas que le fichier est un PDF structurellement valide et parsable : un fichier tronqué, corrompu, ou disposant d'un header correct mais d'un contenu cassé passe cette vérification sans problème.

## Options évaluées

- **Léger** : vérifier en plus la présence du marqueur de fin `%%EOF` — détecte les fichiers tronqués sans dépendance externe, reste une heuristique.
- **Robuste** : tenter d'ouvrir/parser le fichier avec une librairie PDF (`pypdf`, `pymupdf`) et rejeter si ça échoue — garantit un vrai PDF valide.

L'objection initiale à l'option robuste était le coût CPU ajouté à chaque upload. Benchmark ci-dessous pour trancher avec des chiffres réels plutôt qu'une estimation.

## Méthode

PDF synthétiques générés localement (texte seul, sans dépendance externe) : 20 pages (~9 KB) et 200 pages (~90 KB). Médiane sur 30 exécutions, `time.perf_counter()`, Python 3.13 sur la machine de dev.

## Résultats

| Méthode | 20 pages (~9 KB) | 200 pages (~90 KB) |
|---|---|---|
| Magic bytes seuls (actuel) | ~0.03 ms | ~0.03 ms |
| `pypdf` (open + compte pages) | ~2.3 ms | ~19.6 ms |
| `pypdf` (+ extraction texte page 1) | ~2.4 ms | ~20 ms |
| `pymupdf` / `fitz` (open) | ~0.6 ms | ~0.7 ms |

## Constats

- `pypdf` (parseur pur Python) scale à peu près **linéairement avec le nombre de pages**. Sous les 20ms pour 200 pages, mais pourrait atteindre ~100ms sur un document de 1000+ pages.
- `pymupdf` (bindings C sur MuPDF) reste **quasi plat, sous 1ms**, indépendamment du nombre de pages — il ne lit que les métadonnées de structure, pas le contenu complet.
- Sur un vrai PDF scanné (images lourdes par page), le coût d'**ouverture/validation structurelle** reste comparable à ces mesures : le poids des images n'est décodé que si on appelle explicitement le rendu de page, ce qu'une simple validation n'a pas besoin de faire.

## Conclusion

Avec `pymupdf`, le coût d'une vraie validation structurelle (`fitz.open(path)`, échoue proprement sur fichier corrompu) est de l'ordre de **0.5–1ms par upload** — négligeable comparé au temps réseau de l'upload lui-même. Ce n'est plus un vrai compromis CPU si on utilise `pymupdf` plutôt que `pypdf`.

**Recommandation :** ne pas ajouter cette validation tant qu'un problème réel n'est pas observé (PDF corrompus qui plantent le worker OCR en aval) — le pipeline échouera de toute façon proprement plus tard sur un PDF cassé. Si le besoin se confirme, `pymupdf` est le choix à privilégier pour son coût quasi nul, pas `pypdf`.
