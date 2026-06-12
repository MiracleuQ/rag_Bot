# Qdrant 接入说明

当前项目支持 Qdrant 作为可切换向量库，适合服务化部署场景。

## 1) 配置 `.env`

```dotenv
RETRIEVER_MODE=qdrant
VECTOR_STORE_MODE=qdrant
VECTOR_STORE_COLLECTION=rag_kb_default
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_TIMEOUT_SEC=30

EMBEDDING_PROVIDER=openai
EMBEDDING_API_KEY=your_embedding_api_key
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
LLM_API_KEY=your_api_key
```

说明：

- `VECTOR_STORE_COLLECTION`：集合名，检索和入库必须一致
- `QDRANT_URL`：Qdrant 服务地址
- `QDRANT_API_KEY`：Qdrant 鉴权（未开启可留空）

## 2) 执行批量入库

```powershell
python -m app.ingest.batch_ingest --dry-run
python -m app.ingest.batch_ingest
```

## 3) 启动问答服务

```powershell
uvicorn app.main:app --reload --port 8000
```
