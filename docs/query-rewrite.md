# Query Rewrite 使用说明

## 是否有必要

有必要。对企业知识库来说，用户问题常见以下情况：

- 口语化（如“帮我看下报销怎么弄”）
- 关键词缺失（没有制度名、流程名）
- 表述冗长（噪声词多）

Query Rewrite 的目标是先把问题规整成更适合检索的查询，提升召回率。

## 已实现模式

- `none`：关闭改写（默认）
- `rule`：规则改写（不额外消耗模型）
- `llm`：模型改写（效果更好，但增加一次模型调用）

## 配置项（`.env`）

```dotenv
ENABLE_QUERY_REWRITE=false
QUERY_REWRITE_MODE=none
QUERY_REWRITE_MAX_CHARS=256
QUERY_REWRITE_CACHE_ENABLED=true
QUERY_REWRITE_CACHE_TTL_SEC=900
QUERY_REWRITE_CACHE_MAX_SIZE=512
RAG_ENABLE_DUAL_ROUTE_RETRIEVAL=true
```

启用规则改写：

```dotenv
ENABLE_QUERY_REWRITE=true
QUERY_REWRITE_MODE=rule
```

启用 LLM 改写：

```dotenv
ENABLE_QUERY_REWRITE=true
QUERY_REWRITE_MODE=llm
```

## 代码入口

- 改写接口：`app/query_rewrite/base.py`
- 规则实现：`app/query_rewrite/rule_based.py`
- LLM 实现：`app/query_rewrite/llm.py`
- 注入位置：`app/main.py` 的 `_build_rag_service()`

## 当前行为

1. 先基于历史对话做追问改写（若开启 `ENABLE_HISTORY_QUESTION_REWRITE`）。  
2. 再执行 Query Rewrite（`none/rule/llm`）。  
3. 对同一 `session_id` + 同一问题，改写结果走内存缓存（TTL + LRU）。  
4. 检索阶段默认开启“双路择优”：改写查询与原问题都参与召回，按命中数/相似度/覆盖度选择更优结果。  
5. 不改变你的 API 输入输出结构。  
