# LangChain 重构说明

项目已完成 LangChain 编排迁移，并保持对外接口不变：

- `/chat`
- `/integrations/wechat/adapter`
- `/history/sessions`
- `/history/sessions/{session_id}/messages`

## 当前检索后端

- `chroma`（生产默认）
- `qdrant`（可选）

## 链路顺序

1. 敏感问题拦截
2. 多轮追问改写（可开关）
3. Query Rewrite（可开关）
4. 检索（含回退）
5. 基于资料生成回答
6. 持久化聊天记录
