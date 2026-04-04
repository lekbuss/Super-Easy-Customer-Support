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

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

_I18N: dict[str, dict[str, str]] = {
    # ---- Status labels ----
    "status.approved":              {"ja": "承認済み",         "zh": "已批准",       "en": "Approved"},
    "status.needs_human_approval":  {"ja": "承認待ち",         "zh": "待人工审批",    "en": "Pending Approval"},
    "status.drafting":              {"ja": "ドラフト生成中",    "zh": "起草中",       "en": "Drafting"},
    "status.reviewing":             {"ja": "レビュー中",       "zh": "审核中",       "en": "Reviewing"},
    "status.revise":                {"ja": "修正対応",         "zh": "需修改",       "en": "Revise"},
    "status.escalated":             {"ja": "エスカレーション", "zh": "已升级",       "en": "Escalated"},
    "status.failed":                {"ja": "失敗",             "zh": "失败",         "en": "Failed"},
    "status.received":              {"ja": "受付済み",         "zh": "已收到",       "en": "Received"},
    # ---- Next action labels ----
    "action.await_human_approval":      {"ja": "承認待ち",             "zh": "等待人工审批",   "en": "Awaiting Approval"},
    "action.review_draft":              {"ja": "初回レビュー",          "zh": "初次审核",       "en": "Review Draft"},
    "action.review_revised_draft":      {"ja": "再レビュー",            "zh": "再次审核",       "en": "Review Revised Draft"},
    "action.generate_initial_draft":    {"ja": "初回ドラフト生成",      "zh": "生成初稿",       "en": "Generate Initial Draft"},
    "action.manual_triage":             {"ja": "手動トリアージ",        "zh": "手动分诊",       "en": "Manual Triage"},
    "action.assign_to_human_specialist":{"ja": "担当者へ引き継ぎ",      "zh": "移交专员",       "en": "Assign to Specialist"},
    "action.route_approve":             {"ja": "承認ルートへ進行",      "zh": "进入审批流程",   "en": "Route to Approve"},
    "action.route_revise":              {"ja": "修正ルートへ進行",      "zh": "进入修改流程",   "en": "Route to Revise"},
    "action.route_escalate":            {"ja": "エスカレーション対応",  "zh": "升级处理",       "en": "Route to Escalate"},
    "action.ready_for_sending_stage":   {"ja": "送信準備完了",          "zh": "待发送",         "en": "Ready for Sending"},
    "action.iteration_recorded":        {"ja": "履歴保存済み",          "zh": "已记录迭代",     "en": "Iteration Recorded"},
    # ---- Page / section labels ----
    "page.title":           {"ja": "超絶カンタン問い合わせ対応",  "zh": "超简单工单对应系统",        "en": "Super Easy Customer Support"},
    "page.eyebrow":         {"ja": "DOCUWARE / SUPPORT FLOW",    "zh": "DOCUWARE / 支持流程",       "en": "DOCUWARE / SUPPORT FLOW"},
    "page.subtitle":        {"ja": "起票内容の確認から、初回回答、内山 agent のレビュー、修正版の確定までを上から順に追える構成にしています。現在のアーカイブ件数は {n} 件です。",
                             "zh": "从工单确认、初次回复、内山 Agent 审核到最终修订版，可从上至下逐步追踪。当前存档共 {n} 件。",
                             "en": "Track the full flow from ticket review, initial draft, Uchiyama Agent review, to final approval — top to bottom. Archive: {n} tickets."},
    "panel.intake.title":   {"ja": "チケット作成",       "zh": "创建工单",       "en": "Create Ticket"},
    "panel.intake.desc":    {"ja": "新しい問い合わせを登録して、すぐ下のフロー表示で追跡できます。",
                             "zh": "注册新问题，可在下方流程视图中实时追踪。",
                             "en": "Register a new inquiry and track it in the flow below."},
    "panel.archive.title":  {"ja": "監視対象チケット",   "zh": "监视工单",       "en": "Monitored Tickets"},
    "panel.archive.desc":   {"ja": "上から順にフローを確認できるよう、対象チケットと実行履歴をここで切り替えます。",
                             "zh": "在此切换目标工单和执行历史，按顺序查看流程。",
                             "en": "Switch between tickets and run history to follow the flow in order."},
    # ---- Form fields ----
    "form.external_id":         {"ja": "外部ID",          "zh": "外部ID",       "en": "External ID"},
    "form.customer_email":      {"ja": "顧客メール",       "zh": "客户邮箱",     "en": "Customer Email"},
    "form.email_placeholder":   {"ja": "例：customer@example.com", "zh": "例：customer@example.com", "en": "e.g. customer@example.com"},
    "form.subject":             {"ja": "件名",             "zh": "主题",         "en": "Subject"},
    "form.subject_placeholder": {"ja": "問い合わせの件名を入力してください", "zh": "请输入问题主题", "en": "Enter inquiry subject"},
    "form.body":                {"ja": "問い合わせ内容",   "zh": "问题内容",     "en": "Inquiry Details"},
    "form.body_placeholder":    {"ja": "顧客からの問い合わせ内容を入力してください", "zh": "请输入客户问题详情", "en": "Enter customer inquiry details"},
    "form.source":              {"ja": "流入元",           "zh": "来源渠道",     "en": "Source"},
    "form.save_ticket":         {"ja": "チケットを保存",   "zh": "保存工单",     "en": "Save Ticket"},
    "form.ticket_saved":        {"ja": "チケットを作成しました。", "zh": "工单已创建。", "en": "Ticket created."},
    # ---- Archive panel ----
    "archive.target_ticket":    {"ja": "対象チケット",     "zh": "目标工单",     "en": "Target Ticket"},
    "archive.run_workflow":     {"ja": "ワークフローを実行", "zh": "执行工作流",  "en": "Run Workflow"},
    "archive.display_run":      {"ja": "表示する実行",     "zh": "查看执行",     "en": "Display Run"},
    "archive.no_runs":          {"ja": "まだワークフロー実行はありません。", "zh": "暂无工作流执行记录。", "en": "No workflow runs yet."},
    "archive.no_tickets":       {"ja": "先にチケットを1件作成してください。", "zh": "请先创建一个工单。", "en": "Please create a ticket first."},
    "archive.running_title":    {"ja": "ワークフローを実行しています", "zh": "正在执行工作流", "en": "Running Workflow"},
    "archive.running_copy":     {"ja": "チケットの解析、ドラフト生成、レビュー判定、履歴保存を順番に進めています。完了後に右側のアーカイブへ最新実行が反映されます。",
                                 "zh": "正在依次进行工单分析、草稿生成、审核判断和历史保存。完成后最新执行将反映在右侧存档中。",
                                 "en": "Processing ticket analysis, draft generation, review decision, and history save in order. The latest run will appear in the archive when done."},
    "archive.running_spinner":  {"ja": "ワークフローを実行しています...", "zh": "工作流执行中...", "en": "Running workflow..."},
    "archive.run_saved":        {"ja": "実行 #{n} を保存しました。", "zh": "已保存执行 #{n}。", "en": "Run #{n} saved."},
    # ---- Monitor stage ----
    "stage.monitor.kicker":     {"ja": "monitor",          "zh": "监控",         "en": "monitor"},
    "stage.monitor.title":      {"ja": "起票内容の監視",   "zh": "工单内容监控", "en": "Ticket Monitor"},
    "stage.monitor.copy":       {"ja": "対象チケットの内容と現在ステータスをここで確認し、そのままワークフローを実行できます。",
                                 "zh": "在此查看目标工单内容和当前状态，可直接执行工作流。",
                                 "en": "Review the ticket content and current status, then run the workflow directly from here."},
    "monitor.subject":          {"ja": "件名",             "zh": "主题",         "en": "Subject"},
    "monitor.body":             {"ja": "問い合わせ内容",   "zh": "问题内容",     "en": "Inquiry Details"},
    "monitor.status":           {"ja": "現在のステータス", "zh": "当前状态",     "en": "Current Status"},
    "monitor.next_action":      {"ja": "次のアクション",   "zh": "下一步操作",   "en": "Next Action"},
    "monitor.iterations":       {"ja": "反復回数",         "zh": "迭代次数",     "en": "Iterations"},
    "monitor.tracking":         {"ja": "監視対象",         "zh": "监控对象",     "en": "Tracking"},
    # ---- Flow stages ----
    "stage.draft.kicker":       {"ja": "first response",  "zh": "初次回复",     "en": "first response"},
    "stage.draft.title":        {"ja": "生成された初回回答", "zh": "生成的初次回复", "en": "Generated Initial Draft"},
    "stage.draft.copy":         {"ja": "ワークフローが最初に作成した返信案です。ここがレビュー前のベースになります。",
                                 "zh": "这是工作流生成的第一版回复草稿，是审核前的基础版本。",
                                 "en": "The first reply draft created by the workflow. This is the base before review."},
    "stage.draft.empty":        {"ja": "ワークフロー実行後に初回回答が表示されます。", "zh": "执行工作流后将显示初次回复。", "en": "Initial draft will appear after running the workflow."},
    "stage.draft.no_content":   {"ja": "まだ初回回答は生成されていません。", "zh": "初次回复尚未生成。", "en": "No initial draft generated yet."},
    "stage.review.kicker":      {"ja": "uchiyama agent",  "zh": "内山 Agent",   "en": "uchiyama agent"},
    "stage.review.title":       {"ja": "内山 agent のレビュー意見", "zh": "内山 Agent 审核意见", "en": "Uchiyama Agent Review"},
    "stage.review.copy":        {"ja": "初回回答をレビューした結果の判断とコメントを表示します。必要ならこのあと修正版へ進みます。",
                                 "zh": "显示对初次回复的审核判断和评论。如有需要将进入修改版。",
                                 "en": "Shows the review decision and comments on the initial draft. A revised version will follow if needed."},
    "stage.review.empty":       {"ja": "ワークフロー実行後にレビュー結果が表示されます。", "zh": "执行工作流后将显示审核结果。", "en": "Review results will appear after running the workflow."},
    "stage.review.no_comment":  {"ja": "まだレビューコメントはありません。", "zh": "暂无审核评论。", "en": "No review comments yet."},
    "stage.review.concerns":    {"ja": "指摘ポイント",     "zh": "指摘要点",     "en": "Key Concerns"},
    "stage.review.suggestions": {"ja": "修正提案",         "zh": "修改建议",     "en": "Suggestions"},
    "review.iteration":         {"ja": "反復",             "zh": "迭代",         "en": "Iteration"},
    "review.decision":          {"ja": "判断",             "zh": "判断",         "en": "Decision"},
    "review.content":           {"ja": "レビュー内容",     "zh": "审核内容",     "en": "Review Content"},
    "stage.revision.kicker":    {"ja": "revised answer",  "zh": "修改后回复",   "en": "revised answer"},
    "stage.revision.title":     {"ja": "修正後の回答",     "zh": "修改后的回复", "en": "Revised Answer"},
    "stage.revision.copy":      {"ja": "レビュー指摘を踏まえて整えた最終回答です。承認対象ならこの下でサインオフできます。",
                                 "zh": "根据审核意见整理后的最终回复。如需审批，可在下方签核。",
                                 "en": "The final answer refined based on review feedback. Sign off below if ready for approval."},
    "stage.revision.empty":     {"ja": "ワークフロー実行後に修正後の回答が表示されます。", "zh": "执行工作流后将显示修改后的回复。", "en": "Revised answer will appear after running the workflow."},
    "stage.revision.no_content":{"ja": "まだ修正後の回答はありません。", "zh": "暂无修改后的回复。", "en": "No revised answer yet."},
    # ---- Approval stage ----
    "stage.approval.kicker":    {"ja": "approval",        "zh": "审批",         "en": "approval"},
    "stage.approval.title":     {"ja": "承認と補助アウトプット", "zh": "审批与辅助输出", "en": "Approval & Outputs"},
    "stage.approval.copy":      {"ja": "最終回答の承認と、顧客返信・連携メモ・社内要約の確認をここでまとめて行います。",
                                 "zh": "在此完成最终回复的审批，并查看客户回复、协作备注和内部摘要。",
                                 "en": "Approve the final answer and review the customer reply, vendor memo, and internal summary here."},
    "approval.no_run":          {"ja": "承認対象の実行がありません。", "zh": "没有待审批的执行记录。", "en": "No run pending approval."},
    "approval.no_history":      {"ja": "承認履歴はまだ記録されていません。", "zh": "暂无审批历史记录。", "en": "No approval history recorded yet."},
    "approval.approver":        {"ja": "承認者",           "zh": "审批人",       "en": "Approver"},
    "approval.notes":           {"ja": "承認メモ",         "zh": "审批备注",     "en": "Approval Notes"},
    "approval.submit":          {"ja": "承認する",         "zh": "批准",         "en": "Approve"},
    "approval.not_needed":      {"ja": "この実行は現在、追加承認の対象ではありません。", "zh": "此执行当前不需要额外审批。", "en": "This run does not require additional approval."},
    "approval.saved":           {"ja": "承認を保存しました。", "zh": "审批已保存。", "en": "Approval saved."},
    "approval.col.approver":    {"ja": "承認者",           "zh": "审批人",       "en": "Approver"},
    "approval.col.action":      {"ja": "アクション",       "zh": "操作",         "en": "Action"},
    "approval.col.notes":       {"ja": "メモ",             "zh": "备注",         "en": "Notes"},
    "approval.col.datetime":    {"ja": "日時",             "zh": "时间",         "en": "Date/Time"},
    "approval.tab.customer":    {"ja": "顧客返信",         "zh": "客户回复",     "en": "Customer Reply"},
    "approval.tab.vendor":      {"ja": "連携メモ",         "zh": "协作备注",     "en": "Vendor Memo"},
    "approval.tab.summary":     {"ja": "社内要約",         "zh": "内部摘要",     "en": "Internal Summary"},
    "approval.no_drafts":       {"ja": "ワークフロー実行後に補助アウトプットが表示されます。", "zh": "执行工作流后将显示辅助输出。", "en": "Outputs will appear after running the workflow."},
    "approval.no_customer":     {"ja": "顧客向け返信はまだ生成されていません。", "zh": "客户回复尚未生成。", "en": "Customer reply not generated yet."},
    "approval.no_vendor":       {"ja": "ベンダー連携メモはまだありません。", "zh": "协作备注尚未生成。", "en": "Vendor memo not available yet."},
    "approval.no_summary":      {"ja": "社内要約はまだありません。", "zh": "内部摘要尚未生成。", "en": "Internal summary not available yet."},
    # ---- Lang switcher ----
    "lang.ja": {"ja": "日", "zh": "日", "en": "JP"},
    "lang.zh": {"ja": "中", "zh": "中", "en": "CN"},
    "lang.en": {"ja": "英", "zh": "英", "en": "EN"},
    # ---- Decision labels ----
    "decision.approve":   {"ja": "✅ 承認",            "zh": "✅ 批准",   "en": "✅ Approve"},
    "decision.revise":    {"ja": "📝 要修正",           "zh": "📝 需修改", "en": "📝 Revise"},
    "decision.escalate":  {"ja": "⚠️ エスカレーション", "zh": "⚠️ 已升级", "en": "⚠️ Escalate"},
    # ---- Review card labels ----
    "review.decision_label":  {"ja": "レビュー判断",     "zh": "审核判断",   "en": "Review Decision"},
    "review.next_stage":      {"ja": "次の段階",         "zh": "下一阶段",   "en": "Next Stage"},
    "review.iter_history":    {"ja": "反復履歴",         "zh": "迭代历史",   "en": "Iteration History"},
    "review.agent_comment":   {"ja": "内山 agent コメント", "zh": "内山 Agent 评论", "en": "Uchiyama Agent Comment"},
    # ---- Copy button ----
    "copy.button":  {"ja": "テキストをコピー", "zh": "复制文本", "en": "Copy Text"},
    "copy.done":    {"ja": "コピーしました",   "zh": "已复制",   "en": "Copied!"},
    # ---- Run label ----
    "run.label":    {"ja": "実行",   "zh": "执行",   "en": "Run"},
    # ---- Approval defaults ----
    "approval.notes_default":  {"ja": "送信して問題ありません。", "zh": "确认无误，可发送。", "en": "Looks good, ready to send."},
    "approval.count_suffix":   {"ja": "件",   "zh": "条",   "en": ""},
}


def T(key: str, **kwargs) -> str:  # noqa: N802
    """Return the translated string for the current session language."""
    lang = st.session_state.get("lang", "ja")
    text = _I18N.get(key, {}).get(lang, _I18N.get(key, {}).get("ja", key))
    return text.format(**kwargs) if kwargs else text


def _status_labels() -> dict[str, str]:
    return {k.split("status.")[-1]: T(k) for k in _I18N if k.startswith("status.")}


def _next_action_labels() -> dict[str, str]:
    return {k.split("action.")[-1]: T(k) for k in _I18N if k.startswith("action.")}


STATUS_LABELS: dict[str, str] = {}   # populated per-render via _status_labels()
NEXT_ACTION_LABELS: dict[str, str] = {}  # populated per-render via _next_action_labels()


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
                font-size: clamp(2.5rem, 4.8vw, 3.8rem);
                line-height: 0.98;
                margin: 0 0 0.5rem 0;
                color: #2f3439;
                letter-spacing: -0.03em;
                font-weight: 800;
                text-shadow: 0 2px 10px rgba(47, 52, 57, 0.12);
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


def render_copy_button(text: str, key: str, label: str | None = None) -> None:
    btn_label = label if label is not None else T("copy.button")
    done_label = T("copy.done")
    payload = html.escape(text).replace("\n", "&#10;").replace("'", "&#39;")
    st.markdown(
        f"""
        <div class="reading-actions">
            <button class="copy-button" onclick="navigator.clipboard.writeText('{payload}').then(() => {{ const el = document.getElementById('copy-{key}'); if (el) el.innerText = '{html.escape(done_label)}'; }});">
                {html.escape(btn_label)}
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
    title = html.escape(T("archive.running_title"))
    copy = html.escape(T("archive.running_copy"))
    st.markdown(
        f"""
        <div class="workflow-running">
            <div class="workflow-dots"><span></span><span></span><span></span></div>
            <div class="workflow-running-title">{title}</div>
            <div class="workflow-running-copy">{copy}</div>
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
    label = _status_labels().get(key, key.replace("_", " ").title())
    return f"<span class='status-pill' style='background:{bg}; color:{color};'>{html.escape(label)}</span>"


def next_action_label(action: str | None) -> str:
    if not action:
        return "-"
    return _next_action_labels().get(action, action.replace("_", " ").title())


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
    eyebrow = html.escape(T("page.eyebrow"))
    title = html.escape(T("page.title"))
    subtitle = html.escape(T("page.subtitle", n=ticket_count))
    st.markdown(
        f"""
        <div class="eyebrow">{eyebrow}</div>
        <h1 class="page-title">{title}</h1>
        <div class="page-subtitle">{subtitle}</div>
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


def _parse_review_notes(notes: str) -> tuple[str, list[str], str]:
    """Parse review_notes JSON into (review_comment, key_concerns, suggestions).
    Falls back gracefully if notes is plain text."""
    import json as _json
    try:
        data = _json.loads(notes)
        return (
            data.get("review_comment", notes),
            data.get("key_concerns", []),
            data.get("suggestions", ""),
        )
    except (_json.JSONDecodeError, TypeError):
        return notes, [], ""


def _decision_label(decision: str) -> str:
    key = f"decision.{decision}"
    return T(key) if key in _I18N else decision


# ---------------------------------------------------------------------------
# Chat UI helpers
# ---------------------------------------------------------------------------

def _decision_badge_html(decision: str) -> str:
    styles = {
        "revise":   ("background:#c47d20;color:#fff;", "🔄 要修正"),
        "approve":  ("background:#2d7a3a;color:#fff;", "✅ 承認"),
        "escalate": ("background:#9a2b1e;color:#fff;", "⚠️ エスカレーション"),
    }
    style, label = styles.get(decision, ("background:#555;color:#fff;", decision))
    return (
        f"<span style='{style}padding:2px 10px;border-radius:12px;"
        f"font-size:0.76rem;font-weight:700;margin-left:6px;'>{label}</span>"
    )


def _render_chat_left(text: str, badge_html: str = "", sources: list | None = None) -> None:
    """Left-aligned bubble: 回答担当（濃い青）"""
    escaped = html.escape(text).replace("\n", "<br>")
    src_html = ""
    if sources:
        items = "".join(
            f"<li style='margin:0;'>{html.escape(s)}</li>"
            for s in sources if s
        )
        src_html = (
            f"<div style='margin-top:8px;font-size:0.76rem;opacity:0.8;'>"
            f"参照：<ul style='margin:2px 0 0 1rem;padding:0;'>{items}</ul></div>"
        )
    st.markdown(
        f"""
        <div style="display:flex;align-items:flex-start;margin-bottom:1.4rem;">
          <div style="margin-right:0.55rem;font-size:1.3rem;line-height:1.3;flex-shrink:0;">🔵</div>
          <div style="max-width:680px;">
            <div style="font-size:0.72rem;color:#7b7268;margin-bottom:3px;">
              回答担当{badge_html}
            </div>
            <div style="background:#1e3a5f;color:#e8f0ff;padding:0.85rem 1.1rem;
                        border-radius:0 14px 14px 14px;font-size:0.875rem;line-height:1.7;">
              {escaped}{src_html}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_chat_right(text: str, badge_html: str = "") -> None:
    """Right-aligned bubble: 内山さん（濃い緑）"""
    escaped = html.escape(text).replace("\n", "<br>")
    st.markdown(
        f"""
        <div style="display:flex;align-items:flex-start;justify-content:flex-end;margin-bottom:1.4rem;">
          <div style="max-width:680px;">
            <div style="font-size:0.72rem;color:#7b7268;margin-bottom:3px;text-align:right;">
              内山さん{badge_html}
            </div>
            <div style="background:#1a3a2a;color:#d6f0e0;padding:0.85rem 1.1rem;
                        border-radius:14px 0 14px 14px;font-size:0.875rem;line-height:1.7;">
              {escaped}
            </div>
          </div>
          <div style="margin-left:0.55rem;font-size:1.3rem;line-height:1.3;flex-shrink:0;">🟢</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_chat_workflow(iteration_history: list, final_status: str, wf_meta: dict) -> None:
    """Render the full draft↔review conversation as a chat UI."""
    _llm_fallback = wf_meta.get("llm_fallback", False)
    _rag_sources  = wf_meta.get("rag_sources", [])

    # Opening message from 内山
    _render_chat_right("こちらの問い合わせの回答をお願いします。")

    for i, step in enumerate(iteration_history):
        # --- 回答担当の草稿 ---
        draft_text = step.draft_response or ""
        if draft_text:
            # fallback badge only shown for first draft (wf_meta tracks initial run)
            draft_badge = ""
            sources = []
            if i == 0:
                if _llm_fallback:
                    draft_badge = (
                        "<span style='background:#888;color:#fff;padding:1px 8px;"
                        "border-radius:10px;font-size:0.73rem;font-weight:600;"
                        "margin-left:6px;'>テンプレート</span>"
                    )
                sources = _rag_sources
            _render_chat_left(draft_text, badge_html=draft_badge, sources=sources)

        # --- 内山のレビューコメント ---
        review_comment, key_concerns, suggestions = _parse_review_notes(step.review_notes or "")
        decision = step.decision or ""

        if review_comment:
            # Build message body
            msg_parts = [review_comment]
            if key_concerns:
                msg_parts.append("\n【指摘ポイント】\n" + "\n".join(f"・{c}" for c in key_concerns))
            if suggestions:
                msg_parts.append("\n【修正提案】\n" + suggestions)
            review_text = "\n".join(msg_parts)
            review_badge = _decision_badge_html(decision) if decision else ""
            _render_chat_right(review_text, badge_html=review_badge)

    # Final approval message if workflow ended with approval
    if final_status == "approved":
        _render_chat_right("✅ この内容で送付してください。承認します。")


def render_review_comment_card(decision: str, next_action: str, count: int, notes: str) -> None:
    review_comment, key_concerns, suggestions = _parse_review_notes(notes)
    decision_label = _decision_label(decision) if decision else html.escape(decision)

    count_str = f"{count} {T('approval.count_suffix')}".strip()
    st.markdown(
        f"""
        <div class="review-memo">
            <div class="review-meta-card">
                <div class="review-meta-label">{html.escape(T('review.decision_label'))}</div>
                <div class="review-meta-value">{decision_label}</div>
                <div class="review-meta-label">{html.escape(T('review.next_stage'))}</div>
                <div class="review-meta-value">{html.escape(next_action)}</div>
                <div class="review-meta-label">{html.escape(T('review.iter_history'))}</div>
                <div class="review-meta-value">{count_str}</div>
            </div>
            <div class="review-note-card">
                <div class="review-note-header">
                    <div class="review-note-title">{html.escape(T('review.agent_comment'))}</div>
                    <div class="review-note-badge">Review Memo</div>
                </div>
                <div class="review-note-body">{html.escape(review_comment).replace(chr(10), "<br>")}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if key_concerns:
        st.markdown(f"**{T('stage.review.concerns')}**")
        for concern in key_concerns:
            st.markdown(f"- {concern}")
    if suggestions:
        st.markdown(f"**{T('stage.review.suggestions')}**")
        st.info(suggestions)


def format_ticket_label(ticket) -> str:
    created = ticket.created_at.strftime("%m/%d %H:%M") if ticket.created_at else "-"
    return f"#{ticket.id} / {ticket.external_id} / {ticket.customer_email} / {created}"


def format_workflow_label(run) -> str:
    created = run.created_at.strftime("%m/%d %H:%M") if run.created_at else "-"
    status = _status_labels().get(getattr(run.status, "value", str(run.status)), str(run.status))
    return f"{T('run.label')} #{run.id} / {status} / {created}"


def init_state() -> None:
    defaults = {
        "selected_ticket_id": None,
        "selected_workflow_run_id": None,
        "workflow_running": False,
        "pending_workflow_ticket_id": None,
        "lang": "ja",
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

        # Language switcher (top-right)
        _, _lang_col = st.columns([5, 1])
        with _lang_col:
            _c1, _c2, _c3 = st.columns(3)
            with _c1:
                if st.button(T("lang.ja"), key="lang_ja", use_container_width=True):
                    st.session_state.lang = "ja"
                    st.rerun()
            with _c2:
                if st.button(T("lang.zh"), key="lang_zh", use_container_width=True):
                    st.session_state.lang = "zh"
                    st.rerun()
            with _c3:
                if st.button(T("lang.en"), key="lang_en", use_container_width=True):
                    st.session_state.lang = "en"
                    st.rerun()

        render_page_intro(len(tickets))

        control_left, control_right = st.columns([0.78, 1.22], gap="large")

        with control_left:
            panel_start(T("page.eyebrow"), T("panel.intake.title"), T("panel.intake.desc"))
            with st.form("create_ticket_form", clear_on_submit=True):
                now_code = datetime.now().strftime("sp-%Y%m%d%H%M%S")
                external_id = st.text_input(T("form.external_id"), value=now_code)
                customer_email = st.text_input(T("form.customer_email"), placeholder=T("form.email_placeholder"))
                subject = st.text_input(T("form.subject"), placeholder=T("form.subject_placeholder"))
                body = st.text_area(
                    T("form.body"),
                    placeholder=T("form.body_placeholder"),
                    height=160,
                )
                source = st.selectbox(T("form.source"), ["dashboard", "email", "portal", "phone"], index=0)
                submitted = st.form_submit_button(T("form.save_ticket"))

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
                st.success(T("form.ticket_saved"))
                st.rerun()
            panel_end()

        with control_right:
            panel_start(T("page.eyebrow"), T("panel.archive.title"), T("panel.archive.desc"))
            if tickets:
                ticket_ids = [ticket.id for ticket in tickets]
                current_ticket_id = st.session_state.selected_ticket_id
                if current_ticket_id not in ticket_ids:
                    current_ticket_id = ticket_ids[0]
                    st.session_state.selected_ticket_id = current_ticket_id

                selected_ticket_id = st.selectbox(
                    T("archive.target_ticket"),
                    options=ticket_ids,
                    index=ticket_ids.index(current_ticket_id),
                    format_func=lambda ticket_id: format_ticket_label(next(ticket for ticket in tickets if ticket.id == ticket_id)),
                    key="ticket_picker",
                )
                st.session_state.selected_ticket_id = selected_ticket_id

                if st.button(T("archive.run_workflow"), key="run_workflow_button", use_container_width=True):
                    st.session_state.workflow_running = True
                    st.session_state.pending_workflow_ticket_id = selected_ticket_id
                    st.rerun()

                if (
                    st.session_state.workflow_running
                    and st.session_state.pending_workflow_ticket_id == selected_ticket_id
                ):
                    render_workflow_running_card()
                    with st.spinner(T("archive.running_spinner")):
                        time.sleep(0.4)
                        workflow_run, _wf_result = run_and_persist_workflow_for_ticket(db=db, ticket_id=selected_ticket_id)
                    st.session_state.selected_workflow_run_id = workflow_run.id
                    st.session_state[f"wf_meta_{workflow_run.id}"] = {
                        "llm_fallback": _wf_result.get("llm_fallback", False),
                        "rag_sources": _wf_result.get("rag_sources", []),
                    }
                    st.session_state.workflow_running = False
                    st.session_state.pending_workflow_ticket_id = None
                    st.success(T("archive.run_saved", n=workflow_run.id))
                    st.rerun()

                workflow_runs = list_workflow_runs_for_ticket(db, selected_ticket_id, limit=30)
                if workflow_runs:
                    run_ids = [run.id for run in workflow_runs]
                    current_run_id = st.session_state.selected_workflow_run_id
                    if current_run_id not in run_ids:
                        current_run_id = run_ids[0]
                        st.session_state.selected_workflow_run_id = current_run_id

                    selected_run_id = st.selectbox(
                        T("archive.display_run"),
                        options=run_ids,
                        index=run_ids.index(current_run_id),
                        format_func=lambda run_id: format_workflow_label(next(run for run in workflow_runs if run.id == run_id)),
                        key="run_picker",
                    )
                    st.session_state.selected_workflow_run_id = selected_run_id
                else:
                    st.info(T("archive.no_runs"))
                    st.session_state.selected_workflow_run_id = None
            else:
                st.info(T("archive.no_tickets"))
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
        first_draft = first_step.draft_response if first_step else None
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

        render_flow_stage("01", T("stage.monitor.kicker"), T("stage.monitor.title"), T("stage.monitor.copy"), active=active_stage == "01")
        monitor_left, monitor_right = st.columns([1.2, 0.8], gap="large")
        with monitor_left:
            st.markdown(
                f"<div class='ticket-monitor-body'><div class='monitor-block-title'>{html.escape(T('monitor.subject'))}</div><div>{html.escape(selected_ticket.subject)}</div></div>",
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
            st.markdown(
                f"<div class='ticket-monitor-body'><div class='monitor-block-title'>{html.escape(T('monitor.body'))}</div><div>{html.escape(selected_ticket.body).replace(chr(10), '<br>')}</div></div>",
                unsafe_allow_html=True,
            )
        with monitor_right:
            stat_cols = st.columns(1)
            with stat_cols[0]:
                render_compact_stat(T("monitor.status"), status_badge_html(getattr(selected_ticket.status, "value", str(selected_ticket.status))))
                render_compact_stat(T("monitor.next_action"), html.escape(next_action_label(selected_run.next_action if selected_run else None)))
                render_compact_stat(T("monitor.iterations"), f"<strong>{selected_run.iteration_count if selected_run else 0}</strong>")
                render_compact_stat(T("monitor.tracking"), html.escape(f"{selected_ticket.external_id} / {selected_ticket.customer_email}"))
        close_flow_stage()

        render_flow_divider("Chat", active=active_stage in ("02", "03", "04"))

        render_flow_stage(
            "02–04",
            "conversation",
            "回答担当 × 内山さん",
            "回答担当が草稿を起案し、内山さんがレビューするやり取りをチャット形式で表示します。",
            active=active_stage in ("02", "03", "04"),
        )
        if selected_run is None:
            st.info(T("stage.draft.empty"))
        else:
            st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
            _wf_meta = st.session_state.get(f"wf_meta_{selected_run.id}", {})
            _final_status = getattr(selected_run.status, "value", str(selected_run.status))
            if iteration_history:
                render_chat_workflow(iteration_history, _final_status, _wf_meta)
                # Copy button for the final draft (last step's draft)
                _last_draft = iteration_history[-1].draft_response or ""
                render_copy_button(_last_draft, "final-draft")
            else:
                st.info(T("stage.draft.no_content"))
        close_flow_stage()

        render_flow_stage("05", T("stage.approval.kicker"), T("stage.approval.title"), T("stage.approval.copy"), active=active_stage == "05")
        approval_left, approval_right = st.columns([0.72, 1.28], gap="large")
        with approval_left:
            if selected_run is None:
                st.info(T("approval.no_run"))
            else:
                if approval_actions:
                    approval_df = pd.DataFrame(
                        [
                            {
                                T("approval.col.approver"): item.approver,
                                T("approval.col.action"): item.action,
                                T("approval.col.notes"): item.notes or "-",
                                T("approval.col.datetime"): item.created_at.strftime("%Y-%m-%d %H:%M") if item.created_at else "-",
                            }
                            for item in approval_actions
                        ]
                    )
                    st.dataframe(approval_df, use_container_width=True, hide_index=True)
                else:
                    st.info(T("approval.no_history"))

                needs_approval = getattr(selected_run.status, "value", str(selected_run.status)) == "needs_human_approval"
                with st.form("approval_form"):
                    approver = st.text_input(T("approval.approver"), value="team.lead@company.com")
                    notes = st.text_input(T("approval.notes"), value=T("approval.notes_default"))
                    approved = st.form_submit_button(T("approval.submit"), disabled=not needs_approval)

                if not needs_approval:
                    st.caption(T("approval.not_needed"))
                elif approved:
                    approve_workflow_run(
                        db=db,
                        workflow_run_id=selected_run.id,
                        approver=approver.strip(),
                        notes=notes.strip(),
                    )
                    st.success(T("approval.saved"))
                    st.rerun()

        with approval_right:
            if drafts is None:
                st.info(T("approval.no_drafts"))
            else:
                customer_reply = drafts.get("customer_reply_draft") or T("approval.no_customer")
                vendor_reply = drafts.get("vendor_escalation_draft") or T("approval.no_vendor")
                internal_summary = drafts.get("internal_summary") or T("approval.no_summary")
                out1, out2, out3 = st.tabs([T("approval.tab.customer"), T("approval.tab.vendor"), T("approval.tab.summary")])
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
