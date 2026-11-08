"""Analyze long notices/PDFs in bounded pieces and retain a reusable parent result."""
from copy import deepcopy
import json

from notice_ai import (AnalysisError, Cache, MAX_CHARS, digest, find_evidence,
                       run_analysis as run_bounded, source_texts)


def fragments(text, width=24000):
    start = 0
    while start < len(text):
        end = min(len(text), start + width)
        if end < len(text):
            boundary = text.rfind('\n', start + width // 2, end)
            if boundary >= 0:
                end = boundary + 1
        yield text[start:end]
        if end == len(text):
            break
        start = max(start + 1, end - 400)


def split_job(job):
    current = job['payload']['current']
    text = current.get('text', '')
    chunks = []

    def add(value):
        if len(json.dumps(value, ensure_ascii=False)) > MAX_CHARS:
            raise AnalysisError('metadata_too_large')
        payload = {**job['payload'], 'current': value}
        chunks.append({'post': job['post'], 'payload': payload,
                       'key': digest({'parent': job['key'], 'chunk': payload})})

    if len(text) > 6000 or not current.get('documents'):
        for part in fragments(text):
            add({**current, 'text': part, 'text_partial': part != text, 'documents': []})
    base = {**current, 'text': text[:6000], 'text_partial': len(text) > 6000,
            'documents': [], 'documents_partial': True}
    active = deepcopy(base)
    page_keys = set()
    for document in current.get('documents', []):
        for page in document.get('pages', []):
            for part in fragments(page.get('text', '')):
                page_key = (document['file_id'], page['page'])
                candidate = deepcopy(active)
                target = next((doc for doc in candidate['documents'] if doc['file_id'] == document['file_id']), None)
                if target is None:
                    target = {**document, 'pages': []}
                    candidate['documents'].append(target)
                target['pages'].append({**page, 'text': part})
                if page_key in page_keys or len(json.dumps(candidate, ensure_ascii=False)) > MAX_CHARS:
                    if active['documents']:
                        add(active)
                    active = deepcopy(base)
                    active['documents'] = [{**document, 'pages': [{**page, 'text': part}]}]
                    page_keys = {page_key}
                else:
                    active = candidate
                    page_keys.add(page_key)
    if active['documents']:
        add(active)
    if not chunks:
        add({**current, 'documents': []})
    return chunks


def merge_results(job, records):
    sources = source_texts(job['payload'])
    items, relations, seen = [], [], set()
    for record in records:
        if not record or record['status'] != 'success':
            continue
        for original in record['result']['items']:
            item = deepcopy(original)
            for field, source_field in (('task_evidence', 'task_evidence_source'), ('deadline_evidence', 'deadline_evidence_source')):
                quote = item.get(field)
                if quote and not find_evidence(quote, item.get(source_field) or 'post', sources)[1]:
                    item[field] = None
                    item.setdefault('review_flags', []).append('chunk_quote_unverified')
                    if field == 'task_evidence':
                        item['task_status'] = 'unknown'
                    else:
                        item['deadline'] = None
                        item['deadline_status'] = 'unknown'
            identity = json.dumps([item.get(field) for field in ('title', 'action', 'task_evidence', 'task_evidence_source',
                                                               'deadline_kind', 'deadline', 'proposed_deadline')], sort_keys=True)
            if identity not in seen:
                seen.add(identity)
                items.append(item)
        for relation in record['result'].get('relations', []):
            if relation not in relations and relation.get('evidence') in sources['post']:
                relations.append(relation)
    return {'items': items, 'relations': relations}


def run_extended_analysis(client, cache, jobs, model, limit=None, retry_failed=False,
                          dry_run=False, progress=None, minimum_credits=None, stop_requested=None):
    large, normal = [], []
    for job in jobs:
        (large if len(json.dumps(job['payload']['current'], ensure_ascii=False)) > MAX_CHARS else normal).append(job)
    if not large:
        return run_bounded(client, cache, jobs, model, len(jobs) if limit is None else limit,
                           retry_failed, dry_run, progress, minimum_credits, stop_requested)
    if callable(getattr(type(cache), 'preload', None)):
        cache.preload([job['key'] for job in jobs])
    records = {job['key']: cache.get(job['key']) for job in large}
    plans = {job['key']: split_job(job) for job in large
             if not dry_run and not (records[job['key']] and records[job['key']]['status'] == 'success')}
    budget = limit if limit is not None else len(normal) + sum(len(parts) for parts in plans.values())
    report = run_bounded(client, cache, normal, model, budget, retry_failed, dry_run,
                         progress, minimum_credits, stop_requested)
    report['total'] = len(jobs)
    report['chunked_posts'] = len(large)
    for index, job in enumerate(large):
        record = records[job['key']]
        if record and record['status'] == 'success':
            report['cached'] += 1
            continue
        blocked = record and record['status'] != 'partial' and (not retry_failed or record['status'] == 'processing')
        blocked = blocked or (record and record['status'] == 'partial' and record['result'].get('requires_retry') and not retry_failed)
        if blocked:
            report['skipped'] += 1
            continue
        if dry_run or report.get('stopped') or report['calls'] >= budget:
            report['pending'] += 1
            continue
        claimed = cache.claim(job, model, retry_failed)
        if not claimed and record and record['status'] == 'partial':
            with cache.conn:
                claimed = bool(cache.conn.execute("UPDATE analyses SET status='processing' WHERE key=? AND status='partial'", (job['key'],)).rowcount)
        if not claimed:
            report['skipped'] += 1
            continue
        before_calls = report['calls']
        def relay(value):
            if progress:
                progress({**report, 'calls': before_calls + value['calls']})
        try:
            sub = run_bounded(client, cache, plans[job['key']], model, budget - report['calls'],
                              retry_failed, False, relay, minimum_credits, stop_requested)
            children = [Cache.get(cache, part['key']) for part in plans[job['key']]]
            complete = all(child and child['status'] == 'success' for child in children)
            merged = merge_results(job, children)
            merged['chunk_count'] = len(children)
            merged['requires_retry'] = any(child and child['status'] in ('failed', 'invalid', 'uncertain') for child in children)
            cache.finish(job['key'], 'success' if complete else 'partial', merged)
            for field in ('calls', 'succeeded', 'failed'):
                report[field] += sub[field]
            if not complete:
                report['pending'] += 1
            if sub.get('stopped'):
                report['stopped'] = sub['stopped']
        except BaseException:
            # Saved children remain reusable; never label an incomplete parent
            # successful or repeat a failed/uncertain child automatically.
            cache.finish(job['key'], 'partial', {'items': [], 'relations': [], 'requires_retry': False})
            raise
    return report
