<div align="right">

🌐 **English** · [简体中文](README.zh-CN.md)

</div>

# AskSql — Chat with your database. Seriously.

> 🧠 Natural language → SQL → results → charts. One agent, zero hassle.
> Stop pestering your data team. Become your own data team.

---

## 🤔 Why build this?

Let's be real — data work in most teams looks like this:

- **PM**: "Can you pull last week's new user retention? Oh, split by channel too." → you spend 30 minutes writing SQL
- **Ops**: "This number doesn't look right, did you mess up the query?" → you spend an hour debugging
- **CEO**: "Why did conversion drop?" → you spend 20 minutes figuring out what they're *actually* asking

SQL isn't the hard part. **The back-and-forth is.** It's always the same loop: understand the question → find the right tables → write SQL → run it → realize it's wrong → fix it → run it again…

**AskSql exists to break that loop. Ask a question in plain English. It thinks, writes SQL, runs it, checks the result, and gives you an answer.**

This isn't one of those "generate SQL and pray" tools. It actually **thinks things through**:
- Didn't understand your question? It'll ask for clarification.
- Not sure which table to use? It pokes around the data first.
- SQL returns garbage? It reflects and rewrites — on its own.
- Results look chart-able? Boom, you get a visualization.

## ✨ What can it do?

| Feature | What it actually means |
|---------|----------------------|
| 🧠 **Intent Analysis** | You say "what's selling well lately?" — it knows to hit the sales table, group by product, and sort. |
| 🔍 **Data Probing** | Unsure what a column means? It samples the data instead of guessing blindly. |
| ❓ **Smart Clarification** | Big ambiguity? It asks. Small ambiguity? It takes a guess *and tells you it guessed*. |
| 🛡️ **Sandboxed Execution** | SQL runs in an isolated container — read-only, timeouts, row limits. No "oops I dropped the table" disasters. |
| 🔄 **Self-Reflection** | Results look off? It debugs and rewrites itself. No "uhh, that doesn't seem right" from you required. |
| 📊 **Auto-Visualization** | Data looks chart-friendly? You get charts. No copy-pasting into Excel. |
| 💬 **Multi-Turn Chat** | "Split by region." "Exclude test data." — it remembers the context. |
| 🔌 **Multi-Datasource** | MySQL / PostgreSQL / SQLite / ClickHouse… if SQLAlchemy connects to it, AskSql chats with it. |
| 🤖 **Multi-LLM** | Claude / OpenAI / local models. Pick your favorite. |

## 🎯 Who's this for?

- **Product Managers** — skip the data queue. Ask, get answers, ship faster.
- **Ops & Growth** — "how's the campaign doing?" → answer in seconds, not hours.
- **Data Analysts** — offload the repetitive queries. Spend time on actual analysis.
- **Engineers** — debug with data without digging through old SQL snippets.
- **Small teams** — no dedicated data person? AskSql is your half-data-analyst-in-a-box.

## 🚀 Quick Start

Three steps, that's it.

### 1. Copy the env file

```bash
cp backend/.env.example .env
```

### 2. Pick an LLM and add your API key

Open `.env` and set **just two things** — provider + key. Everything else has sensible defaults.

**Using Claude (recommended):**
```dotenv
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxx
```

**Using OpenAI:**
```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxxxxxx
```

**Using a local model (Ollama / vLLM / etc.):**
```dotenv
LLM_PROVIDER=local_openai_compatible
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=qwen2.5:7b
```

### 3. Launch

```bash
docker compose up -d
```

Open http://localhost:5173 and start chatting with your data.

### Development Mode

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

## 🧱 Project Structure

```
AskSql/
├── backend/                # Python FastAPI backend
│   ├── nl2sql/            # ★ Core agent library (usable standalone)
│   │   ├── agent/         # LangGraph agent + nodes
│   │   ├── schema/        # Schema management
│   │   ├── llm/           # LLM abstraction layer
│   │   └── executor/      # SQL executor + sandbox
│   ├── app/               # FastAPI application layer
│   │   ├── api/           # API routes
│   │   ├── services/      # Business logic
│   │   └── core/          # Config + database
│   └── sandbox-image/     # Sandbox container image
│
├── frontend/              # React frontend
│   └── src/
│       ├── components/
│       ├── hooks/
│       └── pages/
│
├── docs/                   # Design docs
├── docker-compose.yml     # Docker Compose config
└── run.sh                 # One-click deploy script
```

## 🧠 How does the agent think?

```
You ask a question
    ↓
Intent analysis → what are we asking? which tables?
    ↓
Data probing → peek at actual data to validate understanding
    ↓
Clarification check → ambiguous? ask user or take a guess?
  ↙          ↘
Ask user     Generate SQL
 ↓              ↓
User answers  Sandbox executes SQL
 ↓              ↓
Generate SQL  Reflect: does the result make sense?
  ↘          ↙
    Summarize + visualize
         ↓
    You get an answer
```

In short: **think first → execute → verify → deliver.** Exactly how a good data analyst works.

## ⚙️ Advanced Configuration

All config lives in `.env` — that's the only file you need. The defaults work for most people, but here's what you can tweak:

### LLM options

| Variable | Default | What it does |
|----------|---------|-------------|
| `LLM_PROVIDER` | `claude` | `claude`, `openai`, or `local_openai_compatible` |
| `ANTHROPIC_API_KEY` | — | Your Claude API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Which Claude model to use |
| `OPENAI_API_KEY` | — | Your OpenAI (or compatible) API key |
| `OPENAI_MODEL` | `gpt-4o` | Which OpenAI-compatible model to use |
| `OPENAI_BASE_URL` | — | Base URL for local / compatible providers |

### Agent behavior

| Variable | Default | What it does |
|----------|---------|-------------|
| `MAX_ITERATIONS` | `5` | Max retry loops before giving up |
| `SQL_TIMEOUT_SECONDS` | `30` | SQL query timeout |
| `SQL_MAX_ROWS` | `1000` | Max rows returned (safety limit) |

### Sandbox

SQL runs inside isolated containers with read-only mode, timeouts, and resource limits. Toggle it on if you want to let the agent install database drivers on the fly:

```dotenv
SANDBOX_ENABLED=true
SANDBOX_NETWORK=true
```

See `.env.example` for the full list of sandbox options.

## 🧪 Running Tests

```bash
cd backend && pytest tests/ -v
```

## 📄 License

MIT — use it, build on it, just don't be evil about it.
