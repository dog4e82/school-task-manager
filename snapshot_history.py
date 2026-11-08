"""Observe per-account source changes without inventing dates or calling AI."""

import hashlib
import json
from datetime import datetime, timezone

MAX_CHANGES = 100


def post_id(post):
    return f"{post['course_id']}:{post['source']}:{post['id']}"


def indexed(snapshot):
    return {post_id(post): post for name in ('assignments', 'announcements', 'materials')
            for post in snapshot.get(name, [])}


def with_history(previous, current):
    previous = previous or {}
    before, after = indexed(previous), indexed(current)
    changes = [entry for entry in previous.get('change_history', [])
               if isinstance(entry, dict) and entry.get('post_id') in after]
    observed = current.get('fetched_at') or datetime.now(timezone.utc).isoformat()
    for key in sorted(before.keys() & after.keys()):
        old, new = before[key], after[key]
        if old.get('due_at') != new.get('due_at'):
            change = {'post_id': key, 'kind': 'registered_deadline', 'observed_at': observed,
                      'before': old.get('due_at'), 'after': new.get('due_at')}
            change['id'] = hashlib.sha256(json.dumps(change, sort_keys=True).encode()).hexdigest()[:24]
            changes.append(change)
        if (old.get('title', ''), old.get('text', '')) != (new.get('title', ''), new.get('text', '')):
            change = {'post_id': key, 'kind': 'body', 'observed_at': observed}
            # Content hashes distinguish repeated observations without keeping a
            # second copy of the notice or claiming which prose date changed.
            for label, post in (('before_hash', old), ('after_hash', new)):
                change[label] = hashlib.sha256(json.dumps([post.get('title', ''), post.get('text', '')]).encode()).hexdigest()
            change['id'] = hashlib.sha256(json.dumps(change, sort_keys=True).encode()).hexdigest()[:24]
            changes.append(change)
    return {**current, 'change_history': changes[-MAX_CHANGES:]}
