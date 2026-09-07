# 每日新闻简报（个性化 PDF 日报）

自动采集国内外新闻源，用 DeepSeek V4 Flash 智能处理（摘要、英文翻译、分类、今日综述、跨源去重），生成护眼风 HTML 和图片型 PDF 日报，并将**两个附件同时发送到你的 QQ 邮箱**。

## 功能特点

- 📡 **国内外 25 个新闻源**：科技媒体之外，增加 BBC Business、美联储、SEC、BBC World、联合国、Nature、Nature 光学与光子学、NASA JPL 等财经监管、国际与科研一手源
- 🌐 **国外源自动走你的梯子代理**，国内源直连
- 🤖 **DeepSeek V4 Flash**：智能摘要、英文翻译成中文（**双语对照**）、五类编排、低质内容过滤和“今日要闻综述”；摘要覆盖事实、数据、背景、影响与不确定性
- 🎨 **与护眼 HTML 同款的图片型 PDF**（网页长图智能分页，完整保留深色配色与卡片）；HTML 附件保留可复制文字和链接
- 📊 **财经数据速览**：A股/港股/美股指数、汇率、金价
- 🧠 **个性化**：按你的画像（光电专业 + 股民）加权筛选，聚焦半导体/AI/新能源/军工等持仓板块
- 🛡️ **AI 完整性保护**：DeepSeek 任一批次失败时不生成、不发送，避免混入本地降级摘要
- 🧯 **去重安全阀**：只合并不同来源对同一具体事件的报道；拒绝大组、跨类别、重叠分组，并限制单次删除比例，避免 AI 误删整批新闻
- 🗂️ 按月归档，自动清理 N 天前的旧报告
- 📬 **可靠定时 + 邮件**：每天 07:00 自动运行，睡眠/关机错过后自动补跑；隐藏启动器同步等待并把真实退出码返回计划任务，启动、结束和异常都有独立日志
- 💰 **用量透明**：报告页脚显示 DeepSeek token 用量与估算费用

## 快速开始

### 1. 安装依赖

```bash
# 首次安装：建立项目专用环境并安装依赖
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
# requirements.txt 已包含 PDF 依赖；本机还需有 Chrome、Edge 或 Chromium
```

### 2. 配置

本机已配置 DPAPI 加密的 DeepSeek API Key；需要更新时运行密钥录入工具：

```bash
python tools/store_key.py
```

编辑 `config.yaml` 可调整：
- `network.proxy`：你的梯子本地代理地址（默认 `http://127.0.0.1:7892`，请改成实际端口；配置后检测失败不会再回退直连）
- `network.min_foreign_sources` / `min_foreign_items`：允许生成和发送日报所需的最低海外来源数与条数
- `user_profile`：你的背景、关注领域、排除词（决定 AI 筛选倾向）
- `report.categories`：各分类条数、保留天数
- `report.max_items_per_source_in_category`：每个分类优先采用同一来源的条数上限，候选不足时自动回填
- `ai.dedup_max_group_size` / `dedup_max_drop_ratio`：AI 去重单组及总删除比例上限
- `sources`：新闻源列表（可自由增删）

### 3. 一键生成（手动）

**双击桌面「每日新闻」图标**（或双击 `run_now.bat`）→ 自动抓取 → AI 处理（含跨源去重）→ 生成 HTML 和图片型 PDF → **以双附件发送到 QQ 邮箱**（不再自动打开），通常约 3-8 分钟，取决于当日新闻量和免费接口负载。

命令行方式：
```bash
python -m news_crawler.main
python -m news_crawler.main --date 2026-08-10   # 指定日期
python -m news_crawler.main --no-ai              # 强制本地处理（不调用 AI）
python -m news_crawler.main --no-mail            # 只保存报告，不发邮件
python -m news_crawler.main --resend-mail        # PDF 未变化时也强制重发
python -m news_crawler.main --wait-net           # 先检测 VPN/外网再生成（计划任务模式）
```

报告输出到 `output/2026-08/2026-08-10.pdf` 及同名 HTML。QQ 邮件同时附带 PDF 和 HTML。日志在 `logs/`。

### 4. 定时生成 + 邮箱发送（默认启用）

**流程**：每天 **07:00** 计划任务启动 → 严格检测配置的代理/VPN（**不通则每 5 分钟重试，当天 23:00 截止**）→ 抓取后校验海外来源覆盖 → DeepSeek 并行处理 → 生成 PDF → 发送到 QQ 邮箱。海外覆盖不足或 AI 临时不可用时不生成、不发送，并在 5 分钟后重试。隐藏启动器会一直等待整个流程结束，将真实退出码交给 Windows；任务最长运行至 23:30，防止异常进程跨天占用任务实例。

**首次配置邮箱（必须一次）**：
1. QQ 邮箱网页版 → 设置 → 账户 → **POP3/SMTP 服务 → 开启**并生成**授权码**（16 位纯字母数字，不是 QQ 密码）；
2. 终端运行 `python tools/store_smtp.py`，粘贴授权码（不回显，自动加密存入 `.env` 并验证登录）；首次运行会顺带输入 QQ 邮箱地址，存在本地 `.env`，**不进公开仓库**；
3. 收件邮箱在 `.env` 的 `SMTP_TO_ADDRS` 配置（多个用英文逗号分隔，留空则发给自己）。

**注册/更新定时任务**：右键 `install_task.bat` 并选择“以管理员身份运行”（任务名 `DailyNewsReport`，错过 07:00 会在开机/唤醒后补跑）。更新代码后也应重新运行一次，使最新可靠性设置写入 Windows。

常用命令：
```bat
schtasks /Run /TN DailyNewsReport        # 立即运行一次
schtasks /Query /TN DailyNewsReport /V /FO LIST  # 查看真实退出码和下次运行时间
schtasks /Delete /TN DailyNewsReport /F  # 删除任务
```

日志分为两层：`logs\scheduler.log` 记录隐藏启动器的启动时间、结束时间和真实退出码；`logs\run.log` 与 `logs\report_YYYY-MM-DD.log` 记录 Python 选择、联网等待、抓取、生成及邮件发送详情。任务返回码 `0` 表示完整流程成功；`2` 表示等待条件超时，`3` 表示海外覆盖不足，`4` 表示必需的 AI 处理失败，`5` 表示报告已生成但邮件发送失败，`100` 表示隐藏启动器未能启动批处理。

## 项目结构

```
d:\新闻news\
├── config.yaml          # 全部配置（源/分类/条数/画像/代理）
├── .env                 # DeepSeek API Key（已 gitignore，勿提交）
├── news_crawler\        # 核心代码
│   ├── fetcher.py       # RSS + JSON 抓取（代理/超时/容错）
│   ├── fulltext.py      # 重点源正文抓取
│   ├── market.py        # 财经数据（指数/汇率/金价）
│   ├── dedup.py         # 相似度去重
│   ├── classify.py      # 本地关键词分类（兜底）
│   ├── filter.py        # 排除八卦/软文/标题党
│   ├── ai.py            # DeepSeek 批量摘要/翻译/综述
│   ├── nlp_local.py     # 本地回退处理
│   ├── netcheck.py      # 严格 VPN 检测、等待与海外源覆盖闸门
│   ├── mail.py          # QQ 邮箱 SMTP 发送报告
│   ├── report.py        # HTML 报告 + 浏览器直出 PDF
│   ├── cleanup.py       # 清理过期报告
│   └── main.py          # 主流程
├── output\2026-08\      # 生成的 PDF/HTML 报告（按月归档）
├── logs\                # 调度器、批处理和日报运行日志
├── run_now.bat          # ★ 一键生成并发送邮箱（桌面快捷方式指向这里）
├── run_daily.bat        # 定时任务入口（07:00，含联网检测等待）
├── run_scheduled.vbs    # 同步等待、回传退出码的隐藏启动器
├── install_task.bat     # 注册每天 07:00 的定时任务
├── assets\news.ico      # 应用图标
└── tools\
    ├── make_icon.py     # 图标生成脚本
    ├── store_key.py     # 当前 AI 服务商 Key 加密录入
    └── store_smtp.py    # QQ 邮箱授权码加密录入
```

## 开发检查

```bash
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\ruff check .
.venv\Scripts\pytest
.venv\Scripts\python tools\qa_pdf.py output\2026-08\2026-08-10.pdf
```

`requirements.lock.txt` 记录当前已验证环境的精确版本；GitHub Actions 会在每次推送和 Pull Request 时自动运行静态检查与测试。

## 常见问题

- **国外新闻抓不到？** 确认梯子已开启，且 `config.yaml` 里 `network.proxy` 是实际端口（一般 7890/7892/10809）。计划任务会等待，不会发送只有国内源的日报。
- **某个源失效了？** 在 `config.yaml` 的 `sources` 里删除或替换即可，单个源失败不影响整体。
- **想换 AI 服务商？** `ai.py` 兼容 OpenAI 接口格式，改 `config.yaml` 的 `base_url`、`model` 和 `api_key_env` 即可。
- **报告想更简洁/更详细？** 调整 `config.yaml` 的 `report.categories.*.max_items`（条数）或 `user_profile.item_summary_chars`（单条摘要字数）。
- **去重太松/太紧？** AI 模式下调整去重提示（`ai.py` 的 `find_duplicates`）；本地模式调整 `report.post_dedup_threshold`。
- **任务显示成功但没收到邮件？** 先看 `logs\scheduler.log` 是否有对应日期的 `START`/`END`，再看 `logs\run.log` 和 `logs\report_当天.log`。新版启动器会把真实退出码返回 Windows，不再把“仅启动了 wscript”误报为完整成功。
- **07:00 没运行？** 若电脑当时睡眠或关机，任务会在唤醒/登录后补跑；用 `schtasks /Query /TN DailyNewsReport /V /FO LIST` 核对 `Last Run Time`、`Last Result` 和 `Next Run Time`。
- **生成成功但没收到邮件？** 查看当日日志里的「邮件发送」记录；确认已开启 QQ 邮箱 SMTP 服务、已运行 `tools/store_smtp.py` 录入授权码，并检查垃圾箱。

## 安全说明

- API Key 已通过 **Windows DPAPI 加密**存入 `.env` 的 `DEEPSEEK_API_KEY_ENC`，**绑定当前 Windows 用户与本机**，明文不落盘；即使 `.env` 文件被拷贝，也无法在其它机器或账号上解密盗用。
- 旧明文 `.env` 文件已被 `.gitignore` 排除，不会进代码库。
- 首次使用或更换 Key：把明文填入 `.env` 后运行 `python tools/store_key.py`，会自动加密并清除明文。
- 更换电脑/重装系统后需重新运行 `tools/store_key.py` 加密新 Key。
- QQ 邮箱 SMTP 授权码同样通过 DPAPI 加密存入 `.env` 的 `QQ_SMTP_AUTH_ENC`（`tools/store_smtp.py` 录入），明文不落盘。
- 若 Key 曾泄露，可在 DeepSeek 开放平台重置，再运行 `tools/store_key.py` 更新。
