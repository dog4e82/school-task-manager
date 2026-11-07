"""Combine registered work and distinct application deadlines for one dashboard."""

import hashlib


def combine(tasks, opportunities):
    def replaced(task):
        for opportunity in opportunities:
            if task['postId'] != opportunity['postId']:
                continue
            if not any(d['kind'] in ('registration', 'local_signup') and d.get('date') for d in opportunity['dates']):
                continue
            if any(ref['title'] == task['title'] and ref.get('evidence') == task.get('evidence')
                   and ref.get('source') == (task.get('evidenceSource') or 'post')
                   for ref in opportunity.get('itemRefs', [])):
                return task['status'] == 'optional' or task['deadlineKind'] in ('registration', 'local_signup')
        return False
    result = [{**t, "type": "task"} for t in tasks if t['status'] != 'reference' and not replaced(t)]
    for opportunity in opportunities:
        for index, entry in enumerate(opportunity["dates"]):
            if entry["kind"] not in ("registration", "local_signup") or not entry.get("date"):
                continue
            identity = opportunity.get('id', opportunity['postId'])
            key = f"{identity}:{entry['kind']}:{entry.get('source')}:{index}"
            result.append({"id": "application-" + hashlib.sha256(key.encode()).hexdigest()[:24],
                           "type": "opportunity", "category": opportunity["category"], "postId": opportunity["postId"], "opportunityId": identity,
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
