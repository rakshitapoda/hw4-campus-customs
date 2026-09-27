# Campus Customs — Homework 4

A Campus Customs storefront (React + Vite + TypeScript) with a FastAPI backend and a PydanticAI
shopping assistant. The assistant answers price, stock and size questions from the real
`campus_customs.db` data, turns catalogue searches into product cards on the website, remembers
logged-in shoppers, and records every agent run in an append-only audit trail.

## Project layout

```
hw4/
├── AI_prompts.md            Prompt log for every problem
├── requirements.txt         Backend Python dependencies
├── .env.example             Environment variables (placeholders only)
├── .gitignore               Excludes .env, the data pack, .venv, node_modules, build output
├── README.md
├── frontend/                Vite + React + TypeScript app
│   ├── vite.config.ts       Dev server on :5173; proxies /api and /media to the backend on :8000
│   └── src/
│       ├── api/client.ts    All HTTP calls to the backend
│       ├── components/      ChatWidget, ProductCard, Navbar, Footer, error/offline states
│       ├── lib/             Auth context, chat-search state, filters, formatting
│       ├── pages/           Home, Products, ProductDetail, About, Login, CreateAccount, NotFound
│       └── types.ts         Mirrors the backend response models
├── backend/                 FastAPI app — run with: uvicorn main:app --reload --port 8000
│   ├── main.py              API: products, images, /api/chat, chat history, health
│   ├── agent.py             PydanticAI agent: prompt, Portkey model, 4 tools, usage limits, audit entry
│   ├── models.py            Pydantic models: products, tool results, AgentReply, chat request/response
│   ├── tools.py             Read-only catalogue tools, product cards, append-only audit writer
│   ├── memory.py            Saved chat history, customer context, page context
│   ├── auth.py              Sign-up / login / current-user routes
│   ├── security.py          Password hashing, session tokens, loads .env
│   ├── db.py                SQLite connections (read-only unless a write is needed)
│   ├── errors.py            Safe error responses, request ids, body-size limit, rate limiter
│   └── prompts/
│       └── prompt.md        System prompt, including the Safety rules
└── output/
    ├── harness.md           Full system documentation (overview, models, tools, memory, safety, specs, audit, run)
    ├── design.md            Visual design changes (Problem 10)
    ├── usability.md         Usability improvements (Problem 9)
    ├── app_check.html       Live-site test report (Problem 11); open directly in a browser
    ├── app_check_images/    Screenshots linked from app_check.html
    └── audit_trail.json     Append-only log of every agent run
```

The files in the assignment's layout are all present. `memory.py`, `auth.py`, `security.py`,
`db.py` and `errors.py` are extra backend modules that `main.py` and `agent.py` import (login,
saved chat history, safe errors), so they are required to run the app.

## 1. Add the local data pack (not in git)

The database and product photos are **not** committed. Put the provided data pack in `hw4/data/`:

```
hw4/
└── data/
    ├── campus_customs.db
    └── products/            the product images referenced by the catalogue (e.g. basic-hoodie-big-yale.jpg)
```

The backend finds it automatically at `hw4/data/` (the path is resolved from `backend/db.py`). To use
a database somewhere else, set `CAMPUS_CUSTOMS_DB=/path/to/campus_customs.db`.

## 2. Configure environment variables

```bash
cd hw4
cp .env.example .env
```

Edit `.env`:

| Variable | Needed for | Notes |
|----------|------------|-------|
| `PORTKEY_API_KEY` | the chatbot | Or set `OPENAI_API_KEY` instead to call OpenAI directly |
| `PORTKEY_BASE_URL` | the chatbot | Default `https://api.portkey.ai/v1` |
| `OPENAI_MODEL` | the chatbot | Default `gpt-4o-mini` |
| `AUTH_SECRET_KEY` | login sessions | Any long random string, e.g. `python3 -c "import secrets; print(secrets.token_hex(32))"`. Without it, a random key is used and sessions end when the server restarts. |

Variables already set in your shell take precedence over `.env`. Never commit the real `.env`.

## 3. Run the backend (port 8000)

Requires Python 3.13. The server must be started **from `backend/`**, because the modules import
each other by name.

```bash
cd hw4
python3.13 -m venv .venv                     # first time only
.venv/bin/pip install -r requirements.txt    # first time only
cd backend
../.venv/bin/uvicorn main:app --reload --port 8000
```

Check it at http://localhost:8000/api/health (API docs: http://localhost:8000/docs). Products and
login work without a model key; the chat returns a friendly "offline" message until one is set.

## 4. Run the frontend (port 5173)

In a second terminal:

```bash
cd hw4/frontend
npm install        # first time only
npm run dev
```

Open **http://localhost:5173**. Both servers must be running, because Vite forwards `/api` and `/media`
to the backend. Production build and lint checks: `npm run build` and `npm run lint`.

## Test account

The provided data pack includes a test shopper: `test@campuscustoms.yale.edu` / `password`. You can
also create an account on the Create Account page.

## Documentation

- `output/harness.md`: how the system works (flow, models, tools, customer memory, page context,
  safety rules, agent limits, audit trail, run commands).
- `output/app_check.html`: screenshots and results of the live-site tests.
- `output/audit_trail.json`: every agent run, with tool calls, short arguments, result summaries
  and stop reasons.
