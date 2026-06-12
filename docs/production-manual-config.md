# 正式使用时需要手动填写的配置

## 必填

- `LLM_API_KEY`：问答模型 API Key
- `EMBEDDING_API_KEY`：向量化模型 API Key

## 按场景必填

- `LLM_BASE_URL`：如果你不用默认 OpenAI 网关，需要填写兼容地址
- `EMBEDDING_BASE_URL`：如果向量化不走默认 OpenAI 网关，需要填写兼容地址
- `WECHAT_TOKEN` / `WECHAT_AES_KEY` / `WECHAT_CORP_ID`：接企业微信回调时需要

## 强烈建议确认

- `APP_ENV=prod`
- `APP_NAME=your_rag_service_name`
- `ALLOW_CORS_ORIGINS=你的前端域名`
- `RETRIEVER_MODE=chroma` 或 `qdrant`
- `VECTOR_STORE_MODE=chroma` 或 `qdrant`
- `VECTOR_STORE_COLLECTION=rag_kb_default`
- `CHROMA_PERSIST_DIR=data/vector_store/chroma`（chroma 模式）
- `QDRANT_URL=http://localhost:6333`（qdrant 模式）
- `QDRANT_API_KEY=`（qdrant 模式，可留空）
- `QDRANT_TIMEOUT_SEC=30`（qdrant 模式）
- `HISTORY_ENFORCE_USER_SCOPE=true`
- `HISTORY_ADMIN_TOKEN=仅运维掌握的随机长串（可留空表示禁用管理员旁路）`

## 向量化相关

- `KNOWLEDGE_BASE_DIR`
- `KNOWLEDGE_BASE_EXTENSIONS`
- `INGEST_CHUNK_SIZE`
- `INGEST_CHUNK_OVERLAP`
- `EMBEDDING_PROVIDER`
- `EMBEDDING_API_KEY`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_TIMEOUT_SEC`
- `EMBEDDING_MODEL`
- `EMBEDDING_BATCH_SIZE`
