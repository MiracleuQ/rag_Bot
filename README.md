# RAG 知识库问答（LangChain + Chroma/Qdrant）

这是一个可直接运行的企业知识库 RAG 服务，当前默认链路为：

- 问答服务：FastAPI
- 编排层：LangChain（LCEL）
- 向量库：Chroma / Qdrant（可切换）
- 历史记录：SQLite（会话/消息）
- 批量入库：按目录扫描 + 增量更新 + 混合分块

## 快速开始

1) 安装依赖

```powershell
python -m pip install -r requirements.txt
```

2) 配置环境变量

```powershell
Copy-Item .env.example .env
```

3) 启动服务

```powershell
uvicorn app.main:app --reload --port 8000
```

4) 调用问答接口

```powershell
curl -X POST "http://127.0.0.1:8000/chat" `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"报销流程是什么\"}"
```

## 批量向量化入库

把文件放入 `data/knowledge_base/` 后执行：

```powershell
python -m app.ingest.batch_ingest --dry-run
python -m app.ingest.batch_ingest
```

默认写入 Chroma 持久化目录：

- `data/vector_store/chroma`

切换到 Qdrant 时写入 `VECTOR_STORE_COLLECTION` 指定的集合（默认 `rag_kb_default`）。

## 核心配置

`.env` 常用项：

```dotenv
RETRIEVER_MODE=chroma
VECTOR_STORE_MODE=chroma
VECTOR_STORE_COLLECTION=rag_kb_default
CHROMA_PERSIST_DIR=data/vector_store/chroma

# 切到 qdrant 时使用
# RETRIEVER_MODE=qdrant
# VECTOR_STORE_MODE=qdrant
# QDRANT_URL=http://localhost:6333
# QDRANT_API_KEY=
# QDRANT_TIMEOUT_SEC=30

EMBEDDING_PROVIDER=openai
EMBEDDING_API_KEY=your_embedding_api_key
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
LLM_API_KEY=your_api_key
HISTORY_ENFORCE_USER_SCOPE=true
RAG_CANDIDATE_K=8
RAG_MAX_RETRIEVAL_DISTANCE=1.25
RAG_MIN_CHUNK_CHARS=20
RAG_ENABLE_DUAL_ROUTE_RETRIEVAL=true
QUERY_REWRITE_CACHE_ENABLED=true
```

## 当前支持文档格式

- `.txt`
- `.md`
- `.pdf`（文本提取失败会走 OCR 兜底）
- `.doc`（需安装 Microsoft Word + pywin32，或 antiword/catdoc，或 LibreOffice）
- `.docx`
- `.xlsx`
- `.csv`
- `.json`

## Web 测试页

启动服务后，可直接打开：

- `http://127.0.0.1:8000/`

页面会调用同服务的 `/chat` 接口，支持手动设置 `session_id` 和查看 `used_docs`。
