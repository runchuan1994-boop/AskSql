<div align="center">

# AskSql

**Chat with your database. Seriously.**

🧠 Natural language → SQL → results → charts. One agent, zero hassle.

[Quick Start](#-quick-start) ·
[How it works](#-how-it-works) ·
[Architecture](#-architecture) ·
[FAQ](#-faq)

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)]()
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)]()
[![LangGraph](https://img.shields.io/badge/🦜🕸️-LangGraph-123693)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## 🤔 The problem

Let's be real — data work in most teams looks like this:

- **PM**: "Can you pull last week's new user retention? Oh, split by channel too." → 30 minutes writing SQL
- **Ops**: "This number doesn't look right, did you mess up the query?" → an hour debugging
- **CEO**: "Why did conversion drop?" → 20 minutes figuring out what they're *actually* asking

SQL isn't the hard part. **The back-and-forth is.** It's always the same loop:

> Understand the question → find the right tables → write SQL → run it → realize it's wrong → fix it → run again…

And most "AI SQL" tools? They generate SQL and pray. One wrong table name and you get garbage.

## ✨ The solution

**AskSql breaks that loop.** Ask a question in plain English. It thinks, writes SQL, runs it, checks the result, and gives you an answer — with charts.

This isn't a prompt-wrapper around an LLM. It's a **multi-agent system with reflection loops** that actually thinks things through:

| Before (typical AI SQL tool) | After (AskSql) |
|---|---|
| Generates SQL and hopes for the best | Probes your schema, samples data, *then* writes SQL |
| Returns wrong results silently | Self-reflects, debugs, and rewrites — on its own |
| "I don't understand" on ambiguity | Asks clarifying questions *or* makes reasonable guesses (and tells you it guessed) |
| One question, one answer | Multi-turn conversation with full context |
| Tables, tables, tables | Natural language summary + auto-visualization |

## 🎯 Who's this for?

- **Product Managers** — skip the data queue. Ask, get answers, ship faster.
- **Ops & Growth** — "how's the campaign doing?" → answer in seconds, not hours.
- **Data Analysts** — offload the repetitive queries. Spend time on actual analysis.
- **Engineers** — debug with data without digging through old SQL snippets.
- **Small teams** — no dedicated data person? AskSql is your half-data-analyst-in-a-box.

---

## 🌟 Core Features

### 🧠 Intelligence that actually works

- **Intent Analysis** — You say "what's selling well lately?" — it knows to hit the sales table, group by product, and sort.
- **Schema Profiling** — Automatically profiles your tables (row counts, value distributions, top values) so the agent understands your data before writing a single line of SQL.
- **Data Probing** — Unsure what a column means? It samples real data instead of guessing blindly.
- **Smart Clarification** — Big ambiguity? It asks. Small ambiguity? It takes a guess *and tells you it guessed*.
- **Self-Reflection (ReAct loop)** — Results look off? It debugs and rewrites itself. Up to N iterations, no human needed.
- **Query Rewriting** — Refines ambiguous queries based on schema and context before generation even starts.

### 🛡️ Safety & reliability you can trust

- **Sandboxed Execution** — SQL runs in isolated containers — read-only, timeouts, row limits, resource caps. No "oops I dropped the table" disasters.
- **Multi-Agent Orchestration** — Built on LangGraph with specialized agents (intent, generation, reflection, visualization) — each does one thing well.
- **Result Caching** — Identical queries hit the cache, saving tokens and time.
- **Step-by-step transparency** — Every agent step is logged. See *exactly* what it did, why, and how long it took.

### 📊 Output that's actually useful

- **Auto-Visualization** — Data looks chart-friendly? You get charts (line, bar, area, pie). No copy-pasting into Excel.
- **Natural Language Summary** — Not just a table. It tells you what the data *means*.
- **Multi-Turn Chat** — "Split by region." "Exclude test data." — it remembers the context.
- **Correction Detection** — If you say "that's wrong", it detects the correction and re-runs with your feedback.

### 🔌 Connect anything

- **Multi-Datasource** — MySQL / PostgreSQL / SQLite / ClickHouse… if SQLAlchemy connects to it, AskSql chats with it.
- **Multi-LLM** — Claude / OpenAI / any OpenAI-compatible local model (Ollama, vLLM, etc.). Pick your favorite.
- **Memory System** — Remembers your preferences, table nicknames, and past corrections. Gets better the more you use it.

---

## 🚀 Quick Start

Three steps, that's it.

### 1. Clone & configure

```bash
git clone https://github.com/yourusername/asksql.git
cd asksql
cp backend/.env.example .env
```

### 2. Pick an LLM and add your API key

Open `.env` and set **just two things** — provider + key. Everything else has sensible defaults.

**Claude (recommended — best reasoning):**
```dotenv
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxx
```

**OpenAI:**
```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxxxxxx
```

**Local model (Ollama / vLLM / etc.):**
```dotenv
LLM_PROVIDER=local_openai_compatible
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=qwen2.5:7b
```

### 3. Launch

```bash
docker compose up -d
```

Open **http://localhost:5173** and start chatting with your data.

<details>
<summary>📦 Development mode (no Docker)</summary>

```bash
# Backend
cd backend
uv pip install -e ".[dev]"
uv run uvicorn app.main:app --reload --port 8000

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173
</details>

---

## 🧠 How it works

AskSql is built on a **LangGraph multi-agent architecture** with a full ReAct reflection loop. Here's what happens when you ask a question:

```
                    ┌─────────────────────────┐
                    │    You ask a question   │
                    └───────────┬─────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │   🧭 Intent Analysis    │
                    │  What are we asking?    │
                    │  Which tables matter?   │
                    └───────────┬─────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │   🔍 Schema Probing     │
                    │  Peek at real data      │
                    │  Validate understanding │
                    └───────────┬─────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │   ❓ Clarification?     │
                    │  Ambiguous → ask user   │
                    │  Clear → keep going     │
                    └───────────┬─────────────┘
                          ┌────┴────┐
                          ↓         ↓
                   Ask user     Generate SQL
                      ↓              ↓
                   Answer         Execute SQL
                      ↓              ↓
                Generate SQL   ┌───────────────┐
                      ↘        │  🔄 Reflect  │
                       ↘       │  Does this   │
                        ↘      │  make sense? │
                         ↘     └───────┬───────┘
                          ↘    yes ↗   ↘ no
                           ↘  ↗         ↘
                    ┌─────────────────────────┐
                    │   📝 Summarize + 📊 Viz  │
                    └───────────┬─────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │    You get an answer    │
                    └─────────────────────────┘
```

**In short: think first → execute → verify → deliver.** Exactly how a good data analyst works.

---

## 🏗️ Architecture

```
AskSql/
├── backend/                    # Python FastAPI backend
│   ├── nl2sql/                # ★ Core agent library (usable standalone)
│   │   ├── agent/             # LangGraph graph + nodes
│   │   │   ├── graph.py       # Main agent graph definition
│   │   │   ├── dispatcher.py  # Top-level intent routing
│   │   │   └── nodes/         # Specialized nodes:
│   │   │                    #   intent, generate, reflect,
│   │   │                    #   execute, clarify, rewrite,
│   │   │                    #   summarize, visualize, probe
│   │   ├── schema/            # Schema models + matching + profiling
│   │   ├── llm/               # LLM abstraction (Claude / OpenAI / local)
│   │   └── executor/          # SQL executor + sandbox
│   ├── app/                   # FastAPI application layer
│   │   ├── api/               # REST API routes
│   │   ├── services/          # Business logic services
│   │   └── core/              # Config + database
│   └── tests/                 # pytest test suite
│
├── frontend/                  # React 18 + TypeScript frontend
│   └── src/
│       ├── components/        # Chat, Chart, Schema panels
│       ├── hooks/             # Custom React hooks
│       ├── i18n/              # Internationalization
│       └── lib/               # Utilities
│
├── docs/                      # Design docs & plans
├── docker-compose.yml         # Docker Compose config
├── Makefile                   # Dev commands
└── run.sh                     # One-click deploy script
```

---

## ⚙️ Configuration

All config lives in `.env` — that's the only file you need. Defaults work for most people.

### LLM

| Variable | Default | What it does |
|----------|---------|-------------|
| `LLM_PROVIDER` | `claude` | `claude`, `openai`, or `local_openai_compatible` |
| `ANTHROPIC_API_KEY` | — | Claude API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Claude model to use |
| `OPENAI_API_KEY` | — | OpenAI (or compatible) API key |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI-compatible model |
| `OPENAI_BASE_URL` | — | Base URL for local / compatible providers |

### Agent behavior

| Variable | Default | What it does |
|----------|---------|-------------|
| `MAX_ITERATIONS` | `5` | Max reflection loops before giving up |
| `SQL_TIMEOUT_SECONDS` | `30` | SQL query timeout |
| `SQL_MAX_ROWS` | `1000` | Max rows returned (safety limit) |

### Sandbox

SQL runs inside isolated containers with read-only mode, timeouts, and resource limits.

```dotenv
SANDBOX_ENABLED=true
SANDBOX_NETWORK=true
```

See `.env.example` for the full list.

---

## 🧪 Running Tests

```bash
cd backend && pytest tests/ -v
```

---

## ❓ FAQ

<details>
<summary><strong>Is this better than just asking ChatGPT to write SQL?</strong></summary>

Yes, for database work specifically. Here's why:

1. **Schema awareness** — ChatGPT doesn't know your table names, column types, or data distribution. AskSql profiles your schema and uses that context.
2. **Execution & reflection** — ChatGPT gives you SQL and you run it. AskSql runs it, looks at the result, and fixes it if it's wrong.
3. **Safety** — Read-only sandbox with timeouts and row limits. You can't accidentally `DROP TABLE`.
4. **Multi-turn context** — It remembers your database, your past questions, and your corrections.
5. **Visualization** — It doesn't just give you a table. It charts the data and explains what it means.
</details>

<details>
<summary><strong>Can it modify my data?</strong></summary>

No. By default, the SQL executor runs in read-only mode. Even if the LLM generates an `INSERT` or `DROP`, it won't execute.
</details>

<details>
<summary><strong>Does it work with my database?</strong></summary>

Probably. AskSql uses SQLAlchemy under the hood, which supports MySQL, PostgreSQL, SQLite, ClickHouse, MariaDB, Oracle, MSSQL, and more. If SQLAlchemy has a dialect for it, it works.
</details>

<details>
<summary><strong>Can I run this fully local?</strong></summary>

Yes. Use any OpenAI-compatible local model (Ollama, vLLM, LM Studio, etc.) with the `local_openai_compatible` provider. Your data never leaves your machine.
</details>

<details>
<summary><strong>How accurate is it?</strong></summary>

It depends on the model, your schema complexity, and the question. With Claude Sonnet+ on well-structured schemas, expect ~85-95% accuracy on first try, and higher with the reflection loop. The agent will tell you when it's unsure rather than making up numbers.
</details>

---

## 📄 License

MIT — use it, build on it, just don't be evil about it.

---

<div align="center">

Made with ❤️ for people who want answers, not SQL.

[⭐ Star on GitHub](https://github.com/yourusername/asksql) ·
[🐛 Report a bug](https://github.com/yourusername/asksql/issues) ·
[💬 Discuss](https://github.com/yourusername/asksql/discussions)

</div>
