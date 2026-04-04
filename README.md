# DocuWare Support Workflow Platform

> AI-powered technical support automation for DocuWare partner teams — from first-draft generation to human approval, in one streamlined workflow.

> DocuWareパートナー向けAI技術サポート自動化プラットフォーム — 初回ドラフト生成から人間承認まで、一貫したワークフローで。

---

## Overview / 概要

**EN** — The **DocuWare Support Workflow Platform** accelerates customer inquiry resolution by combining retrieval-augmented generation (RAG), autonomous agent review, and a structured human-approval gate. Support engineers receive a reviewed, ready-to-send reply draft within seconds, while retaining full control over every outbound communication.

**JA** — **DocuWare Support Workflow Platform** は、RAG（検索拡張生成）・自律エージェントレビュー・人間承認ゲートを組み合わせ、顧客問い合わせへの対応を大幅に加速します。サポートエンジニアはレビュー済みの返信ドラフトを数秒で受け取り、すべての送信内容に対して完全なコントロールを維持できます。

### How it works / 処理フロー

```
Incoming Inquiry / 問い合わせ受信
      │
      ▼
┌─────────────────────────────┐
│  Draft Agent  / 回答担当    │  RAG (ChromaDB) → Web Search → LLM-only
│                             │  Generates a customer-facing reply draft
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  Uchiyama Review Agent      │  approve / revise / escalate
│  内山さん                    │  Few-shot examples from historical memory
└────────────┬────────────────┘
             │ revise → loop (up to N iterations)
             ▼
┌─────────────────────────────┐
│  Human Intervention Panel   │  ✅ Approve  📧 DocuWare inquiry email  ❌ Reject & re-draft
│  担当者アクション             │
└─────────────────────────────┘
```

---

## Key Features / 主な機能

| Feature | 機能 | Description / 説明 |
|---|---|---|
| **RAG-first drafting** | RAG優先起草 | ChromaDB indexes DocuWare KB articles; cosine similarity threshold filters low-quality hits |
| **Web search fallback** | Web検索フォールバック | Anthropic built-in `web_search` supplements RAG when local knowledge is insufficient |
| **Uchiyama Review Agent** | 内山レビューAgent | Persona-based LLM reviewer with few-shot examples; hard escalation for legal/security keywords |
| **Chat-style dashboard** | チャット形式UI | Full draft↔review conversation rendered as color-coded chat bubbles |
| **Human intervention** | 人間介入パネル | One-click approve, AI-generated DocuWare inquiry email, reject-and-redraft with reason propagation |
| **Fallback resilience** | フォールバック耐性 | 30 s timeout, 3-attempt retry with exponential backoff, template fallback on all LLM paths |
| **Token usage logging** | トークンログ | Input/output token counts logged at INFO level for cost visibility |
| **CI/CD** | CI/CD | GitHub Actions → SSH deploy to Azure VM on every merge to `main` |

---

## Tech Stack / 技術スタック

| Layer / レイヤー | Technology / 技術 |
|---|---|
| API | FastAPI + Uvicorn |
| Dashboard / ダッシュボード | Streamlit |
| LLM | Anthropic Claude (claude-sonnet-4-6) |
| Vector Store / ベクトルDB | ChromaDB (persistent local collection) |
| Embeddings | Anthropic Embeddings API |
| Workflow / ワークフロー | LangGraph (local loop fallback) |
| Database / データベース | SQLite (dev) / PostgreSQL-compatible via SQLAlchemy |
| Deployment / デプロイ | systemd + GitHub Actions |

---

## Project Structure / プロジェクト構成

```
.
├── app/
│   ├── agents/
│   │   ├── main_agent.py        # Draft generation: RAG → web search → LLM-only
│   │   ├── review_agent.py      # Uchiyama review agent with rule-based fallback
│   │   └── uchiyama_profile.py  # Few-shot review examples and persona
│   ├── api/v1/endpoints/
│   │   ├── workflow.py          # run / approve / reject / generate-inquiry-email
│   │   ├── ticket.py            # Ticket CRUD
│   │   ├── rag.py               # RAG stats
│   │   └── health.py
│   ├── db/                      # SQLAlchemy models and session
│   ├── llm/
│   │   ├── client.py            # AnthropicClient: retry, timeout, token logging
│   │   └── prompts.py           # System prompts for draft and review agents
│   ├── rag/
│   │   ├── vectorstore.py       # ChromaDB wrapper
│   │   ├── indexer.py           # KB article ingestion
│   │   └── admin.py             # Collection stats and clear helpers
│   ├── services/                # Workflow orchestration and persistence
│   ├── schemas/                 # Pydantic request/response models
│   └── workflows/
│       └── support_workflow.py  # LangGraph state machine
├── dashboard/
│   ├── main.py                  # Streamlit UI (chat view + human action panel)
│   └── uchiyama_avatar.jpg      # Reviewer avatar photo
├── deploy/
│   ├── fastapi.service          # systemd unit — FastAPI
│   ├── streamlit.service        # systemd unit — Streamlit
│   └── deploy.sh                # Pull → install → restart script
├── .github/workflows/
│   └── deploy.yml               # GitHub Actions: SSH deploy on push to main
├── docker-compose.yml
└── requirements.txt
```

---

## Quick Start / クイックスタート

### Prerequisites / 前提条件

- Python 3.12+
- [Anthropic API key](https://console.anthropic.com/)

### Setup / セットアップ

```bash
git clone https://github.com/lekbuss/Super-Easy-Customer-Support.git
cd Super-Easy-Customer-Support

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### Environment variables / 環境変数

Create / 作成: `.env`

```env
ANTHROPIC_API_KEY=sk-ant-...

# Optional / 任意
APP_NAME=DocuWare Support Workflow
MAX_REVIEW_ITERATIONS=2
CHROMA_PERSIST_DIR=./chroma_data
DATABASE_URL=sqlite:///./support_workflow.db
```

### Run / 起動

```bash
# API  (port 8000)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Dashboard / ダッシュボード  (port 8501) — separate terminal / 別ターミナル
streamlit run dashboard/main.py --server.address 0.0.0.0 --server.port 8501
```

Open / アクセス: `http://localhost:8501`

---

## Docker Compose

```bash
docker compose up --build
```

| Service / サービス | URL |
|---|---|
| API | `http://localhost:8000/api/v1/health` |
| Dashboard | `http://localhost:8501` |

---

## API Reference / APIリファレンス

### Core workflow / コアワークフロー

| Method | Path | Description / 説明 |
|---|---|---|
| `POST` | `/api/v1/workflow/run` | Run the full draft→review workflow / ワークフロー実行 |
| `POST` | `/api/v1/workflow/{id}/approve` | Human approval / 人間承認 |
| `POST` | `/api/v1/workflow/{id}/reject` | Reject with reason; triggers fresh run / 差し戻し・再起草 |
| `POST` | `/api/v1/workflow/{id}/generate-inquiry-email` | Generate English inquiry email to DocuWare / 英文問い合わせメール生成 |
| `GET` | `/api/v1/workflow/{id}/outcome` | Full run outcome / 実行結果取得 |

### Tickets / チケット

| Method | Path | Description / 説明 |
|---|---|---|
| `POST` | `/api/v1/tickets` | Create ticket / チケット作成 |
| `GET` | `/api/v1/tickets` | List tickets / 一覧取得 |
| `GET` | `/api/v1/tickets/{id}` | Get by ID |

### RAG admin

| Method | Path | Description / 説明 |
|---|---|---|
| `GET` | `/api/v1/rag/stats` | ChromaDB stats / コレクション情報 |

Interactive docs / インタラクティブドキュメント: `http://localhost:8000/docs`

---

## Deployment / デプロイ (Azure VM)

### First-time setup / 初回セットアップ

```bash
# Clone and create venv / クローンとvenv作成
git clone https://github.com/lekbuss/Super-Easy-Customer-Support.git /home/azureuser/Super-Easy-Customer-Support
cd /home/azureuser/Super-Easy-Customer-Support
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Place environment variables / 環境変数を配置
# Edit /home/azureuser/.env

# Register systemd services / systemdサービス登録
sudo cp deploy/fastapi.service /etc/systemd/system/
sudo cp deploy/streamlit.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fastapi streamlit
```

### Continuous deployment / 継続的デプロイ (GitHub Actions)

Every push to `main` → `.github/workflows/deploy.yml` → SSH → `deploy/deploy.sh`:

1. `git fetch && git reset --hard origin/main`
2. `pip install -r requirements.txt`
3. Restart both services via `pkill` + `nohup`

**Required GitHub Secrets / 必要なSecrets:**

| Secret | Value / 値 |
|---|---|
| `AZURE_VM_HOST` | VM public IP / パブリックIPアドレス |
| `AZURE_VM_USER` | `azureuser` |
| `AZURE_VM_SSH_KEY` | SSH private key contents / SSH秘密鍵の中身 |

---

## Configuration Reference / 設定リファレンス

| Variable / 変数 | Default / デフォルト | Description / 説明 |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required / 必須** |
| `DATABASE_URL` | `sqlite:///./support_workflow.db` | SQLAlchemy DB URL |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | ChromaDB persistence directory |
| `LLM_MODEL` | `claude-sonnet-4-6` | Anthropic model ID |
| `LLM_MAX_TOKENS` | `4096` | Max tokens per response |
| `LLM_TEMPERATURE` | `0.3` | Sampling temperature |
| `RAG_TOP_K` | `5` | KB chunks retrieved per query |
| `MAX_REVIEW_ITERATIONS` | `2` | Max draft→review cycles before escalation |
| `APP_NAME` | `Support Workflow Platform` | Application display name |

---

## Roadmap / 今後の予定

- [ ] SharePoint KB auto-ingestion (scheduled indexer) / SharePoint KB自動インデックス
- [ ] Automatic customer email dispatch / 顧客メール自動送信統合
- [ ] Multi-tenant ticket source support (Zendesk, ServiceNow)
- [ ] Analytics dashboard — resolution time, escalation rate, LLM cost per ticket / 分析ダッシュボード
- [ ] PostgreSQL migration for production scale / 本番向けPostgreSQL移行

---

## License / ライセンス

Proprietary. All rights reserved. / 独自ライセンス。無断複製・転用禁止。
