# 增量入库说明

已实现基于 `manifest + 文件内容哈希` 的增量入库，支持三类变化：

- 新增文件：仅新增向量
- 修改文件：先写新向量，再删除确实过期的旧向量
- 删除文件：删除对应旧向量

## 关键配置

```dotenv
INGEST_ENABLE_INCREMENTAL=true
INGEST_MANIFEST_PATH=data/vector_store/ingest_manifest.json
```

## 运行方式

1. 预检查（不写库）：

```powershell
python -m app.ingest.batch_ingest --dry-run
```

2. 增量执行：

```powershell
python -m app.ingest.batch_ingest
```

3. 全量重建（忽略增量差异）：

```powershell
python -m app.ingest.batch_ingest --full-reindex
```

## 输出指标含义

- `changed_document_count`: 新增或内容变更的文档数
- `skipped_document_count`: 哈希未变化、被跳过的文档数
- `removed_document_count`: 相比上次已删除的文档数
- `delete_count`: 本次删除的旧向量条数
- `vector_count`: 本次写入的新向量条数
