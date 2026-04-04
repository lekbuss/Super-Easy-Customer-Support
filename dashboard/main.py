from __future__ import annotations

from datetime import datetime
from pathlib import Path
import html
import sys
import time

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

from app.db.base import Base
from app.db.session import SessionLocal, engine, ensure_sqlite_schema
from app.services.draft_service import build_workflow_drafts
from app.services.ticket_service import create_ticket, get_ticket_by_id, list_tickets
from app.services.workflow_service import (
    approve_workflow_run,
    get_approval_actions,
    get_iteration_history,
    get_workflow_run,
    list_workflow_runs_for_ticket,
    run_and_persist_workflow_for_ticket,
)


st.set_page_config(page_title="超絶カンタン問い合わせ対応", layout="wide")


STATUS_LABELS = {
    "approved": "承認済み",
    "needs_human_approval": "承認待ち",
    "drafting": "ドラフト生成中",
    "reviewing": "レビュー中",
    "revise": "修正対応",
    "escalated": "エスカレーション",
    "failed": "失敗",
    "received": "受付済み",
}

NEXT_ACTION_LABELS = {
    "await_human_approval": "承認待ち",
    "review_draft": "初回レビュー",
    "review_revised_draft": "再レビュー",
    "generate_initial_draft": "初回ドラフト生成",
    "manual_triage": "手動トリアージ",
    "assign_to_human_specialist": "担当者へ引き継ぎ",
    "route_approve": "承認ルートへ進行",
    "route_revise": "修正ルートへ進行",
    "route_escalate": "エスカレーション対応",
    "ready_for_sending_stage": "送信準備完了",
    "iteration_recorded": "履歴保存済み",
}


def apply_custom_theme() -> None:
    st.markdown(
        """
        <style>
            :root {
                --paper: #f6efe3;
                --paper-soft: rgba(255, 249, 241, 0.88);
                --paper-card: rgba(255, 251, 246, 0.93);
                --ink: #241d18;
                --body: #53493f;
                --muted: #7b7268;
                --line: rgba(76, 58, 38, 0.14);
                --accent: #b57c39;
                --ok-bg: #dde9cf;
                --ok-text: #315228;
                --warn-bg: #f0dfb5;
                --warn-text: #6d521c;
                --danger-bg: #ecd1ca;
                --danger-text: #7a3227;
                --neutral-bg: #ddd5c8;
                --neutral-text: #4f463e;
                --panel-shadow: 0 18px 44px rgba(47, 35, 21, 0.10);
                --soft-shadow: 0 10px 28px rgba(47, 35, 21, 0.08);
                --btn-bg: #30241c;
                --btn-bg-hover: #3d2e25;
                --btn-text: #fff8ee;
                --reading-text: #f6f2ea;
            }

            html, body, [class*="css"] {
                font-family: "Yu Gothic", "Hiragino Sans", "Meiryo", sans-serif;
                color: var(--ink);
            }

            [data-testid="stAppViewContainer"] {
                background:
                    radial-gradient(circle at top left, rgba(255,255,255,0.55), transparent 26%),
                    radial-gradient(circle at top right, rgba(255,242,216,0.34), transparent 24%),
                    linear-gradient(180deg, #f7f0e5 0%, #ebdfcb 100%);
            }

            [data-testid="stHeader"] {
                background: transparent;
            }

            .block-container {
                max-width: 1320px;
                padding-top: 1.25rem;
                padding-bottom: 3.5rem;
            }

            h1, h2, h3, h4 {
                font-family: "Yu Mincho", "Hiragino Mincho ProN", serif;
                color: var(--ink);
                letter-spacing: -0.02em;
            }

            .hero {
                display: grid;
                grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.95fr);
                gap: 2.4rem;
                align-items: center;
                margin-bottom: 2.2rem;
            }

            .eyebrow {
                font-family: Consolas, "Courier New", monospace;
                font-size: 0.8rem;
                letter-spacing: 0.18em;
                text-transform: uppercase;
                color: var(--muted);
                margin-bottom: 1rem;
            }

            .hero-title {
                font-size: clamp(3rem, 6.8vw, 5.4rem);
                line-height: 0.96;
                margin: 0 0 1.3rem 0;
                font-weight: 700;
            }

            .hero-title .accent {
                color: var(--accent);
                font-style: italic;
            }

            .hero-meta {
                display: flex;
                align-items: center;
                gap: 0.9rem;
                flex-wrap: wrap;
                margin-bottom: 1.6rem;
            }

            .hero-chip {
                display: inline-flex;
                align-items: center;
                gap: 0.55rem;
                padding: 0.55rem 0.95rem;
                border-radius: 999px;
                border: 1px solid var(--line);
                background: rgba(255, 249, 238, 0.82);
                color: var(--ink);
                font-size: 0.85rem;
                box-shadow: var(--soft-shadow);
            }

            .hero-chip-dot {
                width: 0.55rem;
                height: 0.55rem;
                border-radius: 999px;
                background: #78c669;
                box-shadow: 0 0 0 5px rgba(120, 198, 105, 0.14);
            }

            .inventory-line {
                font-family: Consolas, "Courier New", monospace;
                font-size: 0.82rem;
                color: var(--muted);
            }

            .hero-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(180px, 1fr));
                gap: 1rem 1.8rem;
                max-width: 42rem;
            }

            .hero-grid-label {
                font-family: Consolas, "Courier New", monospace;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                font-size: 0.75rem;
                color: var(--muted);
                margin-bottom: 0.2rem;
            }

            .hero-grid-value {
                font-size: 1rem;
                line-height: 1.75;
                color: var(--body);
            }

            .pipeline-card,
            .panel-box,
            div[data-testid="stForm"],
            div[data-testid="stExpander"] {
                background: var(--paper-soft);
                border: 1px solid var(--line);
                border-radius: 24px;
                box-shadow: var(--panel-shadow);
            }

            .pipeline-card {
                padding: 1.35rem;
            }

            .pipeline-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1rem;
                gap: 1rem;
            }

            .pipeline-title {
                font-family: "Yu Mincho", "Hiragino Mincho ProN", serif;
                font-size: 1.55rem;
                color: var(--ink);
            }

            .pipeline-live {
                display: inline-flex;
                align-items: center;
                gap: 0.45rem;
                color: var(--muted);
                font-size: 0.8rem;
            }

            .pipeline-live-dot {
                width: 0.5rem;
                height: 0.5rem;
                border-radius: 999px;
                background: #72c36a;
                box-shadow: 0 0 0 6px rgba(114, 195, 106, 0.14);
            }

            .pipeline-track {
                display: grid;
                grid-template-columns: repeat(5, minmax(0, 1fr));
                gap: 0.55rem;
                margin-bottom: 1rem;
            }

            .pipeline-step {
                padding: 0.72rem 0.45rem;
                border-radius: 16px;
                border: 1px solid var(--line);
                background: rgba(255,255,255,0.36);
                text-align: center;
                font-size: 0.88rem;
                color: var(--body);
            }

            .pipeline-step.done {
                background: rgba(221, 233, 207, 0.75);
                color: var(--ok-text);
            }

            .pipeline-step.active {
                background: rgba(240, 223, 181, 0.78);
                color: var(--warn-text);
            }

            .pipeline-stats {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.7rem;
            }

            .pipeline-stat {
                border: 1px solid var(--line);
                border-radius: 18px;
                padding: 0.85rem 0.9rem;
                background: rgba(255,255,255,0.38);
            }

            .pipeline-stat-num {
                font-size: 1.4rem;
                font-weight: 700;
                color: var(--ink);
            }

            .pipeline-stat-label {
                margin-top: 0.18rem;
                color: var(--muted);
                font-size: 0.8rem;
            }

            .panel-box {
                padding: 1.25rem 1.25rem 1.1rem 1.25rem;
                margin-bottom: 1.2rem;
            }

            .panel-kicker {
                font-family: Consolas, "Courier New", monospace;
                color: var(--muted);
                text-transform: uppercase;
                letter-spacing: 0.12em;
                font-size: 0.78rem;
                margin-bottom: 0.4rem;
            }

            .panel-title {
                font-family: "Yu Mincho", "Hiragino Mincho ProN", serif;
                font-size: 1.8rem;
                line-height: 1.1;
                margin-bottom: 0.4rem;
            }

            .panel-copy {
                color: var(--body);
                line-height: 1.7;
                font-size: 0.98rem;
            }

            .page-title {
                font-family: "Yu Mincho", "Hiragino Mincho ProN", serif;
                font-size: clamp(2.2rem, 4vw, 3.2rem);
                line-height: 1.02;
                margin: 0 0 0.5rem 0;
                color: #1a130f;
                letter-spacing: -0.03em;
            }

            .page-subtitle {
                color: var(--body);
                line-height: 1.8;
                margin-bottom: 1.35rem;
            }

            .flow-stage {
                position: relative;
                padding: 1.25rem 1.35rem 1.2rem 1.35rem;
                margin-bottom: 1rem;
                background: var(--paper-card);
                border: 1px solid var(--line);
                border-radius: 24px;
                box-shadow: var(--panel-shadow);
            }

            .flow-stage.active {
                border-color: rgba(181, 124, 57, 0.34);
                box-shadow: 0 0 0 1px rgba(181, 124, 57, 0.08), 0 20px 48px rgba(47, 35, 21, 0.12);
                background:
                    linear-gradient(180deg, rgba(255,252,247,0.98), rgba(255,247,237,0.95));
            }

            .flow-stage.active::before {
                content: "";
                position: absolute;
                inset: 0 auto 0 0;
                width: 6px;
                border-radius: 24px 0 0 24px;
                background: linear-gradient(180deg, #c28a46 0%, #8f612c 100%);
            }

            .flow-stage-header {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 1rem;
                margin-bottom: 0.9rem;
            }

            .flow-stage-title-wrap {
                display: flex;
                align-items: center;
                gap: 0.85rem;
            }

            .flow-stage-index {
                width: 2.2rem;
                height: 2.2rem;
                border-radius: 999px;
                background: linear-gradient(180deg, #3a2c22 0%, #241a14 100%);
                color: #fff7ef;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-family: Consolas, "Courier New", monospace;
                font-size: 0.88rem;
                font-weight: 700;
                flex: 0 0 auto;
            }

            .flow-stage-kicker {
                font-family: Consolas, "Courier New", monospace;
                color: var(--muted);
                letter-spacing: 0.12em;
                text-transform: uppercase;
                font-size: 0.76rem;
                margin-bottom: 0.15rem;
            }

            .flow-stage-title {
                font-family: "Yu Mincho", "Hiragino Mincho ProN", serif;
                font-size: 1.55rem;
                line-height: 1.08;
                color: var(--ink);
            }

            .flow-stage-copy {
                color: var(--body);
                line-height: 1.7;
                margin-bottom: 0.85rem;
            }

            .flow-divider {
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0.35rem 0 1rem 0;
                color: var(--muted);
                font-family: Consolas, "Courier New", monospace;
                font-size: 0.85rem;
                letter-spacing: 0.08em;
            }

            .flow-divider::before,
            .flow-divider::after {
                content: "";
                flex: 1;
                height: 1px;
                background: var(--line);
            }

            .flow-divider span {
                padding: 0 0.85rem;
            }

            .flow-divider.active span {
                color: #8f612c;
                font-weight: 700;
            }

            .monitor-grid {
                display: grid;
                grid-template-columns: 1.35fr 0.65fr;
                gap: 1rem;
                margin-bottom: 1rem;
            }

            .monitor-stats {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.8rem;
                margin-bottom: 0.9rem;
            }

            .compact-stat {
                background: rgba(255,255,255,0.34);
                border: 1px solid var(--line);
                border-radius: 18px;
                padding: 0.9rem 1rem;
            }

            .compact-stat-label {
                color: var(--muted);
                font-size: 0.82rem;
                margin-bottom: 0.35rem;
            }

            .compact-stat-value {
                color: var(--ink);
                font-family: "Yu Mincho", "Hiragino Mincho ProN", serif;
                font-size: 1.2rem;
                line-height: 1.25;
                word-break: break-word;
            }

            .compact-stat-value strong {
                font-size: 1.9rem;
                font-weight: 700;
            }

            .ticket-monitor-body {
                background: rgba(255,255,255,0.26);
                border: 1px solid var(--line);
                border-radius: 20px;
                padding: 1rem 1.05rem;
            }

            .monitor-block-title {
                color: var(--muted);
                font-size: 0.82rem;
                margin-bottom: 0.35rem;
            }

            .review-note {
                background: linear-gradient(180deg, rgba(255,248,236,0.96), rgba(248,238,225,0.92));
                border: 1px solid rgba(181, 124, 57, 0.18);
                border-radius: 20px;
                padding: 1rem 1.05rem;
                color: var(--ink);
                line-height: 1.8;
            }

            .review-memo {
                display: grid;
                grid-template-columns: 240px 1fr;
                gap: 1rem;
                align-items: stretch;
            }

            .review-meta-card {
                background: rgba(255,255,255,0.42);
                border: 1px solid var(--line);
                border-radius: 18px;
                padding: 1rem;
            }

            .review-meta-label {
                color: var(--muted);
                font-size: 0.8rem;
                margin-bottom: 0.35rem;
            }

            .review-meta-value {
                color: var(--ink);
                font-family: "Yu Mincho", "Hiragino Mincho ProN", serif;
                font-size: 1.18rem;
                line-height: 1.35;
                margin-bottom: 0.9rem;
            }

            .review-note-card {
                background: linear-gradient(180deg, rgba(255,248,236,0.98), rgba(247,236,220,0.96));
                border: 1px solid rgba(181, 124, 57, 0.2);
                border-radius: 20px;
                padding: 1.05rem 1.1rem;
                box-shadow: var(--soft-shadow);
            }

            .review-note-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 0.8rem;
                margin-bottom: 0.8rem;
            }

            .review-note-title {
                font-family: "Yu Mincho", "Hiragino Mincho ProN", serif;
                font-size: 1.2rem;
                color: #2a211b;
            }

            .review-note-badge {
                display: inline-flex;
                align-items: center;
                gap: 0.4rem;
                border-radius: 999px;
                padding: 0.35rem 0.7rem;
                background: rgba(181, 124, 57, 0.12);
                color: #7b5325;
                font-size: 0.78rem;
                font-weight: 700;
            }

            .review-note-body {
                color: #2f2721;
                line-height: 1.85;
                white-space: pre-wrap;
                word-break: break-word;
            }

            .review-summary {
                display: grid;
                grid-template-columns: 1fr 1fr 1fr;
                gap: 0.75rem;
                margin-bottom: 0.85rem;
            }

            .metric-card {
                background: rgba(255, 251, 246, 0.93);
                border: 1px solid var(--line);
                border-radius: 22px;
                box-shadow: var(--panel-shadow);
                padding: 1.1rem 1.2rem;
                min-height: 132px;
            }

            .metric-label {
                color: var(--body);
                font-size: 0.96rem;
                margin-bottom: 0.65rem;
            }

            .metric-value {
                font-family: "Yu Mincho", "Hiragino Mincho ProN", serif;
                font-size: 2rem;
                line-height: 1.15;
                color: var(--ink);
                word-break: break-word;
            }

            .metric-value.large {
                font-size: clamp(2rem, 3.8vw, 3rem);
            }
            .status-pill {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-height: 2.1rem;
                padding: 0.4rem 0.8rem;
                border-radius: 999px;
                font-weight: 700;
                font-size: 0.92rem;
            }

            .reading-block {
                background: linear-gradient(180deg, #1a1b20 0%, #15161a 100%);
                color: var(--reading-text) !important;
                border-radius: 22px;
                padding: 1.3rem 1.35rem;
                border: 1px solid rgba(255,255,255,0.06);
                box-shadow: 0 16px 36px rgba(14, 15, 19, 0.22);
                font-family: "Yu Gothic", "Hiragino Sans", "Meiryo", sans-serif;
                font-size: 0.96rem;
                line-height: 1.86;
                white-space: pre-wrap;
                word-break: break-word;
                min-height: 360px;
            }

            .reading-block, .reading-block * {
                color: var(--reading-text) !important;
            }

            .reading-actions {
                display: flex;
                justify-content: flex-end;
                margin-top: 0.85rem;
            }

            .workflow-running {
                border: 1px solid rgba(181, 124, 57, 0.16);
                border-radius: 20px;
                background: linear-gradient(180deg, rgba(255,249,241,0.96), rgba(247,238,226,0.92));
                padding: 1.1rem 1.15rem;
                margin-top: 0.85rem;
            }

            .workflow-running-title {
                font-family: "Yu Mincho", "Hiragino Mincho ProN", serif;
                font-size: 1.25rem;
                margin-bottom: 0.35rem;
                color: var(--ink);
            }

            .workflow-running-copy {
                color: var(--body);
                line-height: 1.7;
                font-size: 0.94rem;
            }

            .workflow-dots {
                display: inline-flex;
                align-items: center;
                gap: 0.45rem;
                margin-bottom: 0.7rem;
            }

            .workflow-dots span {
                width: 0.56rem;
                height: 0.56rem;
                border-radius: 999px;
                background: var(--accent);
                animation: pulse 1.1s infinite ease-in-out;
            }

            .workflow-dots span:nth-child(2) { animation-delay: 0.12s; }
            .workflow-dots span:nth-child(3) { animation-delay: 0.24s; }

            @keyframes pulse {
                0%, 80%, 100% { transform: scale(0.72); opacity: 0.45; }
                40% { transform: scale(1); opacity: 1; }
            }

            .plain-card {
                background: rgba(255,255,255,0.28);
                border: 1px solid var(--line);
                border-radius: 18px;
                padding: 1rem 1.05rem;
                color: var(--body);
                line-height: 1.72;
            }

            div[data-testid="stForm"] {
                padding: 1rem 1rem 0.35rem 1rem;
            }

            div[data-testid="stTextInputRootElement"] > div,
            div[data-testid="stTextArea"] textarea,
            div[data-baseweb="select"] > div,
            div[data-testid="stSelectbox"] > div,
            div[data-testid="stTextInput"] input {
                background: linear-gradient(180deg, rgba(255,250,244,0.98), rgba(248,240,230,0.96)) !important;
                color: var(--ink) !important;
                border-radius: 16px !important;
                border: 1px solid rgba(94, 71, 46, 0.20) !important;
                box-shadow: inset 0 1px 0 rgba(255,255,255,0.66) !important;
            }

            textarea, input {
                color: var(--ink) !important;
                font-size: 0.97rem !important;
            }

            textarea:focus, input:focus {
                border-color: rgba(181, 124, 57, 0.48) !important;
                box-shadow: 0 0 0 3px rgba(181, 124, 57, 0.15) !important;
            }

            .stTabs [data-baseweb="tab-list"] {
                gap: 0.7rem;
                margin-bottom: 0.65rem;
            }

            .stTabs [data-baseweb="tab"] {
                background: transparent;
                border-radius: 999px;
                padding: 0.45rem 0.15rem 0.65rem 0.15rem;
                color: var(--muted);
                font-weight: 700;
            }

            .stTabs [aria-selected="true"] {
                color: var(--ink) !important;
            }

            div.stButton > button,
            div[data-testid="stFormSubmitButton"] button {
                background: linear-gradient(180deg, var(--btn-bg) 0%, #1f1712 100%) !important;
                color: var(--btn-text) !important;
                border: 1px solid rgba(23, 17, 11, 0.9) !important;
                border-radius: 18px !important;
                min-height: 3rem;
                padding: 0.7rem 1.1rem !important;
                font-weight: 700 !important;
                box-shadow: 0 10px 24px rgba(32, 24, 18, 0.20);
            }

            div.stButton > button:hover,
            div[data-testid="stFormSubmitButton"] button:hover {
                background: linear-gradient(180deg, var(--btn-bg-hover) 0%, #241a14 100%) !important;
                color: var(--btn-text) !important;
            }

            div.stButton > button:disabled,
            div[data-testid="stFormSubmitButton"] button:disabled {
                opacity: 0.55;
                color: #f7efe6 !important;
            }

            .copy-button {
                background: linear-gradient(180deg, var(--btn-bg) 0%, #1f1712 100%);
                color: var(--btn-text);
                border-radius: 16px;
                border: 1px solid rgba(23, 17, 11, 0.9);
                padding: 0.68rem 1rem;
                font-weight: 700;
                cursor: pointer;
                font-family: "Yu Gothic", "Hiragino Sans", "Meiryo", sans-serif;
            }

            .copy-button:hover {
                background: linear-gradient(180deg, var(--btn-bg-hover) 0%, #241a14 100%);
            }

            .copy-feedback {
                margin-left: 0.7rem;
                color: var(--muted);
                font-size: 0.9rem;
            }

            @media (max-width: 980px) {
                .hero {
                    grid-template-columns: 1fr;
                }

                .monitor-grid,
                .review-summary {
                    grid-template-columns: 1fr;
                }

                .pipeline-track,
                .pipeline-stats,
                .hero-grid,
                .monitor-stats {
                    grid-template-columns: 1fr 1fr;
                }
            }

            @media (max-width: 680px) {
                .pipeline-track,
                .pipeline-stats,
                .hero-grid,
                .monitor-stats {
                    grid-template-columns: 1fr;
                }

                .hero-title {
                    font-size: 2.8rem;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def panel_start(kicker: str, title: str, copy: str | None = None) -> None:
    copy_html = f"<div class='panel-copy'>{copy}</div>" if copy else ""
    st.markdown(
        f"""
        <div class="panel-box">
            <div class="panel-kicker">{html.escape(kicker)}</div>
            <div class="panel-title">{html.escape(title)}</div>
            {copy_html}
        """,
        unsafe_allow_html=True,
    )


def panel_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def render_copy_button(text: str, key: str, label: str = "テキストをコピー") -> None:
    payload = html.escape(text).replace("\n", "&#10;").replace("'", "&#39;")
    st.markdown(
        f"""
        <div class="reading-actions">
            <button class="copy-button" onclick="navigator.clipboard.writeText('{payload}').then(() => {{ const el = document.getElementById('copy-{key}'); if (el) el.innerText = 'コピーしました'; }});">
                {html.escape(label)}
            </button>
            <span id="copy-{key}" class="copy-feedback"></span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_reading_block(text: str) -> None:
    escaped = html.escape(text or "").replace("\n", "<br>")
    st.markdown(f"<div class='reading-block'>{escaped}</div>", unsafe_allow_html=True)


def render_workflow_running_card() -> None:
    st.markdown(
        """
        <div class="workflow-running">
            <div class="workflow-dots"><span></span><span></span><span></span></div>
            <div class="workflow-running-title">ワークフローを実行しています</div>
            <div class="workflow-running-copy">チケットの解析、ドラフト生成、レビュー判定、履歴保存を順番に進めています。完了後に右側のアーカイブへ最新実行が反映されます。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_badge_html(status: str | None) -> str:
    palette = {
        "approved": ("var(--ok-bg)", "var(--ok-text)"),
        "needs_human_approval": ("var(--warn-bg)", "var(--warn-text)"),
        "drafting": ("var(--warn-bg)", "var(--warn-text)"),
        "reviewing": ("var(--warn-bg)", "var(--warn-text)"),
        "revise": ("var(--warn-bg)", "var(--warn-text)"),
        "escalated": ("var(--danger-bg)", "var(--danger-text)"),
        "failed": ("var(--danger-bg)", "var(--danger-text)"),
        "received": ("var(--neutral-bg)", "var(--neutral-text)"),
    }
    key = status or "received"
    bg, color = palette.get(key, ("var(--neutral-bg)", "var(--neutral-text)"))
    label = STATUS_LABELS.get(key, key.replace("_", " ").title())
    return f"<span class='status-pill' style='background:{bg}; color:{color};'>{html.escape(label)}</span>"


def next_action_label(action: str | None) -> str:
    if not action:
        return "-"
    return NEXT_ACTION_LABELS.get(action, action.replace("_", " ").title())


def render_metric_card(label: str, content: str, large: bool = False) -> None:
    value_class = "metric-value large" if large else "metric-value"
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{html.escape(label)}</div>
            <div class="{value_class}">{content}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_intro(ticket_count: int) -> None:
    st.markdown(
        f"""
        <div class="eyebrow">DOCUWARE / SUPPORT FLOW</div>
        <h1 class="page-title">超絶カンタン問い合わせ対応</h1>
        <div class="page-subtitle">
            起票内容の確認から、初回回答、内山 agent のレビュー、修正版の確定までを
            上から順に追える構成にしています。現在のアーカイブ件数は {ticket_count} 件です。
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_flow_stage(index: str, kicker: str, title: str, copy: str, active: bool = False) -> None:
    active_class = " active" if active else ""
    st.markdown(
        f"""
        <section class="flow-stage{active_class}">
            <div class="flow-stage-header">
                <div class="flow-stage-title-wrap">
                    <div class="flow-stage-index">{html.escape(index)}</div>
                    <div>
                        <div class="flow-stage-kicker">{html.escape(kicker)}</div>
                        <div class="flow-stage-title">{html.escape(title)}</div>
                    </div>
                </div>
            </div>
            <div class="flow-stage-copy">{html.escape(copy)}</div>
        """,
        unsafe_allow_html=True,
    )


def close_flow_stage() -> None:
    st.markdown("</section>", unsafe_allow_html=True)


def render_compact_stat(label: str, value: str) -> None:
    st.markdown(
        f"""
        <div class="compact-stat">
            <div class="compact-stat-label">{html.escape(label)}</div>
            <div class="compact-stat-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_flow_divider(label: str, active: bool = False) -> None:
    active_class = " active" if active else ""
    st.markdown(
        f"<div class='flow-divider{active_class}'><span>{html.escape(label)}</span></div>",
        unsafe_allow_html=True,
    )


def render_review_comment_card(decision: str, next_action: str, count: int, notes: str) -> None:
    st.markdown(
        f"""
        <div class="review-memo">
            <div class="review-meta-card">
                <div class="review-meta-label">レビュー判断</div>
                <div class="review-meta-value">{html.escape(decision)}</div>
                <div class="review-meta-label">次の段階</div>
                <div class="review-meta-value">{html.escape(next_action)}</div>
                <div class="review-meta-label">反復履歴</div>
                <div class="review-meta-value">{count} 件</div>
            </div>
            <div class="review-note-card">
                <div class="review-note-header">
                    <div class="review-note-title">内山 agent コメント</div>
                    <div class="review-note-badge">Review Memo</div>
                </div>
                <div class="review-note-body">{html.escape(notes).replace(chr(10), '<br>')}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_ticket_label(ticket) -> str:
    created = ticket.created_at.strftime("%m/%d %H:%M") if ticket.created_at else "-"
    return f"#{ticket.id} / {ticket.external_id} / {ticket.customer_email} / {created}"


def format_workflow_label(run) -> str:
    created = run.created_at.strftime("%m/%d %H:%M") if run.created_at else "-"
    status = STATUS_LABELS.get(getattr(run.status, "value", str(run.status)), str(run.status))
    return f"実行 #{run.id} / {status} / {created}"


def init_state() -> None:
    defaults = {
        "selected_ticket_id": None,
        "selected_workflow_run_id": None,
        "workflow_running": False,
        "pending_workflow_ticket_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def ensure_db_ready() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_schema()


def main() -> None:
    ensure_db_ready()
    init_state()
    apply_custom_theme()

    with SessionLocal() as db:
        tickets = list_tickets(db, limit=80)
        if tickets and st.session_state.selected_ticket_id is None:
            st.session_state.selected_ticket_id = tickets[0].id

        render_page_intro(len(tickets))

        control_left, control_right = st.columns([0.78, 1.22], gap="large")

        with control_left:
            panel_start("intake", "チケット作成", "新しい問い合わせを登録して、すぐ下のフロー表示で追跡できます。")
            with st.form("create_ticket_form", clear_on_submit=True):
                now_code = datetime.now().strftime("sp-%Y%m%d%H%M%S")
                external_id = st.text_input("外部ID", value=now_code)
                customer_email = st.text_input("顧客メール", value="customer@example.com")
                subject = st.text_input("件名", value="検索結果に文書が表示されない")
                body = st.text_area(
                    "問い合わせ内容",
                    value="DocuWare 上で検索結果に期待した文書が表示されません。検索条件と権限を確認したいです。",
                    height=160,
                )
                source = st.selectbox("流入元", ["dashboard", "email", "portal", "phone"], index=0)
                submitted = st.form_submit_button("チケットを保存")

            if submitted:
                new_ticket = create_ticket(
                    db=db,
                    external_id=external_id.strip(),
                    customer_email=customer_email.strip(),
                    subject=subject.strip(),
                    body=body.strip(),
                    source=source,
                )
                st.session_state.selected_ticket_id = new_ticket.id
                st.session_state.selected_workflow_run_id = None
                st.success("チケットを作成しました。")
                st.rerun()
            panel_end()

        with control_right:
            panel_start("archive", "監視対象チケット", "上から順にフローを確認できるよう、対象チケットと実行履歴をここで切り替えます。")
            if tickets:
                ticket_ids = [ticket.id for ticket in tickets]
                current_ticket_id = st.session_state.selected_ticket_id
                if current_ticket_id not in ticket_ids:
                    current_ticket_id = ticket_ids[0]
                    st.session_state.selected_ticket_id = current_ticket_id

                selected_ticket_id = st.selectbox(
                    "対象チケット",
                    options=ticket_ids,
                    index=ticket_ids.index(current_ticket_id),
                    format_func=lambda ticket_id: format_ticket_label(next(ticket for ticket in tickets if ticket.id == ticket_id)),
                    key="ticket_picker",
                )
                st.session_state.selected_ticket_id = selected_ticket_id

                if st.button("ワークフローを実行", key="run_workflow_button", use_container_width=True):
                    st.session_state.workflow_running = True
                    st.session_state.pending_workflow_ticket_id = selected_ticket_id
                    st.rerun()

                if (
                    st.session_state.workflow_running
                    and st.session_state.pending_workflow_ticket_id == selected_ticket_id
                ):
                    render_workflow_running_card()
                    with st.spinner("ワークフローを実行しています..."):
                        time.sleep(0.4)
                        workflow_run, _ = run_and_persist_workflow_for_ticket(db=db, ticket_id=selected_ticket_id)
                    st.session_state.selected_workflow_run_id = workflow_run.id
                    st.session_state.workflow_running = False
                    st.session_state.pending_workflow_ticket_id = None
                    st.success(f"実行 #{workflow_run.id} を保存しました。")
                    st.rerun()

                workflow_runs = list_workflow_runs_for_ticket(db, selected_ticket_id, limit=30)
                if workflow_runs:
                    run_ids = [run.id for run in workflow_runs]
                    current_run_id = st.session_state.selected_workflow_run_id
                    if current_run_id not in run_ids:
                        current_run_id = run_ids[0]
                        st.session_state.selected_workflow_run_id = current_run_id

                    selected_run_id = st.selectbox(
                        "表示する実行",
                        options=run_ids,
                        index=run_ids.index(current_run_id),
                        format_func=lambda run_id: format_workflow_label(next(run for run in workflow_runs if run.id == run_id)),
                        key="run_picker",
                    )
                    st.session_state.selected_workflow_run_id = selected_run_id
                else:
                    st.info("まだワークフロー実行はありません。")
                    st.session_state.selected_workflow_run_id = None
            else:
                st.info("先にチケットを1件作成してください。")
            panel_end()

        if not tickets:
            return

        selected_ticket = get_ticket_by_id(db, st.session_state.selected_ticket_id)
        selected_run = None
        iteration_history = []
        approval_actions = []
        drafts = None

        if st.session_state.selected_workflow_run_id is not None:
            selected_run = get_workflow_run(db, st.session_state.selected_workflow_run_id)
            if selected_run is not None:
                iteration_history = get_iteration_history(db, selected_run.id)
                approval_actions = get_approval_actions(db, selected_run.id)
                drafts = build_workflow_drafts(db, selected_run.id)

        first_step = iteration_history[0] if iteration_history else None
        latest_step = iteration_history[-1] if iteration_history else None
        first_draft = first_step.draft_response if first_step else None
        review_notes = latest_step.review_notes if latest_step else (selected_run.final_review_notes if selected_run else None)
        final_draft = selected_run.final_draft_response if selected_run else None
        current_action = selected_run.next_action if selected_run else None
        active_stage = "01"
        if selected_run is None:
            active_stage = "01"
        elif not first_draft:
            active_stage = "02"
        elif current_action in {"review_draft", "review_revised_draft", "route_revise", "route_escalate"}:
            active_stage = "03"
        elif current_action in {"await_human_approval", "ready_for_sending_stage", "route_approve"}:
            active_stage = "05"
        else:
            active_stage = "04"

        render_flow_stage("01", "monitor", "起票内容の監視", "対象チケットの内容と現在ステータスをここで確認し、そのままワークフローを実行できます。", active=active_stage == "01")
        monitor_left, monitor_right = st.columns([1.2, 0.8], gap="large")
        with monitor_left:
            st.markdown(
                f"<div class='ticket-monitor-body'><div class='monitor-block-title'>件名</div><div>{html.escape(selected_ticket.subject)}</div></div>",
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
            st.markdown(
                f"<div class='ticket-monitor-body'><div class='monitor-block-title'>問い合わせ内容</div><div>{html.escape(selected_ticket.body).replace(chr(10), '<br>')}</div></div>",
                unsafe_allow_html=True,
            )
        with monitor_right:
            stat_cols = st.columns(1)
            with stat_cols[0]:
                render_compact_stat("現在のステータス", status_badge_html(getattr(selected_ticket.status, "value", str(selected_ticket.status))))
                render_compact_stat("次のアクション", html.escape(next_action_label(selected_run.next_action if selected_run else None)))
                render_compact_stat("反復回数", f"<strong>{selected_run.iteration_count if selected_run else 0}</strong>")
                render_compact_stat("監視対象", html.escape(f"{selected_ticket.external_id} / {selected_ticket.customer_email}"))
        close_flow_stage()

        render_flow_divider("Draft", active=active_stage == "02")

        render_flow_stage("02", "first response", "生成された初回回答", "ワークフローが最初に作成した返信案です。ここがレビュー前のベースになります。", active=active_stage == "02")
        if selected_run is None:
            st.info("ワークフロー実行後に初回回答が表示されます。")
        else:
            render_reading_block(first_draft or "まだ初回回答は生成されていません。")
            render_copy_button(first_draft or "", "first-draft")
        close_flow_stage()

        render_flow_divider("Review", active=active_stage == "03")

        render_flow_stage("03", "uchiyama agent", "内山 agent のレビュー意見", "初回回答をレビューした結果の判断とコメントを表示します。必要ならこのあと修正版へ進みます。", active=active_stage == "03")
        if selected_run is None:
            st.info("ワークフロー実行後にレビュー結果が表示されます。")
        else:
            render_review_comment_card(
                latest_step.decision if latest_step and latest_step.decision else "-",
                next_action_label(selected_run.next_action),
                len(iteration_history),
                review_notes or "まだレビューコメントはありません。",
            )
            if iteration_history:
                history_df = pd.DataFrame(
                    [
                        {
                            "反復": step.iteration,
                            "判断": step.decision or "-",
                            "レビュー内容": step.review_notes,
                        }
                        for step in iteration_history
                    ]
                )
                st.markdown("<div style='height:0.9rem'></div>", unsafe_allow_html=True)
                st.dataframe(history_df, use_container_width=True, hide_index=True)
        close_flow_stage()

        render_flow_divider("Revision", active=active_stage == "04")

        render_flow_stage("04", "revised answer", "修正後の回答", "レビュー指摘を踏まえて整えた最終回答です。承認対象ならこの下でサインオフできます。", active=active_stage == "04")
        if selected_run is None:
            st.info("ワークフロー実行後に修正後の回答が表示されます。")
        else:
            render_reading_block(final_draft or "まだ修正後の回答はありません。")
            render_copy_button(final_draft or "", "final-draft")
        close_flow_stage()

        render_flow_stage("05", "approval", "承認と補助アウトプット", "最終回答の承認と、顧客返信・連携メモ・社内要約の確認をここでまとめて行います。", active=active_stage == "05")
        approval_left, approval_right = st.columns([0.72, 1.28], gap="large")
        with approval_left:
            if selected_run is None:
                st.info("承認対象の実行がありません。")
            else:
                if approval_actions:
                    approval_df = pd.DataFrame(
                        [
                            {
                                "承認者": item.approver,
                                "アクション": item.action,
                                "メモ": item.notes or "-",
                                "日時": item.created_at.strftime("%Y-%m-%d %H:%M") if item.created_at else "-",
                            }
                            for item in approval_actions
                        ]
                    )
                    st.dataframe(approval_df, use_container_width=True, hide_index=True)
                else:
                    st.info("承認履歴はまだ記録されていません。")

                needs_approval = getattr(selected_run.status, "value", str(selected_run.status)) == "needs_human_approval"
                with st.form("approval_form"):
                    approver = st.text_input("承認者", value="team.lead@company.com")
                    notes = st.text_input("承認メモ", value="送信して問題ありません。")
                    approved = st.form_submit_button("承認する", disabled=not needs_approval)

                if not needs_approval:
                    st.caption("この実行は現在、追加承認の対象ではありません。")
                elif approved:
                    approve_workflow_run(
                        db=db,
                        workflow_run_id=selected_run.id,
                        approver=approver.strip(),
                        notes=notes.strip(),
                    )
                    st.success("承認を保存しました。")
                    st.rerun()

        with approval_right:
            if drafts is None:
                st.info("ワークフロー実行後に補助アウトプットが表示されます。")
            else:
                customer_reply = drafts.get("customer_reply_draft") or "顧客向け返信はまだ生成されていません。"
                vendor_reply = drafts.get("vendor_escalation_draft") or "ベンダー連携メモはまだありません。"
                internal_summary = drafts.get("internal_summary") or "社内要約はまだありません。"
                out1, out2, out3 = st.tabs(["顧客返信", "連携メモ", "社内要約"])
                with out1:
                    render_reading_block(customer_reply)
                    render_copy_button(customer_reply, "customer-reply")
                with out2:
                    render_reading_block(vendor_reply)
                    render_copy_button(vendor_reply, "vendor-reply")
                with out3:
                    render_reading_block(internal_summary)
                    render_copy_button(internal_summary, "internal-summary")
        close_flow_stage()


if __name__ == "__main__":
    main()
