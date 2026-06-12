# RAG 项目技术实现与面试复习文档

本文档用于梳理本项目中已经实现的 RAG 技术点、简历表述中可延展但尚未完整实现的技术点，以及面试官可能追问的问题与参考回答。

## 1. 项目整体架构

本项目是一个面向企业采购知识库的 RAG 问答服务，整体链路如下：

```text
用户问题
  -> FastAPI 接口层
  -> 会话历史读取
  -> 历史追问改写
  -> Query Rewrite
  -> Chroma/Qdrant 向量检索
  -> 多路召回择优
  -> Prompt 构造
  -> OpenAI-compatible LLM 生成答案
  -> 返回答案与引用文档
```

主要模块：

- `app/main.py`：FastAPI 应用创建、CORS、路由挂载、RAG 服务初始化。
- `app/api/routers/chat.py`：`/chat` 和企业微信适配接口。
- `app/services/langchain_rag_service.py`：核心 RAG 编排逻辑。
- `app/ingest/`：文档解析、分块、向量化、增量入库。
- `app/retrievers/`：Chroma/Qdrant 检索器。
- `app/query_rewrite/`：规则改写与 LLM 改写。
- `app/history/`：SQLite 会话历史与多轮上下文。

## 2. 已实现技术点

### 2.1 FastAPI + LangChain LCEL

FastAPI 负责 API 层，包括：

- `/chat` 问答接口；
- `/history/sessions` 历史会话接口；
- `/history/sessions/{session_id}/messages` 历史消息接口；
- `/health` 健康检查；
- `/` 前端测试页面。

LangChain 主要用于 Prompt 模板和 LCEL 链式编排：

```text
RunnableLambda
  -> ChatPromptTemplate
  -> RunnableLambda 调用 LLMClient
```

面试表达：

> 我没有把业务逻辑完全绑定在 LangChain 上，而是只使用它做 Prompt 模板和链式编排。检索、改写、分块、历史上下文等核心逻辑仍然是自定义实现，这样更容易控制企业知识库场景下的细节。

### 2.2 Chroma/Qdrant 双向量库

项目同时支持 Chroma 和 Qdrant：

- Chroma：适合本地开发、小规模部署、本地持久化；
- Qdrant：适合服务化部署、远程向量库、生产扩展。

相关配置：

```dotenv
RETRIEVER_MODE=chroma
VECTOR_STORE_MODE=chroma
VECTOR_STORE_COLLECTION=rag_kb_default
CHROMA_PERSIST_DIR=data/vector_store/chroma

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_TIMEOUT_SEC=30
```

实现方式：

- 检索阶段根据 `RETRIEVER_MODE` 创建 `ChromaRetriever` 或 `QdrantRetriever`；
- 入库阶段根据 `VECTOR_STORE_MODE` 创建 `ChromaVectorStore` 或 `QdrantVectorStore`；
- 两边都通过抽象接口屏蔽底层向量库差异。

面试表达：

> 我把向量库访问封装成检索器和写入器两层。业务侧只关心 retrieve 和 upsert，不直接依赖 Chroma 或 Qdrant 的 SDK，因此可以通过配置切换本地向量库和远程向量服务。

### 2.3 多格式文档解析

当前支持 8 类文档格式：

- `.txt`
- `.md`
- `.pdf`
- `.doc`
- `.docx`
- `.xlsx`
- `.csv`
- `.json`

解析策略：

- 文本类文件按多编码尝试读取，如 `utf-8`、`gb18030`、`gbk`；
- JSON 会格式化为可检索文本；
- PDF 先用 `pypdf` 抽取文本；
- 如果 PDF 文本抽取内容过少，则走 OCR 降级；
- DOCX 用 `python-docx` 解析段落和表格；
- XLSX 用 `openpyxl` 读取各 Sheet；
- DOC 使用 Word COM、antiword、catdoc、LibreOffice 多策略兜底。

面试表达：

> 企业知识库中文档来源比较杂，所以解析层按后缀分发，并对 PDF、DOC 这类复杂格式做了兜底策略。PDF 优先文本抽取，低于阈值时再渲染页面走 Tesseract OCR，避免普通 PDF 也走高成本 OCR。

### 2.4 PDF OCR 降级

PDF 解析流程：

```text
PDF 文件
  -> pypdf 文本抽取
  -> 判断文本长度是否达到阈值
  -> 达到：直接使用文本
  -> 不足：pypdfium2 渲染页面
  -> pytesseract OCR
  -> 返回 OCR 文本
```

关键配置：

```dotenv
PDF_OCR_FALLBACK_ENABLED=true
PDF_TEXT_MIN_CHARS=30
PDF_OCR_ENGINE=tesseract
PDF_OCR_LANG=chi_sim+eng
PDF_OCR_DPI=200
PDF_OCR_MAX_PAGES=0
PDF_OCR_TESSERACT_CMD=
```

面试表达：

> 我用文本长度作为是否需要 OCR 的启发式判断。因为很多扫描版制度 PDF 用 pypdf 抽不到有效文本，如果直接入库会产生空文档。OCR 降级可以保证扫描件也能进入向量库。

### 2.5 增量向量化入库

项目使用 `manifest + 内容哈希` 做增量入库。

每个文档会记录：

- `doc_id`
- `source_path`
- `content_sha256`
- `chunk_count`
- `point_ids`
- `updated_at`

增量逻辑：

```text
扫描当前知识库目录
  -> 解析文档内容
  -> 计算 content_sha256
  -> 和上次 manifest 对比
  -> 新增文件：解析、分块、向量化、写入
  -> 修改文件：重算向量，清理过期 point
  -> 删除文件：删除旧 point
  -> 未变化文件：跳过
```

面试表达：

> 我没有每次全量重建向量库，而是维护 manifest。每次入库只处理新增、修改、删除的文档，避免重复调用 embedding API，也减少向量库写入压力。

### 2.6 分块策略：Sliding 与 Hybrid

项目实现了两种分块模式。

#### Sliding

固定窗口滑动分块：

```text
chunk_size=800
chunk_overlap=120
```

优点：

- 实现简单；
- 不依赖文档结构；
- 适合普通长文本。

缺点：

- 可能切断章节、表格和流程步骤；
- 对制度类文档的语义完整性不够好。

#### Hybrid

混合分块流程：

```text
原始文档
  -> 按标题/章节切 section
  -> section 内按段落/句子切 unit
  -> 按 chunk_size 贪心打包
  -> 保留 overlap
```

适合企业制度类文档，因为制度文档通常具有：

- 章节标题；
- 流程编号；
- 条款结构；
- 表格说明；
- 职责描述。

面试表达：

> Sliding 容易切断流程语义，所以我默认使用 Hybrid。它先识别标题和章节边界，再在章节内部做段落、句子级切分，最后打包成 chunk，这样能尽量保证一个 chunk 是语义完整的。

### 2.7 Query Rewrite

项目支持三种 Query Rewrite 模式：

- `none`：关闭改写；
- `rule`：规则改写；
- `llm`：LLM 改写。

规则改写主要处理：

- 去掉“帮我、请问、麻烦”等口语化前缀；
- 去掉“是什么、吗”等低信息量后缀；
- 标点规范化；
- 控制最大长度。

LLM 改写主要处理：

- 口语问题规整；
- 缺少关键词的问题补全；
- 长问题压缩；
- 保留关键实体和约束。

为了避免改写失败影响主流程：

- LLM 改写异常时回退原问题；
- 改写结果为空时回退原问题；
- 改写结果过长时截断；
- 改写结果使用 session 级 TTL/LRU 缓存。

面试表达：

> Query Rewrite 的风险是改写漂移，所以我没有只依赖改写后的 query。改写失败或为空时会回退原问题，同时检索阶段会保留原问题参与召回。

### 2.8 多轮历史感知

会话历史使用 SQLite 存储。

每轮请求会：

1. 根据 `session_id` 找到会话；
2. 读取最近 N 条历史消息；
3. 判断当前问题是否像追问；
4. 如果是追问，则结合历史改写成独立问题；
5. 用独立问题进入检索链路。

例如：

```text
上一轮：采购订单变更流程有哪些步骤？
当前轮：第二步要谁审批？
改写后：采购订单变更流程的第二步需要谁审批？
```

面试表达：

> 多轮问答的关键不是把所有历史都塞进生成 Prompt，而是先判断当前问题是不是追问。如果是追问，就把它改写成独立可检索的问题，再进入 RAG 检索。

### 2.9 双路/多路召回

项目实现了多路召回择优，不是只用一个 query 检索。

候选 query 包括：

- Query Rewrite 后的问题；
- 历史追问改写后的 standalone question；
- 用户原始问题。

每一路都会检索，然后根据以下指标择优：

- 命中文档数量；
- 最大相似度分数；
- query 和前几个文档内容的覆盖率；
- 平均相似度。

面试表达：

> 多路召回主要是为了解决 Query Rewrite 改写漂移的问题。改写 query 可能更适合检索，但也可能丢失原问题中的实体，所以我保留原问题和历史改写问题一起参与召回，再选择效果更好的那一路。

### 2.10 枚举类/流程类问题增强

枚举类问题特点：

- 用户通常问“有哪些、全部、列出、完整流程”等；
- 普通 top-k 容易只召回部分片段；
- 回答容易漏项。

项目中做了两类增强：

1. 对枚举类问题提高检索 top-k；
2. 对流程枚举类问题，从文档中解析流程标题和编号，生成结构化列表。

面试表达：

> 枚举类问题不能只拿默认 top3，因为它需要覆盖完整条目。我会先识别枚举意图，提高召回数量；对于流程类文档，再利用流程编号和标题规则做结构化抽取，降低漏项概率。

## 3. 当前简历中需要谨慎表述的技术点

你的简历中提到了：

- Parent-Child；
- CRAG；
- MMR；
- 动态 Prompt 自动匹配表格/层级列表；
- 部门职责类输出格式。

这些方向都合理，但当前代码里没有完整实现证据。

建议更稳妥的表述：

> 基于 FastAPI + LangChain LCEL 构建企业采购知识库 RAG 问答服务，接入 Chroma/Qdrant 双向量库，支持 PDF、DOC/DOCX、XLSX、CSV、JSON、Markdown、TXT 等文档解析；PDF 文本抽取失败时自动降级 OCR。实现基于 manifest + 内容哈希的增量入库、删除清理与 Hybrid/Sliding 分块策略。
>
> 设计多路查询召回链路：结合历史追问改写、规则/LLM Query Rewrite、原问题兜底召回和候选结果择优排序，缓解 Query 改写漂移与枚举类问题召回不完整问题；针对流程枚举类问题增加结构化列表输出，并支持 SQLite 会话历史与用户作用域隔离。

如果你后续补上 Reranker、MMR、CRAG，再把简历写得更强会更稳。

## 4. Reranker

### 4.1 Reranker 是什么

Reranker 叫重排序器。

向量检索一般是粗召回：

```text
从向量库中先找出 top20/top50 个可能相关的 chunk
```

Reranker 再对每个候选 chunk 重新判断：

```text
这个 chunk 能不能直接、准确地回答当前问题？
```

它解决的问题是：

- 向量相似度高，不一定业务相关；
- 关键词相似，不一定能回答问题；
- 初召回排序可能不准；
- 企业制度文档中大量章节用词相近，容易误召回。

### 4.2 Reranker 的打分标准

常见打分标准：

1. 语义相关性  
   chunk 是否和问题讨论同一主题。

2. 答案充分性  
   chunk 是否包含足够信息回答问题。

3. 关键词/实体匹配  
   是否命中制度名、流程名、部门名、表单名、编号等关键实体。

4. 问题类型匹配  
   “是什么”更需要定义片段；“怎么做”更需要流程片段；“有哪些”更需要清单片段。

5. 来源可信度  
   文件名、章节标题、正式制度文档、新版本文档可以加权。

6. 条件约束匹配  
   如果问题包含“新供应商导入时，质量部门负责什么”，高分 chunk 需要同时覆盖“新供应商导入 + 质量部门 + 职责”。

### 4.3 模型型 Reranker 实现

常见模型：

- `bge-reranker`
- Cohere Rerank
- Jina Reranker
- Cross-Encoder Reranker

输入：

```text
query + candidate_chunk
```

输出：

```text
相关性分数
```

伪代码：

```python
docs = retriever.retrieve(query, top_k=30)

pairs = [(query, doc.content) for doc in docs]
scores = reranker.score(pairs)

reranked_docs = sorted(
    zip(docs, scores),
    key=lambda item: item[1],
    reverse=True,
)

final_docs = [doc for doc, score in reranked_docs[:5]]
```

### 4.4 规则型 Reranker 实现

如果不用模型，可以做轻量打分：

```python
score = 0.6 * vector_score
score += 0.2 * keyword_coverage
score += 0.1 * source_title_match
score += 0.1 * question_type_match
```

本项目当前更接近轻量 rerank：

- Chroma 检索后结合向量分数与来源文件名 overlap 排序；
- 多路召回时用命中数量、最大分数、覆盖率、平均分数择优。

面试表达：

> Reranker 的标准不是单纯看 embedding 相似度，而是判断候选片段对当前问题的可用性。我会综合主题相关性、关键实体匹配、答案充分性、问题类型匹配和来源可信度。模型型 reranker 输入 query-document pair 输出相关性分数；轻量实现可以用向量分数、关键词覆盖、标题命中和业务规则做加权。

## 5. MMR

### 5.1 MMR 是什么

MMR 全称 Maximal Marginal Relevance，最大边际相关性。

它解决的是：

```text
召回结果高度重复，覆盖面差
```

普通 top-k 可能返回 5 个非常相似的 chunk：

```text
chunk1：采购订单变更审批
chunk2：采购订单变更审批补充说明
chunk3：采购订单变更审批注意事项
chunk4：采购订单变更审批表单
chunk5：采购订单变更审批记录
```

这些都相关，但内容集中，容易遗漏其他流程环节。

MMR 希望结果：

```text
既相关，又不重复
```

### 5.2 MMR 公式

```text
MMR = λ * Sim(query, doc) - (1 - λ) * max Sim(doc, selected_doc)
```

含义：

- `Sim(query, doc)`：候选文档与问题的相关性；
- `max Sim(doc, selected_doc)`：候选文档与已选文档的最大相似度；
- `λ`：相关性和多样性的平衡系数，常用 `0.5 ~ 0.8`。

`λ` 越大，越偏向相关性；`λ` 越小，越偏向多样性。

### 5.3 MMR 实现伪代码

```python
def mmr(query_vector, candidate_docs, candidate_vectors, top_k=5, lambda_mult=0.7):
    selected = []
    remaining = list(range(len(candidate_docs)))

    while remaining and len(selected) < top_k:
        best_idx = None
        best_score = float("-inf")

        for idx in remaining:
            relevance = cosine_similarity(query_vector, candidate_vectors[idx])

            if not selected:
                diversity_penalty = 0
            else:
                diversity_penalty = max(
                    cosine_similarity(candidate_vectors[idx], candidate_vectors[j])
                    for j in selected
                )

            score = lambda_mult * relevance - (1 - lambda_mult) * diversity_penalty

            if score > best_score:
                best_score = score
                best_idx = idx

        selected.append(best_idx)
        remaining.remove(best_idx)

    return [candidate_docs[i] for i in selected]
```

接入 RAG 的位置：

```text
向量库召回 top30
  -> MMR 从 top30 中选 top5
  -> 交给 LLM
```

面试表达：

> MMR 不是单纯选择相似度最高的 chunk，而是在每轮选择时惩罚和已选 chunk 过于相似的候选。这样可以避免 top-k 全部来自同一段附近，提升上下文覆盖面，特别适合枚举类和流程类问题。

## 6. CRAG

### 6.1 CRAG 是什么

CRAG 通常指 Corrective RAG，纠错式 RAG。

核心思想：

```text
检索后不要马上回答，而是先判断检索结果是否足够可靠。
```

典型流程：

```text
用户问题
  -> 初次检索
  -> 检索结果评估
  -> 结果好：直接生成
  -> 结果差：改写 query / 扩大 top-k / 换检索策略 / 重检索
  -> 仍然不好：返回资料不足
```

### 6.2 CRAG 的关键模块

1. Retriever  
   负责初次检索。

2. Retrieval Grader  
   判断检索结果是否相关、充分。

3. Corrector  
   如果结果不好，决定如何纠错。

4. Generator  
   基于最终可信上下文生成答案。

### 6.3 规则型 CRAG

简单评估器：

```python
def grade_retrieval(query, docs):
    if not docs:
        return "bad"

    max_score = max(doc.score or 0 for doc in docs)
    if max_score < 0.45:
        return "bad"

    coverage = keyword_coverage(query, docs[:3])
    if coverage < 0.2:
        return "bad"

    return "good"
```

完整流程：

```python
docs = retriever.retrieve(query, top_k=10)
grade = grade_retrieval(query, docs)

if grade == "good":
    final_docs = docs[:5]
else:
    rewritten_query = query_rewriter.rewrite(query)
    docs = retriever.retrieve(rewritten_query, top_k=20)
    grade = grade_retrieval(rewritten_query, docs)

    if grade != "good":
        return "当前资料不足以准确回答该问题。"

answer = llm.generate(query, final_docs)
```

### 6.4 LLM 型 CRAG

也可以让 LLM 判断检索结果：

```text
请判断以下资料是否足以回答用户问题。
只输出 good / partial / bad。

用户问题：
...

检索资料：
...
```

决策：

```text
good：正常回答
partial：回答并提示资料不足
bad：重写 query 后重新检索
```

面试表达：

> CRAG 的重点不是某个固定算法，而是在检索后增加评估与纠错环节。我会先判断初次召回结果是否相关和充分，如果分数低或关键词覆盖不足，就触发 query rewrite、扩大 top-k 或混合检索；如果多次检索仍然不足，就明确返回资料不足，而不是强行生成。

## 7. 召回率怎么检测

召回率衡量的是：

```text
系统有没有把应该找到的文档或 chunk 找出来。
```

常用指标：

```text
Recall@K = top K 中命中的相关文档数 / 该问题所有相关文档数
```

例子：

```text
问题：采购订单变更流程有哪些步骤？

人工标注相关 chunk：
A, B, C, D

系统 top5 召回：
A, C, X, Y, Z

Recall@5 = 2 / 4 = 50%
```

另一个常见指标是 Hit@K：

```text
top K 中只要命中至少一个正确 chunk，就算命中。
```

评估流程：

1. 构建评测集  
   每条样本包含 question 和人工标注的相关 doc_id/chunk_id/章节。

2. 只跑检索，不跑生成  
   这样可以单独评估 retriever，不被 LLM 生成质量干扰。

3. 统计 Recall@3、Recall@5、Recall@10、Hit@K、MRR。

4. 按问题类型分组  
   例如定义类、流程类、枚举类、职责类、追问类。

5. 对比不同策略  
   例如原始 query、Query Rewrite、双路召回、Reranker、MMR、不同 chunk_size。

面试表达：

> 我会先构建一套检索评测集，每条样本包含 question 和人工标注的相关 chunk_id 或文档章节。评估时只跑 retriever，不跑 LLM，统计 Recall@K、Hit@K、MRR 等指标。然后按问题类型分组分析，判断 Query Rewrite、双路召回、chunk size、reranker 是否真的带来提升。

## 8. 面试常见问题与参考回答

### Q1：为什么要用 RAG，而不是直接微调模型？

答：

> 企业制度、流程文件经常变化，RAG 更适合知识频繁更新的场景。文档更新后只需要重新入库向量，不需要重新训练模型。微调更适合学习风格或固定任务模式，不适合承载大量实时变化的企业知识。

### Q2：为什么要做 Query Rewrite？

答：

> 用户问题往往比较口语化，比如“这个怎么弄”“第二步呢”，直接检索效果不好。Query Rewrite 的目标是把问题改写成独立、明确、适合检索的查询。但为了避免改写漂移，我会保留原问题参与召回，并在改写失败时回退原问题。

### Q3：为什么做多路召回？

答：

> 单一路径有风险。改写 query 可能更适合检索，但也可能丢失原始实体；原问题保真度高，但可能太口语化。所以我让改写问题、历史改写问题和原问题都参与召回，再按命中数量、相似度和覆盖率选择更好的结果。

### Q4：为什么 Hybrid 分块比 Sliding 更适合制度文档？

答：

> 制度文档有章节、条款、流程编号。纯 Sliding 可能把一个流程步骤切成两段，也可能把两个章节混在一起。Hybrid 会先按标题切章节，再按段落和句子拆分，最后打包成 chunk，语义完整性更好。

### Q5：如果检索不到正确内容怎么办？

答：

> 当前项目有无结果返回和多路召回兜底。进一步可以引入 CRAG：先评估检索结果是否足够相关，如果不相关就改写 query、扩大 top-k 或换检索策略；如果仍然不足，就明确回答资料不足，而不是强行生成。

### Q6：如何防止幻觉？

答：

> Prompt 中明确要求只能基于知识库回答；没有相关资料时返回固定话术；检索为空时不调用生成；后续可以加入 CRAG 评估、引用校验和 answer grounding，确保答案中的关键结论能在检索上下文中找到依据。

### Q7：Reranker 和向量检索有什么区别？

答：

> 向量检索是粗召回，主要看 embedding 相似度；Reranker 是精排，会同时读 query 和 chunk，判断这个 chunk 对当前问题是否真正有用。它更关注答案充分性、实体匹配和问题类型匹配。

### Q8：MMR 适合解决什么问题？

答：

> MMR 适合解决结果重复的问题。普通 top-k 可能召回多个来自同一章节附近的 chunk，相关但重复。MMR 会在相关性之外惩罚与已选结果过于相似的候选，从而提高上下文覆盖面。

### Q9：CRAG 和 Query Rewrite 有什么区别？

答：

> Query Rewrite 是检索前优化 query；CRAG 是检索后评估结果是否可靠。如果检索结果不好，CRAG 可以触发 Query Rewrite、扩大 top-k、混合检索或返回资料不足。CRAG 是一个带反馈的纠错流程。

### Q10：召回率怎么评估？

答：

> 构建带人工标注的评测集，每条样本标注相关 chunk_id 或章节。评估时只跑 retriever，统计 Recall@K、Hit@K、MRR。然后按问题类型分组，比较不同策略对召回效果的影响。

## 9. 后续优化路线

建议优化优先级：

1. 补自动化评测集  
   先有 question -> relevant chunk 的数据集，才能量化优化效果。

2. 引入 Reranker  
   先用 top30 粗召回，再用 reranker 选 top5。

3. 实现 MMR  
   在候选结果中选择相关但不重复的上下文，提升枚举类问题覆盖面。

4. 实现标准 CRAG  
   增加检索评估器，支持 bad/partial/good 分支。

5. 实现 Parent-Child Retrieval  
   用 child chunk 检索，用 parent chunk 提供更完整上下文。

6. 增强 Prompt Router  
   根据问题类型选择不同输出模板，例如定义、流程、枚举、职责、风险分析。

7. 增强安全性  
   给企业微信适配接口加签名校验，历史接口强化鉴权，生产环境关闭通配 CORS。

## 10. 一段完整的面试项目介绍

可以这样介绍：

> 这个项目是一个企业采购知识库 RAG 问答服务，后端基于 FastAPI，RAG 编排使用 LangChain LCEL。知识库支持 PDF、DOC/DOCX、XLSX、CSV、JSON、Markdown、TXT 等多种格式，PDF 会先做文本抽取，如果抽取内容不足再走 Tesseract OCR 降级。入库侧使用 manifest 和内容哈希做增量更新，只对新增、修改、删除的文档处理向量，避免每次全量重建。
>
> 检索侧支持 Chroma 和 Qdrant 切换，并实现了历史追问改写、规则/LLM Query Rewrite、原问题兜底召回的多路召回策略。为了避免 Query Rewrite 漂移，系统不会只使用改写后的 query，而是会把原问题、历史改写问题和 query rewrite 结果都参与检索，再根据命中数量、相似度和覆盖率选择更好的结果。对于“有哪些流程”这类枚举问题，会提高召回数量，并针对流程编号做结构化列表输出。
>
> 后续如果继续优化，我会优先补检索评测集，用 Recall@K、Hit@K、MRR 量化召回质量，然后引入 reranker 做精排、MMR 做去重和多样性选择，最后实现完整 CRAG，让系统在检索结果不可靠时自动重写 query 或返回资料不足，减少幻觉。
