# Data Directory

- `knowledge_base/`: put source documents here for batch vectorization.
- `vector_store/`: local persistence for Chroma.

Run:

```powershell
python -m app.ingest.batch_ingest --dry-run
python -m app.ingest.batch_ingest
```
