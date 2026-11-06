"""Combine registered work and distinct application deadlines for one dashboard."""

import hashlib


def combine(tasks, opportunities):
    opportunity_ids = {o["postId"] for o in opportunities}
    result = [{**t, "type": "task"} for t in tasks if t["status"] != "reference" and not (
        t["postId"] in opportunity_ids and (t["status"] == "optional" or t["deadlineKind"] in ("registration", "local_signup", "event")))]
    for opportunity in opportunities:
        for index, entry in enumerate(opportunity["dates"]):
            if entry["kind"] not in ("registration", "local_signup") or not entry.get("date"):
                continue
            key = f"{opportunity['postId']}:{entry['kind']}:{entry.get('source')}:{index}"
            result.append({"id": "application-" + hashlib.sha256(key.encode()).hexdigest()[:24],
                           "type": "opportunity", "category": opportunity["category"], "postId": opportunity["postId"],
                           "courseId": opportunity["courseId"], "courseName": opportunity["courseName"],
                           "title": opportunity["title"], "status": "optional", "group": "optional",
                           "action": entry.get("action") or ("교내 참여 의사 전달" if entry["kind"] == "local_signup" else "참가 대상과 접수 방법을 원문에서 확인하세요."),
                           "audience": " / ".join(opportunity["audience"]), "due": entry["date"], "apiDue": False,
                           "analyzed": opportunity["analyzed"], "deadlineConfirmed": entry["confirmed"],
                           "deadlineKind": entry["kind"], "deadlineExpression": entry.get("expression"),
                           "deadlineEvidence": entry.get("evidence"), "deadlineEvidenceSource": entry.get("source"),
                           "evidence": None, "evidenceSource": None, "flags": entry.get("flags", []),
                           "dateMethod": entry.get("method", "ai")})
    return result
