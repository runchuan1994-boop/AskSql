# AskSql — 跟数据库聊天，就这么简单

> 🧠 自然语言 → SQL → 结果 → 图表，一个 Agent 全搞定。
> 不用再找数据同学了，你自己就是数据同学。

---

## 🤔 为什么要做这个？

说实话，做数据分析的日常是这样的：

- **产品经理**："帮我拉个上周新增用户的留存？对了按渠道分一下。" → 你写 SQL 写半小时
- **运营同学**："这个数对不上啊，是不是 SQL 写错了？" → 你查 bug 查一小时
- **老板**："帮我看看为什么转化率掉了？" → 你得先猜他到底想问啥

SQL 本身不难，难的是**来回沟通的成本**和**重复劳动的时间**。每次都是一样的流程：理解需求 → 查表结构 → 写 SQL → 跑 → 发现不对 → 改 → 再跑……

**AskSql 就是想把这件事变简单：你用大白话问，它自己想、自己写、自己跑、自己检查，最后给你答案。**

它不是那种"生成 SQL 就完事"的玩具 —— 它真的会**思考**：
- 没听懂你的问题？它会反问你
- 不确定哪个表？它先去摸一下数据
- SQL 跑出来不对？它自己反思重写
- 结果适合画图？直接给你可视化了

## ✨ 它能干啥？

| 能力 | 人话版 |
|------|--------|
| 🧠 **意图识别** | 你说"最近什么东西卖得好"，它知道要去查销售表 + 按商品聚合 + 排序 |
| 🔍 **数据探查** | 不确定字段含义？它先跑几条 sample 看看，不瞎猜 |
| ❓ **智能澄清** | 歧义太大就问你，小歧义自己先扛着，猜完还会告诉你"我假设了 XXX，不对告诉我" |
| 🛡️ **沙盒执行** | SQL 在隔离容器里跑，只读、超时、行数限制一条龙，不用担心删库跑路 |
| 🔄 **自我反思** | 结果不对劲？它自己找问题重写，不用你说"这不对啊" |
| 📊 **自动可视化** | 适合画图的数据直接给你上图表，不用自己再粘到 Excel 里 |
| 💬 **多轮对话** | "再按地区拆分一下"、"去掉测试数据"——上下文接得住 |
| 🔌 **多数据源** | MySQL / PostgreSQL / SQLite / ClickHouse……SQLAlchemy 能连的它都能聊 |
| 🤖 **多模型支持** | Claude / OpenAI / 本地模型，想用啥用啥 |

## 🎯 适合谁用？

- **产品经理** — 再也不用排队等数据了，想啥直接问
- **运营同学** — 活动效果怎么样？甩个问题过去就有答案
- **数据分析师** — 把重复的取数活儿交给它，你去搞更有价值的分析
- **工程师** — 排查问题快速查数据，不用翻 SQL 历史
- **小团队** — 没有专职数据岗？AskSql 就是你的半个数据分析师

## 🚀 快速开始

### Docker 一键启动（推荐）

```bash
# 1. 复制环境变量
cp backend/.env.example .env

# 2. 编辑 .env，填入你的 API Key
vim .env

# 3. 启动
docker compose up -d
```

打开 http://localhost:5173 开聊。

### 开发模式

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

## 🧱 项目结构

```
AskSql/
├── backend/                # Python FastAPI 后端
│   ├── nl2sql/            # ★ 核心 Agent 库（可独立使用）
│   │   ├── agent/         # LangGraph Agent + 各节点
│   │   ├── schema/        # Schema 管理
│   │   ├── llm/           # LLM 适配层
│   │   └── executor/      # SQL 执行器 + 沙盒
│   ├── app/               # FastAPI 应用层
│   │   ├── api/           # API 路由
│   │   ├── services/      # 业务服务
│   │   └── core/          # 配置 + 数据库
│   └── sandbox-image/     # 沙盒容器镜像
│
├── frontend/              # React 前端
│   └── src/
│       ├── components/
│       ├── hooks/
│       └── pages/
│
├── docs/                   # 设计文档
├── docker-compose.yml     # Docker Compose
└── run.sh                 # 一键部署脚本
```

## 🧠 Agent 是怎么思考的？

```
你问了个问题
    ↓
意图分析 → 这是问啥？要查哪些表？
    ↓
意图探查 → 先摸一下数据，验证一下理解对不对
    ↓
澄清判断 → 有歧义？是问你还是先猜？
  ↙          ↘
问你         生成 SQL
 ↓              ↓
你回答        沙盒执行 SQL
 ↓              ↓
生成 SQL    反思一下结果对不对
  ↘          ↙
    生成摘要 + 可视化
         ↓
      给你答案
```

简单说就是：**先想清楚 → 再动手 → 做完检查 → 给你结果**。跟一个靠谱的数据分析师干活儿一个路子。

## 🔧 配置

### LLM 提供商

| Provider | 说明 | 环境变量 |
|----------|------|----------|
| `claude` | Anthropic Claude（推荐，思考能力强） | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |
| `openai` | OpenAI 官方 | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| `local_openai_compatible` | 本地兼容模型（Ollama / vLLM / LM Studio 等） | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` |

### 沙盒配置

Agent 执行 SQL 在沙盒容器中，支持：
- 只读模式保护数据安全
- 超时 + 内存 + CPU 限制
- 可选网络访问（用于动态安装数据库驱动）

详见 `.env.example`。

## 🧪 运行测试

```bash
cd backend && pytest tests/ -v
```

## 📄 License

MIT — 随便用，别做坏事就行。
