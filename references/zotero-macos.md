# macOS 上每天自动转换 Zotero 文献

把论文和 PDF 放进 Zotero 个人文库中的一个分类，脚本会在北京时间每天 22:30 扫描该分类，把缺少阅读版的论文转成中文 HTML。原文、中文、逐段中英对照可在页面中切换。自动审校通过的 HTML 会作为原论文的 **Zotero 存储附件** 回写，原 PDF 保留。

本文配套的两个 Python 脚本在 [automation/macos](../automation/macos/) 中。下列命令在 **Mac 本机终端**执行，工作目录为仓库根目录。

## 1. 准备运行环境

- macOS 装有 Zotero 10 或更高版本。本文使用支持附件写入的 [Zotero 本机 API](https://www.zotero.org/support/dev/web_api/v3/local_api)，不需要 Zotero 网页 API 密钥。处理范围是个人文库指定分类直属的条目。
- 安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 Chrome。`/usr/bin/python3 --version` 应能运行。处理扫描 PDF 时还需要 Tesseract 和相应语言包。
- 安装可用的 Codex CLI，并以运行任务的同一 macOS 用户登录。Codex 两次审校需要联网和可用的额度。脚本默认查找 ChatGPT Mac 应用内的 CLI，其次查找 PATH 上的 `codex`。登录状态可用同一个可执行文件的 `login status` 查看。

先在线准备依赖和 Chrome 本机翻译组件。夜间转换器用 `uv --offline` 方式运行，复用缓存。

```sh
uv run scripts/reader.py --help
uv run scripts/reader.py models
```

使用默认的 ChatGPT Mac 应用路径时，可以这样检查 Codex。独立安装的 CLI 可直接运行 `codex login status`。

```sh
"/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex" login status
```

如果未登录，对同一个可执行文件运行 `login`。本机机翻不可用时，由 Codex 根据原文补译。启用本机机翻并不改变 Codex 联网审校的要求。

## 2. 创建分类并保存写入权限

1. 启动 Zotero，在「我的文库」新建分类，例如「待处理」。在「设置 → 高级」启用允许本机其他应用与 Zotero 通信的选项。
2. 在本机终端列出分类。第一列是分类标识，第三列是父分类标识。重名时结合父分类确认目标。

   ```sh
   /usr/bin/python3 automation/macos/zotero-attach-html.py collections
   ```

3. 复制示例配置，然后编辑 `automation/macos/config.json`。把 `REPLACE_ME` 换成上一步得到的标识。该配置由前台和定时任务共用。

   ```sh
   cp automation/macos/config.example.json automation/macos/config.json
   open -e automation/macos/config.json
   ```

   表中的可选字段只在默认路径找不到组件、或想指定另一套 CLI 时填写。值必须是绝对路径。

   | 字段 | 用途 |
   | --- | --- |
   | `collection_key` | 目标 Zotero 分类标识，8 位大写字母或数字，必填。 |
   | `uv` | uv 可执行文件，如 `/opt/homebrew/bin/uv`。 |
   | `codex` | 已登录的 Codex CLI 可执行文件，如 `/opt/homebrew/bin/codex`。 |

4. 在前台授权。在 Zotero 弹窗中选「始终允许」。脚本把写入授权存到当前用户的登录钥匙串。后台任务复用授权。

   ```sh
   /usr/bin/python3 automation/macos/zotero-attach-html.py authorize
   /usr/bin/python3 automation/macos/zotero-nightly.py check
   ```

   `check` 只读，列出待处理 PDF。若连接失败，确认正在运行的是 Zotero 桌面版、已启用本机 API，并从 Mac 本机终端重试。授权失效时，在前台运行 `zotero-attach-html.py authorize --renew`，路径同上。

## 3. 先前台跑通一篇论文

在目标分类中放一篇带本机 PDF 的测试论文。展开条目并在 Zotero 打开 PDF，确认已下载。选择有清晰文字层和图注的论文，且条目下还没有此工具生成的 HTML。

```sh
/usr/bin/python3 automation/macos/zotero-nightly.py check
/usr/bin/python3 automation/macos/zotero-nightly.py run
/usr/bin/python3 automation/macos/zotero-nightly.py check
```

第一次 `check` 应列出测试 PDF。成功后，`run` 会显示「已确认 Zotero 存储副本」，最后一次 `check` 会跳过该 PDF。展开原条目，确认多了「中文版 HTML」子附件，并实际打开验证。宽屏应从左至右显示目录、图表栏和正文。

脚本按原文提取、Codex 原文审校、本机翻译、Codex 译文审校、HTML 校验和附件回写的顺序处理。它使用 PDF 标识识别对应的 HTML，多个 PDF 可以分别有自己的阅读版。现有阅读版被跳过，常规成功路径无需人工审批。

## 4. 安装每天北京时间 22:30 的任务

将 Mac 系统时区设为 `Asia/Shanghai`，保持当前用户已登录，并让 Zotero 继续运行。前台试跑成功后安装用户级 LaunchAgent。

```sh
/usr/bin/python3 automation/macos/zotero-nightly.py install
launchctl print "gui/$(id -u)/org.paper-pdf-to-html.zotero-nightly"
```

任务文件在 `~/Library/LaunchAgents/org.paper-pdf-to-html.zotero-nightly.plist`。安装后将仓库留在原路径。可再放一篇全新的测试 PDF，用下面的命令立即测试后台环境。

```sh
launchctl kickstart "gui/$(id -u)/org.paper-pdf-to-html.zotero-nightly"
tail -f automation/macos/zotero-nightly.log
```

按 Ctrl-C 退出日志跟踪。后台测试的验收条件和前台相同，以原条目下出现并能打开存储附件为准。日志显示「待处理 0 份」只说明扫描完成。

## 5. 设置唤醒并做一次过夜验收

首次验证时让 Mac 接电、保持登录，Zotero 留在后台，先用开盖熄屏的方式测试。运行期间脚本用 `caffeinate -i` 阻止空闲睡眠，退出后释放该限制，电脑按自身电源设置休眠。

如需在计划时间前唤醒，先用 `pmset -g sched` 检查现有重复电源计划。下面的命令会设置每天 22:28 唤醒，可能替换已有重复计划。

```sh
pmset -g sched
sudo pmset repeat wake MTWRFSU 22:28:00
pmset -g sched
```

如果也要复现「接电空闲 10 分钟后休眠」的电源配置，可运行 `sudo pmset -c sleep 10`。这会修改接电时的系统空闲睡眠定时器。实际睡眠还受当前电源配置和系统活动影响。

合盖、关机或重启后尚未登录的环境需要另外验证。已设置唤醒时刻只表示 macOS 收到了计划。要验证合盖使用，放一篇新的 PDF 并按平时习惯合盖，次日查看 22:30 后的日志和对应 Zotero 附件。不同电源和合盖条件下，应以实际跑过的结果为准。相关设置见 [Apple 的定时电源说明](https://support.apple.com/zh-cn/guide/mac-help/mchl40376151/mac)。

## 6. 查看结果、处理异常与停用

| 位置或现象 | 核对方法 |
| --- | --- |
| `automation/macos/zotero-nightly.log` | 查扫描、处理、写入失败和本轮汇总。用 `launchctl print` 看运行次数和最近退出状态。 |
| `automation/macos/zotero-review-queue/` | 每个 PDF 的底稿、审校记录、译文与 HTML。目录名包含论文标识、PDF 标识和源文件摘要前缀。 |
| `review-status.json` | 查看原文或译文未通过审校的原因。异常稿会留在工作目录。 |
| `automation/macos/PDF2html-terminology.md` | 公共脚本附带空白模板。将核定的术语写入表格，后续任务会按原词匹配。审校提出的候选词保存在本篇的 `suggested-terms.json`，复核后再并入术语库。 |
| 日志提示 PDF 未下载 | 在 Zotero 打开 PDF，再运行 `run` 或等下一轮。 |
| 登录、额度、授权或网络故障 | 恢复服务后运行 `run`。相同源 PDF 会复用工作目录，已有存储附件的条目会跳过。 |

确需人工修复异常稿时，先按主流程校订并验证成品，然后用队列中的目录名登记修好的 HTML，再运行一次任务。可通过 `ls automation/macos/zotero-review-queue` 查看目录名。

```sh
/usr/bin/python3 automation/macos/zotero-nightly.py approve "队列目录名" "/绝对路径/校订版.html"
/usr/bin/python3 automation/macos/zotero-nightly.py run
```

停用计划任务时，卸载该 LaunchAgent，再移除它的配置文件。Zotero 的写入授权可在 Zotero 高级设置中撤销。

```sh
launchctl bootout "gui/$(id -u)/org.paper-pdf-to-html.zotero-nightly"
rm "$HOME/Library/LaunchAgents/org.paper-pdf-to-html.zotero-nightly.plist"
```
