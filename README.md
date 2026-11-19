# Paper PDF to HTML

把论文 PDF 转为一个可离线打开的 HTML 阅读文件。支持英文原文、简体中文和逐段中英对照，可在同一页面切换。

## 功能

- 将双栏论文重排为单栏，保留可搜索、可复制的正文。
- 内嵌原图、图注和独立公式，目录可跳转，图片可点击放大。
- 支持本地英译中、DeepSeek 和兼容 OpenAI Chat Completions 的翻译 API。
- API 翻译按章节处理，校验段落与占位符，并保存已完成的批次以便续译。
- 扫描件可用 OCR 提取文字，表单和复杂附页可以原页图像保留。

## 安装

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，然后把仓库根目录放到 Codex 的 Skill 目录中。macOS 上可以运行以下命令。

```sh
mkdir -p "$HOME/.codex/skills"
git clone https://github.com/VidsHidden/paper-pdf-to-html.git "$HOME/.codex/skills/paper-pdf-to-html"
```

在 Codex 中上传论文 PDF，并说：

> 用 `$paper-pdf-to-html` 把这份论文转成可离线阅读的中英对照 HTML。

## 翻译方式

| 方式 | 适用场景 | 设置 |
| --- | --- | --- |
| 本地翻译 | 英译中，论文文字在本机处理 | 默认选项。已在 Apple Silicon Mac 上验证，首次需联网下载 Chrome 本地翻译组件 |
| DeepSeek | 使用 DeepSeek 官方 Flash 模型翻译 | macOS 上首次在本机密码框输入自己的 API Key，后续从钥匙串读取 |
| 兼容 API | 使用其他支持 Chat Completions 的服务 | 设置服务地址、模型和密钥，见[配置说明](references/operation.md#ai-api-翻译) |

使用 DeepSeek 时，先在 [DeepSeek 开放平台](https://platform.deepseek.com/api_keys) 创建 API Key，再运行一次：

```sh
uv run "$HOME/.codex/skills/paper-pdf-to-html/scripts/reader.py" deepseek-setup
```

在本机密码框粘贴密钥并保存。以后可以直接在 Codex 里说「用 DeepSeek 把这份论文转成中英对照 HTML」。密钥保存在 Mac 钥匙串。

## 命令行示例

```sh
uv run "$HOME/.codex/skills/paper-pdf-to-html/scripts/reader.py" \
  convert "paper.pdf" "paper-bilingual.html" \
  --work "./paper-work" --mode both --translator deepseek
```

只需要英文版时用 `--mode en`。扫描件可用 `--ocr force --ocr-language eng`，并安装 Tesseract 和所需语言包。要保留某几页的原貌，可用 `--facsimile 20-24`，数字指 PDF 文件页码。更多用法见[运行与校订](references/operation.md)。

## 数据与校对

API 模式会把标题、摘要、待译文字和术语表发给所选服务。原始 PDF 和图像在本机处理。生成后的 HTML 内嵌原文、译文和图片，打开时无需联网。

接收图注跨页、表格复杂或扫描清晰度较低的论文时，请对照 PDF 核对阅读顺序、公式和图注归属。图内标注、独立公式图和参考文献条目会保留原文。
