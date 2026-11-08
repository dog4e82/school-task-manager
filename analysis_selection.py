"""Skip elapsed deadlines, never equate an old publication date with a deadline."""
import re
from datetime import datetime, time

from classroom_data import SEOUL
from notice_dates import extract_dates, deadline_past
from task_extraction import blocks, schedules, sources, NUMBERED, NAMED_WORK, FIELD_HEADING, SUBMISSION

UNKNOWN = re.compile(r'(?:기한|마감|제출|신청|접수)[^.!?]{0,35}(?:추후|미정|별도\s*공지)|내년|다음\s*해|마감\s*연장|제출\s*연기|제출할\s*때.{0,20}함께')


def expired_for_analysis(post, today=None):
    now=datetime.now(SEOUL)
    today=today or now.date()
    reference=now if today==now.date() else datetime.combine(today,time.min,tzinfo=SEOUL)
    created=post.get('raw',{}).get('creationTime','')
    texts=sources(post)
    combined='\n'.join(texts.values())
    if UNKNOWN.search(combined):
        return False
    if re.search(r'오늘|내일|이번\s*주|다음\s*주',combined) and post.get('raw',{}).get('updateTime') not in (None,created):
        return False
    def dates(text, source):
        submissions = (schedules(text,created,source) if SUBMISSION.search(text)
                       or re.search(r'까지[^\n]{0,45}제출',text) else [])
        return extract_dates(text,created,source)+submissions
    all_dates=[value for source,text in texts.items() for value in dates(text,source) if value.get('date')]
    if any(not deadline_past(value['date'],today,reference) for value in all_dates):
        return False
    sections=[(source,section) for source,text in texts.items() for section in blocks(text)]
    if sections:
        for source,section in sections:
            found=dates(section['text'],source)
            if not found or any(not value.get('date') or not deadline_past(value['date'],today,reference) for value in found):
                return False
        return True
    # An undated child in a numbered notice must not inherit its neighbour's
    # old registered deadline and disappear from the analysis queue.
    if any(sum(not FIELD_HEADING.search(match[1]) and bool(NAMED_WORK.search(match[1]))
               for match in NUMBERED.finditer(text))>=2 for text in texts.values()):
        return False
    official=post.get('due_at') if post.get('source')=='coursework' else None
    if official:
        return deadline_past(official,today,reference)
    return bool(all_dates) and all(deadline_past(value['date'],today,reference) for value in all_dates)


def select_jobs(jobs,today=None):
    active,expired=[],[]
    for job in jobs:
        (expired if expired_for_analysis(job['post'],today) else active).append(job)
    return active,expired
