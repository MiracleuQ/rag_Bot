# 多轮上下文问答说明

当前版本已支持把历史消息用于当前问答，处理“第二步呢 / 那这个怎么办”这类追问。

## 生效范围

- `POST /chat`
- `POST /integrations/wechat/adapter`

两者都会在同一 `session_id` 下读取最近消息，作为上下文参与本轮问题改写与检索。

## 配置项

`.env`:

```dotenv
ENABLE_HISTORY_CONTEXT=true
HISTORY_CONTEXT_MAX_MESSAGES=8
ENABLE_HISTORY_QUESTION_REWRITE=true
```

- `ENABLE_HISTORY_CONTEXT`：是否读取历史消息
- `HISTORY_CONTEXT_MAX_MESSAGES`：最多读取最近多少条消息
- `ENABLE_HISTORY_QUESTION_REWRITE`：是否先把追问改写为可独立检索问题

## 处理顺序

1. 读取最近历史消息
2. 判断当前问题是否像“追问”
3. 若是追问：基于历史改写为独立问题
4. 进入现有检索与回答链路
