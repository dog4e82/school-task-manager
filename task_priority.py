"""Schedule useful current work first without claiming it is unfinished."""

import re
from datetime import datetime, timedelta, timezone


SEOUL = timezone(timedelta(hours=9))
ACTION = re.compile(r"제출|과제|보고서|수행평가|마감|신청|말씀|말해|발표자료|활동지")


def prioritize_posts(posts, today=None):
    today = today or datetime.now(SEOUL).date()

    def key(post):
        due = post.get("due_at")
        try:
            due_day = datetime.fromisoformat(due).astimezone(SEOUL).date() if due else None
        except ValueError:
            due_day = None
        try:
            created = datetime.fromisoformat(post.get("raw", {}).get("creationTime", "").replace("Z", "+00:00"))
            age = (today - created.astimezone(SEOUL).date()).days
            timestamp = created.timestamp()
        except ValueError:
            age, timestamp = 9999, 0
        actionable = bool(ACTION.search(post.get("title", "") + "\n" + post.get("text", "")))
        if due_day and due_day >= today:
            return (0, due_day.toordinal(), -timestamp)
        if age <= 45 and actionable:
            return (1, -timestamp, 0)
        if age <= 45:
            return (2, -timestamp, 0)
        if post["source"] == "coursework" and due_day is None:
            return (3, -timestamp, 0)
        return (4, -timestamp, 0)

    return sorted(posts, key=key)
