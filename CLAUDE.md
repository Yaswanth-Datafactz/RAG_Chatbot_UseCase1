# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Scaffolding is in progress per the approved build plan. **Read [docs/plan.md](docs/plan.md) first** — it is the source of truth for architecture, the phase-by-phase build order, and the full decisions register (chunking, retrieval depth, refusal threshold, embedding/generation model choice, history window, background-job approach) with rejected alternatives for each. Do not re-derive decisions already recorded there; update it if a decision changes.

Run/build/test/lint commands: not yet established — fill this section in once `backend/` and `frontend/` exist, and keep it current as the scaffold lands. Don't leave it stale.

## What this project is

An internal "RAG Knowledge Chatbot" (DataFactZ AI Engineering Internship, Use Case 1): employees ask natural-language questions about company policies/benefits/procedures and get accurate, **cited** answers drawn only from a self-assembled corpus (15–30 docs spanning PDF, DOCX, and HTML/Markdown — a fictional "Contoso Corp" policy set) — never from the model's general knowledge. Functional requirements, technical constraints, and design decisions to defend are all detailed in [docs/plan.md](docs/plan.md).

## Hard rules that always apply (Handbook §6.2 / §7 — scored, non-negotiable)

- **API**: resource-oriented REST under `/api/v1`, correct HTTP methods/status codes, Pydantic request/response models on every endpoint, accurate OpenAPI docs, at least API-key auth. Never return HTTP 200 with an error in the body.
- **Database**: real relational schema, normalized and indexed, managed with Alembic migrations. ERD lives in the design doc.
- **Code structure**: layered backend (routers → services → data access), typed Python, config via environment variables, structured logging, centralized error handling, unit tests on core business logic — not boilerplate.
- **Scalability**: stateless API processes, async I/O for all LLM/network calls, background jobs for long-running work, explicit caching reasoning.
- **Frontend**: componentized React with a shared layout shell (reused across all three internship use cases), loading/error states on every async call, zero console errors in the demo build.
- **Brand** (Handbook §7): gradient `#F4AD0B → #FC7900 → #E3434A`; primary orange `#FC7900`; navy `#182127` chrome; Inter typeface; **Lucide icons only** (no Font Awesome/Material/emoji); rounded-xl cards (12px) / rounded-md buttons (6px) / rounded-full pills, cards lift on hover (`translateY(-5px)` + shadow); dark mode default. Voice: confident, plainspoken, enterprise, no exclamation marks, "your teams" not "users."
- **Secrets**: API keys (Claude/Anthropic, OpenAI, DeepSeek, Azure) go in environment variables or `.env` files — never commit a key; a committed key is an automatic deduction.
- **Azure**: shared Resource Group only, tag every resource `owner=<yourname>`, stop/delete expensive resources when idle.
