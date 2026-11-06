"""Read published Classroom posts; preserve originals without AI inference."""

import json
from datetime import datetime, timedelta, timezone

from googleapiclient.errors import HttpError

from classroom_errors import error_reason


SEOUL = timezone(timedelta(hours=9))


class CollectionError(Exception):
    pass


def all_pages(resource, field, **params):
    items, seen = [], set()
    while True:
        page = resource.list(pageSize=100, **params).execute(num_retries=0)
        rows = page.get(field, [])
        if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("id"), str) for r in rows):
            raise CollectionError("게시물 응답 형식 오류. 이번 수집은 저장하지 않았습니다.")
        items.extend(rows)
        token = page.get("nextPageToken")
        if not token:
            return items
        if not isinstance(token, str) or token in seen:
            raise CollectionError("게시물 페이지 정보 오류. 이번 수집은 저장하지 않았습니다.")
        seen.add(token)
        params["pageToken"] = token


def deadline(raw):
    date, time = raw.get("dueDate"), raw.get("dueTime")
    if date is None:
        return None
    # Empty TimeOfDay means midnight UTC: all omitted components are zero.
    if not isinstance(date, dict) or not isinstance(time, dict):
        return None
    try:
        moment = datetime(date["year"], date["month"], date["day"],
                          time.get("hours", 0), time.get("minutes", 0),
                          time.get("seconds", 0), time.get("nanos", 0) // 1000,
                          tzinfo=timezone.utc)
        return moment.astimezone(SEOUL).isoformat()
    except (ValueError, TypeError, KeyError):
        return None


def normalize(raw, course, kind):
    due_at = deadline(raw) if kind == "coursework" else None
    return {
        "id": raw["id"], "course_id": course["id"], "course_name": course.get("name", ""),
        "source": kind, "title": raw.get("title", ""),
        "text": raw.get("description", "") if kind in ("coursework", "material") else raw.get("text", ""),
        "original_url": raw.get("alternateLink"), "due_at": due_at,
        "task_status": "unknown", "deadline_status": "confirmed" if due_at else "unknown",
        "deadline_source": "classroom_due_fields" if due_at else None,
        "raw": raw,
    }


def sort_tasks(items):
    return sorted(items, key=lambda item: (item["due_at"] is None, item["due_at"] or "",
                                          item["course_id"], item["id"]))


def collect_snapshot(service, courses, include_materials=False):
    assignments, announcements, materials, failures = [], [], [], []
    for number, course in enumerate(courses, 1):
        print(f"수집 중: 수업 {number}/{len(courses)}")
        collected = {}
        resources = [
            ("courseWork", service.courses().courseWork(), {"courseWorkStates": ["PUBLISHED"]}),
            ("announcements", service.courses().announcements(), {"announcementStates": ["PUBLISHED"]}),
        ]
        if include_materials:
            resources.append(("courseWorkMaterial", service.courses().courseWorkMaterials(),
                              {"courseWorkMaterialStates": ["PUBLISHED"]}))
        for field, resource, states in resources:
            try:
                collected[field] = all_pages(resource, field, courseId=course["id"], **states)
            except HttpError as exc:
                reason = error_reason(exc)
                if exc.resp.status != 403 or reason != "CALLER_NO_PERMISSION":
                    raise
                # Discard this resource's partial pages, but still read other resources.
                collected[field] = []
                failures.append({"course_id": course["id"], "course_name": course.get("name", ""),
                                 "resource": field, "http_status": 403, "reason": reason})
                print(f"수업 {number}: {field} 조회 권한 없음. 이 항목은 미수집으로 기록하고 계속합니다.")
        work, posts = collected["courseWork"], collected["announcements"]
        assignments.extend(normalize(row, course, "coursework") for row in work)
        announcements.extend(normalize(row, course, "announcement") for row in posts)
        materials.extend(normalize(row, course, "material") for row in collected.get("courseWorkMaterial", []))
    return {"schema_version": 1, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "complete": not failures, "failures": failures,
            "courses": [{k: c[k] for k in ("id", "name", "alternateLink") if k in c} for c in courses],
            "assignments": sort_tasks(assignments), "announcements": announcements,
            "materials": materials, "materials_collected": include_materials}


def show_tasks(snapshot):
    print(f"저장된 수집 시각: {snapshot['fetched_at']}")
    for failure in snapshot.get("failures", []):
        name = json.dumps(failure["course_name"], ensure_ascii=False)
        print(f"미수집: {name} / {failure['resource']} (HTTP 403, 수업 조회 권한 없음)")
    if snapshot.get("failures"):
        print("일부 수업의 게시물을 읽지 못했습니다. 아래 목록은 조회에 성공한 게시물입니다.")
    print("과제·질문 목록 (마감순, 한국 시간 / 마감 미등록은 마지막)")
    for number, task in enumerate(sort_tasks(snapshot["assignments"]), 1):
        label = task["due_at"] or "마감 미등록·확인 필요"
        course = json.dumps(task["course_name"], ensure_ascii=False)
        title = json.dumps(task["title"], ensure_ascii=False)
        link = json.dumps(task["original_url"], ensure_ascii=False) if task.get("original_url") else "원문 링크 미제공"
        print(f"{number}. [{label}] {course} — {title}\n   {link}")
    if not snapshot["assignments"]:
        print("조회된 과제·질문이 없습니다.")
    print(f"공지 {len(snapshot['announcements'])}개 원문은 로컬 수집 파일에 보관했습니다.")
    print(f"자료 게시물 {len(snapshot.get('materials', []))}개 상세 본문을 보관했습니다.")
    print("제출 완료 여부·선택 과제 여부·공지 속 마감 변경은 아직 판별하지 않았습니다.")
