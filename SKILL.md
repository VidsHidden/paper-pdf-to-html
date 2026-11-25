---
name: paper-pdf-to-html
description: Convert an uploaded or local academic PDF into a single offline HTML reading file. Use for 论文 PDF 转 HTML、网页阅读版、双栏转单栏、网页翻译、中文阅读版、逐段中英对照 HTML. Preserve source figures, captions, tables and equations where recoverable. Use a page facsimile for layout-sensitive forms or ambiguous pages. For Markdown research readers or translated PDFs, use the workflow for the requested format.
---

# 论文 PDF 转离线 HTML

交付一个可双击打开的 HTML 文件。默认用单栏阅读布局。用户要求翻译时，为英文论文提供原文、简体中文、逐段中英对照三种模式。图、公式图、参考文献及原版表单可共用一份原文。只要求转换时，生成原文 HTML。

## 转换

在当前任务的工作目录保留中间结果，用用户指定的输出目录存放成品。不要复用另一篇论文的裁切坐标、论文术语或译文。

- 原文版运行 `uv run <skill>/scripts/reader.py convert INPUT.pdf OUTPUT.html --work WORKDIR --mode en`。
- 中英对照版改用 `--mode both`，仅将中文设为初始视图时使用 `--mode zh`。默认使用本机翻译。用户明确指定 DeepSeek 时加 `--translator deepseek`，从 Mac 钥匙串读取凭据。用户选择其他兼容 API 时加 `--translator api`，使用已经配置的服务地址、模型和密钥。DeepSeek 的首次设置通过 `reader.py deepseek-setup` 弹出本机密码框。配置方法、首次模型准备和分步校订见 [运行与校订](references/operation.md)。
- 默认按需 OCR。知道原件有清晰文字层时可用 `--ocr off`。扫描件可用 `--ocr force --ocr-language eng`，并检查 OCR。需要完整保留表单或特别复杂的页面时用 `--facsimile 33-37` 一类的 **PDF 文件页码**。仅对需要保留原貌的页使用该选项。
- 期刊排版常用矢量图（Elsevier、Cell Press、Nature 等）。脚本以图注为锚点把整版区域恢复成一张裁图，收紧到实际绘图内容的边界，剔除页角的出版社水印，并丢弃没有图注的小碎片。某页仍被拆散或裁偏时，用 `--facsimile` 保留该页原貌。

## 阅读界面

成品是三栏阅读页：左侧目录可收起，中间正文，右侧图表栏独立滚动，图注在图正下方。正文里的「图 1」「表 2」可点，点击后右栏滚到对应图表并高亮；文献引用可点，弹出该条参考文献。顶栏有七档正文字号，图表栏头部另有四档图注字号，两者独立；图表栏高度随内容自适应，不会被截断；图表栏还有三档宽度（浏览器里还能拖拽微调）。正文两端对齐，含邮箱或网址的段落自动改回左对齐。宽屏以下图表回到正文对应小节末尾。

目录折叠、图表栏开关和五档字号用原生 checkbox/radio 加 CSS 实现，不依赖脚本，在 Zotero 阅读器这类禁用 JavaScript 的环境里同样可用。脚本只负责：记住字号与栏宽、拖拽调宽、点击引用弹浮层、图表在窄屏回到小节末尾。

## 检查成品

1. 查看 `WORKDIR/extraction.json`，核对页数、图表、公式和未匹配图注。`caption_audit` 列出每条图注的字数和是否以句末标点收尾；`clean_end` 为 false 的说明图注被分页截断，先看能不能补齐，补不上就对该页用 `--facsimile`。`caption_strategy` 为 `labels-only` 表示扫描件没有字号信息，图注只能按图号锚定。对照 PDF 检查首页、双栏顺序、跨页句子、图注归属、公式与补充页。检查用户关心的版面和关键数值。图是矢量图时，确认整版图四角完整、没有出版社水印、没有孤立的小图残片。发现错配时在中间稿修正，或者保留该页原图并说明。
2. 翻译时通读标题、摘要和关键结论。检查专名、同位素、单位、数值和引文。保留作者表述的确定程度，标明机器译文的校订范围。结构化参考文献原样保留。
3. 运行 `uv run <skill>/scripts/reader.py verify OUTPUT.html`，用浏览器点验目录、语言切换和图片放大。最终只交付 HTML，说明实际采用的回退和校订范围。
