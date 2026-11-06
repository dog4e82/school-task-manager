"""Find opt-in notices and present analyzed application dates without inventing them."""

import re

from notice_ai import grounded_date
from notice_dates import post_dates, reconcile_dates, deadline_past


INVITATION = re.compile(r"대회|공모|경진|모집|신청|접수|희망|선택\s*활동|참여를?\s*원|참가를?\s*원")
APPLICATION_KINDS = {"registration", "local_signup"}


def confirmed_date(item):
    """An exact application date can be grounded while participation stays uncertain."""
    if item.get("deadline"):
        return True
    value = item.get("proposed_deadline")
    quote = item.get("deadline_evidence")
    kind = item.get("deadline_kind")
    return bool(value and quote and kind in APPLICATION_KINDS and grounded_date(value, quote, kind))


def candidate(post):
    text = "\n".join([post.get("title", ""), post.get("text", ""),
                      *(p.get("text", "") for a in post.get("attachments", []) for p in a.get("pages", []))])
    # A registration word inside a compulsory assignment alone doesn't make it opt-in.
    return bool(INVITATION.search(text)) and (post["source"] != "coursework" or bool(re.search(r"희망|선택|공모|대회", text)))


def category(text):
    if re.search(r"대회|공모|경진", text):
        return "competition"
    if re.search(r"탐구|연구|R&E", text, re.I):
        return "research"
    if re.search(r"캠프|특강|강연|체험|프로그램", text):
        return "program"
    return "activity"


def collect(jobs, cache, today):
    result = []
    for job in jobs:
        post = job["post"]
        record = cache.get(job["key"])
        analyzed = bool(record and record["status"] == "success")
        items = record["result"]["items"] if analyzed else []
        relevant = [i for i in items if i.get("proposed_task_status", i.get("task_status")) == "optional"
                    or i.get("deadline_kind") in APPLICATION_KINDS]
        if not relevant and not candidate(post):
            continue
        # Successfully analyzed compulsory/reference notices aren't advertised as opportunities.
        extracted = post_dates(post)
        if analyzed and not relevant and not extracted:
            continue
        dates = []
        for item in items:
            kind = item.get("deadline_kind", "unknown")
            if kind not in (*APPLICATION_KINDS, "event"):
                continue
            value = item.get("deadline") or item.get("proposed_deadline")
            dates.append({"kind": kind, "date": value,
                          "confirmed": confirmed_date(item),
                          "expression": item.get("deadline_expression"),
                          "evidence": item.get("deadline_evidence"),
                          "source": item.get("deadline_evidence_source"),
                          "action": item.get("action", ""), "method": "ai", "flags": item.get("review_flags", [])})
        dates = reconcile_dates(dates, extracted)
        applications = [d for d in dates if d["kind"] in APPLICATION_KINDS]
        future = [d["date"] for d in applications if d["date"] and not deadline_past(d["date"], today)]
        known = [d["date"] for d in applications if d["date"]]
        # An inferred date never turns the whole opportunity into a confirmed closure.
        closed = bool(applications) and all(d["confirmed"] and d["date"] and deadline_past(d["date"], today)
                                           for d in applications)
        past = bool(applications) and all(d["date"] and deadline_past(d["date"], today) for d in applications)
        result.append({"postId": f"{post['course_id']}:{post['source']}:{post['id']}",
                       "title": post.get("title") or post.get("text", "").split("\n", 1)[0][:100],
                       "courseId": post["course_id"], "courseName": post.get("course_name", ""),
                       "category": category(post.get("title", "") + "\n" + post.get("text", "")),
                       "analyzed": analyzed, "datesExtracted": bool(extracted),
                       "optionalConfirmed": any(i.get("task_status") == "optional" for i in relevant),
                       "action": relevant[0].get("action", "") if relevant else "신청 대상과 조건을 원문에서 확인하세요.",
                       "audience": list(dict.fromkeys(i["audience"] for i in relevant if i.get("audience"))),
                       "dates": dates, "nextDeadline": min(future) if future else (max(known) if known else None),
                       "closed": closed, "past": past, "created": post.get("raw", {}).get("creationTime", "")})
    return sorted(result, key=lambda o: (o["closed"], not o["analyzed"], o["nextDeadline"] is None,
                                         o["nextDeadline"] or "", -(int(re.sub(r"\D", "", o["created"])[:14] or 0))))
