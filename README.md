# Task Hub · 任务工作台

让 Agent 把邮件或用户描述整理成可阅读、可审计、可操作的本地任务看板。

项目包含两个可独立安装的技能：

- **mail-reader-summary**：只读同步 IMAP 收件箱和已发送邮件，或免凭据导入客户端导出的 `.eml` 文件夹；增量记录正文与附件，由 Agent 理解任务和交付证据，也可直接输出文本摘要。
- **task-board**：根据用户描述或结构化任务创建 JSON 数据库和自动载入的 HTML 看板，支持卡片拖动、优先级和截止日期调整，以及证据和附件查看。

企业微信、Teams 是预留的来源类型，尚未接入。项目不包含大模型服务，语义理解由运行技能的 Agent 完成。

## 下载后直接交给 Agent

克隆或下载本仓库，在解压后的项目目录中打开支持读取本地文件、执行 Python 的 Agent，发送：

> 请先读 AGENTS.md。使用 task-board 技能，为我创建一个“整理本周项目进展”的任务，内容是汇总进展、风险和下一步安排，并打开看板。

读取企业邮箱时可以发送：

> 请先读 AGENTS.md。使用邮箱读取技能帮我配置本机网易企业邮箱，随后读取新邮件并更新任务看板。邮箱配置从我本机 Foxmail 获取，授权码由我在本机隐藏输入框输入。

Agent 应使用当前项目绝对路径作为 `--project-dir`，根据机器实际情况选择 Python。首次读取默认只读最近一个自然月，收件箱和启用的已发送文件夹使用相同范围。用户说“读取最近两个月”时，Agent 使用 `--history-months 2`；已经连接过的邮箱也能这样补读历史，按 UID 去重。`--initial-latest 10` 可进一步限制首次范围内最多读取 10 封。后续普通同步只读新增 UID。旧配置若明确设置仅建立基线，则保留该选择，显式历史参数可覆盖。

数据源按“已验证连接 → 免凭据本地缓存/归档 → 导出 EML → IMAP”选择；能满足需求就停止升级。Thunderbird mbox 和 Apple Mail `.emlx` 可通过 `read_mail_archive.py` 导入，IMAP 仍是完整附件、已发送证据和持续增量同步的首选。

## 环境与命令

需要 **Python 3.9+**、现代浏览器；核心脚本仅使用标准库，无需 npm、云数据库或额外 API Key。

```sh
python skills/task-board/scripts/task_board.py --project-dir . --init
python skills/task-board/scripts/task_board.py --project-dir . --title "整理本周项目进展" --add-task "汇总进展、风险和下一步安排。" --priority medium
```

macOS/Linux 可使用 `python3`；Windows 可使用 `py -3` 或有效的 Python 完整路径。`--no-open` 适用于无桌面的环境，脚本会输出 HTML 路径；将工作区复制到有浏览器的电脑可查看。

```sh
python skills/mail-reader-summary/scripts/read_mail.py --project-dir . --init
# 由 Agent 配置生成的 config/mail-reader-config.json，再在本机运行：
python skills/mail-reader-summary/scripts/read_mail.py --project-dir . --sync --prompt-credentials
# 或导入 Foxmail/其他客户端导出的 EML（默认最近一个自然月）：
python skills/mail-reader-summary/scripts/read_eml_folder.py --project-dir . --eml-dir "<导出目录>"
# Thunderbird mbox / Apple Mail emlx：
python skills/mail-reader-summary/scripts/read_mail_archive.py --discover
# 项目内导出 Markdown、CSV 或精简 JSON 摘要：
python skills/mail-reader-summary/scripts/export_mail_summary.py --project-dir . --format markdown
```

模板使用占位服务器。连接前必须配置实际 IMAP 主机、端口和加密方式。网易企业邮箱用户通过[授权码申请页](https://mail.qiye.163.com/static/commonweb/authcode.html?p=qiye-authcode)获取客户端授权码；不要把密码或授权码发到聊天或写进命令。Windows 可选的图形输入工具需要 Tkinter；其他环境使用终端隐藏输入。Windows 用户环境变量持久化为可选项，变量并非加密存储。

## 文件结构与隐私

```text
AGENTS.md                  Agent 入口与项目约定
skills/
  mail-reader-summary/     邮箱读取技能及空模板
  task-board/              看板技能及 HTML/JSON 模板
tests/                     仅虚构数据的离线验证
task-workspace/            首次使用时生成；不进入 Git
  config/                  本机设置、可选品牌配置
  data/                    邮件记录、UID 游标、任务 JSON
  attachments/             本机邮件附件
  audit/                   Agent 复核清单
  logs/                    运行日志
  archive/                 备份
  task-board.html          自动载入任务的本地页面
```

仓库只分发代码、技能和空模板。不包含真实账号、授权码、邮件、任务、附件、公司 Logo 或聊天记录。根目录采用 Git 发布允许列表，`task-workspace/` 和工具私有目录默认不提交。新建顶层源码目录时，应明确更新 `.gitignore` 后再提交。

## 单独安装技能

可将 `skills/mail-reader-summary` 或 `skills/task-board` 整个文件夹复制到 Agent 支持的技能目录，例如 Codex 用户技能目录 `$CODEX_HOME/skills`（默认 `~/.codex/skills`）。只复制所需技能即可，不需要复制运行数据。若目标已存在，先比较版本并保留用户修改。

两个技能各自携带运行所需模板和脚本，不依赖本仓库固定安装路径。独立项目中明确告诉 Agent 项目目录；两个技能都使用 `<项目>/task-workspace/`，可自然衔接。完整项目模式下，Agent 通过 `AGENTS.md` 查找 `skills/`，无需全局安装。

## 行为与边界

- 卡片标题由 Agent 阅读完整来源后归纳，详情保留任务内容及审计证据；派发人显示人名。
- 只有实际交付才能自动完成任务。收悉或计划不代表完成；后续修改要求创建关联任务。
- HTML 自带数据库快照，无需服务器或手动选择 JSON。Agent 修改数据库后重新生成页面。
- 页面编辑保存在当前浏览器本地存储；换电脑前应导出修改后的 JSON。刷新页面不会连接邮箱，也不会将浏览器编辑直接写回磁盘。
- 浏览器可打开普通附件。Foxmail 自定义 EML 协议仅在已注册的 Windows 机器启用；其他机器使用普通文件链接/下载。移动技能或 Python 路径后需重新注册。
- IMAP 正文与附件读取可跨平台；本地 Foxmail 缓存适配器为实验性、版本相关能力。PDF、PPT、图片等附件可保存，但没有内置文本识别，需 Agent 的其他可用能力读取。
- 通用 EML 导入会保留原始邮件和解码后的附件，并按内容哈希去重；专有 Outlook `.msg` 不属于 EML，当前不宣称支持。
- Logo 与品牌设置通过工作区 `config/brand.json` 配置，缺省显示中性看板。

## 离线验证

```sh
python -m unittest discover -s tests -v
```

测试在临时目录创建空项目和虚构邮件，不连接邮箱、不打开个人工作区、不发送邮件。
