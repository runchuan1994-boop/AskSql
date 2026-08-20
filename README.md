# NL2SQL Agent

自然语言转 SQL 的数据分析工具，基于 LangGraph 的 ReAct Agent。

> 用自然语言提问，自动生成 SQL 并查询数据库，支持反思迭代和多轮对话。

## ✨ 功能特性

- 🧠 意图分析 — 自动识别表、维度、筛选条件、聚合方式
- 🔍 意图探查 — 用轻量 SQL 自动消除歧义
- ❓ 混合式澄清 — 关键歧义主动问，次要歧义先猜后验
- 📝 SQL 生成 — 基于 Schema 生成准确 SQL
- 🛡️ 沙盒执行 — 只读保护 + 超时 + 行数限制
- 🔄 ReAct 反思 — 自动检查结果，迭代优化
- 💬 多轮对话 — 支持上下文追问
- 🗄️ 多项目/多数据源 — Schema 自动导入
- 🤖 多 LLM 支持 — Claude / OpenAI / 本地模型

## 🚀 快速开始

### 方式一：Docker 一键启动（推荐）

```bash
# 1. 复制环境变量
cp backend/.env.example .env

# 2. 编辑 .env，填入你的 API Key
vim .env

# 3. 启动
make up
# 或者
docker compose up -d
```

打开 http://localhost:5173 即可使用。

### 方式二：开发模式

```bash
# 后端
cd backend
uv pip install -e ".[dev]"
uv run uvicorn app.main:app --reload --port 8000

# 前端（另开终端）
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173

## 📦 项目结构

```
nl2sql/
├── backend/                # Python FastAPI 后端
│   ├── nl2sql/            # ★ 核心库（可独立使用）
│   │   ├── agent/         # LangGraph Agent
│   │   ├── schema/        # Schema 管理
│   │   ├── llm/           # LLM 适配层
│   │   └── executor/      # SQL 执行器
│   ├── app/               # FastAPI 应用层
│   │   ├── api/           # API 路由
│   │   ├── services/      # 业务服务
│   │   └── core/          # 配置 + 数据库
│   ├── config/schemas/    # Schema YAML 文件
│   └── data/              # SQLite 数据文件
│
├── frontend/              # React 前端
│   └── src/
│       ├── components/
│       ├── hooks/
│       └── pages/
│
├── docs/                   # 设计文档 + 实现计划
│   └── superpowers/
│       ├── specs/         # 设计文档
│       └── plans/         # 实现计划
│
├── docker-compose.yml     # Docker Compose 配置
└── Makefile              # 常用命令
```

## 🧪 运行测试

```bash
# 后端测试
make test-backend

# 或手动
cd backend && pytest tests/ -v
```

## 📚 架构

```
用户提问 → 意图分析 → 意图探查 → 澄清判断
                              ↓
                     ask_clarify  /  generate_sql
                                           ↓
                                     execute_sql
                                           ↓
                                       reflect
                                   ↙          ↘
                        generate_sql (重试)   summarize → 输出
```

详细设计请查看 [设计文档](docs/superpowers/specs/2026-08-19-nl2sql-agent-design.md)。

## 🔧 配置

### LLM 配置

支持三种 provider：

| Provider | 说明 | 环境变量 |
|----------|------|----------|
| `claude` | Anthropic Claude | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |
| `openai` | OpenAI 官方 | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| `local_openai_compatible` | 本地兼容模型（Ollama / vLLM / LM Studio 等） | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` |

### 数据库配置

在前端添加数据源时配置。支持所有 SQLAlchemy 兼容的数据库：
- MySQL
- PostgreSQL
- SQLite
- ClickHouse
- 等等

## 📄 License

MIT
