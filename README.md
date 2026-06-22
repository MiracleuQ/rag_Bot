<div align="center">

# RAG 知识库问答系统

**企业级 RAG 服务 | LangChain + Chroma/Qdrant**

[![CI](https://img.shields.io/github/actions/workflow/status/MiracleuQ/rag_Bot/ci.yml?branch=master&label=CI)](https://github.com/MiracleuQ/rag_Bot/actions)
[![Tests](https://img.shields.io/badge/tests-93%20passing-brightgreen)](https://github.com/MiracleuQ/rag_Bot)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-LCEL-000000?style=flat)](https://python.langchain.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

开箱即用的企业知识库 RAG 服务，支持多格式文档导入、语义检索、多轮对话。

[快速开始](#快速开始) · [API 文档](#api-接口) · [架构设计](#架构概览) · [高级功能](#高级-rag-功能)

</div>

---

## 功能特性

<table>
  <tr>
    <td width="50%">

**核心能力**
- 多格式解析：PDF / DOCX / XLSX / MD / TXT / CSV / JSON
- PDF OCR 降级：PyPDF + Tesseract 双通道，文本不足自动兜底
- 智能分块：Hybrid / Sliding Window / Parent-Child 三模式
- 双路检索：ChromaDB / Qdrant 可切换，Embedding 去重

    </td>
    <td width="50%">

**高级 RAG**
- HyDE：假设文档嵌入，弥合口语与文档词汇鸿沟
- CRAG：矫正式检索，自动过滤低质量结果
- MMR：多样性过滤，避免结果同质化
- Cross-Encoder：bge-reranker 精排，MRR 提升 10-25%

    </td>
  </tr>
  <tr>
    <td width="50%">

**企业级特性**
- RBAC 权限：admin / editor / viewer 三角色控制
- 租户隔离：向量库前缀 + DB 列，零代码侵入
- 安全过滤：敏感词归一化 + hmac 防时序攻击
- 多轮历史：SQLite 持久化，上下文感知

    </td>
    <td width="50%">

**工程化**
- 增量入库：manifest + SHA256，变更检测 O(1)
- RRF 融合：三路查询分数融合排序
- TTL 缓存：查询改写结果缓存，避免重复调用
- RAG 评估：25 条 QA 集 + 自动化评估脚本

    </td>
  </tr>
</table>

---

## 快速开始

### 方式一：本地启动

```bash
pip install -r requirements.txt
cp .env.example .env    # 填入 API Key
uvicorn app.main:app --reload --port 8000
```

### 方式二：Docker 启动

```bash
cp .env.example .env    # 填入 API Key
docker-compose up -d    # 含 Qdrant 向量库
```

启动后访问 **http://localhost:8000** 打开 Web 界面。

---

## API 接口

| 接口 | 方法 | 说明 |
|:---|:---:|:---|
| `/chat` | POST | 问答接口 |
| `/ingest` | POST | 批量入库（需 editor 权限） |
| `/history/sessions` | GET | 会话历史查询 |
| `/health` | GET | 健康检查 |

<details>
<summary>展开查看请求示例</summary>

```bash
# 问答
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"question": "采购流程的主要步骤有哪些？"}'

# 入库
curl -X POST "http://localhost:8000/ingest" \
  -H "Content-Type: application/json" \
  -H "X-Role: editor" \
  -d '{"input_dir": "data/knowledge_base", "dry_run": false}'

# 会话历史
curl "http://localhost:8000/history/sessions?user_id=user1" \
  -H "X-User-ID: user1"
```

</details>

---

## 批量入库

```bash
# 预览变更（不写入）
python -m app.ingest.batch_ingest --dry-run

# 执行入库
python -m app.ingest.batch_ingest

# 完全重建索引
python -m app.ingest.batch_ingest --full-reindex
```

---

## 核心配置

<details>
<summary><b>基础配置</b></summary>

```dotenv
RETRIEVER_MODE=chroma          # chroma | qdrant
EMBEDDING_MODEL=text-embedding-3-small
LLM_MODEL=gpt-4o-mini
```

</details>

<details>
<summary><b>高级 RAG 配置</b></summary>

```dotenv
ENABLE_HYDE=true               # 假设文档嵌入
ENABLE_CRAG=true               # 矫正检索
ENABLE_MMR=true                # 多样性检索
ENABLE_CROSS_ENCODER_RERANKER=true  # Cross-Encoder 精排
```

</details>

<details>
<summary><b>企业级配置</b></summary>

```dotenv
RBAC_ENABLED=false             # RBAC 权限控制
TENANT_ISOLATION_ENABLED=false  # 租户数据隔离
```

</details>

完整配置请参考 [`.env.example`](.env.example)。

---

## 高级 RAG 功能

<details>
<summary><b>Contextual Chunk Enrichment</b></summary>

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

用 `BAAI/bge-reranker-v2-m3` 对检索结果做精排，MRR 提升 10-25%。

需额外安装：`pip install sentence-transformers`

</details>

<details>
<summary><b>HyDE</b></summary>

先用 LLM 生成假设文档再检索，弥合口语化查询与正式文档的词汇鸿沟。

</details>

<details>
<summary><b>Reciprocal Rank Fusion</b></summary>

多路查询（原始问题、改写问题、历史问题）结果自动融合排序，无需配置，默认开启。

</details>

<details>
<summary><b>Embedding Near-Duplicate Detection</b></summary>

入库时检测余弦相似度 > 0.95 的近似 chunk 并跳过，防止修订版文档污染索引。

</details>

---

## 架构概览

```
                        ┌─────────────────┐
                        │    用户提问     │
                        └────────┬────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   RBAC 权限校验          │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   租户数据隔离           │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   敏感词过滤             │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   历史对话改写           │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   查询改写               │
                    └────────────┬────────────┘
                                 │
         ┌───────────┬───────────┼───────────┐
         ▼           ▼           ▼           ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
    │  HyDE   │ │  CRAG   │ │   MMR   │ │Cross-Enc│
    └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
         └──────────┴───────────┴──────────┘
                         │
              ┌──────────▼──────────┐
              │   RRF 融合排序       │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  Parent Chunk 扩展   │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  LLM 生成 + 引用    │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  RAG 评估           │
              └─────────────────────┘
```

---

## 项目结构

```
app/
├── main.py                 # FastAPI 入口
├── config.py               # 配置管理 (pydantic-settings)
├── llm_client.py           # LLM 调用（带重试）
├── prompts.py              # 系统提示词 + 输出格式检测
├── schemas.py              # 请求/响应模型
├── utils.py                # 共享工具函数
│
├── api/routers/            # HTTP 接入层
├── bootstrap/              # RAG 管线组装
├── ingest/                 # 文档入库管线
├── retrievers/             # 检索器抽象层
├── security/               # 敏感词 + RBAC
├── services/               # 核心 RAG 编排
├── history/                # SQLite 会话管理
├── query_rewrite/          # 查询改写模块
├── integrations/           # 企业微信适配
└── web/                    # 前端页面

eval/                       # RAG 评估
tests/                      # 单元测试 (93 passing)
```

---

## 支持的文档格式

| 格式 | 扩展名 | 备注 |
|:---:|:---:|:---|
| 文本文件 | `.txt` `.md` `.csv` `.log` | 自动检测编码 |
| PDF | `.pdf` | 文本提取 + OCR 兜底 |
| Word | `.doc` `.docx` | .doc 需 LibreOffice |
| Excel | `.xlsx` | 自动读取所有 Sheet |
| JSON | `.json` | 格式化输出 |

---

## 测试

```bash
python -m pytest tests/ -v                    # 运行全部测试
python -m pytest tests/test_utils.py -v      # 运行特定模块
python -m pytest tests/ --cov=app            # 覆盖率报告
```

---

## RAG 评估

```bash
python eval/run.py --api-url http://localhost:8000
```

评估指标：关键词覆盖 · 上下文相关度 · 响应延迟

---

## License

[MIT](LICENSE)
