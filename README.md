# 每日新闻简报（个性化 PDF 日报）

自动采集国内外新闻源，用 DeepSeek AI 智能处理（摘要、英文翻译、分类、今日综述、跨源去重），生成**护眼风的中文 PDF 日报**并**自动发送到你的 QQ 邮箱**。HTML 仅作为本地备份，不会出现在邮件中。

## 功能特点

- 📡 **国内外 17 个新闻源**：科技（少数派、钛媒体、极客公园、爱范儿、Hacker News、The Verge、TechCrunch 等）、财经（CNBC、MarketWatch 等）、国际（NPR、DW 德国之声、The Guardian、Al Jazeera、NHK 等，全部使用原版英文源）
- 🌐 **国外源自动走你的梯子代理**，国内源直连
- 🤖 **DeepSeek V4-Flash AI 全流程**（已关闭推理提速降本）：智能摘要、英文翻译成中文（**双语对照**）、智能分类、剔除低质/八卦内容、生成"今日要闻综述"
- 🎨 **适合邮件阅读的 PDF**（清晰层级、中文字体、分页与页码），并可保留深色护眼 HTML 备份
- 📊 **财经数据速览**：A股/港股/美股指数、汇率、金价
- 🧠 **个性化**：按你的画像（光电专业 + 股民）加权筛选，聚焦半导体/AI/新能源/军工等持仓板块
- 🔄 **AI 不可用时自动回退**本地处理，保证每天都能出报告
- 🗂️ 按月归档，自动清理 N 天前的旧报告
- � **定时 + 邮件**：每天 07:00 计划任务自动生成并发送到 QQ 邮箱（生成前检测 VPN/外网，不通每 5 分钟重试至 23:00；只在空闲时段生成）；生成后只保存+发邮件，不再自动打开报告
- 💰 **费用透明**：报告页脚显示本次消耗的 token 数与费用（按官方 V4 峰值价估算，单次约 ¥0.3，随条数/时段波动）

## 快速开始

### 1. 安装依赖

```bash
# 首次安装：建立项目专用环境并安装依赖
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
# 生成 PDF 不需浏览器/Playwright；运行脚本会优先使用 .venv
```

### 2. 配置

复制 `.env.example` 为 `.env`，填入你的 DeepSeek API Key：

```
DEEPSEEK_API_KEY=sk-你的密钥
```

编辑 `config.yaml` 可调整：
- `network.proxy`：你的梯子本地代理地址（程序默认用 `http://127.0.0.1:7892`，请改成你的实际端口；梯子关了国内源照常工作）
- `user_profile`：你的背景、关注领域、排除词（决定 AI 筛选倾向）
- `report.categories`：各分类条数、保留天数
- `sources`：新闻源列表（可自由增删）

### 3. 一键生成（手动）

**双击桌面「每日新闻」图标**（或双击 `run_now.bat`）→ 自动抓取 → AI 处理（含跨源去重）→ 生成 PDF → **发送到 QQ 邮箱**（不再自动打开），约 1-2 分钟。

命令行方式：
```bash
python -m news_crawler.main
python -m news_crawler.main --date 2026-08-10   # 指定日期
python -m news_crawler.main --no-ai              # 强制本地处理（不调用 AI）
python -m news_crawler.main --no-mail            # 只保存报告，不发邮件
python -m news_crawler.main --resend-mail        # PDF 未变化时也强制重发
python -m news_crawler.main --wait-net           # 先检测 VPN/外网再生成（计划任务模式）
```

报告输出到 `output/2026-08/2026-08-10.pdf`（可选保留同名 HTML 备份）。QQ 邮件仅附带 PDF。日志在 `logs/`。

### 4. 定时生成 + 邮箱发送（默认启用）

**流程**：每天 **07:00** 计划任务启动 → 检测 VPN/外网（**不通则每 5 分钟重试，当天 23:00 截止**；高峰时段 9-12/14-18 不生成，等空闲时段）→ 生成 PDF → 发送到 QQ 邮箱。相同内容不会重复发送；生成成功后当天不再检测，也不再自动打开报告。

**首次配置邮箱（必须一次）**：
1. QQ 邮箱网页版 → 设置 → 账户 → **POP3/SMTP 服务 → 开启**并生成**授权码**（16 位纯字母数字，不是 QQ 密码）；
2. 终端运行 `python tools/store_smtp.py`，粘贴授权码（不回显，自动加密存入 `.env` 并验证登录）；首次运行会顺带输入 QQ 邮箱地址，存在本地 `.env`，**不进公开仓库**；
3. 收件邮箱在 `.env` 的 `SMTP_TO_ADDRS` 配置（多个用英文逗号分隔，留空则发给自己）。

**注册/更新定时任务**：双击 `install_task.bat`（任务名 `DailyNewsReport`，错过 07:00 会在开机/唤醒后补跑），或命令行：

```bat
schtasks /Create /TN "DailyNewsReport" /TR "wscript.exe \"%~dp0run_scheduled.vbs\"" /SC DAILY /ST 07:00 /F
```

常用命令：
```bat
schtasks /Run /TN DailyNewsReport        # 立即运行一次
schtasks /Query /TN DailyNewsReport      # 查看任务
schtasks /Delete /TN DailyNewsReport /F  # 删除任务
```

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
│   ├── netcheck.py      # VPN/外网检测与等待（空闲时段调度）
│   ├── mail.py          # QQ 邮箱 SMTP 发送报告
│   ├── report.py        # PDF 日报 + HTML 备份生成
│   ├── cleanup.py       # 清理过期报告
│   └── main.py          # 主流程
├── output\2026-08\      # 生成的 PDF/HTML 报告（按月归档）
├── logs\                # 运行日志
├── run_now.bat          # ★ 一键生成并发送邮箱（桌面快捷方式指向这里）
├── run_daily.bat        # 定时任务入口（07:00，含联网检测等待）
├── run_scheduled.vbs    # 计划任务隐藏启动器（避免黑框常驻）
├── install_task.bat     # 注册每天 07:00 的定时任务
├── assets\news.ico      # 应用图标
└── tools\
    ├── make_icon.py     # 图标生成脚本
    ├── store_key.py     # DeepSeek Key 加密录入
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

- **国外新闻抓不到？** 确认梯子已开启，且 `config.yaml` 里 `network.proxy` 是你梯子的实际端口（一般 7890/7892/10809）。
- **某个源失效了？** 在 `config.yaml` 的 `sources` 里删除或替换即可，单个源失败不影响整体。
- **想换 AI 服务商？** `ai.py` 兼容 OpenAI 接口格式，改 `config.yaml` 的 `base_url`/`model` 即可。
- **报告想更简洁/更详细？** 调整 `config.yaml` 的 `report.categories.*.max_items`（条数）或 `user_profile.item_summary_chars`（单条摘要字数）。
- **去重太松/太紧？** AI 模式下调整去重提示（`ai.py` 的 `find_duplicates`）；本地模式调整 `report.post_dedup_threshold`。
- **没收到邮件？** 看 `logs\report_当天.log` 里的「邮件发送」记录；确认已开启 QQ 邮箱 SMTP 服务、已运行 `tools/store_smtp.py` 录入授权码，并翻一下垃圾箱。

## 安全说明

- API Key 已通过 **Windows DPAPI 加密**存入 `.env` 的 `DEEPSEEK_API_KEY_ENC`，**绑定当前 Windows 用户与本机**，明文不落盘；即使 `.env` 文件被拷贝，也无法在其它机器或账号上解密盗用。
- 旧明文 `.env` 文件已被 `.gitignore` 排除，不会进代码库。
- 首次使用或更换 Key：把明文填入 `.env` 后运行 `python tools/store_key.py`，会自动加密并清除明文。
- 更换电脑/重装系统后需重新运行 `tools/store_key.py` 加密新 Key。
- QQ 邮箱 SMTP 授权码同样通过 DPAPI 加密存入 `.env` 的 `QQ_SMTP_AUTH_ENC`（`tools/store_smtp.py` 录入），明文不落盘。
- 若 Key 曾泄露，可在 DeepSeek 后台重置，再运行 `tools/store_key.py` 更新。
