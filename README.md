# Super Easy Customer Support

## Project Structure

- `app/api`: FastAPI route handlers
- `app/agents`: Main and review assistant logic
- `app/workflows`: LangGraph workflow orchestration
- `app/db`: SQLAlchemy setup and models
- `app/schemas`: Pydantic request/response schemas
- `app/integrations`: External connectors (SharePoint placeholder)
- `dashboard`: Streamlit internal dashboard

## Requirements

- Python 3.10+
- `pip`

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Run API

```bash
uvicorn app.main:app --reload
```

## Run Dashboard

```bash
streamlit run dashboard/app.py
```

## Run Local End-to-End Workflow Demo

```bash
python -m app.scripts.demo_workflow_run
```

## Minimal Verification Commands

```bash
python -m compileall app dashboard
python -m app.scripts.demo_workflow_run
```

The second command is a minimal end-to-end proof that the workflow executes from draft to review routing and returns final structured state.
