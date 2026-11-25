# 运行与校订

## 本地组件

脚本以 `uv` 管理 Python 依赖。版面分析使用 PyMuPDF4LLM 和 PyMuPDF Layout。按需 OCR 可使用系统 Tesseract 和相应语言包。扫描件检查误识别、图内文字和低质量页。参考 [PyMuPDF API](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/api.html) 和 [OCR 文档](https://pymupdf.readthedocs.io/en/latest/ocr/index.html)。

`--translator local` 为默认选项，使用 Chrome 的本机模型将英文翻译为简体中文。已验证 Apple Silicon macOS。缓存位于 `~/.cache/codex-paper-pdf-to-html`，可用 `PAPER_HTML_MODEL_CACHE` 指定，要用非默认 Chrome 时设置 `PAPER_HTML_CHROME`。首次准备由 `reader.py models` 完成，也可由双语转换自动触发。只下载语言模型和运行组件。翻译进程使用独立的空白本地页面，纸面文字仅在本机处理。成品中的两种语言都已嵌入文件，阅读时无需 Chrome 翻译组件。

## DeepSeek 快速设置

在 Mac 上运行一次 `uv run <skill>/scripts/reader.py deepseek-setup`，在本机密码框中粘贴 DeepSeek API Key 并保存。密钥存入登录钥匙串。以后用户说“用 DeepSeek 转成中英对照 HTML”时，转换命令使用 `--translator deepseek`。预设调用 DeepSeek 官方地址和 `deepseek-flash` 模型，关闭思考模式。校订或离线重新打包时读取 `WORKDIR/translations-deepseek.json`，也可用 `render --translator deepseek` 自动选取此文件。上游接入方式见 [DeepSeek 接口文档](https://api-docs.deepseek.com/api/create-chat-completion/)。

## AI API 翻译

`--translator api` 支持兼容 OpenAI [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) 的文本接口。设置好以下环境变量后使用。

| 环境变量 | 用途 |
|---|---|
| `PAPER_HTML_API_BASE_URL` | 服务的 API 基础地址，通常含 `/v1`。脚本会补上 `/chat/completions`，也可直接填完整端点。 |
| `PAPER_HTML_API_MODEL` | 服务商提供的模型标识。 |
| `PAPER_HTML_API_KEY` | 从本机的环境或密钥管理器注入。密钥只用于请求认证。 |

```sh
uv run <skill>/scripts/reader.py convert INPUT.pdf OUTPUT.html --work WORKDIR --mode both --translator api
```

可以用 `translate --work WORKDIR --translator api` 单独翻译。在取得完整结果后，脚本写出 `WORKDIR/translations-api.json`。后续可在断网时运行 `render OUTPUT.html --work WORKDIR --translator api --mode both`。模型生成的术语表和通过校验的译文会逐批保存到 `WORKDIR/api-cache/`，同一工作目录和配置可断点续译。手动修订 `translations-api.json` 后直接渲染。

API 模式将标题、摘要、待译文本及术语表发送给配置的服务。原 PDF、内嵌图片和占位符背后的 HTML 数据留在本机。API 返回临时错误时会有限重试，译文漏段或丢失占位符时会拆小批次重试。失败时会保留已通过校验的批次。需要保持全文本地处理时用 `--translator local`。

## 分步校订

1. `reader.py prepare INPUT.pdf --work WORKDIR` 生成 `article.html`、`extraction.json` 和 `translation-input.json`。
2. 对照 PDF 修正 `article.html`。标题和正文用普通 HTML 标签，图用现有的内嵌 PNG 结构，页锚点保留 `page-N`。重排复杂段落时不要把轴标签混入正文。补裁图或公式时从原 PDF 区域渲染，再写入图片数据。图号和页码锚点使用稳定的 ID。
3. `reader.py translate --work WORKDIR` 根据修正后的原文重建输入，生成 `translations.json`。译文文件由区块内容的哈希值索引。在同一个工作目录重跑能复用已生成译文。需要完全重新生成时使用新工作目录。
4. 校订时修改 `translations.json` 对应的中文字符串，保留每个 `[Z1]` 等标记各一次。标记代表公式、链接、上下标或受保护的技术文本。只须提供文本，不要写入 HTML。没有本机翻译组件时，可按 `translation-input.json` 用当前助手逐段写出同样的 JSON，键为 `id`，值为中文字符串。若先修改了中间稿，可再次运行 `prepare` 从 PDF 开始，或以 `translate` 重建输入。自备译文需与当前中间稿一致。
5. `reader.py render OUTPUT.html --work WORKDIR --mode both --translations WORKDIR/translations.json` 交付双语版。渲染会拒绝缺失译文、丢失标记、重复锚点和失效的页内链接。只需要英文时，省略译文并用 `--mode en`。

## 阅读界面

`render` 输出三栏布局：`#outline` 目录、`main>article` 正文、`#rail` 图表栏。宽于 1180px 时脚本把图表移进右栏，窄于此宽度图表留在原位——由 `place_figures` 放在首次提及它的那一小节末尾，图注随图。正文的「图 1」链接由 `FIG` 正则识别，点击时右栏滚动并高亮；参考文献由 `structure_references` 拆成 `ref-entry` 条目，`link_citations` 把正文里的作者-年份与`<sup>`数字引用接到对应条目，点击弹浮层。字号分两组独立控制：正文三档 radio（0.94/1.00/1.10 倍），图表栏头部四档（0.85–1.45 倍）只影响图注。正文两端对齐，含邮箱或 URL 的段落加 `.plain` 保持左对齐以免拉伸出大空隙。图表栏宽度有三档 radio（22/28/44rem，默认 28rem），纯 CSS 生效；浏览器里还能拖动分隔条做 260–760px 的连续调节，双击复位，方向键微调。宽度与字号都记在浏览器本地。

图注识别以字号为准：正文与图注在版面上通常差 0.5pt 以上，`body_font_size` 取长段落的中位数，比正文小 0.25pt 以上的文字块视为图注，按阅读顺序接在对应的图号之后。分页后的续写（“（图例续下页）”）先在同页找，再在后续两页里找以面板字母开头的独立小块，接回同一条图注，并删掉分页标记。扫描件没有字号信息时退回按图号锚定。

图注常被 PDF 分页切成两段：第一段以“（图例续下页）”结尾，续写落在下一页。`gather_captions` 会把续写段落接回同一条图注，并删掉这个标记；若续写被出版方拼进了正文段落，只能保留在正文里。

目录、图表栏和字号是三组隐藏的 checkbox/radio，用 `:checked ~ .app` 改 CSS 变量，所以禁脚本也能点。标题字号用容器查询单位（`4.2cqw`）跟着正文栏宽度走，长 CJK 标题始终一行；图表栏默认常驻（静态 HTML 里图就在 `#rail`），高度随内容走：内容短就贴底收住，超过一屏才在自己的滚动区里滚动，和正文互不干扰；滚动条常显，不做渐隐等叠层提示，以免在非滚动容器里压住正文。脚本只在窄屏把图搬回小节锚点。浮层、拖拽调宽、字号与栏宽记忆依赖脚本；Zotero 阅读器里这些不生效，但三栏布局、图表、图注、字号调节都照常。

默认自动配对使用图号、页面和几何位置。跨页分栏长图注、多面板图、无边框表格和带表单的附页都值得回看。

## 矢量图整版恢复

Distiller 排版（Elsevier、Cell Press、Nature 等）把图存成矢量绘图，页面里只有零星的位图碎片。脚本对此按以下规则处理：

- 以图注为锚点，把整版图区渲染成一张裁图，图注在页底时取图注上方，图注在页顶时取第一条正文之前的区域；图注独占一栏时不把该栏算进裁图。
- 裁图收紧到实际绘图的边界，去掉页边留白；位于页角的出版社水印（OPEN ACCESS、Cell Press 标志）不参与边界计算。
- 没有图注、且小于一个可读面板的位图当作图的残片丢弃，不再单独成图。

因此 `extraction.json` 里的 `picture` 数通常等于图的数量。若某页仍被拆成多块、裁图缺角或水印残留，直接用 `--facsimile 页码` 保留该页原图，比逐块裁更可靠。确认仍不理想时，按[分步校订](#分步校订)在中间稿里替换该图的内嵌 PNG。

参考文献、公式图片和图内文字可直接从原文查看。
