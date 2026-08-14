# 每日新闻简报（个性化 HTML 日报）

自动采集国内外新闻源，用 DeepSeek AI 智能处理（摘要、英文翻译、分类、今日综述、跨源去重），生成**深色护眼风的中文 HTML 日报**。双击桌面图标即可生成并自动打开，15 分钟即可读完。

## 功能特点

- 📡 **国内外 17 个新闻源**：科技（少数派、钛媒体、极客公园、爱范儿、Hacker News、The Verge、TechCrunch 等）、财经（CNBC、MarketWatch 等）、国际（NPR、DW 德国之声、The Guardian、Al Jazeera、NHK 等，全部使用原版英文源）
- 🌐 **国外源自动走你的梯子代理**，国内源直连
- 🤖 **DeepSeek AI 全流程**：智能摘要、英文翻译成中文（**双语对照**）、智能分类、剔除低质/八卦内容、生成"今日要闻综述"
- 🎨 **深色护眼主题 HTML**（柔和深灰底 + 低饱和文字，低蓝光、低对比度、久看不累）
- 📊 **财经数据速览**：A股/港股/美股指数、汇率、金价
- 🧠 **个性化**：按你的画像（光电专业 + 股民）加权筛选，聚焦半导体/AI/新能源/军工等持仓板块
- 🔄 **AI 不可用时自动回退**本地处理，保证每天都能出报告
- 🗂️ 按月归档，自动清理 N 天前的旧报告
- 🖱️ **桌面快捷方式**：双击即生成并自动打开 HTML（可随时改为定时运行）
- 💰 **费用透明**：报告页脚显示本次消耗的 token 数与费用（单次约 ¥0.1，随摘要长度/条数变化）

## 快速开始

### 1. 安装依赖

```bash
# 首次安装依赖（国内建议加清华镜像）
pip install -r requirements.txt
# 纯 Python 生成 HTML，无需浏览器/Playwright
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

### 3. 一键生成并打开

**双击桌面「每日新闻」图标**（或双击 `run_now.bat`）→ 自动抓取 → AI 处理（含跨源去重）→ 生成 HTML → **自动打开**，约 1-2 分钟。

命令行方式：
```bash
python -m news_crawler.main
python -m news_crawler.main --date 2026-08-10   # 指定日期
python -m news_crawler.main --no-ai              # 强制本地处理（不调用 AI）
```

报告输出到 `output/2026-08/2026-08-10.html`。日志在 `logs/`。

### 4. （可选）定时自动运行

默认是**手动双击运行**。如果你希望每天定时自动生成，可注册 Windows 计划任务：

双击运行 `install_task.bat`，或在命令行执行：

```bat
schtasks /Create /TN "DailyNewsReport" /TR "\"%~dp0run_daily.bat\"" /SC DAILY /ST 08:00 /F
```

常用命令：
```bat
schtasks /Run /TN DailyNewsReport        # 立即运行一次
schtasks /Query /TN DailyNewsReport      # 查看任务
schtasks /Delete /TN DailyNewsReport /F  # 删除任务
```

> 注意：定时运行时请确保**电脑处于开机状态、梯子已开启**（国外源需要梯子）。

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
│   ├── report.py        # 护眼风 HTML 报告生成
│   ├── cleanup.py       # 清理过期报告
│   └── main.py          # 主流程
├── output\2026-08\      # 生成的 HTML 报告（按月归档）
├── logs\                # 运行日志
├── run_now.bat          # ★ 一键生成并打开（桌面快捷方式指向这里）
├── run_daily.bat        # （可选）定时任务入口
├── install_task.bat     # （可选）注册每日定时任务
├── assets\news.ico      # 应用图标
└── tools\make_icon.py   # 图标生成脚本
```

## 常见问题

- **国外新闻抓不到？** 确认梯子已开启，且 `config.yaml` 里 `network.proxy` 是你梯子的实际端口（一般 7890/7892/10809）。
- **某个源失效了？** 在 `config.yaml` 的 `sources` 里删除或替换即可，单个源失败不影响整体。
- **想换 AI 服务商？** `ai.py` 兼容 OpenAI 接口格式，改 `config.yaml` 的 `base_url`/`model` 即可。
- **报告想更简洁/更详细？** 调整 `config.yaml` 的 `report.categories.*.max_items`（条数）或 `user_profile.item_summary_chars`（单条摘要字数）。
- **去重太松/太紧？** AI 模式下调整去重提示（`ai.py` 的 `find_duplicates`）；本地模式调整 `report.post_dedup_threshold`。

## 安全说明

- API Key 已通过 **Windows DPAPI 加密**存入 `.env` 的 `DEEPSEEK_API_KEY_ENC`，**绑定当前 Windows 用户与本机**，明文不落盘；即使 `.env` 文件被拷贝，也无法在其它机器或账号上解密盗用。
- 旧明文 `.env` 文件已被 `.gitignore` 排除，不会进代码库。
- 首次使用或更换 Key：把明文填入 `.env` 后运行 `python tools/store_key.py`，会自动加密并清除明文。
- 更换电脑/重装系统后需重新运行 `tools/store_key.py` 加密新 Key。
- 若 Key 曾泄露，可在 DeepSeek 后台重置，再运行 `tools/store_key.py` 更新。
