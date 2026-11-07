"""Find opt-in notices and present analyzed application dates without inventing them."""

import re
import hashlib

from notice_ai import grounded_date
from notice_dates import post_dates, extract_dates, reconcile_dates, deadline_past
from task_extraction import blocks, sources


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


def relevant(item):
    return (item.get('proposed_task_status', item.get('task_status')) == 'optional'
            or item.get('deadline_kind') in APPLICATION_KINDS)


def activity_groups(post, items):
    """Scope each activity before reconciling dates, including cached analyses."""
    texts = sources(post)
    created = post.get('raw', {}).get('creationTime', '')
    groups, matched = [], set()
    for source, text in texts.items():
        sections = blocks(text)
        for section in sections:
            selected = []
            for index, item in enumerate(items):
                quote = item.get('task_evidence') or ''
                title_match = item.get('title') == section['title']
                if ((item.get('task_evidence_source') or 'post') == source and quote
                        and quote in section['text']
                        and (sum(quote in other['text'] for other in sections) == 1
                             or (title_match and sum(other['title'] == item['title'] for other in sections) == 1))):
                    selected.append(item)
                    matched.add(index)
            scoped = {**post, 'title': section['title'], 'text': section['text'], 'attachments': []}
            if not any(relevant(item) for item in selected) and not candidate(scoped):
                continue
            groups.append({'title': section['title'], 'items': selected, 'source': source,
                           'dates': extract_dates(section['text'], created, source),
                           'refs': [{'title': section['title'], 'evidence': section['text'][:500], 'source': source}]})
        if sections and groups:
            # Source sections already recover the children of an overly broad
            # cached answer. Do not add that answer as a duplicate whole notice.
            matched.update(index for index, item in enumerate(items)
                           if (item.get('task_evidence_source') or 'post') == source
                           and item.get('task_evidence')
                           and any(item['task_evidence'] in section['text'] or section['text'] in item['task_evidence']
                                   for section in sections))
    # With no clear source sections, keep the individual answers already
    # extracted by AI. Never merge different activities merely because their
    # application deadlines happen to fall on the same day.
    named = {}
    for index, item in enumerate(items):
        if index in matched or not relevant(item) or not item.get('title'):
            continue
        if groups and item['title'] == post.get('title'):
            continue
        source = item.get('task_evidence_source') or 'post'
        named.setdefault((source, item['title']), []).append(item)
    if groups or len(named) > 1:
        for (source, title), selected in named.items():
            dates = []
            for item in selected:
                for field, source_field in (('deadline_evidence', 'deadline_evidence_source'),
                                            ('task_evidence', 'task_evidence_source')):
                    quote = item.get(field) or ''
                    quote_source = item.get(source_field) or 'post'
                    if quote and quote in texts.get(quote_source, ''):
                        dates.extend(extract_dates(quote, created, quote_source))
            groups.append({'title': title, 'items': selected, 'source': source, 'dates': dates, 'refs': []})
    return groups


def activity_row(post, items, extracted, analyzed, today, title, identity, refs):
    optional = [item for item in items if relevant(item)]
    dates = []
    for item in items:
        kind = item.get('deadline_kind', 'unknown')
        if kind not in (*APPLICATION_KINDS, 'event'):
            continue
        dates.append({'kind': kind, 'date': item.get('deadline') or item.get('proposed_deadline'),
                      'confirmed': confirmed_date(item), 'expression': item.get('deadline_expression'),
                      'evidence': item.get('deadline_evidence'), 'source': item.get('deadline_evidence_source'),
                      'action': item.get('action', ''), 'method': 'ai', 'flags': item.get('review_flags', [])})
    dates = reconcile_dates(dates, extracted)
    applications = [d for d in dates if d['kind'] in APPLICATION_KINDS]
    future = [d['date'] for d in applications if d['date'] and not deadline_past(d['date'], today)]
    known = [d['date'] for d in applications if d['date']]
    refs = refs + [{'title': item.get('title'), 'evidence': item.get('task_evidence'),
                    'source': item.get('task_evidence_source') or 'post'} for item in optional]
    return {'id': identity, 'postId': f"{post['course_id']}:{post['source']}:{post['id']}",
            'title': title, 'courseId': post['course_id'], 'courseName': post.get('course_name', ''),
            'category': category(title), 'analyzed': analyzed, 'datesExtracted': bool(extracted),
            'optionalConfirmed': any(i.get('task_status') == 'optional' for i in optional),
            'action': optional[0].get('action', '') if optional else '신청 대상과 조건을 원문에서 확인하세요.',
            'audience': list(dict.fromkeys(i['audience'] for i in optional if i.get('audience'))),
            'dates': dates, 'nextDeadline': min(future) if future else (max(known) if known else None),
            'closed': bool(applications) and all(d['confirmed'] and d['date'] and deadline_past(d['date'], today) for d in applications),
            'past': bool(applications) and all(d['date'] and deadline_past(d['date'], today) for d in applications),
            'created': post.get('raw', {}).get('creationTime', ''), 'itemRefs': refs}


def collect(jobs, cache, today):
    result = []
    for job in jobs:
        post = job["post"]
        record = cache.get(job["key"])
        analyzed = bool(record and record["status"] == "success")
        items = record["result"]["items"] if analyzed else []
        optional = [i for i in items if relevant(i)]
        if not optional and not candidate(post):
            continue
        groups = activity_groups(post, items)
        if groups:
            post_id = f"{post['course_id']}:{post['source']}:{post['id']}"
            for group in groups:
                key = group['source'] + '\n' + group['title']
                identity = post_id + ':activity:' + hashlib.sha256(key.encode()).hexdigest()[:24]
                result.append(activity_row(post, group['items'], group['dates'], analyzed and bool(group['items']),
                                           today, group['title'], identity, group['refs']))
            continue
        # Successfully analyzed compulsory/reference notices aren't advertised as opportunities.
        extracted = post_dates(post)
        if analyzed and not optional and not extracted:
            continue
        title = post.get('title') or post.get('text', '').split('\n', 1)[0][:100]
        identity = f"{post['course_id']}:{post['source']}:{post['id']}"
        result.append(activity_row(post, items, extracted, analyzed, today, title, identity, []))
    return sorted(result, key=lambda o: (o["closed"], not o["analyzed"], o["nextDeadline"] is None,
                                         o["nextDeadline"] or "", -(int(re.sub(r"\D", "", o["created"])[:14] or 0))))
