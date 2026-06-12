# Chroma 接入说明

当前项目已切换为 Chroma 作为默认向量库，适合中小规模知识库场景。

如需服务化向量库，可参考 `docs/qdrant-integration.md`。

## 1) 配置 `.env`

```dotenv
RETRIEVER_MODE=chroma
VECTOR_STORE_MODE=chroma
VECTOR_STORE_COLLECTION=rag_kb_default
CHROMA_PERSIST_DIR=data/vector_store/chroma

EMBEDDING_PROVIDER=openai
EMBEDDING_API_KEY=your_embedding_api_key
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
LLM_API_KEY=your_api_key
```

说明：

- `VECTOR_STORE_COLLECTION`：集合名，检索和入库必须一致
- `CHROMA_PERSIST_DIR`：本地持久化目录，重启后数据仍在

## 2) 执行批量入库

```powershell
python -m app.ingest.batch_ingest --dry-run
python -m app.ingest.batch_ingest
```

## 3) 启动问答服务

```powershell
uvicorn app.main:app --reload --port 8000
```
