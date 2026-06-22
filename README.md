<div align="center">

# RAG 知识库问答系统

**企业级 RAG 服务 | LangChain + Chroma/Qdrant**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-LCEL-000000?style=flat)](https://python.langchain.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

开箱即用的企业知识库 RAG 服务，支持多格式文档导入、语义检索、多轮对话。

</div>

---

## 功能特性

| 模块 | 说明 |
|:---:|:---|
| **多格式解析** | PDF / DOCX / XLSX / MD / TXT / CSV / JSON，PDF 支持 OCR 兜底 |
| **智能分块** | 混合分块 / 滑动窗口 / 父子分块，自动注入文档标题和章节上下文 |
| **双路检索** | ChromaDB / Qdrant 可切换，支持 Embedding 去重 |
| **高级 RAG** | HyDE / CRAG / MMR / Cross-Encoder 精排 / RRF 多路融合 |
| **会话管理** | SQLite 持久化，支持多轮对话历史 |
| **查询改写** | 规则 / LLM / Noop 三种模式，带 TTL 缓存 |
| **安全过滤** | 敏感词归一化匹配，防止信息泄露 |
| **Web 界面** | 深色主题聊天 UI，支持 Markdown 渲染 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 填入你的 API Key：

```dotenv
LLM_API_KEY=your_api_key
EMBEDDING_API_KEY=your_embedding_api_key
```

### 3. 启动服务

```bash
uvicorn app.main:app --reload --port 8000
```

### 4. 访问 Web 界面

打开浏览器访问 **http://localhost:8000**

---

## API 接口

### 问答接口

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"question": "你好，请问有什么可以帮助你？"}'
```

### 健康检查

```bash
curl http://localhost:8000/health
```

---

## 批量入库

### 导入文档

将文件放入 `data/knowledge_base/` 目录，然后执行：

```bash
# 预览变更（不写入）
python -m app.ingest.batch_ingest --dry-run

# 执行入库
python -m app.ingest.batch_ingest
```

### 重新索引

```bash
# 完全重建索引（启用 Contextual Enrichment 后需执行）
python -m app.ingest.batch_ingest --full-reindex
```

---

## 核心配置

### 基础配置

```dotenv
# 向量库模式
RETRIEVER_MODE=chroma          # chroma | qdrant
VECTOR_STORE_MODE=chroma
VECTOR_STORE_COLLECTION=rag_kb_default
CHROMA_PERSIST_DIR=data/vector_store/chroma

# Qdrant 配置（切换到 qdrant 时使用）
# RETRIEVER_MODE=qdrant
# QDRANT_URL=http://localhost:6333
# QDRANT_API_KEY=

# Embedding
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

# LLM
LLM_MODEL=gpt-4o-mini
```

### 高级 RAG 配置

```dotenv
# HyDE - 假设文档嵌入
ENABLE_HYDE=true

# CRAG - 矫正检索
ENABLE_CRAG=true
CRAG_MAX_RETRIES=1

# MMR - 多样性检索
ENABLE_MMR=true
MMR_LAMBDA=0.5

# Cross-Encoder 精排（需安装 sentence-transformers）
ENABLE_CROSS_ENCODER_RERANKER=true
CROSS_ENCODER_MODEL=BAAI/bge-reranker-v2-m3
CROSS_ENCODER_TOP_N=5
```

### 入库配置

```dotenv
# 分块模式
CHUNK_MODE=hybrid              # hybrid | sliding | parent_child
INGEST_CHUNK_SIZE=800
INGEST_CHUNK_OVERLAP=120

# 去重阈值
EMBEDDING_DEDUP_THRESHOLD=0.95
```

完整配置请参考 [`.env.example`](.env.example)。

---

## 高级 RAG 功能

<details>
<summary><b>Contextual Chunk Enrichment</b> - 上下文增强分块</summary>

入库时自动为每个 chunk 注入文档标题和章节层级：

```
[文档: 采购管理规定]
[章节: 一、供应商准入]
不得低于3家供应商参与竞标...
```

解决裸 chunk 语义歧义，提升检索精度。启用后需 `--full-reindex` 重新入库。

</details>

<details>
<summary><b>Cross-Encoder Reranking</b> - 交叉编码器精排</summary>

用 `BAAI/bge-reranker-v2-m3` 对检索结果做精排，MRR 提升 10-25%。

需额外安装：`pip install sentence-transformers`

</details>

<details>
<summary><b>HyDE</b> - 假设文档嵌入</summary>

先用 LLM 生成假设文档再检索，弥合口语化查询与正式文档的词汇鸿沟。

</details>

<details>
<summary><b>Reciprocal Rank Fusion</b> - 多路融合</summary>

多路查询（原始问题、改写问题、历史问题）结果自动融合排序，无需配置，默认开启。

</details>

<details>
<summary><b>Embedding Near-Duplicate Detection</b> - 近似去重</summary>

入库时检测余弦相似度 > 0.95 的近似 chunk 并跳过，防止修订版文档污染索引。

</details>

---

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                      用户提问                            │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                 敏感词过滤（归一化匹配）                   │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              历史对话改写（LLM + TTL 缓存）               │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                查询改写（规则/LLM/Noop）                  │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              多路并行检索 + RRF 融合                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │
│  │  HyDE   │ │  CRAG   │ │   MMR   │ │Cross-Enc│       │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘       │
│       └──────────┴──────────┴──────────┘               │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Parent Chunk 扩展 + 结构化输出               │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                LLM 生成回答 + 文档引用                    │
└─────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
app/
├── main.py                     # FastAPI 入口
├── config.py                   # 配置管理 (pydantic-settings)
├── llm_client.py               # LLM 调用（带重试）
├── prompts.py                  # 系统提示词 + 输出格式检测
├── schemas.py                  # 请求/响应模型
├── utils.py                    # 共享工具函数
│
├── api/routers/
│   ├── chat.py                 # POST /chat + 微信适配
│   ├── history.py              # 会话历史查询
│   ├── system.py               # 健康检查
│   └── web.py                  # 测试页面
│
├── bootstrap/
│   └── rag_factory.py          # RAG 管线组装
│
├── ingest/
│   ├── batch_ingest.py         # 批量入库 CLI
│   ├── chunker.py              # 混合/滑动/父子分块
│   ├── document_loader.py      # 多格式文档读取
│   ├── embedders.py            # Embedding 客户端
│   ├── manifest.py             # 增量入库清单
│   └── vector_store/           # 向量存储适配器
│
├── retrievers/
│   ├── base.py                 # BaseRetriever ABC
│   ├── chroma_retriever.py     # ChromaDB 检索
│   ├── qdrant_retriever.py     # Qdrant 检索
│   ├── mmr.py                  # MMR 多样性
│   ├── crag.py                 # CRAG 矫正
│   ├── cross_encoder_reranker.py  # Cross-Encoder 精排
│   └── hyde_retriever.py       # HyDE 假设文档
│
├── services/
│   ├── langchain_rag_service.py   # 核心 RAG 编排
│   └── flow_enumerator.py         # 流程枚举
│
├── history/                    # SQLite 会话管理
├── security/                   # 敏感词过滤
├── query_rewrite/              # 查询改写模块
├── integrations/               # 企业微信适配
└── web/                        # 前端页面
```

---

## 支持的文档格式

| 格式 | 扩展名 | 备注 |
|:---:|:---:|:---|
| 文本文件 | `.txt` `.md` `.csv` `.log` | 自动检测编码 |
| PDF | `.pdf` | 文本提取 + OCR 兜底 |
| Word | `.doc` `.docx` | .doc 需 LibreOffice 或 antiword |
| Excel | `.xlsx` | 自动读取所有 Sheet |
| JSON | `.json` | 格式化输出 |

---

## License

[MIT](LICENSE)
