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

重新索引（Contextual Enrichment 生效需重新入库）：

```powershell
python -m app.ingest.batch_ingest --full-reindex
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

## 高级 RAG 功能

### Contextual Chunk Enrichment（上下文增强分块）

入库时自动为每个 chunk 注入文档标题和章节层级：

```
[文档: 采购管理规定]
[章节: 一、供应商准入]
不得低于3家供应商参与竞标...
```

解决裸 chunk 语义歧义，提升检索精度。启用后需 `--full-reindex` 重新入库。

### Cross-Encoder Reranking（精排）

用 `BAAI/bge-reranker-v2-m3` 对检索结果做精排，MRR 提升 10-25%。

```dotenv
ENABLE_CROSS_ENCODER_RERANKER=true
CROSS_ENCODER_MODEL=BAAI/bge-reranker-v2-m3
CROSS_ENCODER_TOP_N=5
```

需额外安装：`pip install sentence-transformers`

### HyDE（假设文档嵌入）

先用 LLM 生成假设文档再检索，弥合口语化查询与正式文档的词汇鸿沟。

```dotenv
ENABLE_HYDE=true
```

### Reciprocal Rank Fusion（多路融合）

多路查询（原始问题、改写问题、历史问题）结果自动融合排序，无需配置，默认开启。

### Embedding 近似去重

入库时检测余弦相似度 > 0.95 的近似 chunk 并跳过，防止修订版文档污染索引。

```dotenv
EMBEDDING_DEDUP_THRESHOLD=0.95
```

### 其他可选功能

```dotenv
# MMR 多样性检索
ENABLE_MMR=true
MMR_LAMBDA=0.5

# CRAG 矫正检索（LLM 评估文档相关性）
ENABLE_CRAG=true
CRAG_MAX_RETRIES=1

# LLM 查询改写
ENABLE_QUERY_REWRITE=true
QUERY_REWRITE_MODE=llm
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

## 架构概览

```
用户提问
  │
  ├─ 敏感词过滤（归一化匹配）
  │
  ├─ 历史对话改写（LLM + 缓存）
  │
  ├─ 查询改写（规则/LLM/Noop）
  │
  ├─ 多路并行检索 + RRF 融合
  │    ├─ 可选: HyDE 假设文档检索
  │    ├─ 可选: Cross-Encoder 精排
  │    ├─ 可选: MMR 多样性筛选
  │    └─ 可选: CRAG 矫正重试
  │
  ├─ Parent Chunk 解析
  │
  ├─ 流程枚举检测（采购SOP专用）
  │
  ├─ 结构化输出检测（表格/列表）
  │
  └─ LLM 生成回答 + 文档引用
```

## 项目结构

```
app/
├── main.py                  # FastAPI 入口
├── config.py                # 配置管理 (pydantic-settings)
├── llm_client.py            # LLM 调用（带重试）
├── prompts.py               # 系统提示词 + 输出格式检测
├── schemas.py               # 请求/响应模型
├── utils.py                 # 共享工具函数
│
├── api/routers/
│   ├── chat.py              # POST /chat + 微信适配
│   ├── history.py           # 会话历史查询
│   ├── system.py            # 健康检查
│   └── web.py               # 测试页面
│
├── bootstrap/
│   └── rag_factory.py       # RAG 管线组装
│
├── ingest/
│   ├── batch_ingest.py      # 批量入库 CLI
│   ├── chunker.py           # 混合/滑动/父子分块
│   ├── document_loader.py   # 多格式文档读取
│   ├── embedders.py         # Embedding 客户端
│   ├── manifest.py          # 增量入库清单
│   └── vector_store/        # 向量存储适配器
│
├── retrievers/
│   ├── base.py              # BaseRetriever ABC
│   ├── chroma_retriever.py  # ChromaDB 检索
│   ├── qdrant_retriever.py  # Qdrant 检索
│   ├── mmr.py               # MMR 多样性
│   ├── crag.py              # CRAG 矫正
│   ├── cross_encoder_reranker.py  # Cross-Encoder 精排
│   └── hyde_retriever.py    # HyDE 假设文档
│
├── services/
│   ├── langchain_rag_service.py   # 核心 RAG 编排
│   └── flow_enumerator.py         # 采购流程枚举
│
├── history/                 # SQLite 会话管理
├── security/                # 敏感词过滤
├── query_rewrite/           # 查询改写模块
└── integrations/            # 企业微信适配
```
