"""Extract application end dates from quoted notice text, retaining uncertainty."""

import re
from datetime import date, datetime, timedelta, timezone


SEOUL = timezone(timedelta(hours=9))
DATE = re.compile(
    r"(?<!\d)(?:(?P<year>20\d{2})\s*(?:년|[./。-])\s*)?"
    r"(?P<month>\d{1,2})\s*(?:월|[./。-])\s*(?P<day>\d{1,2})(?!\d)\s*일?\.?"
    r"(?:\s*\((?P<weekday>[월화수목금토일])(?:요일)?\))?")
TIME = re.compile(r"\s*(?P<period>오전|오후)?\s*(?P<hour>\d{1,2})"
                  r"(?::(?P<minute>\d{2})|\s*시(?:\s*(?P<kminute>\d{1,2})\s*분)?)")
CUE = re.compile(r"(?:신청|접수|등록|모집)\s*(?:기간|기한|마감(?:일|시간)?|종료(?:일|시간)?)\s*[:：]?")
RELATIVE = re.compile(r"(?:이번|다음)\s*주\s*[월화수목금토일]요일|내일|오늘")
TEACHER = re.compile(r"선생님|교사|담임|연구실|T에게|말씀|말해|알려|의사\s*(?:전달|표시)")
CONNECTOR = re.compile(r"\s*[~∼〜–—－-]\s*")


def deadline_past(value, today, reference=None):
    if not value:
        return False
    if value[:10] != today.isoformat():
        return value[:10] < today.isoformat()
    if "T" not in value:
        return False
    reference = reference or datetime.now(SEOUL)
    if reference.date() != today:
        return False
    return datetime.fromisoformat(value) < reference


def published_day(created):
    try:
        value = datetime.fromisoformat(created.replace("Z", "+00:00"))
        return value.astimezone(SEOUL).date() if value.tzinfo else None
    except (ValueError, AttributeError):
        return None


def endpoint(match, text, year=None, anchored=False):
    values = match.groupdict()
    selected_year = int(values["year"]) if values["year"] else year
    if not selected_year:
        return None
    try:
        chosen = date(selected_year, int(values["month"]), int(values["day"]))
    except ValueError:
        return None
    confirmed = bool(values["year"] or anchored)
    flags = [] if confirmed else ["year_inferred"]
    if values["weekday"] and "월화수목금토일"[chosen.weekday()] != values["weekday"]:
        confirmed = False
        flags.append("weekday_mismatch")
    end = match.end()
    time = TIME.match(text, end)
    value = chosen.isoformat()
    if time:
        hour = int(time["hour"])
        minute = int(time["minute"] or time["kminute"] or 0)
        if time["period"]:
            if not 1 <= hour <= 12:
                return None
            hour = hour % 12 + (12 if time["period"] == "오후" else 0)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return None
        value += f"T{hour:02}:{minute:02}:00+09:00"
        end = time.end()
    return {"date": value, "confirmed": confirmed, "end": end, "flags": flags}


def dated_span(text, start, created):
    first = DATE.search(text, start, start + 90)
    if not first or first.start() - start > 25:
        return None
    if not re.fullmatch(r"[\s:：~∼〜(（※\-–]*", text[start:first.start()]):
        return None
    published = published_day(created)
    left = endpoint(first, text, published.year if published else None)
    if not left:
        return None
    connector = CONNECTOR.match(text, left["end"])
    right_match = DATE.match(text, connector.end()) if connector else None
    if right_match:
        right = endpoint(right_match, text, int(left["date"][:4]), bool(first["year"]))
        if not right:
            return None
        if right["date"][:10] < left["date"][:10]:
            # Only a December -> January range can inherit a following year.
            if not right_match["year"] and first["month"] == "12" and int(right_match["month"]) == 1:
                right = endpoint(right_match, text, int(left["date"][:4]) + 1, bool(first["year"]))
            else:
                return None
        return {**right, "start": left["date"], "begin": first.start()}
    if connector:
        # A range with an unreadable endpoint must not use its start as a deadline.
        return None
    return {**left, "start": None, "begin": first.start()}


def extract_dates(text, created="", source="post"):
    result = []
    for cue in CUE.finditer(text):
        span = dated_span(text, cue.end(), created)
        if not span:
            continue
        prefix = text[max(0, cue.start() - 12):cue.start()]
        kind = "local_signup" if "교내" in prefix else "registration"
        result.append({"kind": kind, "date": span["date"], "confirmed": span["confirmed"],
                       "start": span["start"], "expression": text[span["begin"]:span["end"]].strip(),
                       "evidence": text[cue.start():span["end"]].strip(), "source": source,
                       "method": "source_text", "flags": span["flags"], "action": ""})
    # Relative dates need an actual post timestamp. They are never confirmed.
    published = published_day(created)
    for match in RELATIVE.finditer(text):
        before, after = text[max(0, match.start() - 70):match.start()], text[match.end():match.end() + 90]
        if not re.match(r"\s*(?:까지|\([^)]*\)\s*까지)", after) or not published:
            continue
        if TEACHER.search(after) and re.search(r"참가|참여|신청|희망|원하|원하는", before):
            kind = "local_signup"
        elif re.search(r"신청|접수", before + after):
            kind = "registration"
        else:
            continue
        expression = match.group()
        if expression == "내일":
            selected = published + timedelta(days=1)
        elif expression == "오늘":
            selected = published
        else:
            weekday = "월화수목금토일".index(expression[-3])
            selected = published + timedelta(days=weekday - published.weekday() + (7 if expression.startswith("다음") else 0))
        evidence = text[max(0, match.start() - 45):min(len(text), match.end() + 75)].strip()
        result.append({"kind": kind, "date": selected.isoformat(), "confirmed": False, "start": None,
                       "expression": expression, "evidence": evidence, "source": source,
                       "method": "source_text", "flags": ["relative_date"], "action": ""})
    for match in DATE.finditer(text):
        published = published_day(created)
        span = endpoint(match, text, published.year if published else None)
        if not span:
            continue
        before, after = text[max(0, match.start() - 65):match.start()], text[span["end"]:span["end"] + 70]
        if not re.match(r"\s*까지", after):
            continue
        if TEACHER.search(after) and re.search(r"참가|참여|신청|희망|원하|원하는", before):
            kind = "local_signup"
        elif re.match(r"\s*까지.{0,20}(?:신청|접수)", after, re.S):
            kind = "registration"
        else:
            continue
        result.append({"kind": kind, "date": span["date"], "confirmed": span["confirmed"], "start": None,
                       "expression": text[match.start():span["end"]].strip(),
                       "evidence": text[max(0, match.start() - 35):span["end"] + min(70, len(after))].strip(),
                       "source": source, "method": "source_text", "flags": span["flags"], "action": ""})
    return result


def post_dates(post):
    created = post.get("raw", {}).get("creationTime", "")
    result = extract_dates(post.get("text", ""), created)
    for attachment in post.get("attachments", []):
        for page in attachment.get("pages", []):
            result.extend(extract_dates(page.get("text", ""), created, f"pdf:{attachment.get('file_id')}:{page['page']}"))
    return result


def reconcile_dates(ai_dates, extracted):
    """Prefer an exact source range/time, preserve distinct stages and conflicts."""
    result = []
    for entry in ai_dates:
        matches = [d for d in extracted if d["kind"] == entry["kind"] and d["source"] == entry.get("source")
                   and ((entry.get("date") and d["date"][:10] == entry["date"][:10])
                        or (entry.get("expression") and entry["expression"] in (d.get("evidence") or "")))]
        selected = matches[0] if len(matches) == 1 else None
        result.append({**entry, **selected, "action": entry.get("action", "")} if selected else entry)
    result.extend(extracted)
    unique = []
    for entry in result:
        previous = next((d for d in unique if d["kind"] == entry["kind"] and d.get("date") and entry.get("date")
                         and d["date"][:10] == entry["date"][:10]), None)
        if previous:
            # Conflicting explicit times stay visible. A missing time can be enriched.
            if "T" in previous["date"] and "T" in entry["date"] and previous["date"] != entry["date"]:
                previous["confirmed"] = entry["confirmed"] = False
                previous["flags"] = list(set(previous.get("flags", []) + ["source_date_conflict"]))
                entry["flags"] = list(set(entry.get("flags", []) + ["source_date_conflict"]))
                unique.append(entry)
            elif (entry.get("confirmed") and not previous.get("confirmed")) or ("T" in entry["date"] and "T" not in previous["date"]):
                unique[unique.index(previous)] = entry
        else:
            unique.append(entry)
    return unique
