# 运行与校订

## 本地组件

脚本以 `uv` 管理 Python 依赖。版面分析使用 PyMuPDF4LLM 和 PyMuPDF Layout。按需 OCR 可使用系统 Tesseract 和相应语言包。扫描件检查误识别、图内文字和低质量页。参考 [PyMuPDF API](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/api.html) 和 [OCR 文档](https://pymupdf.readthedocs.io/en/latest/ocr/index.html)。

省略 `--translator` 时，命令行默认使用 Chrome 的本机翻译。如果任务要求用大模型翻译，按已配置的后端显式加 `--translator deepseek` 或 `--translator api`。本机翻译已在 Apple Silicon macOS 上验证过。缓存位于 `~/.cache/codex-paper-pdf-to-html`，可用 `PAPER_HTML_MODEL_CACHE` 指定，要用非默认 Chrome 时设置 `PAPER_HTML_CHROME`。首次准备由 `reader.py models` 完成，也可由双语转换自动触发。只下载语言模型和运行组件。翻译进程使用独立的空白本地页面，纸面文字仅在本机处理。成品中的两种语言都已嵌入文件，阅读时无需 Chrome 翻译组件。

## DeepSeek 快速设置

在 Mac 上运行一次 `uv run <skill>/scripts/reader.py deepseek-setup`，在本机密码框中粘贴 DeepSeek API Key 并保存。密钥存入登录钥匙串。原文底稿核对完毕后运行 `reader.py translate --work WORKDIR --translator deepseek`。预设调用 DeepSeek 官方地址和 `deepseek-flash` 模型，关闭思考模式。校订及离线重建时显式传入 `--translations WORKDIR/translations-deepseek.json`。上游接入方式见 [DeepSeek 接口文档](https://api-docs.deepseek.com/api/create-chat-completion/)。

## AI API 翻译

`--translator api` 支持兼容 OpenAI [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) 的文本接口。设置好以下环境变量后使用。

| 环境变量 | 用途 |
|---|---|
| `PAPER_HTML_API_BASE_URL` | 服务的 API 基础地址，通常含 `/v1`。脚本会补上 `/chat/completions`，也可直接填完整端点。 |
| `PAPER_HTML_API_MODEL` | 服务商提供的模型标识。 |
| `PAPER_HTML_API_KEY` | 从本机的环境或密钥管理器注入。密钥只用于请求认证。 |

```sh
uv run <skill>/scripts/reader.py translate --work WORKDIR --translator api
```

可以用 `translate --work WORKDIR --translator api` 单独翻译。在取得完整结果后，脚本写出 `WORKDIR/translations-api.json`。后续可在断网时运行 `render OUTPUT.html --work WORKDIR --translator api --mode both`。模型生成的术语表和通过校验的译文会逐批保存到 `WORKDIR/api-cache/`，同一工作目录和配置可断点续译。手动修订 `translations-api.json` 后直接渲染。

API 模式将标题、摘要、待译文本及术语表发送给配置的服务。原 PDF、内嵌图片和占位符背后的 HTML 数据留在本机。API 返回临时错误时会有限重试，译文漏段或丢失占位符时会拆小批次重试。失败时会保留已通过校验的批次。需要保持全文本地处理时用 `--translator local`。

研究论文要求用大模型翻译时，按用户选定的模型运行。遇到连通、凭据或配额错误时，从原工作目录恢复，并保留已通过占位符校验的批次。交付前至少对照校订标题、摘要和抽样图注，留意空间方位、样本分组、数值单位及作者限定语。把校订保存在译文 JSON 中，并用该文件离线重建 HTML。双语验收同时检查三种语言视图和窄屏长网址换行。

## 分步校订

交付版按 [SKILL.md 的六步流程](../SKILL.md#分步执行与验收)执行。先验收原文底稿，再调用已选定的翻译后端。

1. `reader.py prepare INPUT.pdf --work WORKDIR` 生成 `article.html`、`extraction.json` 和 `translation-input.json`。
2. 对照 PDF 修正 `article.html`。标题和正文用普通 HTML 标签，图用现有的内嵌 PNG 结构，页锚点保留 `page-N`。重排复杂段落时不要把轴标签混入正文。补裁图或公式时从原 PDF 区域渲染，再写入图片数据。图号和页码锚点使用稳定的 ID。
3. DeepSeek 使用 `reader.py translate --work WORKDIR --translator deepseek`，从修正后的原文重建输入，生成 `translations-deepseek.json`。其他兼容 API 使用 `--translator api`，输出 `translations-api.json`。选择 Chrome 本机翻译时使用 `--translator local`，输出 `translations.json`。译文按区块内容的哈希值索引，同一目录和配置可续跑；需要新的翻译结果时另建工作目录。
4. 校订时修改对应译文 JSON 的中文字符串，保留每个 `[Z1]` 等标记各一次。标记代表公式、链接、上下标或受保护的技术文本。只须提供文本，不要写入 HTML。如果用户选择由当前助手直接翻译，可按 `translation-input.json` 生成同样的 JSON，键为 `id`，值为中文字符串。修改中间稿后，用同一后端重建待译区块，确认审校译文和底稿匹配。重新运行 `prepare` 会重新生成中间稿。
5. 对于 DeepSeek，运行 `reader.py render OUTPUT.html --work WORKDIR --mode both --translations WORKDIR/translations-deepseek.json` 生成双语版；其他后端传入对应的已校订译文文件。渲染会拒绝缺失译文、丢失标记、重复锚点和失效的页内链接。只需要英文时，省略译文并用 `--mode en`。验收按主流程执行，随后用同一底稿及译文离线重建。

## 阅读界面

`render` 输出三栏布局：`#outline` 目录、`main>article` 正文、`#rail` 图表栏。宽于 1180px 时脚本把图表移进右栏，窄于此宽度图表留在原位——由 `place_figures` 放在首次提及它的那一小节末尾，图注随图。正文的「图 1」链接由 `FIG` 正则识别，点击时右栏滚动并高亮；参考文献由 `structure_references` 拆成 `ref-entry` 条目，`link_citations` 把正文里的作者-年份与`<sup>`数字引用接到对应条目，点击弹浮层。字号分两组独立控制：正文三档 radio（0.94/1.00/1.10 倍），图表栏头部四档（0.85–1.45 倍）只影响图注。正文两端对齐，含邮箱或 URL 的段落加 `.plain` 保持左对齐以免拉伸出大空隙。图表栏宽度有三档 radio（22/28/44rem，默认 28rem），纯 CSS 生效；浏览器里还能拖动分隔条做 260–760px 的连续调节，双击复位，方向键微调。宽度与字号都记在浏览器本地。

图注识别以字号为准：正文与图注在版面上通常差 0.5pt 以上，`body_font_size` 取长段落的中位数，比正文小 0.25pt 以上的文字块视为图注，按阅读顺序接在对应的图号之后。分页后的续写（“（图例续下页）”）先在同页找，再在后续两页里找以面板字母开头的独立小块，接回同一条图注，并删掉分页标记。扫描件没有字号信息时退回按图号锚定。

图注常被 PDF 分页切成两段：第一段以“（图例续下页）”结尾，续写落在下一页。`gather_captions` 会把续写段落接回同一条图注，并删掉这个标记；若续写被出版方拼进了正文段落，只能保留在正文里。

目录、图表栏和字号是三组隐藏的 checkbox/radio，用 `:checked ~ .app` 改 CSS 变量，所以禁脚本也能点。标题字号用容器查询单位（`4.2cqw`）跟着正文栏宽度走，长标题可以换行；图表栏默认常驻（静态 HTML 里图就在 `#rail`），高度随内容走：内容短就贴底收住，超过一屏才在自己的滚动区里滚动，和正文互不干扰；滚动条常显，不做渐隐等叠层提示，以免在非滚动容器里压住正文。脚本只在窄屏把图搬回小节锚点。浮层、拖拽调宽、字号与栏宽记忆依赖脚本；Zotero 阅读器里这些不生效，但三栏布局、图表、图注、字号调节都照常。

## AI 校订回路

| 命令 | 作用 |
|---|---|
| `reader.py review OUTPUT.html` | 扫描成品，列出可疑文字单元到 `OUTPUT.review.json` |
| `reader.py apply --work WORKDIR patch.json` | 把 `[{find, replace}]` 追加到 `WORKDIR/polish.json` |
| `reader.py render ...` | 渲染收尾时自动套用 `polish.json` 的替换 |

`find` 必须与成品里的文本逐字一致（先 review 再复制原文），找不到会直接报错，不会静默失败。补丁每个查找串必须正好命中一次。重复登记同一条补丁无效，重复渲染结果稳定。

默认自动配对使用图号、页面和几何位置。跨页分栏长图注、多面板图、无边框表格和带表单的附页都值得回看。

## 矢量图整版恢复

Distiller 排版（Elsevier、Cell Press、Nature 等）把图存成矢量绘图，页面里只有零星的位图碎片。脚本对此按以下规则处理：

- 以图注为锚点，把整版图区渲染成一张裁图，图注在页底时取图注上方，图注在页顶时取第一条正文之前的区域；图注独占一栏时不把该栏算进裁图。
- 裁图收紧到实际绘图的边界，去掉页边留白；位于页角的出版社水印（OPEN ACCESS、Cell Press 标志）不参与边界计算。
- 没有图注、且小于一个可读面板的位图当作图的残片丢弃，不再单独成图。

因此 `extraction.json` 里的 `picture` 数通常等于图的数量。若某页仍被拆成多块、裁图缺角或水印残留，直接用 `--facsimile 页码` 保留该页原图，比逐块裁更可靠。确认仍不理想时，按[分步校订](#分步校订)在中间稿里替换该图的内嵌 PNG。

参考文献、公式图片和图内文字可直接从原文查看。

## 回归检查

用两个不同的工作目录分别运行同一份 PDF，并以文件摘要比较 HTML。对已校订的双语版保留最终译文 JSON，核对重新渲染的摘要，不以翻译服务的新响应作为复现标准。

Nature 两份回归样本的基准如下。页码均为 PDF 文件页码。

| 文件 | 页数 | 正文图 | 扩展数据图 | 原版附页 | 跨页或多面板检查 |
| --- | ---: | ---: | ---: | --- | --- |
| s41586-026-10377-y.pdf | 29 | 5 | 10 | 26–29 | 图 3、图 5、扩展数据图 5 的图版与图注跨页 |
| s41592-023-02007-6.pdf | 23 | 4 | 9 | 21–23 | 图 3 的图版与图注跨页，扩展数据图 5 包含三个面板 |

针对第一份样本，使用 `apply --work WORKDIR tests/atlas-text-fix.json` 登记对照原件确认的连字修正，再运行 `render`。两次试跑套用同一补丁后，可用 `tests/check_nature_readers.py` 核对两份 HTML 及提取报告。

宽屏检查图表栏、正文图号跳转、参考文献浮层及图版放大。窄屏检查同一图版回到正文及横向溢出。关闭脚本再次检查原文和图版是否仍可到达。图版是否裁全须与原 PDF 比对。
