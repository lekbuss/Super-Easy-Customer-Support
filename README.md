# DocuWare Support Workflow Platform

> AI-powered technical support automation for DocuWare partner teams — from first-draft generation to human approval, in one streamlined workflow.

---

## Overview

The **DocuWare Support Workflow Platform** accelerates customer inquiry resolution by combining retrieval-augmented generation (RAG), autonomous agent review, and a structured human-approval gate. Support engineers receive a reviewed, ready-to-send reply draft within seconds, while retaining full control over every outbound communication.

### How it works

```
Incoming Inquiry
      │
      ▼
┌─────────────────────────────┐
│  Draft Agent                │  RAG (ChromaDB) → Web Search → LLM-only
│  (回答担当)                  │  Generates a customer-facing reply draft
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  Uchiyama Review Agent      │  Structured JSON decision: approve / revise / escalate
│  (内山さん)                  │  Few-shot examples from historical review memory
└────────────┬────────────────┘
             │ revise (up to N iterations)
             ▼
┌─────────────────────────────┐
│  Human Intervention Panel   │  ✅ Approve  📧 Generate DocuWare inquiry  ❌ Reject & re-draft
│  (担当者アクション)           │
└─────────────────────────────┘
```

---

## Key Features

| Feature | Description |
|---|---|
| **RAG-first drafting** | ChromaDB vector store indexes DocuWare official KB articles; cosine similarity threshold filters low-quality hits |
| **Web search fallback** | Anthropic's built-in `web_search` tool supplements RAG when local knowledge is insufficient |
| **Uchiyama Review Agent** | Persona-based LLM reviewer with few-shot examples, hard escalation for legal/security keywords |
| **Chat-style dashboard** | Conversation UI renders the full draft↔review exchange; color-coded bubbles per agent |
| **Human intervention** | One-click approve, AI-generated DocuWare support email, reject-and-redraft with reason propagation |
| **Fallback resilience** | Every LLM call has a 30 s timeout, 3-attempt retry with exponential backoff, and a template fallback |
| **Token usage logging** | Input/output token counts logged at INFO level for cost visibility |
| **CI/CD** | GitHub Actions pushes to Azure VM via SSH on every merge to `main` |

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Dashboard | Streamlit |
| LLM | Anthropic Claude (claude-sonnet-4-x) |
| Vector Store | ChromaDB (persistent local collection) |
| Embeddings | Anthropic Embeddings API |
| Workflow orchestration | LangGraph (falls back to local loop if unavailable) |
| Database | SQLite (dev) / PostgreSQL-compatible via SQLAlchemy |
| Deployment | systemd + GitHub Actions |

---

## Project Structure

```
.
├── app/
│   ├── agents/
│   │   ├── main_agent.py        # Draft generation (RAG → web search → LLM-only)
│   │   ├── review_agent.py      # Uchiyama review agent with rule-based fallback
│   │   └── uchiyama_profile.py  # Few-shot review examples and persona
│   ├── api/v1/
│   │   └── endpoints/
│   │       ├── workflow.py      # Workflow run, approve, reject, email generation
│   │       ├── ticket.py        # Ticket CRUD
│   │       ├── rag.py           # RAG stats endpoint
│   │       └── health.py
│   ├── db/                      # SQLAlchemy models and session
│   ├── llm/
│   │   ├── client.py            # AnthropicClient with retry, timeout, token logging
│   │   └── prompts.py           # System prompts for draft and review agents
│   ├── rag/
│   │   ├── vectorstore.py       # ChromaDB wrapper
│   │   ├── indexer.py           # KB article ingestion
│   │   └── admin.py             # Collection stats and clear helpers
│   ├── services/                # Workflow orchestration and persistence services
│   ├── schemas/                 # Pydantic request/response models
│   └── workflows/
│       └── support_workflow.py  # LangGraph state machine
├── dashboard/
│   └── main.py                  # Streamlit UI (chat view + human action panel)
├── deploy/
│   ├── fastapi.service          # systemd unit for FastAPI
│   ├── streamlit.service        # systemd unit for Streamlit
│   └── deploy.sh                # Pull → install → restart script
├── .github/workflows/
│   └── deploy.yml               # GitHub Actions: SSH deploy on push to main
├── docker-compose.yml
└── requirements.txt
```

---

## Quick Start (Local)

### Prerequisites

- Python 3.12+
- An [Anthropic API key](https://console.anthropic.com/)

### Setup

```bash
git clone https://github.com/lekbuss/Super-Easy-Customer-Support.git
cd Super-Easy-Customer-Support

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### Environment variables

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-...

# Optional overrides
APP_NAME=DocuWare Support Workflow
MAX_REVIEW_ITERATIONS=2
CHROMA_PERSIST_DIR=./chroma_data
DATABASE_URL=sqlite:///./support_workflow.db
```

### Run

```bash
# API (port 8000)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Dashboard (port 8501) — separate terminal
streamlit run dashboard/main.py --server.address 0.0.0.0 --server.port 8501
```

Open `http://localhost:8501` to access the dashboard.

---

## Docker Compose

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| API | `http://localhost:8000/api/v1/health` |
| Dashboard | `http://localhost:8501` |

---

## API Reference

### Core workflow

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/workflow/run` | Run the full draft→review workflow for a ticket |
| `POST` | `/api/v1/workflow/{id}/approve` | Human approval — marks run as approved |
| `POST` | `/api/v1/workflow/{id}/reject` | Reject with reason; triggers a fresh draft run |
| `POST` | `/api/v1/workflow/{id}/generate-inquiry-email` | Generate a professional English email to DocuWare support |
| `GET` | `/api/v1/workflow/{id}/drafts` | Retrieve customer reply, vendor memo, and internal summary |
| `GET` | `/api/v1/workflow/{id}/outcome` | Full run outcome with steps and approvals |

### Tickets

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/tickets` | Create a new support ticket |
| `GET` | `/api/v1/tickets` | List tickets |
| `GET` | `/api/v1/tickets/{id}` | Get ticket by ID |

### RAG admin

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/rag/stats` | ChromaDB collection size and status |

Interactive docs available at `http://localhost:8000/docs`.

---

## Deployment (Azure VM)

### First-time setup on the VM

```bash
# 1. Clone and create venv
git clone https://github.com/lekbuss/Super-Easy-Customer-Support.git /home/azureuser/Super-Easy-Customer-Support
cd /home/azureuser/Super-Easy-Customer-Support
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Place environment variables
#    Edit /home/azureuser/.env with ANTHROPIC_API_KEY etc.

# 3. Register systemd services
sudo cp deploy/fastapi.service /etc/systemd/system/
sudo cp deploy/streamlit.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fastapi streamlit
```

### Continuous deployment (GitHub Actions)

Every push to `main` triggers `.github/workflows/deploy.yml`, which SSH-es into the VM and runs `deploy/deploy.sh`:

1. `git fetch && git reset --hard origin/main`
2. `pip install -r requirements.txt`
3. Restart both services via `pkill` + `nohup`

**Required GitHub Secrets:**

| Secret | Value |
|---|---|
| `AZURE_VM_HOST` | VM public IP address |
| `AZURE_VM_USER` | `azureuser` |
| `AZURE_VM_SSH_KEY` | Contents of the SSH private key |

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** Anthropic API key |
| `DATABASE_URL` | `sqlite:///./support_workflow.db` | SQLAlchemy database URL |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | ChromaDB persistence directory |
| `LLM_MODEL` | `claude-sonnet-4-6` | Anthropic model ID |
| `LLM_MAX_TOKENS` | `4096` | Max tokens per LLM response |
| `LLM_TEMPERATURE` | `0.3` | Sampling temperature |
| `RAG_TOP_K` | `5` | Number of KB chunks retrieved per query |
| `MAX_REVIEW_ITERATIONS` | `2` | Max draft→review cycles before escalation |
| `APP_NAME` | `Support Workflow Platform` | Application display name |

---

## Roadmap

- [ ] SharePoint KB auto-ingestion (scheduled indexer)
- [ ] Automatic customer email dispatch integration
- [ ] Multi-tenant ticket source support (Zendesk, ServiceNow)
- [ ] Analytics dashboard — resolution time, escalation rate, LLM cost per ticket
- [ ] PostgreSQL migration for production scale

---

## License

Proprietary. All rights reserved.
