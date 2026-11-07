"""Offline task-first report. Uses current upgraded-model cache entries only."""

import argparse
import html
import json
import os
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from classroom_data import SEOUL
from classroom_pdf import references
from notice_ai import Cache, DEFAULT_MODEL, prepare
from task_extraction import derive_items


ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / ".local" / "classroom"
OUTPUT = ROOT / ".local" / "analysis-results.html"


def esc(value):
    return html.escape(str(value or ""), quote=True)


def day_of(value):
    try:
        return date.fromisoformat(value[:10]) if value else None
    except (ValueError, TypeError):
        return None


def gather(jobs, cache, today):
    groups = {name: [] for name in ("tasks", "uncertain", "optional", "past", "reference", "pending")}
    analyzed = 0
    posts = [job["post"] for job in jobs]
    for job in jobs:
        post, record = job["post"], cache.get(job["key"])
        cached = bool(record and record["status"] == "success")
        if cached:
            analyzed += 1
        items = derive_items(post, record["result"]["items"] if cached else [], posts)
        for item in items:
            status = item.get("proposed_task_status", item.get("task_status", "unknown"))
            due = item.get("resolved_due")
            row = {"post":post,"item":item,"due":due,"status":status,
                   "analyzed":cached and not item.get("source_extracted"),"api_due":item.get("api_due",False)}
            group = "reference" if status == "reference" else (
                "past" if day_of(due) and day_of(due)<today else (
                    "pending" if status == "pending" and not due else
                    "tasks" if status == "required" else "optional" if status == "optional" else "uncertain"))
            groups[group].append(row)
    for rows in groups.values():
        rows.sort(key=lambda row: (row["due"] is None, row["due"] or "", row["post"].get("course_name", "")))
    return groups, analyzed


def link(url, label):
    if urlsplit(url or "").scheme != "https":
        return ""
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)} ↗</a>'


def card(row):
    post, item, status = row["post"], row["item"], row["status"]
    conditional = bool(item.get("audience")) or "obligation_unconfirmed" in item.get("review_flags", [])
    label = {"required": "대상 조건 확인" if conditional else "필수 지시", "optional": "선택 활동",
             "reference": "참고자료", "pending": "등록 과제 · AI 분석 대기", "unknown": "의무 확인 필요"}.get(status, "확인 필요")
    due = row["due"]
    due_text = str(due).replace("T", " ").replace("+09:00", " (한국 시간)") if due else ("기한 해당 없음" if status == "reference" else "기한 미정")
    if due and due == item.get("proposed_deadline") and not item.get("deadline") and not row.get("api_due"):
        due_text += " · 추정, 확인 필요"
    kind = "등록 마감" if row.get("api_due") else {"registration": "신청 마감", "local_signup": "교내 신청 기한", "event": "행사일", "publication": "공개일"}.get(item.get("deadline_kind"), "마감")
    body = [f'<article class="task"><div class="badge {esc(status)}">{esc(label)}</div>',
            f'<p class="course">{esc(post.get("course_name", ""))}</p><h3>{esc(item.get("title"))}</h3>',
            f'<p class="action">{esc(item.get("action") or item.get("title"))}</p>', f'<p class="due">{kind} · {esc(due_text)}</p>']
    if item.get("audience"):
        body.append(f'<p>대상 · {esc(item["audience"])}</p>')
    if item.get("deadline_expression"):
        body.append(f'<p>원래 기한 표현 · {esc(item["deadline_expression"])}</p>')
    if not row["analyzed"]:
        body.append('<p class="notice">Classroom에 등록된 제목·마감입니다. AI 분류와 실제 제출 완료 여부는 아직 확인하지 않았습니다.</p>')
    elif [flag for flag in item.get("review_flags", []) if not (row.get("api_due") and flag == "deadline_unverified")]:
        body.append('<p class="notice">확인 필요 · 대상 조건, 기한 해석 또는 원문 근거를 아래에서 확인하세요.</p>')
    body.append(link(post.get("original_url"), "Classroom 원문"))
    body.append('<details class="evidence"><summary>판단 근거 · 상세 본문 · PDF 출처</summary>')
    if row["analyzed"]:
        body.append(f'<p class="small">분석 모델 · {DEFAULT_MODEL}</p>')
    for field, source_field, heading in (("task_evidence", "task_evidence_source", "할 일 근거"), ("deadline_evidence", "deadline_evidence_source", "기한 근거")):
        if not item.get(field):
            continue
        body.append(f'<h4>{heading}</h4><blockquote>{esc(item[field])}</blockquote>')
        source = item.get(source_field) or "post"
        if source.startswith("pdf:"):
            _, file_id, page_number = source.split(":", 2)
            file = next((a for a in post.get("attachments", []) if a.get("file_id") == file_id), {})
            body.append(f'<p>PDF · {esc(file.get("title", "첨부파일"))} · {esc(page_number)}쪽</p>')
            body.append(link(file.get("url"), "PDF 원문"))
            page = next((p for p in file.get("pages", []) if str(p["page"]) == page_number), None)
            if page:
                body.append(f'<details><summary>해당 PDF 페이지 텍스트</summary><pre>{esc(page["text"])}</pre></details>')
    if post.get("due_at"):
        body.append(f'<p>원래 과제 API 마감 · {esc(post["due_at"])}</p>')
    body.append(f'<h4>게시물 상세 본문</h4><pre>{esc(post.get("title", ""))}\n{esc(post.get("text", ""))}</pre>')
    for attachment in post.get("attachments", references(post)):
        if attachment.get("status") != "text_extracted":
            body.append(f'<p class="small">첨부 확인 필요 · {esc(attachment.get("title", ""))} · {esc(attachment.get("status", "not_read"))}</p>')
    return "".join(body) + '</details></article>'


STYLE = '''*{box-sizing:border-box}body{margin:0;background:#f3f5fa;color:#202938;font:16px/1.7 system-ui,'Malgun Gothic',sans-serif}main{max-width:1050px;margin:auto;padding:38px 22px 80px}h1{font-size:34px;letter-spacing:-1.5px;margin:5px 0}h2{font-size:23px;margin:32px 0 15px}h3{font-size:20px;margin:8px 0}.brand{font-weight:750;color:#4d64bb}.course,.small{font-size:13px;color:#667387}.stats{display:flex;gap:12px;flex-wrap:wrap;margin:25px 0}.stat{background:white;border:1px solid #e0e5ef;border-radius:14px;padding:16px 20px;min-width:170px}.stat:first-child{background:#e7edff}.stat strong{display:block;font-size:28px}.task{background:white;border:1px solid #e0e5ed;border-radius:15px;padding:22px 25px;margin-bottom:15px}.badge{display:inline-block;background:#fff0cd;color:#8d6608;border-radius:20px;font-size:12px;font-weight:700;padding:3px 11px}.required{background:#ffe7eb;color:#a42d43}.optional{background:#e3f5eb;color:#267452}.reference{background:#e5edff;color:#355cb8}.due{font-weight:750}.notice{padding:12px 15px;background:#fff4d9;color:#70551b;border-radius:9px;font-size:13px}.evidence{border-top:1px solid #edf0f5;margin-top:15px;padding-top:12px}summary{cursor:pointer;color:#435e95;font-weight:650}blockquote{white-space:pre-wrap;padding:12px 16px;margin:8px 0;background:#f6f8fc;border-left:3px solid #a4b6df}pre{white-space:pre-wrap;font-family:inherit;background:#f7f9fc;padding:15px;font-size:14px;overflow-wrap:anywhere}a{color:#325ac1;text-underline-offset:3px}.fold{margin:22px 0;padding:17px;border:1px solid #dce3ef;border-radius:12px}.empty{padding:15px;color:#68768b}footer{font-size:13px;color:#6f7b8b;margin-top:35px}@media print{body{background:white}.task{break-inside:avoid}}'''


def export(today=None):
    source = LOCAL / "snapshot.json"
    if not source.exists():
        raise SystemExit("수집 본문이 아직 저장되지 않았습니다. sync의 본문 저장 후 보고서를 만들 수 있습니다.")
    snapshot = json.loads(source.read_text(encoding="utf-8"))
    load_dotenv(ROOT / ".env", encoding="utf-8-sig", override=False)
    provider = os.environ.get("BAZE_BASE_URL", "").strip()
    if not provider:
        raise SystemExit("BAZE_BASE_URL을 설정하세요. 보고서 생성은 API를 호출하지 않습니다.")
    jobs = prepare(snapshot, DEFAULT_MODEL, provider)
    cache = Cache(LOCAL / "analysis.sqlite3")
    today = today or datetime.now(SEOUL).date()
    try:
        groups, analyzed = gather(jobs, cache, today)
    finally:
        cache.close()
    page = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    page += '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
    page += '<title>학교 과제 · 할 일</title><style>' + STYLE + '</style></head><body><main><div class="brand">학교 과제 · 할 일</div><h1>지금 확인할 과제부터</h1>'
    page += f'<p>{today.isoformat()} 기준 · {DEFAULT_MODEL}의 현재 입력과 일치하는 분석만 반영했습니다.</p><div class="stats">'
    for label, value in (("필수·조건부 지시", len(groups["tasks"])), ("기한·의무 확인", len(groups["uncertain"])), ("선택 활동", len(groups["optional"])), ("AI 분석 완료", f"{analyzed} / {len(jobs)}")):
        page += f'<div class="stat">{esc(label)}<strong>{esc(value)}</strong></div>'
    page += f'</div><p class="notice">제출 완료 여부는 아직 조회하지 않았습니다. 아래 항목을 모두 미제출 과제로 간주하지 마세요. 미분석 게시물은 {len(jobs)-analyzed}개입니다.</p>'
    for key, heading in (("tasks", "필수·대상 조건이 있는 할 일"), ("uncertain", "기한·의무 확인이 필요한 등록 항목"), ("optional", "선택 활동·참여 신청")):
        page += f'<h2>{heading} · {len(groups[key])}개</h2>'
        page += "".join(card(row) for row in groups[key]) or '<p class="empty">현재 완료된 분석에서 해당 항목이 없습니다. 미분석 항목의 완료 여부나 의무를 추정하지 않았습니다.</p>'
    for key, heading in (("past", "기한이 지난 등록 항목 · 완료 여부 미확인"), ("pending", "기한 미정 등록 항목 · AI 분석 대기"), ("reference", "참고자료")):
        page += f'<details class="fold"><summary>{heading} · {len(groups[key])}개</summary>' + "".join(card(row) for row in groups[key]) + '</details>'
    page += f'<footer>{datetime.now(SEOUL).strftime("%Y-%m-%d %H:%M")} 저장 · 원문·PDF 링크는 인터넷과 학교 로그인이 필요합니다. 보고서 생성은 AI를 호출하지 않습니다.</footer></main></body></html>'
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(page, encoding="utf-8")
    temporary.replace(OUTPUT)
    print(f"과제 보고서: {OUTPUT}")
    print(json.dumps({"model": DEFAULT_MODEL, "analyzed_posts": analyzed, "total_posts": len(jobs), "groups": {key:len(value) for key,value in groups.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="업그레이드 모델의 과제 중심 보고서 (네트워크 요청 없음)")
    parser.add_argument("--as-of", type=date.fromisoformat)
    export(parser.parse_args().as_of)
