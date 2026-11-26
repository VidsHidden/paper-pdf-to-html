# Paper PDF to HTML

把学术论文 PDF 转成一个可以双击打开的 HTML 文件。双栏正文重排为单栏，文字可搜索和复制。翻译版可在同一页切换英文原文、简体中文和逐段中英对照。成品内嵌正文、译文和图片，可以离线阅读和分享。

## 阅读体验

- 宽屏从左到右是**目录 → 图表栏 → 正文**。目录可收起，图表栏独立滚动，正文中的图号和表号可跳到对应图表。
- 浏览器中可以放大图版、查看引用浮层，独立调整正文和图注字号，或拖拽图表栏调宽。窄屏下，图表回到正文相应小节。
- 尽量保留原图、图注、表格和公式。图内标注、独立公式图和参考文献保留原文。扫描件支持 OCR，复杂表单和附页可按原页图像保留。

## 安装与更新

先安装 Git 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)。`uv run` 会按脚本声明准备 Python 环境和依赖，首次运行通常需要联网。选择 Chrome 本机翻译时需要 Chrome，扫描件 OCR 需要 Tesseract 和相应语言包。

在 Codex 中使用时，将仓库克隆到[用户技能目录](https://developers.openai.com/codex/skills)。已有同名技能时，更新原来的那份即可。

```sh
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/VidsHidden/paper-pdf-to-html.git \
  "$HOME/.agents/skills/paper-pdf-to-html"
```

如果是用 `git clone` 安装的，从实际安装目录运行 `git pull --ff-only` 更新。使用命令行时，也可以把仓库克隆到任意目录，从仓库根目录运行下文命令。

## 快速开始

在 Codex 上传论文 PDF，再发送下面这类请求。可以直接指定翻译方式和希望打开时看到的语言。

> 用 $paper-pdf-to-html 把这篇论文转成离线中英对照 HTML。先核对 PDF 底稿和图注，再翻译。沿用项目术语库，把核定的新术语写回去。

从仓库根目录运行下面的命令，可快速生成原文预览。

```sh
uv run scripts/reader.py convert paper.pdf paper-en.html \
  --work ./paper-en-work --mode en
```

也可以用 `--mode both --translator local` 一键生成中英对照预览。这条快捷路径会直接翻译提取结果。需要审校的成品按下面的分步流程处理。每篇论文使用独立的工作目录。

## 选择翻译方式

| 方式 | 命令参数 | 准备工作 |
| --- | --- | --- |
| Chrome 本机翻译 | `--translator local`（默认） | 已在 Apple Silicon Mac 验证。首次需要联网下载本地语言模型和组件，待译文字在本机处理。 |
| DeepSeek | `--translator deepseek` | macOS 上运行一次 `deepseek-setup`，用本机密码框保存 API 密钥。 |
| 兼容 API | `--translator api` | 配置服务地址、模型和密钥。见 [兼容 API 配置](references/operation.md#ai-api-翻译)。 |

使用 DeepSeek 时，在 [DeepSeek 开放平台](https://platform.deepseek.com/api_keys) 创建密钥，再从仓库根目录执行以下命令。后续运行从 macOS 登录钥匙串读取密钥。

```sh
uv run scripts/reader.py deepseek-setup
```

API 翻译会将标题、摘要、待译文字和术语上下文发送给所选服务。原 PDF、内嵌图片和占位符保护的原始 HTML 数据留在本机。API 翻译会保存已通过校验的批次，使用同一工作目录和后端可继续未完成的翻译。

## 分步转换与验收

### 1. 提取并核对原文

```sh
uv run scripts/reader.py prepare paper.pdf --work ./paper-work
```

脚本生成 `article.html`、`extraction.json` 和 `translation-input.json`。由 Codex 或人工对照原 PDF 核对双栏阅读顺序、跨页段落、公式、图注和图版。将确认的修正写回 `article.html`，再进入翻译。

| 提取选项 | 用法 |
| --- | --- |
| `--ocr auto` | 默认选项，按需识别扫描页。 |
| `--ocr off` | 原 PDF 的文字层清晰完整时可关闭 OCR。 |
| `--ocr force --ocr-language eng` | 强制识别英文扫描页，再对照原页核查文字。 |
| `--facsimile 20-24` | 将第 20 至 24 页按原页图像保留。这里使用 PDF 文件页码。 |

### 2. 查术语、翻译并审校

翻译前先从项目术语库（例如 `PDF2html-terminology.md`）查对标题、正文和图注里的术语。相同语境沿用首选译法。翻译入口支持自定义术语表时随稿提供，否则在渲染前逐段核对。

以下示例使用 DeepSeek。改用本机翻译时，译文文件为 `translations.json`。改用兼容 API 时，译文文件为 `translations-api.json`。

```sh
uv run scripts/reader.py translate --work ./paper-work --translator deepseek
```

审校时对照原文检查标题、摘要、关键结论及图注，重点关注专业术语、样本分组、空间方位和单位数值。将修正保存到译文 JSON，保留每段中的 `[Z1]` 等标记。审校完成后，将确认可复用的新术语写回术语库，记录英文、首选中文、适用语境及来源章节或图号。

### 3. 生成并检查 HTML

```sh
uv run scripts/reader.py render paper-bilingual.html \
  --work ./paper-work --mode both \
  --translations ./paper-work/translations-deepseek.json

uv run scripts/reader.py review paper-bilingual.html
uv run scripts/reader.py verify paper-bilingual.html
```

`--mode both` 初始显示中英对照，`--mode zh` 初始显示中文，这两种都可以在页面里切换三种阅读模式。只生成原文时用 `--mode en`，并省略 `--translations`。

`review` 生成可疑段落报告，`verify` 检查文件结构。最后在浏览器点验图号跳转、图片放大、引用和语言切换，并检查窄屏排版。论文级审校需要查看原 PDF 和译文。

### 4. 离线重建

保留原 PDF、提取参数、校订底稿、最终译文 JSON 和所用的仓库提交。将相同底稿和译文用于再次 `render`，并比较两份 HTML 的文件摘要。依赖已缓存时，可将命令开头改为 `uv run --offline`。这一轮重建直接读取现有译文。

## 项目范围

本仓库提供 Codex 技能、命令行转换器和离线阅读模板。Zotero 定时扫描、审校调度和附件回写需要在使用方的项目中另行配置。

- [完整技能流程](SKILL.md)
- [运行、审校及回归验证说明](references/operation.md)
