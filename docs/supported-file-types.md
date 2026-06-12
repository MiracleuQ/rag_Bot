# 知识库文件接入范围

当前批量入库支持以下格式：

- `.txt`
- `.md`
- `.pdf`
- `.doc`（需安装 Microsoft Word + pywin32，或 antiword/catdoc，或 LibreOffice）
- `.docx`
- `.xlsx`
- `.csv`
- `.json`

## 说明

1. `pdf/docx/xlsx` 走专用解析器。  
2. `txt/md/csv/json` 按文本读取（`json` 会尝试格式化）。  
3. PDF 支持“文本提取失败自动 OCR 兜底”（默认开启）。  
4. 若某个文件解析失败，批处理会报错并中止，错误里会列出失败文件路径。  

## 对应配置

`.env`:

```dotenv
KNOWLEDGE_BASE_EXTENSIONS=.txt,.md,.pdf,.doc,.docx,.xlsx,.csv,.json
PDF_OCR_FALLBACK_ENABLED=true
PDF_TEXT_MIN_CHARS=30
PDF_OCR_ENGINE=tesseract
PDF_OCR_LANG=chi_sim+eng
PDF_OCR_DPI=200
PDF_OCR_MAX_PAGES=0
PDF_OCR_TESSERACT_CMD=
```
