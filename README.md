# ADAM - Annotation et Données Automatisées

> Branche `master` ne contient pas encore de release stable. Le développement actif se trouve sur la branche `develop`.

## Accéder au code

```bash
git clone https://git.example.com/example-org/adam/adam.git
cd adam
git checkout develop
```

## Branches

| Branche | Rôle |
| :--- | :--- |
| `main` | Releases stables uniquement |
| `develop` | Développement actif |
| `feature/*` | Nouvelles fonctionnalités |
| `fix/*` | Corrections de bugs |

## Contact

- Développeur : dev@example.com

@router.post("/{dataset_id}/documents", response_model=IngestionOut)
async def ingest_documents(
    dataset_id: int,
    payload: IngestionPdfIn = UploadField(),
    db: AsyncSession = Depends(get_db),
) -> IngestionOut:
    dataset = await db.get(Dataset, dataset_id)
    if not dataset:
        raise_not_found(Dataset)

    schema = await db.get(DocSchema, dataset.schema_id)
    project = await db.get(Project, dataset.project_id)
    organisation = await db.get(Organisation, project.organisation_id) if project else None
    if not schema or not organisation:
        raise_unprocessable("Dataset rattache a un schema ou une organisation introuvable")

    pvc_root = Path(settings.pvc_mount_path)
    items: List[FileIngestionItemOut] = []
    for upload in payload.files:
        file_name = upload.filename or "sans_nom.pdf"
        content = await upload.read()
        if not looks_like_pdf(content):
            logger.warning("Fichier ignore (non PDF) [dataset_id=%s file_name=%s]", dataset_id, file_name)
            items.append(FileIngestionItemOut(file_name=file_name, status="rejected", reason="non-PDF"))
            continue
        raw = await ingest_pdf(
            db, dataset,
            organisation_slug=organisation.slug,
            document_type=schema.document_type,
            file_name=file_name, content=content, pvc_root=pvc_root,
        )
        items.append(FileIngestionItemOut(**raw))

    return IngestionOut(
        dataset_id=dataset_id,
        received=len(items),
        created=sum(1 for r in items if r.status in ("created", "created_file_reused")),
        already_exists=sum(1 for r in items if r.status == "already_exists"),
        rejected=sum(1 for r in items if r.status == "rejected"),
        results=items,
    )
