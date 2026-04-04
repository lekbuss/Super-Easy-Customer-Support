# Super Easy Customer Support

## Project Structure

- `app/api`: FastAPI route handlers
- `app/agents`: Main and review assistant logic
- `app/workflows`: LangGraph workflow orchestration
- `app/db`: SQLAlchemy setup and models
- `app/schemas`: Pydantic request/response schemas
- `app/integrations`: External connectors (SharePoint placeholder)
- `app/services`: Persistence and workflow application services
- `dashboard`: Streamlit internal dashboard

## Requirements

- Python 3.12+ (recommended)
- `pip`
- Docker + Docker Compose (for deployment-like local run)

## Install

Run from project root (`C:\Users\Administrator\Desktop\11`):

### Windows (PowerShell)

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

### macOS/Linux

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Run API

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Run Dashboard

```bash
python -m streamlit run dashboard/main.py --server.address=0.0.0.0 --server.port=8501
```

## Ticket API (Optional Quick Checks)

Create a ticket:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/tickets" ^
  -H "Content-Type: application/json" ^
  -d "{\"external_id\":\"api-1001\",\"customer_email\":\"customer@example.com\",\"subject\":\"Indexing issue\",\"body\":\"Cannot find latest docs\",\"source\":\"api\"}"
```

List tickets:

```bash
curl "http://127.0.0.1:8000/api/v1/tickets?limit=20"
```

Run workflow for a ticket:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/workflow/run" ^
  -H "Content-Type: application/json" ^
  -d "{\"ticket_id\":1}"
```

Get business drafts derived from workflow outcome:

```bash
curl "http://127.0.0.1:8000/api/v1/workflow/1/drafts"
```

## Deployment-Like Local Run (Docker Compose)

```bash
docker compose up --build
```

Services:
- API: `http://localhost:8000/api/v1/health`
- Dashboard: `http://localhost:8501`

This mode runs two separate services (`api` and `dashboard`) sharing one persistent Docker volume-backed SQLite database.

## Cloud Deployment Preparation

### Required Environment Variables

- `DATABASE_URL`
  - Local/simple: `sqlite:////data/support_workflow.db`
  - PostgreSQL: `postgresql+psycopg://<user>:<password>@<host>:5432/<db>`
- `APP_ENV` (for example: `cloud`)

### Optional Environment Variables

- `APP_NAME` (default: `Support Workflow Platform`)
- `MAX_REVIEW_ITERATIONS` (default: `2`)
- `API_HOST` (default: `0.0.0.0`)
- `API_PORT` (default: `8000`)
- `DASHBOARD_HOST` (default: `0.0.0.0`)
- `DASHBOARD_PORT` (default: `8501`)

### PostgreSQL Switch

No code changes are required. Set `DATABASE_URL` to a PostgreSQL URL (the app normalizes `postgres://` and `postgresql://` to `postgresql+psycopg://`).

## Manual Demo Script

```bash
python -m app.scripts.demo_persisted_run
```

## Minimal Verification Commands

```bash
python -m compileall app dashboard
python -m app.scripts.demo_persisted_run
```

The second command runs a full workflow, saves ticket/workflow/steps in SQLite, and performs a human-approval write when applicable.

## Dashboard Testing Steps

1. Run `python -m streamlit run dashboard/main.py`
2. Create a new ticket in the "Create Ticket" section
3. Select that ticket in "Recent Tickets"
4. Click "Run Workflow For Selected Ticket"
5. Confirm workflow run appears under "Selected Ticket Workflow History"
6. If status is `needs_human_approval`, click "Human Approve"
7. Refresh the page and confirm status/history/approval actions remain visible

## Intentionally Not Deployed Yet

- Automatic SharePoint ingestion
- Automatic customer email sending
- Fully autonomous trigger/decision/sending loops

Current deployment target is an internal, manually triggered workflow dashboard + API.
