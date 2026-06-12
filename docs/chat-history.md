# 聊天历史持久化

已实现基于 SQLite 的会话/消息持久化。

## 数据表

- `sessions`: 会话主表
- `messages`: 消息表（用户消息 + 助手消息）

数据库路径由 `.env` 控制：

```dotenv
CHAT_HISTORY_ENABLED=true
CHAT_HISTORY_DB_PATH=data/chat_history/chat_history.db
HISTORY_ENFORCE_USER_SCOPE=true
HISTORY_ADMIN_TOKEN=
```

## 接口行为

### 1) `/chat`

- 入参可带：
  - `session_id`（可选，不传会自动创建）
  - `user_id`（可选）
  - `channel`（默认 `api`）
- 每次问答会写入两条消息：
  - `role=user`
  - `role=assistant`

### 2) `/integrations/wechat/adapter`

- 若未显式传 `session_id`，会尝试按 `user_id/chat_id` 生成稳定会话 ID。
- 也会写入历史消息。

### 3) 查询接口

- `GET /history/sessions?user_id=...&channel=...&limit=20`
- `GET /history/sessions/{session_id}/messages?limit=50&offset=0`

当 `HISTORY_ENFORCE_USER_SCOPE=true` 时：

- 查询接口必须携带请求头 `X-User-ID`
- 只能查看自己的会话与消息
- 如需跨用户排障，可配置 `HISTORY_ADMIN_TOKEN`，并在请求头携带 `X-History-Admin-Token`

## 最小示例

```powershell
curl -X POST "http://127.0.0.1:8000/chat" `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"报销流程是什么？\",\"user_id\":\"u001\"}"
```

返回里会带 `session_id`，后续请求复用它即可串联会话历史。

查询历史示例：

```powershell
curl "http://127.0.0.1:8000/history/sessions?limit=20" `
  -H "X-User-ID: u001"
```
