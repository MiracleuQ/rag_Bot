<div align="center">

<img src="https://img.shields.io/badge/Built_with-LangChain-000000?style=for-the-badge&logo=langchain&logoColor=white" alt="LangChain">
<img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
<img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
<img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="MIT License">

<br>
<br>

# <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4a1.png" width="35"> RAG 知识库问答系统

### 企业级 RAG 服务 · 多格式文档导入 · 语义检索 · 多轮对话

<br>

[![CI](https://img.shields.io/github/actions/workflow/status/MiracleuQ/rag_Bot/ci.yml?branch=master&label=CI&style=flat-square)](https://github.com/MiracleuQ/rag_Bot/actions)
[![Tests](https://img.shields.io/badge/tests-93%20passing-brightgreen?style=flat-square)](https://github.com/MiracleuQ/rag_Bot)
[![Code style](https://img.shields.io/badge/code%20style-ruff-000000?style=flat-square)](https://github.com/astral-sh/ruff)

<br>

[快速开始](#-快速开始) · [功能特性](#-功能特性) · [API 文档](#-api-接口) · [架构设计](#-架构概览) · [部署指南](#-部署指南)

<br>

</div>

---

## <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/26a1.png" width="24"> 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/MiracleuQ/rag_Bot.git
cd rag_Bot

# 安装依赖
pip install -e .

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Key
```

### 启动服务

```bash
# 方式一：本地启动
uvicorn app.main:app --reload --port 8000

# 方式二：Docker 启动（含 Qdrant 向量库）
docker-compose up -d
```

<br>

<div align="center">

**访问 http://localhost:8000 打开 Web 界面**

</div>

---

## <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/2728.png" width="24"> 功能特性

<table>
  <tr>
    <td width="50%">

#### <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/2699.png" width="18"> 核心能力

| 功能 | 说明 |
|:---|:---|
| **多格式解析** | PDF / DOCX / XLSX / MD / TXT / CSV / JSON |
| **PDF OCR 降级** | PyPDF + Tesseract 双通道，文本不足自动兜底 |
| **智能分块** | Hybrid / Sliding Window / Parent-Child 三模式 |
| **双路检索** | ChromaDB / Qdrant 可切换，Embedding 去重 |

    </td>
    <td width="50%">

#### <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f52c.png" width="18"> 高级 RAG

| 技术 | 效果 |
|:---|:---|
| **HyDE** | 假设文档嵌入，弥合口语与文档词汇鸿沟 |
| **CRAG** | 矫正式检索，自动过滤低质量结果 |
| **MMR** | 多样性过滤，避免结果同质化 |
| **Cross-Encoder** | bge-reranker 精排，MRR 提升 10-25% |

    </td>
  </tr>
  <tr>
    <td width="50%">

#### <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f512.png" width="18"> 企业级特性

| 特性 | 说明 |
|:---|:---|
| **RBAC 权限** | admin / editor / viewer 三角色控制 |
| **租户隔离** | 向量库前缀 + DB 列，零代码侵入 |
| **安全过滤** | 敏感词归一化 + hmac 防时序攻击 |
| **多轮历史** | SQLite 持久化，上下文感知 |

    </td>
    <td width="50%">

#### <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4e6.png" width="18"> 工程化

| 能力 | 说明 |
|:---|:---|
| **增量入库** | manifest + SHA256，变更检测 O(1) |
| **RRF 融合** | 三路查询分数融合排序 |
| **TTL 缓存** | 查询改写结果缓存，避免重复调用 |
| **RAG 评估** | 25 条 QA 集 + 自动化评估脚本 |

    </td>
  </tr>
</table>

---

## <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4ca.png" width="24"> API 接口

| 接口 | 方法 | 权限 | 说明 |
|:---|:---:|:---:|:---|
| `POST /chat` | <img src="https://img.shields.io/badge/-POST-61affe?style=flat-square"> | 读取 | 智能问答 |
| `POST /ingest` | <img src="https://img.shields.io/badge/-POST-61affe?style=flat-square"> | 编辑 | 批量入库 |
| `GET /history/sessions` | <img src="https://img.shields.io/badge/-GET-49cc90?style=flat-square"> | 读取 | 会话历史 |
| `GET /health` | <img src="https://img.shields.io/badge/-GET-49cc90?style=flat-square"> | 公开 | 健康检查 |

<details>
<summary><img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4dd.png" width="16"> 请求示例</summary>

<br>

```bash
# 智能问答
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "采购流程的主要步骤有哪些？",
    "session_id": "optional-session-id"
  }'

# 响应示例
# {
#   "answer": "采购流程主要包括以下步骤...",
#   "used_docs": [...],
#   "session_id": "abc123"
# }
```

```bash
# 批量入库（需要 editor 权限）
curl -X POST "http://localhost:8000/ingest" \
  -H "Content-Type: application/json" \
  -H "X-Role: editor" \
  -d '{
    "input_dir": "data/knowledge_base",
    "dry_run": false
  }'
```

```bash
# 查询会话历史
curl "http://localhost:8000/history/sessions?user_id=user1" \
  -H "X-User-ID: user1"
```

</details>

---

## <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4c2.png" width="24"> 批量入库

```bash
# 预览变更（不写入）
python -m app.ingest.batch_ingest --dry-run

# 执行增量入库
python -m app.ingest.batch_ingest

# 完全重建索引
python -m app.ingest.batch_ingest --full-reindex
```

---

## <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/2699.png" width="24"> 核心配置

<details>
<summary><b>基础配置</b></summary>

```dotenv
# 向量库选择
RETRIEVER_MODE=chroma          # chroma | qdrant

# Embedding 模型
EMBEDDING_MODEL=text-embedding-3-small

# LLM 模型
LLM_MODEL=gpt-4o-mini
```

</details>

<details>
<summary><b>高级 RAG 配置</b></summary>

```dotenv
# 启用高级检索特性
ENABLE_HYDE=true                    # 假设文档嵌入
ENABLE_CRAG=true                    # 矫正检索
ENABLE_MMR=true                     # 多样性检索
ENABLE_CROSS_ENCODER_RERANKER=true  # Cross-Encoder 精排
```

</details>

<details>
<summary><b>企业级配置</b></summary>

```dotenv
# 安全与权限
RBAC_ENABLED=true                  # RBAC 权限控制
TENANT_ISOLATION_ENABLED=true      # 租户数据隔离

# CORS 配置（生产环境请显式设置）
ALLOW_CORS_ORIGINS=["http://your-domain.com"]
```

</details>

完整配置请参考 [`.env.example`](.env.example)。

---

## <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f52c.png" width="24"> 高级 RAG 功能

<details>
<summary><b>Contextual Chunk Enrichment</b></summary>

<br>

入库时自动为每个 chunk 注入文档标题和章节层级：

```
[文档: 采购管理规定]
[章节: 一、供应商准入]
不得低于3家供应商参与竞标...
```

解决裸 chunk 语义歧义，提升检索精度。启用后需 `--full-reindex` 重新入库。

</details>

<details>
<summary><b>Cross-Encoder Reranking</b></summary>

<br>

用 `BAAI/bge-reranker-v2-m3` 对检索结果做精排，MRR 提升 10-25%。

需额外安装：`pip install sentence-transformers`

</details>

<details>
<summary><b>HyDE (Hypothetical Document Embeddings)</b></summary>

<br>

先用 LLM 生成假设文档再检索，弥合口语化查询与正式文档的词汇鸿沟。

</details>

<details>
<summary><b>Reciprocal Rank Fusion</b></summary>

<br>

多路查询（原始问题、改写问题、历史问题）结果自动融合排序，无需配置，默认开启。

</details>

<details>
<summary><b>Embedding Near-Duplicate Detection</b></summary>

<br>

入库时检测余弦相似度 > 0.95 的近似 chunk 并跳过，防止修订版文档污染索引。

</details>

---

## <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f3d7.png" width="24"> 架构概览

```
                              ┌──────────────────────┐
                              │       用户提问        │
                              └──────────┬───────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
                    ▼                    ▼                    ▼
            ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
            │  RBAC 权限   │    │  租户隔离    │    │  敏感词过滤  │
            └──────┬───────┘    └──────┬───────┘    └──────┬───────┘
                   │                   │                   │
                   └───────────────────┼───────────────────┘
                                       │
                              ┌────────▼────────┐
                              │  历史对话改写    │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │    查询改写      │
                              └────────┬────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            │                          │                          │
            ▼                          ▼                          ▼
    ┌──────────────┐          ┌──────────────┐          ┌──────────────┐
    │     HyDE     │          │     CRAG     │          │     MMR      │
    └──────┬───────┘          └──────┬───────┘          └──────┬───────┘
           │                         │                         │
           └─────────────────────────┼─────────────────────────┘
                                     │
                            ┌────────▼────────┐
                            │   RRF 融合排序   │
                            └────────┬────────┘
                                     │
                            ┌────────▼────────┐
                            │ Parent Chunk 扩展│
                            └────────┬────────┘
                                     │
                            ┌────────▼────────┐
                            │  LLM 生成 + 引用 │
                            └────────┬────────┘
                                     │
                            ┌────────▼────────┐
                            │    RAG 评估     │
                            └─────────────────┘
```

---

## <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4c1.png" width="24"> 项目结构

```
rag_bot/
├── app/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置管理 (pydantic-settings)
│   ├── llm_client.py           # LLM 调用（带重试）
│   ├── prompts.py              # 系统提示词 + 输出格式检测
│   ├── schemas.py              # 请求/响应模型
│   ├── utils.py                # 共享工具函数
│   │
│   ├── api/routers/            # HTTP 接入层
│   │   ├── chat.py             #   问答接口
│   │   ├── ingest.py           #   入库接口
│   │   ├── history.py          #   历史查询
│   │   └── system.py           #   健康检查
│   │
│   ├── bootstrap/              # RAG 管线组装
│   ├── ingest/                 # 文档入库管线
│   │   ├── batch_ingest.py     #   批量入库入口
│   │   ├── chunker.py          #   智能分块
│   │   ├── document_loader.py  #   文档加载
│   │   ├── embedders.py        #   Embedding 生成
│   │   └── manifest.py         #   增量检测
│   │
│   ├── retrievers/             # 检索器抽象层
│   │   ├── chroma_retriever.py #   ChromaDB 检索
│   │   ├── qdrant_retriever.py #   Qdrant 检索
│   │   ├── crag.py             #   矫正检索
│   │   ├── hyde_retriever.py   #   HyDE 检索
│   │   ├── mmr.py              #   多样性检索
│   │   └── cross_encoder_reranker.py  # 精排
│   │
│   ├── security/               # 敏感词 + RBAC
│   ├── services/               # 核心 RAG 编排
│   ├── history/                # SQLite 会话管理
│   ├── query_rewrite/          # 查询改写模块
│   ├── integrations/           # 企业微信适配
│   └── web/                    # 前端页面
│
├── eval/                       # RAG 评估
├── tests/                      # 单元测试 (93 passing)
├── docker-compose.yml          # Docker 编排
└── pyproject.toml              # 项目配置
```

---

## <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4c4.png" width="24"> 支持的文档格式

| 格式 | 扩展名 | 备注 |
|:---:|:---:|:---|
| <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4c3.png" width="16"> 文本文件 | `.txt` `.md` `.csv` `.log` | 自动检测编码 |
| <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4c4.png" width="16"> PDF | `.pdf` | 文本提取 + OCR 兜底 |
| <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4c3.png" width="16"> Word | `.doc` `.docx` | .doc 需 LibreOffice |
| <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4ca.png" width="16"> Excel | `.xlsx` | 自动读取所有 Sheet |
| <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4cb.png" width="16"> JSON | `.json` | 格式化输出 |

---

## <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f9ea.png" width="24"> 测试

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行特定模块
python -m pytest tests/test_utils.py -v

# 生成覆盖率报告
python -m pytest tests/ --cov=app --cov-report=html
```

---

## <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4ca.png" width="24"> RAG 评估

```bash
python eval/run.py --api-url http://localhost:8000
```

评估指标：关键词覆盖 · 上下文相关度 · 响应延迟

---

## <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4dd.png" width="24"> 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## <img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f31f.png" width="24"> License

[MIT License](LICENSE) - 自由使用，欢迎贡献
