# Super Easy Customer Support

## Project Structure

- `app/api`: FastAPI route handlers
- `app/agents`: Main and review assistant logic
- `app/workflows`: LangGraph workflow orchestration
- `app/db`: SQLAlchemy setup and models
- `app/schemas`: Pydantic request/response schemas
- `app/integrations`: External connectors (SharePoint placeholder)
- `dashboard`: Streamlit internal dashboard

## Install

```bash
python -m venv .venv
source .venv/bin/activate
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
