<div align="center">

# AskSql

**跟数据库聊天，就这么简单**

🧠 自然语言 → SQL → 结果 → 图表，一个 Agent 全搞定。

[快速开始](#-快速开始) ·
[工作原理](#-工作原理) ·
[架构设计](#️-架构设计) ·
[常见问题](#-常见问题)

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)]()
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)]()
[![LangGraph](https://img.shields.io/badge/🦜🕸️-LangGraph-123693)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## 🤔 痛点

说实话，做数据分析的日常是这样的：

- **产品经理**："帮我拉个上周新增用户的留存？对了按渠道分一下。" → 写 SQL 写半小时
- **运营同学**："这个数对不上啊，是不是 SQL 写错了？" → 查 bug 查一小时
- **老板**："帮我看看为什么转化率掉了？" → 先猜他到底想问啥

SQL 本身不难，难的是**来回沟通的成本**和**重复劳动的时间**。每次都是一样的流程：

> 理解需求 → 查表结构 → 写 SQL → 跑 → 发现不对 → 改 → 再跑……

市面上大部分"AI 写 SQL"的工具？本质就是套了个 prompt，生成完就完事了。表名猜错一个，结果全是废的。

## ✨ 解决方案

**AskSql 就是来打破这个循环的。** 你用大白话问，它自己想、自己写、自己跑、自己检查，最后给你答案 —— 连图都给你画好了。

它不是套了层壳的 LLM 聊天机器人，而是一个**带反思循环的多 Agent 系统**，真的会思考：

| 传统 AI SQL 工具 | AskSql |
|---|---|
| 生成 SQL，听天由命 | 先摸清楚你的 schema 和数据，再动手写 |
| 错了也不吭声，直接返回垃圾 | 自己反思、自己找 bug、自己重写 |
| 听不懂就说"我不明白" | 歧义大就问你，小歧义先猜（猜完会告诉你） |
| 一问一答，没上下文 | 多轮对话，全程记住你说过啥 |
| 给你一张表自己看 | 人话总结 + 自动可视化 |

## 🎯 适合谁用？

- **产品经理** — 再也不用排队等数据了，想啥直接问
- **运营同学** — 活动效果怎么样？甩个问题过去就有答案
- **数据分析师** — 把重复的取数活儿交给它，你去搞更有价值的分析
- **工程师** — 排查问题快速查数据，不用翻 SQL 历史
- **小团队** — 没有专职数据岗？AskSql 就是你的半个数据分析师

---

## 🌟 核心功能

### 🧠 真正会思考的智能

- **意图识别** — 你说"最近什么东西卖得好"，它知道要去查销售表 + 按商品聚合 + 排序
- **Schema 剖析** — 自动分析你的表（行数、值分布、Top 值），Agent 在写 SQL 之前就理解你的数据
- **数据探查** — 不确定字段含义？先跑几条 sample 看看，不瞎猜
- **智能澄清** — 歧义太大就问你，小歧义自己先扛着，猜完还会告诉你"我假设了 XXX，不对告诉我"
- **自我反思（ReAct 循环）** — 结果不对劲？自己找问题重写，最多 N 轮迭代，不用人插手
- **查询改写** — 在生成 SQL 之前，先根据 schema 和上下文优化模糊的查询

### 🛡️ 安全可靠，放心使用

- **沙盒执行** — SQL 在隔离容器里跑，只读、超时、行数限制、资源限制一条龙，不用担心删库跑路
- **多 Agent 编排** — 基于 LangGraph 构建，每个 Agent 专精一件事（意图识别、SQL 生成、反思、可视化）
- **结果缓存** — 相同问题直接走缓存，省 token 省时间
- **全程透明** — 每一步 Agent 的思考和操作都有日志，看得到它干了啥、为什么、花了多久

### 📊 输出真正有用的结果

- **自动可视化** — 适合画图的数据直接上图表（折线、柱状、面积、饼图），不用自己再粘到 Excel 里
- **人话总结** — 不只是丢给你一张表，它会告诉你数据*意味着什么*
- **多轮对话** — "再按地区拆分一下"、"去掉测试数据" —— 上下文接得住
- **纠错检测** — 你说"这个不对"，它能检测到纠错信息，根据你的反馈重跑

### 🔌 想接啥接啥

- **多数据源** — MySQL / PostgreSQL / SQLite / ClickHouse……SQLAlchemy 能连的它都能聊
- **多模型支持** — Claude / OpenAI / 任何 OpenAI 兼容的本地模型（Ollama、vLLM 等），想用啥用啥
- **记忆系统** — 记住你的偏好、表的别名、过去的纠错，越用越懂你

---

## 🚀 快速开始

三步搞定，就这么简单。

### 1. 克隆 & 配置

```bash
git clone https://github.com/yourusername/asksql.git
cd asksql
cp backend/.env.example .env
```

### 2. 选个模型，填个 Key

打开 `.env`，**只需要填 2 项** —— 选 provider + 填 API Key。其他的默认值都帮你调好了。

**用 Claude（推荐，思考能力最强）：**
```dotenv
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxx
```

**用 OpenAI：**
```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxxxxxx
```

**用本地模型（Ollama / vLLM / 等等）：**
```dotenv
LLM_PROVIDER=local_openai_compatible
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=qwen2.5:7b
```

### 3. 启动

```bash
docker compose up -d
```

打开 **http://localhost:5173**，开始跟你的数据库聊天。

<details>
<summary>📦 开发模式（不用 Docker）</summary>

```bash
# 后端
cd backend
uv pip install -e ".[dev]"
uv run uvicorn app.main:app --reload --port 8000

# 前端（另开一个终端）
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173
</details>

---

## 🧠 工作原理

AskSql 基于 **LangGraph 多 Agent 架构**，拥有完整的 ReAct 反思循环。你问一个问题时，发生了什么：

```
                    ┌─────────────────────────┐
                    │    你问了一个问题       │
                    └───────────┬─────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │   🧭 意图分析           │
                    │  这是问啥？              │
                    │  哪些表相关？            │
                    └───────────┬─────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │   🔍 数据探查           │
                    │  看看真实数据            │
                    │  验证理解对不对          │
                    └───────────┬─────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │   ❓ 需要澄清吗？        │
                    │  有歧义 → 问用户         │
                    │  没问题 → 继续           │
                    └───────────┬─────────────┘
                          ┌────┴────┐
                          ↓         ↓
                   问用户         生成 SQL
                      ↓              ↓
                   你回答        沙盒执行 SQL
                      ↓              ↓
                生成 SQL    ┌───────────────┐
                      ↘     │  🔄 反思一下   │
                       ↘    │  结果对不对？  │
                        ↘   └───────┬───────┘
                         ↘  对 ↗   ↘ 不对
                          ↘↗         ↘
                    ┌─────────────────────────┐
                    │   📝 生成摘要 + 📊 可视化 │
                    └───────────┬─────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │      给你答案           │
                    └─────────────────────────┘
```

**简单说就是：先想清楚 → 再动手 → 做完检查 → 给你结果。** 跟一个靠谱的数据分析师干活儿一个路子。

---

## 🏗️ 架构设计

```
AskSql/
├── backend/                    # Python FastAPI 后端
│   ├── nl2sql/                # ★ 核心 Agent 库（可独立使用）
│   │   ├── agent/             # LangGraph 图 + 节点
│   │   │   ├── graph.py       # 主 Agent 图定义
│   │   │   ├── dispatcher.py  # 顶层意图路由
│   │   │   └── nodes/         # 专业节点：
│   │   │                    #   意图、生成、反思、
│   │   │                    #   执行、澄清、改写、
│   │   │                    #   总结、可视化、探查
│   │   ├── schema/            # Schema 模型 + 匹配 + 剖析
│   │   ├── llm/               # LLM 适配层（Claude / OpenAI / 本地）
│   │   └── executor/          # SQL 执行器 + 沙盒
│   ├── app/                   # FastAPI 应用层
│   │   ├── api/               # REST API 路由
│   │   ├── services/          # 业务服务
│   │   └── core/              # 配置 + 数据库
│   └── tests/                 # pytest 测试套件
│
├── frontend/                  # React 18 + TypeScript 前端
│   └── src/
│       ├── components/        # 聊天、图表、Schema 面板
│       ├── hooks/             # 自定义 React hooks
│       ├── i18n/              # 国际化
│       └── lib/               # 工具函数
│
├── docs/                      # 设计文档 & 计划
├── docker-compose.yml         # Docker Compose 配置
├── Makefile                   # 开发命令
└── run.sh                     # 一键部署脚本
```

---

## ⚙️ 配置说明

所有配置都在 `.env` 里 —— 就这一个文件。默认值已经够用了。

### LLM 相关

| 变量 | 默认值 | 干啥的 |
|------|--------|--------|
| `LLM_PROVIDER` | `claude` | 模型提供商：`claude` / `openai` / `local_openai_compatible` |
| `ANTHROPIC_API_KEY` | — | Claude 的 API Key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | 用哪个 Claude 模型 |
| `OPENAI_API_KEY` | — | OpenAI（或兼容）的 API Key |
| `OPENAI_MODEL` | `gpt-4o` | 用哪个模型 |
| `OPENAI_BASE_URL` | — | 本地模型的接口地址 |

### Agent 行为

| 变量 | 默认值 | 干啥的 |
|------|--------|--------|
| `MAX_ITERATIONS` | `5` | 最多反思几轮 |
| `SQL_TIMEOUT_SECONDS` | `30` | SQL 查询超时时间 |
| `SQL_MAX_ROWS` | `1000` | 最多返回多少行（安全限制） |

### 沙盒

SQL 在隔离容器里执行，只读 + 超时 + 资源限制。

```dotenv
SANDBOX_ENABLED=true
SANDBOX_NETWORK=true
```

更多沙盒选项见 `.env.example`。

---

## 🧪 运行测试

```bash
cd backend && pytest tests/ -v
```

---

## ❓ 常见问题

<details>
<summary><strong>这比直接让 ChatGPT 写 SQL 好在哪？</strong></summary>

好很多，专门针对数据库场景优化：

1. **懂你的数据结构** — ChatGPT 不知道你的表名、字段类型、数据分布。AskSql 会剖析你的 schema，带着这些上下文思考。
2. **执行 + 反思** — ChatGPT 给你 SQL 你自己跑。AskSql 自己跑、自己看结果、不对自己改。
3. **安全** — 只读沙盒 + 超时 + 行数限制，不会不小心 `DROP TABLE`。
4. **多轮上下文** — 记住你的数据库、你之前问过的问题、你纠正过的地方。
5. **可视化** — 不只是给你一张表，它会画图并用自然语言解释结果。
</details>

<details>
<summary><strong>它会修改我的数据吗？</strong></summary>

不会。默认情况下 SQL 执行器是只读模式。即使 LLM 生成了 `INSERT` 或 `DROP`，也不会执行。
</details>

<details>
<summary><strong>支持哪些数据库？</strong></summary>

基本上主流的都支持。AskSql 底层用 SQLAlchemy，支持 MySQL、PostgreSQL、SQLite、ClickHouse、MariaDB、Oracle、MSSQL 等等。只要 SQLAlchemy 有对应的 dialect 就能用。
</details>

<details>
<summary><strong>可以完全本地运行吗？</strong></summary>

可以。用 `local_openai_compatible` 模式，接任何 OpenAI 兼容的本地模型（Ollama、vLLM、LM Studio 等）。你的数据不会离开你的机器。
</details>

<details>
<summary><strong>准确率怎么样？</strong></summary>

看模型、看 schema 复杂度、看问题难度。用 Claude Sonnet+ + 结构清晰的 schema，首次准确率大概 85-95%，加上反思循环还能更高。Agent 不确定的时候会告诉你，而不是瞎编数字。
</details>

---

## 📄 License

MIT — 随便用，别做坏事就行。

---

<div align="center">

用 ❤️ 打造，为了那些想要答案而不是 SQL 的人。

[⭐ 点个 Star](https://github.com/yourusername/asksql) ·
[🐛 提个 Bug](https://github.com/yourusername/asksql/issues) ·
[💬 讨论交流](https://github.com/yourusername/asksql/discussions)

</div>
