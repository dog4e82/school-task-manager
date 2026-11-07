"""Recover distinct tasks and their own schedules from saved source text.

This is a read-time correction layer. It never changes cached AI results or
copies an unrelated post's deadline as a confirmed deadline.
"""

import re
from copy import deepcopy

from notice_dates import DATE, dated_span, endpoint, published_day


ACTION = re.compile(r"제출|수행평가|평가내용|작성|수행해|수행하|발표|신청")
OPTIONAL = re.compile(r"선택|자율|희망자|원하는|필수\s*아니|참여할\s*수")
TIERS = (
    r"^[ \t]*(?:\[\s*과제\s*\d+[^\]\n]*\].*|과제\s*\d+\s*[:.)].*)$",
    r"^[ \t]*과정\s*\d+\s*[.:：].*$",
    r"^[ \t]*1[).]\s*(?:평가영역(?:\s*\([^\n)]*\))?|주제)\s*[:：].*$",
    r"^[ \t]*\[[^\]\n]*(?:수행평가|과제)[^\]\n]*\][ \t]*$",
)
SUBMISSION = re.compile(r"(?:제출\s*(?:마감(?:일|시간)?|기한|기일|기간|일시)|마감일|제출일|제출마감시간|발표\s*자료\s*제출|제출)\s*[:：]\s*")
ACTIVITY = re.compile(r"(?:서술평가|수행평가|평가\s*일시|발표|일시|실시기간|변경\s*기간)\s*[:：]\s*")
ONGOING = re.compile(r"수시(?:로)?[^\n.]*|틈날\s*때\s*마다|틈날때\s*마다|상시")
PERIOD_TEXT = re.compile(r"(?:\d{1,2}월\s*(?:마지막\s*주|[첫둘셋넷다섯한두세네]+째\s*주)[^\n.]*|\d{1,2}월\s*\d{1,2}일부터\s*\d{1,2}일까지)")


def sources(post):
    result = {"post": post.get("text", "")}
    for attachment in post.get("attachments", []):
        for page in attachment.get("pages", []):
            result[f"pdf:{attachment.get('file_id')}:{page['page']}"] = page.get("text", "")
    return result


def blocks(text):
    for pattern in TIERS:
        anchors = list(re.finditer(pattern, text, re.M))
        if len(anchors) < 2:
            continue
        result = []
        for index, anchor in enumerate(anchors):
            end = anchors[index+1].start() if index+1 < len(anchors) else len(text)
            body = text[anchor.start():end].strip()
            if not ACTION.search(body):
                continue
            title = re.sub(r"^\s*(?:1[).]\s*(?:평가영역(?:\([^)]*\))?|주제)\s*[:：]\s*)", "", anchor.group()).strip()
            result.append({"title": title[:200], "text": body})
        if len(result) >= 2:
            return result
    return []


def rule_item(block, source, index):
    optional = bool(OPTIONAL.search(block["text"]))
    return {"title": block["title"], "action": block["title"],
            "task_status": "optional" if optional else "required",
            "proposed_task_status": "optional" if optional else "required",
            "task_evidence": block["text"][:500], "task_evidence_source": source,
            "deadline_kind": "submission", "review_flags": [], "audience": "",
            "source_extracted": True, "source_item_key":f"{source}:section:{index}", "_block_text": block["text"]}


def split_items(post, existing):
    result = deepcopy(existing or [])
    for source, text in sources(post).items():
        sections = blocks(text)
        if not sections:
            continue
        matched = set()
        kept = []
        for item in result:
            quote = item.get("task_evidence") or ""
            indices = [i for i,b in enumerate(sections) if quote and quote in b["text"]]
            if (item.get("task_evidence_source") or "post") != source:
                kept.append(item)
            elif len(indices) == 1:
                item["_block_text"] = sections[indices[0]]["text"]
                matched.add(indices[0])
                kept.append(item)
            elif quote and any(b["text"] in quote for b in sections):
                # A broad extraction spanning several tasks is replaced by children.
                continue
            elif item.get("title") == post.get("title"):
                continue
            else:
                kept.append(item)
        result = kept + [rule_item(b,source,i) for i,b in enumerate(sections) if i not in matched]
    if not result and post["source"] == "coursework":
        result = [{"title":post.get("title", ""), "action":post.get("title", ""),
                   "task_status":"pending", "proposed_task_status":"pending",
                   "deadline_kind":"submission", "review_flags":[], "source_extracted":True}]
    return result


def scoped_text(item, texts):
    source = item.get("deadline_evidence_source") or item.get("task_evidence_source") or "post"
    text = texts.get(source, "")
    block = item.get("_block_text")
    if block and source == (item.get("task_evidence_source") or "post"):
        text = block
    quote = item.get("deadline_evidence")
    if quote and re.sub(r"\s+", " ", quote).strip() in re.sub(r"\s+", " ", text):
        # Prefer the exact quoted schedule; don't borrow a neighbour's date.
        return quote, source
    if block:
        return block, source
    quote = item.get("task_evidence") or ""
    if quote and quote in text:
        start = text.index(quote)
        before = text.rfind("\n\n", 0, start)
        end = text.find("\n\n", start + len(quote))
        return text[before+2 if before >= 0 else 0:end if end >= 0 else len(text)], source
    return text, source


def schedules(text, created, source, activity=False):
    result = []
    cues = list(SUBMISSION.finditer(text))
    if activity:
        cues += list(ACTIVITY.finditer(text))
    for cue in cues:
        span = dated_span(text, cue.end(), created)
        if span:
            qualifier = re.match(r"\s*(?:중\s*\d+\s*시간|수업\s*시간[^\n.]*)",text[span["end"]:])
            expression_end = span["end"] + (qualifier.end() if qualifier else 0)
            result.append({**span, "source":source, "expression":text[span["begin"]:expression_end].strip(),
                           "evidence":text[cue.start():span["end"]],
                           "activity":cue.re is ACTIVITY})
    # The AI may have quoted only the exact date expression, without its label.
    if not result and DATE.match(text.strip()):
        span = dated_span(text.strip(), 0, created)
        if span:
            result.append({**span, "source":source, "expression":text.strip(), "evidence":text.strip(), "activity":activity})
    # Date before instruction: '11월 13일까지 보고서를 제출하세요'.
    if not result:
        for match in DATE.finditer(text):
            published = published_day(created)
            span = endpoint(match,text,published.year if published else None)
            if span and re.match(r"\s*까지[^\n]{0,45}제출",text[span["end"]:]):
                result.append({**span,"start":None,"source":source,"expression":text[match.start():span["end"]],
                               "evidence":text[match.start():span["end"]+45],"activity":False})
    unique = {}
    for entry in result:
        unique[(entry["date"], entry.get("start"))] = entry
    return list(unique.values())


def linked_report(item, post, posts):
    quote = item.get("task_evidence") or ""
    if not re.search(r"(?:최종\s*)?보고서\s*제출할\s*때.{0,20}함께", quote):
        return None
    text = post.get("title", "") + "\n" + post.get("text", "")
    tokens = set(re.findall(r"[가-힣]{2,}", text)) - {"보고서", "최종", "제출", "제출할", "함께", "관련", "자료는", "안내", "기간", "기간에"}
    candidates = []
    for other in posts:
        if other["id"] == post["id"] or other["course_id"] != post["course_id"] or other["source"] != "coursework" or not other.get("due_at"):
            continue
        title = other.get("title", "")
        if any(len(token)>=2 and token in title for token in tokens):
            candidates.append(other)
    if len(candidates) == 1:
        other = candidates[0]
        return {"date":other["due_at"],"url":other.get("original_url"),"title":other.get("title"),"confirmed":False}
    return None


def derive_items(post, existing, posts):
    result = split_items(post, existing)
    texts = sources(post)
    created = post.get("raw",{}).get("creationTime", "")
    sections = blocks(post.get("text", ""))
    for item in result:
        kind = item.get("deadline_kind", "submission")
        status = item.get("proposed_task_status",item.get("task_status", "unknown"))
        item.setdefault("review_flags", [])
        item["resolved_due"] = item.get("deadline") or item.get("proposed_deadline")
        item["resolved_confirmed"] = bool(item.get("deadline"))
        item["api_due"] = False
        if status == "reference":
            item["resolved_due"] = None
            continue
        text, source = scoped_text(item,texts)
        activity = kind == "event" or bool(re.search(r"서술평가|발표\s*참여|종목\s*변경",item["title"]))
        dates = schedules(text,created,source,activity or bool(item.get("source_item_key")))
        if activity:
            dates = [d for d in dates if d["activity"]]
        if len(dates) == 1:
            selected = dates[0]
            item.update(resolved_due=selected["date"],resolved_confirmed=selected["confirmed"],
                        deadline_expression=selected["expression"],deadline_evidence=selected["evidence"],
                        deadline_evidence_source=source, schedule_start=selected.get("start"),
                        schedule_type="window" if selected.get("start") else "event" if activity else "dated")
            item["review_flags"] = sorted(set(item["review_flags"]+selected["flags"]))
        elif len(dates)>1:
            item["resolved_confirmed"] = False
            item["review_flags"].append("source_date_conflict")
        official = post.get("due_at")
        # One registered submission may contain several deliverables. Event/practice
        # stages and independently dated blocks never inherit its submission time.
        eligible = kind == "submission" and not activity and (not sections or (
            item.get("resolved_due") and official and item["resolved_due"][:10] == official[:10]))
        if official and eligible:
            original = item.get("resolved_due")
            if original and (original[:10] != official[:10] or ("T" in original and original != official)):
                item["deadline_alternatives"] = [original]
                item["review_flags"].append("classroom_deadline_conflict")
            item.update(resolved_due=official,resolved_confirmed=not bool(item.get("deadline_alternatives")),api_due=True)
        if not item.get("resolved_due"):
            ongoing = ONGOING.search(text)
            period = PERIOD_TEXT.search(text)
            if ongoing:
                item.update(schedule_type="ongoing",schedule_text=ongoing.group())
            elif period:
                item.update(schedule_type="period",schedule_text=period.group())
            else:
                related = linked_report(item,post,posts)
                if related:
                    item.update(resolved_due=related["date"],resolved_confirmed=False,
                                related_deadline=related,schedule_type="related")
                    item["review_flags"].append("related_deadline_proposal")
        item.pop("_block_text",None)
    return result
