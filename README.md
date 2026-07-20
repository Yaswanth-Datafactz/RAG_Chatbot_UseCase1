# RAG Knowledge Chatbot

An internal "ask your company's policies" chatbot: employees ask natural-language questions about company procedures, benefits, and policies, and get accurate, **cited** answers drawn only from a self-assembled document corpus — never from the model's general knowledge. Out-of-corpus questions get an honest refusal instead of a hallucinated guess.

Built for the DataFactZ AI Engineering Internship (Use Case 1) against a fictional "Contoso Corp" policy set spanning PDF, DOCX, and Markdown.

## What it does

- **Grounded, cited chat.** Every answer streams back with clickable citation chips pointing to the exact source document, section, and page (where a real page number exists). Click a citation to see the underlying passage without leaving the conversation.
- **Honest refusal.** Questions outside the corpus (e.g. topics deliberately not covered, like RSU vesting or sabbatical leave) are refused rather than answered from the model's own training data, gated on a calibrated retrieval-confidence threshold.
- **Multi-turn conversations.** Follow-up questions are rewritten into standalone queries using recent conversation history before retrieval, so "what about part-time employees?" correctly resolves against the prior question's topic.
- **Multiple generation providers, chosen per message.** Claude, Azure OpenAI (GPT), and DeepSeek-V3.2 (via Azure AI Foundry) all sit behind one streaming interface; a model picker in the composer lets you pick per-message, with only actually-configured providers offered.
- **Conversation management.** Conversations auto-title themselves from your first question, support deletion, and offer sample questions to get started.
- **Admin view.** A documents table shows what's currently indexed (chunk counts, formats, sizes), plus a one-click re-index button that rebuilds the search index from the current corpus without any downtime — readers keep querying the old index until the new one is ready, then it swaps in atomically.
- **Markdown-rendered answers.** Assistant responses render as real formatted Markdown (lists, headings, tables) instead of raw `#`/`*`/`-` characters.

## Architecture

```
React (Vite + TypeScript, Tailwind)
   │  SSE (citations event → token stream → done)     REST /api/v1 (X-API-Key auth)
   ▼
FastAPI (layered: routers → services → repositories → DB)
   ├─ Chat service:   rewrite → embed → hybrid search + rerank → refusal gate → stream + persist
   ├─ Ingestion:      load → parse → chunk → embed → index (background job, atomic swap)
   ├─ Generation:     Claude | Azure OpenAI | DeepSeek-V3.2, one adapter interface
   ├─ Embedding:      Azure OpenAI text-embedding-3-large
   └─ Guardrails:     hardened system prompt, retrieved content structurally delimited
        │                                              │
        ▼                                              ▼
   PostgreSQL (SQLAlchemy + Alembic)              Azure AI Search
   documents / ingestion_runs / chunks /          hybrid (keyword + vector) search
   conversations / messages / citations           with semantic reranking
```

**Retrieval-quality-gated refusal, not a keyword blocklist.** Every question is embedded, searched hybrid (keyword + vector) against Azure AI Search, reranked semantically, then compared against a calibrated reranker-score threshold. Below the threshold, the system refuses instead of generating — measured and tuned against a real test set of in-corpus and deliberately-out-of-corpus questions (see `backend/eval/`).

**Content-addressed, zero-downtime re-indexing.** Documents are identified by content hash, so re-ingesting unchanged files reuses their existing rows. Each re-index run is atomic: the new index builds fully in the background, then a single flag flip makes it "current" — no reader ever sees a half-built index, and the previous run's data is cleaned up only after the swap succeeds.

## Tech stack

**Backend** — Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.x + Alembic, PostgreSQL, `httpx`/async I/O throughout, `pypdf` + `python-docx` + Markdown parsing for corpus ingestion, `structlog` for structured logging, `pytest` for tests.

**Frontend** — React 19, TypeScript, Vite, Tailwind CSS v4, React Router v7, `react-markdown` + `remark-gfm` for rendered assistant output, Lucide icons.

**External services** — Azure AI Search (hybrid + semantic reranking), Azure OpenAI (embeddings + optionally generation), Anthropic Claude, Azure AI Foundry (DeepSeek-V3.2 model-inference endpoint).

## Repository layout

```
backend/
  app/
    api/v1/        # routers: chat, conversations, documents, ingestion, models, health
    services/      # chat orchestration, retrieval, rewrite, ingestion, chunking, parsing,
                    # embedding, generation adapters (claude / azure_openai / deepseek)
    search/         # Azure AI Search client (index, hybrid search, atomic run cleanup)
    db/             # SQLAlchemy models, session
    schemas/        # Pydantic request/response models
    core/           # config (env-driven settings), logging, security (API-key auth), errors
  alembic/          # DB migrations
  tests/            # pytest suite
  eval/             # versioned test-question set + retrieval-quality results
  scripts/          # standalone live-measurement scripts (not pytest)
corpus/
  generate_corpus.py  # single source of truth for the fictional Contoso Corp corpus
  manifest.json       # derived from generate_corpus.py; never hand-edited
  *.pdf / *.docx / *.md
frontend/
  src/
    components/{chat,admin,layout,ui}/
    pages/          # Chat, Admin
    lib/{api,sse}/  # typed API client, SSE stream parser
    theme/          # brand tokens (Tailwind v4 @theme)
docs/               # internal planning/decision docs (not part of the pushed repo)
docker-compose.yml  # local Postgres for development
```

## Getting started

### Prerequisites
- Python 3.11+
- Node 20+
- Docker (for local Postgres)
- Azure AI Search, Azure OpenAI, and (optionally) Anthropic / Azure AI Foundry credentials

### 1. Database
```bash
docker compose up -d
```

### 2. Backend
```bash
cd backend
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in your real Azure/Anthropic credentials
./.venv/bin/alembic upgrade head
./.venv/bin/uvicorn app.main:app --port 8000
```

### 3. Corpus + search index
```bash
cd corpus
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python generate_corpus.py    # writes the corpus files + manifest.json
```
Then trigger indexing via the API (see below) or the Admin UI's re-index button.

### 4. Frontend
```bash
cd frontend
npm install
cp .env.example .env   # point VITE_API_BASE_URL at your backend
npm run dev
```

Open the printed local URL (default `http://localhost:5173`).

## Configuration

All backend configuration is environment-driven — see `backend/.env.example` for the full list, including:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string |
| `API_KEY` | Shared secret required on every `/api/v1` request (`X-API-Key` header) |
| `AZURE_SEARCH_*` | Azure AI Search endpoint, key, index name |
| `AZURE_OPENAI_*` | Azure OpenAI endpoint, key, embedding deployment |
| `AZURE_AI_FOUNDRY_*` | Azure AI Foundry endpoint/key/model (DeepSeek-V3.2) |
| `ANTHROPIC_API_KEY` | Claude, if used as a generation provider |
| `GENERATION_PROVIDER` | Default generation provider (`claude` \| `azure_openai` \| `deepseek`); overridable per message |
| `RETRIEVAL_CANDIDATE_COUNT` / `RETRIEVAL_TOP_K` | Hybrid search candidate pool size and final context size |
| `REFUSAL_RERANKER_THRESHOLD` | Calibrated cutoff below which the system refuses instead of answering |

**Never commit a real `.env` file or API key** — `.gitignore` excludes `.env` everywhere; only the `.env.example` templates (placeholders only) are tracked.

## API overview

All routes are under `/api/v1` and require an `X-API-Key` header (except `/health`). Full interactive docs are available at `/docs` once the backend is running.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check, no auth |
| `POST` | `/conversations` | Start a new conversation |
| `GET` | `/conversations` | List conversations |
| `GET` | `/conversations/{id}` | Get a conversation with full message/citation history |
| `DELETE` | `/conversations/{id}` | Delete a conversation (cascades messages/citations) |
| `POST` | `/conversations/{id}/messages` | Ask a question — streams back via Server-Sent Events (`citations` → `token`* → `done`) |
| `GET` | `/documents` | List indexed documents with chunk counts |
| `POST` | `/ingestion-runs` | Trigger a re-index (runs in the background) |
| `GET` | `/ingestion-runs/{id}` | Poll a re-index run's status |
| `GET` | `/models` | List generation providers with real availability/default flags |

## Testing

```bash
cd backend
./.venv/bin/pytest --ignore=tests/test_ingestion.py
```

**Important:** `tests/test_ingestion.py` exercises the real atomic-swap-and-cleanup logic against whichever database it's pointed at. Running it against a database that also holds a real, currently-indexed corpus will replace that live index with the test's tiny fixture corpus. If you need to run it, re-trigger `POST /ingestion-runs` afterward to restore your real index.

```bash
cd frontend
npm run build   # tsc -b && vite build
npm run lint
```

## Evaluation

`backend/eval/questions.json` is a versioned set of in-corpus and deliberately-out-of-corpus test questions. `backend/scripts/run_retrieval_eval.py` runs them against the live retrieval pipeline (real Azure OpenAI embeddings, real Azure AI Search) and reports rank, score, and refusal-gate behavior for each — the basis for the calibrated `REFUSAL_RERANKER_THRESHOLD`.

## Security notes

- API-key auth on every route (see `core/security.py`)
- Structurally delimited prompts: retrieved document content is fenced off from instructions in the system prompt, so text embedded in a policy document can't be interpreted as a command
- No secrets in source control — all credentials are environment variables, `.env` is gitignored everywhere
