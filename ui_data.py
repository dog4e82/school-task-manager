"""Read saved Classroom data for the local UI. No network or generation path."""

import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

from classroom_data import SEOUL
from notice_ai import DEFAULT_MODEL, post_key, prepare
from task_report import gather
from opportunities import collect as collect_opportunities, confirmed_date
from deadline_schedule import combine


class SavedAnalyses:
    def __init__(self, path):
        self.connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3) if path.exists() else None

    def get(self, key):
        if self.connection is None:
            return None
        row = self.connection.execute("SELECT status,result FROM analyses WHERE key=?", (key,)).fetchone()
        return {"status": row[0], "result": json.loads(row[1]) if row[1] else None} if row else None

    def close(self):
        if self.connection:
            self.connection.close()


def identifier(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def build_data(snapshot, cache, provider, today=None):
    today = today or datetime.now(SEOUL).date()
    jobs = prepare(snapshot, DEFAULT_MODEL, provider)
    if callable(getattr(type(cache), "preload", None)):
        cache.preload([job["key"] for job in jobs])
    groups, analyzed = gather(jobs, cache, today)
    posts = []
    for job in jobs:
        raw = job["post"]
        key = post_key(raw)
        attachments = []
        for source in raw.get("attachments", []):
            attachments.append({field: source.get(field) for field in
                                ("file_id", "title", "url", "status", "pages", "total_pages", "unread_pages")})
        posts.append({"id": key, "title": raw.get("title") or raw.get("text", "").split("\n", 1)[0][:100] or "제목 없는 게시물",
                      "courseId": raw["course_id"], "courseName": raw.get("course_name", ""), "source": raw["source"],
                      "text": raw.get("text", ""), "url": raw.get("original_url"), "due": raw.get("due_at"),
                      "created": raw.get("raw", {}).get("creationTime"), "attachments": attachments,
                      "analyzed": bool((cache.get(job["key"]) or {}).get("status") == "success")})
    tasks = []
    task_keys = Counter((post_key(row['post']), row['item'].get('source_item_key') or
                         (row['item'].get('title', '') + '\n' + (row['item'].get('task_evidence') or '')))
                        for rows in groups.values() for row in rows)
    for group, rows in groups.items():
        for row in rows:
            item, raw = row["item"], row["post"]
            source_key = post_key(raw)
            api_due = bool(row.get("api_due"))
            task_key = item.get("source_item_key") or (item.get("title", "") + "\n" + (item.get("task_evidence") or ""))
            if task_keys[(source_key, task_key)] > 1:
                # Keep existing IDs unless they previously collided. Separate
                # actions must not share completion, personal notes or dates.
                task_key += '\n' + json.dumps([item.get('deadline_kind'), item.get('task_evidence_source'),
                                               item.get('action'), item.get('deadline_evidence')], ensure_ascii=False)
            tasks.append({"id": identifier(source_key + "\n" + task_key),
                          "postId": source_key, "courseId": raw["course_id"], "courseName": raw.get("course_name", ""),
                          "title": item.get("title", ""), "action": item.get("action") or item.get("title", ""),
                          "status": row["status"], "group": group, "due": row["due"], "apiDue": api_due,
                          "analyzed": row["analyzed"], "audience": item.get("audience", ""),
                          "deadlineExpression": item.get("deadline_expression"), "deadlineKind": item.get("deadline_kind", "submission"),
                          "deadlineConfirmed": item.get("resolved_confirmed", confirmed_date(item) or api_due),
                          "sourceExtracted": bool(item.get("source_item_key")),
                          "scheduleType": item.get("schedule_type", "dated" if row["due"] else "unknown"),
                          "scheduleStart": item.get("schedule_start"), "scheduleText": item.get("schedule_text"),
                          "deadlineAlternatives": item.get("deadline_alternatives", []),
                          "relatedDeadline": item.get("related_deadline"),
                          "evidence": item.get("task_evidence"), "evidenceSource": item.get("task_evidence_source"),
                          "deadlineEvidence": item.get("deadline_evidence"), "deadlineEvidenceSource": item.get("deadline_evidence_source"),
                          "flags": item.get("review_flags", [])})
    opportunities = collect_opportunities(jobs, cache, today)
    return {"today": today.isoformat(), "generatedAt": datetime.now(SEOUL).isoformat(),
            "snapshotAt": snapshot.get("fetched_at"), "model": DEFAULT_MODEL,
            "courses": [{"id": c["id"], "name": c.get("name", "이름 없는 수업")} for c in snapshot.get("courses", [])],
            "tasks": tasks, "posts": posts, "opportunities": opportunities, "schedule": combine(tasks, opportunities),
            "stats": {"analyzed": analyzed, "totalPosts": len(jobs), "totalCourses": len(snapshot.get("courses", [])),
                      "pdf": snapshot.get("attachment_summary", {}), "collectionComplete": snapshot.get("complete", True)}}


def load_data(snapshot_path, database_path, provider, today=None):
    snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    cache = SavedAnalyses(Path(database_path))
    try:
        return build_data(snapshot, cache, provider, today)
    finally:
        cache.close()
