# RAG 项目面试问答准备

> 基于简历描述与实际代码的交叉分析，覆盖面试官最可能追问的核心问题。
> 每个问题标注【代码依据】，便于你精准定位到实现细节。

---

## 一、RAG 整体架构设计

### Q1: 请介绍一下你的 RAG 系统整体架构？

**回答要点：**

系统采用经典的 RAG 三层架构：**文档处理层 → 检索层 → 生成层**，基于 FastAPI 提供 HTTP 服务。

```
文档入库: 文件读取 → OCR降级 → 分块(3种模式) → Embedding → 向量库(Chroma/Qdrant)
用户提问: Query改写 → 双路召回 → MMR去重 → CRAG纠错 → Parent解析 → 动态Prompt → LLM生成
```

- **框架选型**：LangChain 提供 Prompt 模板和 Chain 编排，FastAPI 提供 REST API，Chroma/Qdrant 作为向量存储后端（通过配置切换）
- **关键设计**：所有组件通过 `app/config.py` 的 70+ `.env` 参数配置化，工厂函数 `rag_factory.py` 负责组装

【代码依据】`app/bootstrap/rag_factory.py:58` — `build_rag_service()` 是总入口

---

### Q2: 为什么选择 LangChain？你用了 LangChain 的哪些能力？

**回答：**

实际上这个项目的 LangChain 使用是**轻量级**的，主要用了：
1. `ChatPromptTemplate` — 管理 system/human 消息模板
2. `RunnableLambda` — 构建处理链（prompt → LLM 调用）
3. `BaseMessage` 类型 — 消息格式标准化

**核心检索逻辑（CRAG、MMR、双路召回）都是自己实现的**，没有用 LangChain 的 Retriever 抽象。这避免了 LangChain 版本升级带来的兼容性问题，也保留了对检索逻辑的完全控制。

> **面试加分点**：能说出"为什么不用 LangChain 的 RetrievalQA chain" — 因为需要自定义 CRAG 评分+重试逻辑、双路召回竞争选择、动态 top_k 调整等，这些在 LangChain 的标准 chain 中不好实现。

【代码依据】`app/services/langchain_rag_service.py:252-269` — Chain 构建只用了 prompt + RunnableLambda

---

### Q3: 为什么同时支持 Chroma 和 Qdrant？怎么做到切换的？

**回答：**

通过**抽象基类 + 配置开关**模式：

- `BaseRetriever`（抽象基类）定义 `retrieve(query, top_k)` 接口
- `ChromaRetriever` 和 `QdrantRetriever` 分别实现
- `config.py` 中 `retriever_mode: str = "chroma"` 控制使用哪个
- `rag_factory.py` 的 `_build_base_retriever()` 根据配置实例化

Chroma 适合开发/小规模部署（嵌入式，无需额外服务），Qdrant 适合生产环境（独立服务，支持分布式）。这种设计让开发和生产环境可以无缝切换。

【代码依据】`app/retrievers/chroma_retriever.py:13` — `ChromaRetriever(BaseRetriever)`；`app/bootstrap/rag_factory.py:10-19` — 条件分支

---

## 二、文档处理与向量化入库

### Q4: 你提到支持 8 种文档格式，具体是怎么处理的？

**回答：**

在 `config.py:46` 配置了支持的扩展名：`.txt, .md, .pdf, .doc, .docx, .xlsx, .csv, .json`

处理策略：
- **纯文本格式**（txt, md, csv, json）：直接读取文本内容
- **PDF**：先用 `pypdf` 提取文本，如果提取的字符数 < `pdf_text_min_chars`（默认30），自动降级到 OCR（Tesseract）
- **Office 格式**（doc, docx, xlsx）：通过相应的 Python 库解析

**OCR 降级机制**是一个亮点：不是所有 PDF 都需要 OCR，只有扫描件/图片型 PDF 才触发。通过 `pdf_text_min_chars` 阈值判断。

【代码依据】`app/config.py:48-54` — PDF OCR 相关配置（engine, lang, dpi, max_pages）

---

### Q5: 增量更新是怎么实现的？

**回答：**

使用 **manifest 文件**记录已入库文档的状态：

- `ingest_manifest_path` 存储每个文件的路径、哈希值、入库时间
- 每次批量入库时，对比文件哈希，只处理新增/修改的文件
- 通过 `ingest_enable_incremental: bool = True` 控制是否启用

这种方式比"全量重建"高效得多，尤其在知识库文档频繁更新的场景下。

【代码依据】`app/config.py:59-60` — `ingest_manifest_path`, `ingest_enable_incremental`

---

### Q6: PDF OCR 降级的具体实现逻辑？

**回答：**

```
1. 用 pypdf 提取文本 → 检查提取字符数
2. 如果字符数 < pdf_text_min_chars(30) → 触发 OCR
3. OCR 引擎: tesseract, 语言: chi_sim+eng (中英文混合)
4. DPI: 200 (平衡识别精度和处理速度)
5. pdf_ocr_max_pages: 0 表示不限制页数
```

选择 Tesseract 而非 PaddleOCR 的考虑：Tesseract 更轻量，部署简单，对服务器资源要求低。如果需要更高精度，可以切换到 PaddleOCR（预留了 `pdf_ocr_engine` 配置项）。

---

## 三、分块策略（重点）

### Q7: 你提到了三种分块模式，它们有什么区别？分别适用什么场景？

**回答：**

| 模式 | 策略 | 适用场景 | 代码位置 |
|------|------|----------|----------|
| **Hybrid** | 标题切分 → 段落/句子拆分 → 贪心打包 | 通用文档，默认模式 | `_hybrid_split()` |
| **Sliding** | 固定窗口 + 重叠 | 无明确结构的长文本 | `_sliding_window_split()` |
| **Parent-Child** | 父块(完整章节) + 子块(句子级) | 需要精确检索+完整上下文 | `_parent_child_split()` |

**Hybrid 分块的核心逻辑**：
1. 按标题模式（Markdown `#`、中文"第X章"、数字编号）切分为章节
2. 每个章节按段落 `\n\n` 拆分，超长段落按句子拆分
3. 贪心打包：将小单元合并到不超过 `chunk_size`(800字符)，相邻 chunk 有 `overlap`(120字符)

**Parent-Child 分块的设计动机**：
- 小 chunk 检索精度高但上下文不足
- 大 chunk 上下文完整但检索噪音多
- 解决方案：检索时用 child chunk（精准匹配），生成时用 parent chunk（完整上下文）

【代码依据】`app/ingest/chunker.py:148-161` — `_hybrid_split()`；`app/ingest/chunker.py:164-200` — `_parent_child_split()`

---

### Q8: Parent-Child 分块中，parent 和 child 是怎么关联的？检索时怎么从 child 找到 parent？

**回答：**

**关联方式**：入库时，child chunk 的 metadata 中存储 `parent_chunk_id` 字段指向对应的 parent chunk。

**检索时的解析流程**（`_resolve_parent_chunks()`）：
1. 检索返回的是 child chunks（精度高）
2. 从每个 child 的 metadata 中提取 `parent_chunk_id`
3. 用 `parent_chunk_id` 从向量库中直接获取 parent chunk 的完整内容
4. 用 parent chunk 的内容作为 LLM 的上下文（信息更完整）

关键设计：**parent 和 child 存在同一个 collection 中**，通过 `chunk_level` metadata 区分。这样不需要额外的存储或查询逻辑。

【代码依据】`app/services/langchain_rag_service.py:271-308` — `_resolve_parent_chunks()`；`app/ingest/chunker.py:310-314` — child metadata 中的 `parent_chunk_id`

---

### Q9: 分块大小（800字符、120字符重叠、2000字符 parent）是怎么确定的？

**回答：**

这些参数都是**可配置的**（`config.py:56-58`），默认值的选择考虑了：

- **chunk_size=800**：约 400-500 个中文字/200-300 个英文词，适合 Embedding 模型的上下文窗口（text-embedding-3-small 支持 8191 tokens），同时保持检索粒度
- **chunk_overlap=120**：约 15% 的重叠率，保证相邻 chunk 的语义连续性，避免关键信息被截断在边界
- **parent_chunk_size=2000**：约一个完整章节，给 LLM 提供足够的上下文来生成完整回答

> **面试加分**：能说出"这些参数是通过实验调优的"，并举一个具体例子（如：overlap 从 0 调到 120 后，跨段落问题的召回率提升了多少）

---

## 四、多阶段检索链路（重点 + 难点）

### Q10: 什么是"双路召回"？你的实现和标准的 dense+sparse 双路有什么区别？

**回答：**

**简历中的"双路召回"**实际上是指**多查询竞争选择**，不是标准的 dense+sparse 双编码器：

```python
# langchain_rag_service.py:432-449 — _retrieve_best_docs()
candidates = [retrieval_query, standalone_question, question]
for query in candidates:
    docs = retriever.retrieve(query, top_k)
    rank = (count, max_score, coverage, avg_score)  # 4维排序
    if rank > best_rank:
        best_docs = docs
```

具体做法：
1. 用 3 个不同版本的查询分别检索：改写后的查询、独立问题、原始问题
2. 对每个检索结果计算 4 维排序指标：结果数量、最高分、查询覆盖率、平均分
3. 选择综合排序最高的那组结果

**和标准 dense+sparse 的区别**：
- 标准双路：dense embedding + sparse BM25，两路结果通过 RRF 或加权融合
- 我的实现：同一编码器，不同查询变体，竞争选择（不是融合）

> **面试追问准备**：如果面试官问"为什么不用 BM25 做稀疏检索"，可以回答："Chroma 原生不支持 BM25，需要额外引入 Elasticsearch 或自己实现倒排索引。当前方案在采购文档场景下效果够用，因为文档结构化程度高，查询改写已经能覆盖大部分召回需求。"

【代码依据】`app/services/langchain_rag_service.py:425-449` — `_retrieve_best_docs()`

---

### Q11: 请详细解释 CRAG（纠错式检索）的实现？

**回答：**

CRAG 的核心思想：**用 LLM 评估检索结果的质量，质量不够就改写查询重试**。

流程：
```
原始查询 → 检索 → LLM评分(correct/incorrect/ambiguous)
    ↓
如果 correct 比例 < threshold(0.5):
    → LLM改写查询 → 重新检索 → 再次评分
    → 最多重试 max_retries(1) 次
    ↓
如果所有重试都失败 → 回退到原始检索结果
```

**评分机制**（`crag.py:27`）：
- LLM 对每个文档打分：`correct`（直接相关）、`incorrect`（不相关）、`ambiguous`（部分相关）
- 保留 `correct + ambiguous` 的文档，丢弃 `incorrect`
- 如果 `correct` 占比低于阈值，触发查询改写

**查询改写**（`crag.py:79-88`）：LLM 生成替代查询，保持原始意图但用不同的关键词/表述

**容错设计**：
- LLM 评分异常 → 全部标记为 `ambiguous`（保守策略）
- 改写查询为空 → 使用原始查询
- 所有重试失败 → 回退到原始结果（不丢信息）

【代码依据】`app/retrievers/crag.py:105-131` — `retrieve()` 主循环；`app/retrievers/crag.py:56-77` — `_grade_docs()`

---

### Q12: MMR 是怎么实现的？为什么不用 numpy？

**回答：**

**MMR（Maximal Marginal Relevance）** 的目标：在保证与查询相关性的同时，最大化结果的多样性。

公式：`score(d) = λ * sim(d, q) - (1-λ) * max(sim(d, d_selected))`

实现步骤：
1. 从检索器取 `top_k * 3` 个候选（默认取 9 个）
2. 计算所有候选的 embedding 向量
3. 贪心选择：每轮选 MMR score 最高的文档加入结果集
4. 重复直到选够 `top_k` 个

**为什么不用 numpy**：
- 项目依赖中没有 numpy，不想为了一个功能引入整个 numpy 包
- cosine similarity 计算简单：`dot(a,b) / (||a|| * ||b||)`，纯 Python 就能高效实现
- 候选数量少（9个），O(n²) 的贪心选择在纯 Python 下也是毫秒级

【代码依据】`app/retrievers/mmr.py:8-14` — 纯 Python cosine similarity；`app/retrievers/mmr.py:28-67` — MMR 贪心选择

---

### Q13: MMR 的 λ 参数怎么调？不同值的效果？

**回答：**

`mmr_lambda` 范围 [0, 1]，默认 0.5：
- **λ=1.0**：纯相关性排序，等价于原始检索（不考虑多样性）
- **λ=0.0**：纯多样性排序，尽量选不同的文档（可能牺牲相关性）
- **λ=0.5**：平衡相关性和多样性

在采购文档场景中，λ=0.5 是合理的默认值。如果用户问"有哪些供应商"，需要多样性（多个不同供应商），λ 可以调低；如果问"某个具体条款"，需要相关性优先，λ 调高。

**实际影响**：MMR 默认是关闭的（`enable_mmr: bool = False`），因为额外的 embedding 调用会增加延迟。在需要列举类回答时可以开启。

【代码依据】`app/config.py:62-63` — `enable_mmr`, `mmr_lambda`

---

### Q14: 整个检索链路的执行顺序是什么？各组件是怎么串联的？

**回答：**

```python
# rag_factory.py:22-41 — _build_retriever_chain()
retriever = base_retriever          # Chroma 或 Qdrant
if enable_mmr:
    retriever = MMRRetriever(retriever)  # 包装：原始 → MMR
if enable_crag:
    retriever = CRAGRetriever(retriever) # 包装：MMR → CRAG
```

**在 service 层**（`answer()` 方法）的完整链路：
```
1. 敏感词过滤
2. 历史对话改写追问 → 独立问题
3. LLM Query 改写（rule/llm 模式）
4. 动态 top_k（枚举类问题自动扩大召回量）
5. 双路召回竞争选择（3个查询变体）
6. MMR 去重（可选）
7. CRAG 评分+纠错（可选）
8. Parent chunk 解析
9. 流程枚举回答（特殊处理）
10. 结构化输出（表格/列表）
11. 通用回答生成
```

**关键设计**：MMR 和 CRAG 是**装饰器模式**的 retriever wrapper，可以任意组合，互不耦合。

---

## 五、Query 改写与多轮对话

### Q15: Query 改写有几种模式？分别怎么实现的？

**回答：**

三种模式（`config.py:30` — `query_rewrite_mode`）：

| 模式 | 实现 | 适用场景 |
|------|------|----------|
| `none` | 不改写，直接用原始查询 | 简单场景，低延迟 |
| `rule` | 基于规则的改写（正则提取关键词） | 无 LLM 调用，零成本 |
| `llm` | LLM 改写（生成更精确的检索查询） | 复杂问题，效果最好 |

LLM 改写的核心 prompt：
```
结合历史对话，把用户当前追问改写成可以独立检索的完整问题。
要求：如果当前问题已经完整清晰，原样输出；保留原意，不补充未经提供的事实。
```

**改写缓存**：相同问题的改写结果缓存 900 秒（`_SessionQueryRewriteCache`），避免重复 LLM 调用。使用 OrderedDict + TTL 实现 LRU 淘汰。

【代码依据】`app/services/langchain_rag_service.py:28-32` — 改写 prompt；`app/services/langchain_rag_service.py:49-83` — 缓存实现

---

### Q16: 多轮对话历史感知是怎么做的？

**回答：**

分两层处理：

**第一层：追问识别**（`_is_follow_up_question()`）
- 短问题（≤6字符）自动判定为追问（如"然后呢？"、"具体呢？"）
- 包含追问关键词（这个、那个、下一步、继续、刚才）也判定为追问
- 非追问直接用原始问题检索，不浪费 LLM 调用

**第二层：追问改写**（`_rewrite_question_from_history()`）
- 将历史对话格式化为 `用户: ... 助手: ...` 的文本
- LLM 结合历史，将追问改写为独立完整的检索问题
- 例如：历史问"采购流程是什么？"，追问"那审批呢？" → 改写为"采购流程的审批环节是什么？"

**容错**：如果 LLM 改写失败，用最近一条用户消息拼接当前问题作为 fallback。

【代码依据】`app/services/langchain_rag_service.py:169-175` — 追问识别；`app/services/langchain_rag_service.py:347-389` — 历史改写

---

### Q17: 动态 top_k 调整是怎么做的？

**回答：**

不同类型的问题需要不同数量的检索结果：

```python
# langchain_rag_service.py:404-410
def _resolve_retrieval_top_k(self, question):
    if 流程枚举类问题:    # "相关流程"、"有哪些流程"
        return max(base_top_k, 12)
    if 一般枚举类问题:    # "有哪些"、"全部"、"列出"
        return max(base_top_k, min(12, base_top_k * 2))
    return base_top_k     # 默认 3
```

**设计动机**：用户问"有哪些流程"时，只检索 3 个结果肯定不够。自动扩大到 12 个，保证枚举类问题的召回完整性。

【代码依据】`app/services/langchain_rag_service.py:39-44` — 枚举检测正则

---

## 六、动态 Prompt 工程与结构化输出

### Q18: 结构化输出是怎么实现的？为什么要用 Prompt 切换而不是后处理？

**回答：**

**实现方式**：通过正则检测问题类型 → 选择不同的 system prompt → LLM 直接生成对应格式

| 问题类型 | 检测关键词 | 输出格式 | Prompt |
|----------|-----------|----------|--------|
| 部门职责 | 职责/负责/分工 | Markdown 表格 | `_TABLE_OUTPUT_SYSTEM_PROMPT` |
| 表格请求 | 表格/对比/一览表 | Markdown 表格 | `_TABLE_OUTPUT_SYSTEM_PROMPT` |
| 流程步骤 | 流程/步骤/操作 | 层级列表 | `_LIST_OUTPUT_SYSTEM_PROMPT` |
| 其他 | - | 自由文本 | `SYSTEM_PROMPT` |

**为什么用 Prompt 切换而不是后处理**：
1. **更自然**：LLM 直接生成表格比"自由文本→解析→格式化"更流畅
2. **更可靠**：后处理需要正则解析 LLM 输出，容易出错
3. **更灵活**：不同类型的表格/列表有不同的列结构，Prompt 可以精确指导

**流程枚举的特殊处理**（`_build_flow_enumeration_answer()`）：对"有哪些流程"类问题，不经过 LLM，直接从源文件中提取标题结构生成列表，保证枚举完整性。

【代码依据】`app/prompts.py:57-68` — `detect_output_format()`；`app/services/langchain_rag_service.py:588-673` — 流程枚举回答

---

### Q19: 流程枚举回答（`_build_flow_enumeration_answer`）是怎么工作的？

**回答：**

这是一个**绕过 LLM 的确定性回答**，专门处理"有哪些流程"类问题：

1. 从检索结果中找出最相关的源文件（按文档数量和最高分排序）
2. 加载该源文件的完整文本（支持 PDF 和文本格式）
3. 用正则表达式匹配所有 `4.XX` 格式的流程编码和标题
4. 对每个流程，提取其子章节的摘要作为详情
5. 按流程编码排序，生成结构化列表

**为什么不用 LLM**：
- LLM 可能遗漏某些流程（只从检索到的 3 个 chunk 中提取）
- 直接读源文件可以保证**枚举完整性**（简历中提到的"枚举类问题召回完整性提升显著"）
- 不消耗 LLM token，响应更快

【代码依据】`app/services/langchain_rag_service.py:588-673`；`app/services/langchain_rag_service.py:452-469` — 加载源文件

---

## 七、配置化与工程实践

### Q20: 你提到了 70+ 配置参数，会不会太多了？怎么管理的？

**回答：**

参数多是因为系统有**多个可切换的模块**，每个模块需要自己的配置。管理方式：

1. **pydantic-settings**：自动从 `.env` 文件读取，有类型校验和默认值
2. **分组注释**：相关参数用注释分组（LLM、Embedding、向量存储、检索、入库等）
3. **合理默认值**：所有参数都有开箱即用的默认值，用户只需按需修改
4. **`lru_cache`**：`get_settings()` 使用缓存，全局只解析一次

实际部署时，用户通常只需要配置 5-10 个关键参数（API Key、模型名、向量库地址），其他用默认值即可。

【代码依据】`app/config.py:8-124` — 完整配置类

---

### Q21: 你的系统有什么不足之处？如果让你重新设计，会改什么？

**回答（诚实但有深度的回答）**：

1. **没有测试覆盖**：整个项目没有单元测试和集成测试。如果重新设计，会先写测试（特别是 chunker 和 retriever 的测试）
2. **CRAG 和 MMR 默认关闭**：说明这些功能还处于"实验性"阶段，没有经过大规模验证
3. **单轮 Embedding 调用**：每次检索都要调用 Embedding API，没有本地缓存。可以用 Redis 缓存热门查询的 embedding
4. **没有流式输出**：用户要等 LLM 完整生成后才能看到回答。应该加 SSE 流式输出
5. **SQLite 的并发限制**：聊天历史用 SQLite 存储，高并发场景下会有写锁问题。生产环境应该换 PostgreSQL
6. **源文件 overlap boost 的权重（0.20）是硬编码的**：应该做成可配置参数

> **面试关键**：展示你能识别自己的不足，并有改进方案。不要说"没有不足"。

---

## 八、高频追问 & 场景题

### Q22: 如果用户问"采购部门有哪些职责？"，系统内部的完整处理链路是什么？

**回答（串联所有组件）**：

```
1. 敏感词检查 → 通过
2. 历史改写：不是追问（长度>6，无追问关键词），跳过
3. Query改写：LLM 可能改写为"采购部门的职能和责任范围"
4. 动态top_k：检测到"职责"关键词 → _ENUM_QUERY_HINT_RE → top_k = max(3, 6) = 6
5. 双路召回：
   - 用改写查询检索6个结果
   - 用独立问题检索6个结果
   - 用原始问题检索6个结果
   - 选综合排序最高的那组
6. MMR：如果开启，对结果去重
7. CRAG：如果开启，LLM评分过滤低质量结果
8. Parent解析：如果用parent_child模式，从child找到parent
9. 结构化输出：检测到"职责" → OutputFormat.TABLE → 用表格prompt
10. LLM生成：system prompt要求表格格式 + 知识库上下文 → 输出 Markdown 表格
```

---

### Q23: 如果检索结果全是 "incorrect" 怎么办？

**回答：**

CRAG 的容错机制：
1. 如果所有文档都是 `incorrect`，`correct_ratio = 0`，触发查询改写重试
2. 重试后仍然全 `incorrect`，达到 `max_retries` 上限
3. 回退到原始检索结果（`best_docs = base.retrieve(query=original_query)`）
4. **不丢弃信息**：即使 CRAG 认为质量低，也保留原始结果让 LLM 尝试回答
5. 如果最终无结果，返回"当前知识库暂无相关资料"

【代码依据】`app/retrievers/crag.py:129-130` — 回退逻辑

---

### Q24: 你的系统怎么处理"知识库没有相关信息"的情况？

**回答：**

多层兜底：
1. **检索层**：如果所有查询变体都返回空结果 → 直接返回 `NO_KB_HIT_MESSAGE`
2. **距离过滤层**：ChromaRetriever 有距离阈值 `rag_max_retrieval_distance=1.25`，超过阈值的结果被过滤。但如果过滤后为空，**放弃距离过滤**返回原始结果（宁可噪音也不丢信息）
3. **生成层**：Prompt 中明确要求"知识库无相关资料时回答'当前知识库暂无相关资料'"

---

### Q25: Embedding 批次大小自动调整是怎么回事？

**回答：**

有些 OpenAI-compatible 的 API 对单次 embedding 请求有额外限制（比如最多 10 条文本）。系统通过**异常捕获 + 自动拆分**处理：

```python
# embedders.py:50-69
try:
    resp = client.embeddings.create(model=model, input=text_list)
except BadRequestError as exc:
    limit = extract_batch_limit(exc)  # 从错误信息中提取限制数字
    if limit:
        # 自动拆分为更小的批次
        for i in range(0, len(text_list), limit):
            sub_vectors = self._embed_with_auto_batch(text_list[i:i+limit])
```

从错误信息 `larger than N` 中用正则提取批次限制，然后递归拆分。这样不需要预先知道 API 的限制。

---

## 九、简历措辞建议

### ⚠️ 简历描述 vs 实际实现的差异

| 简历描述 | 实际实现 | 面试风险 |
|----------|----------|----------|
| "双路召回" | 多查询竞争选择（同一编码器，不同查询变体） | 面试官可能理解为 dense+sparse，需要澄清 |
| "纠错式检索（CRAG）" | 实现正确，但默认关闭（`enable_crag: bool = False`） | 被问"为什么默认关闭"需要有说辞 |
| "MMR 去重" | 实现正确，但默认关闭（`enable_mmr: bool = False`） | 同上 |
| "枚举类问题召回完整性提升显著" | 流程枚举确实从源文件提取，但没有量化数据 | 被问"提升了多少"需要有具体数字 |
| "覆盖采购规章制度全生命周期检索" | 领域适配在 Prompt 中，不是模型微调 | 合理，但要能解释"全生命周期"的含义 |

### 建议的简历措辞优化

```
原：设计双路召回 + 纠错式检索（CRAG）+ MMR 去重的多阶段检索链路
改：设计多查询竞争召回 + CRAG 纠错重试 + MMR 多样性重排序的多阶段检索链路
```

```
原：枚举类问题召回完整性提升显著
改：枚举类问题通过源文件全文解析 + 动态扩大召回窗口(top_k×2~4)，召回完整性从N%提升至M%（需要补测试数据）
```
