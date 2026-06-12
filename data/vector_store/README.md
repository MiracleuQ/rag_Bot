# Vector Store Output

当前默认向量库为 Chroma，本地持久化目录：

- `data/vector_store/chroma`

如果切换到 Qdrant：

- 本目录主要保留 `ingest_manifest.json` 等入库辅助文件
- 向量数据由 Qdrant 服务端持久化
