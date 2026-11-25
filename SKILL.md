---
name: paper-pdf-to-html
description: Convert an uploaded or local academic PDF into a single offline HTML reading file. Use for 论文 PDF 转 HTML、网页阅读版、双栏转单栏、网页翻译、中文阅读版、逐段中英对照 HTML. Preserve source figures, captions, tables and equations where recoverable. Use a page facsimile for layout-sensitive forms or ambiguous pages. For Markdown research readers or translated PDFs, use the workflow for the requested format.
---

# 论文 PDF 转离线 HTML

交付一个可双击打开的 HTML 文件。默认用单栏阅读布局。用户要求翻译时，为英文论文提供原文、简体中文、逐段中英对照三种模式。图、公式图、参考文献及原版表单可共用一份原文。只要求转换时，生成原文 HTML。

## 选择执行路径

每篇 PDF 使用独立的 `WORKDIR`，保留底稿、提取报告和校订记录。用用户指定的输出目录存放成品。

- **交付双语版或可复现的审校版**时，走下面的分步流程。目标是让原文底稿先通过核对，再进入翻译。
- **快速生成英文预览**时，可用 `uv run <skill>/scripts/reader.py convert INPUT.pdf OUTPUT.html --work WORKDIR --mode en`。需要交付时仍要验收。带翻译参数的一键 `convert` 会直接翻译提取结果，适用于用户明确要求的快速预览。
- **按用户指定的后端翻译**。DeepSeek 用 `--translator deepseek`，其他已配置的兼容接口用 `--translator api`。省略 `--translator` 会调用 Chrome 本机翻译。如果用户要求大模型翻译或排除本机机器翻译，明确指定已获授权的后端。服务不可用时保留底稿和已通过校验的译文，说明失败原因。配置见 [运行与校订](references/operation.md)。

## 阅读界面

成品是三栏阅读页：左侧目录可收起，中间正文，右侧图表栏独立滚动，图注在图正下方。正文里的「图 1」「表 2」可点，点击后右栏滚到对应图表并高亮；文献引用可点，弹出该条参考文献。顶栏有三档正文字号，图表栏头部另有四档图注字号，两者独立；图表栏独立滚动、高度随内容自适应，与正文互不干扰；图表栏有三档宽度，最宽 44rem（浏览器里还能拖拽微调）。正文两端对齐，含邮箱或网址的段落自动改回左对齐。宽屏以下图表回到正文对应小节末尾。

目录折叠、图表栏开关和五档字号用原生 checkbox/radio 加 CSS 实现，不依赖脚本，在 Zotero 阅读器这类禁用 JavaScript 的环境里同样可用。脚本只负责：记住字号与栏宽、拖拽调宽、点击引用弹浮层、图表在窄屏回到小节末尾。

## 分步执行与验收

以下命令中的 `reader.py` 指 `uv run <skill>/scripts/reader.py`。DeepSeek 首次使用前通过 `deepseek-setup` 在 Mac 上配置钥匙串。

1. **提取 PDF，由脚本完成。** 运行 `reader.py prepare INPUT.pdf --work WORKDIR`，生成 `article.html`、`extraction.json` 和 `translation-input.json`。默认按需 OCR。已确认文字层清晰时可用 `--ocr off`。扫描页可用 `--ocr force --ocr-language eng` 后对照核查。
2. **核对原文，由 AI 或人工完成。** 对照 PDF 和 `extraction.json` 核对首页、双栏顺序、跨页段落、公式、参考文献、图注配对和图版各面板。查看未匹配图注和 `unlabelled_pictures`。若 `caption_audit` 的 `clean_end` 为 false，回到 PDF 判断图注是否完整。`caption_strategy` 为 `labels-only` 时重点核对按图号配对的结果。确认的问题修到 `article.html`。图版、表单等需要保留原貌时，可按 **PDF 文件页码**用 `--facsimile 33-37` 重新提取，之后再完成该轮底稿校订。仅交付英文时跳过第 3、4 步。
3. **生成译文，由翻译模型和脚本完成。** DeepSeek 运行 `reader.py translate --work WORKDIR --translator deepseek`。脚本从当前底稿重建待译区块，按批校验并保存结果。继续未完成的任务时沿用原工作目录和同一后端。
4. **审校译文，由 AI 或人工完成。** 对照原文核对标题、摘要、关键结论和抽样图注。特别核对专名、样本分组、空间方位、单位、数值、引文和作者的限定语。将修订保存至译文 JSON，每个 `[Z1]` 一类的占位符在所属段落内保留一次。参考文献条目保留原文。
5. **生成并验收 HTML。** 脚本用 `reader.py render OUTPUT.html --work WORKDIR --mode both --translations WORKDIR/translations-deepseek.json` 生成逐段对照的初始视图。用 `--mode zh` 可初始显示中文，英文版用 `--mode en` 并省略译文。执行 `reader.py review OUTPUT.html` 筛查可疑段落，执行 `reader.py verify OUTPUT.html` 检查文件结构。AI 或人工在浏览器点验目录、图号跳转、图片放大、引用和窄屏排版。双语版也要测试三种语言切换。可用 `reader.py apply --work WORKDIR patch.json` 登记成品文字修正，重新渲染后再次验收。每条补丁的查找串必须唯一匹配。
6. **离线复现，由脚本完成。** 保留原 PDF、提取选项、校订底稿、补丁、最终译文 JSON 和脚本版本。使用同一份校订底稿与译文再次运行第 5 步的 `render`，比较两份 HTML 的文件摘要。需要验证提取时，在两个独立目录从 PDF 重新提取。首次翻译与固定译文的离线重建分别记录结果。

交付 HTML 时，说明实际译文来源、审校范围和保留原版的页码。
