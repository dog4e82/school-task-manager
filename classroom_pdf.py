"""Read only Drive files attached to collected Classroom posts; retain page sources."""

import hashlib
import io
import json
import logging
from pathlib import Path

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from classroom_errors import error_reason


MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 50
MAX_TEXT = 200000
EXTRACTION_VERSION = 1


def references(post):
    result = []
    for material in post.get("raw", {}).get("materials", []):
        shared = material.get("driveFile", {})
        file = shared.get("driveFile", {})
        if isinstance(file, dict) and isinstance(file.get("id"), str):
            result.append({"file_id": file["id"], "title": file.get("title", ""),
                           "url": file.get("alternateLink"), "status": "not_read"})
        elif isinstance(material.get("link"), dict):
            link = material["link"]
            result.append({"file_id": None, "title": link.get("title", ""), "url": link.get("url"),
                           "status": "external_link_not_read"})
        else:
            result.append({"file_id": None, "title": "기타 첨부", "url": None, "status": "unsupported"})
    return result


def extract_pdf(data):
    # Library diagnostics can include fragments of document data. Keep them local and silent.
    logger = logging.getLogger("pypdf")
    previous_handlers, previous_propagate = logger.handlers, logger.propagate
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            return {"status": "encrypted", "pages": []}
        total = len(reader.pages)
        pages, characters, missing = [], 0, []
        for index in range(min(total, MAX_PAGES)):
            text = reader.pages[index].extract_text() or ""
            if not text.strip():
                missing.append(index + 1)
            if characters + len(text) > MAX_TEXT:
                return {"status": "partial", "pages": pages, "total_pages": total,
                        "unread_pages": missing + list(range(index + 1, total + 1)), "reason": "text_limit"}
            pages.append({"page": index + 1, "text": text})
            characters += len(text)
        missing.extend(range(MAX_PAGES + 1, total + 1))
        status = "text_extracted" if not missing else ("partial" if characters else "ocr_needed")
        return {"status": status, "pages": pages, "total_pages": total, "unread_pages": missing}
    except (PdfReadError, ValueError, TypeError, OSError, NotImplementedError):
        return {"status": "parse_failed", "pages": []}
    finally:
        logger.handlers, logger.propagate = previous_handlers, previous_propagate


def read_attachment(drive, reference, cache_dir):
    result = dict(reference)
    if not reference["file_id"]:
        return result
    suffix = Path(reference["title"]).suffix.lower()
    if suffix in (".hwp", ".hwpx", ".zip", ".ppt", ".pptx", ".doc", ".docx", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".mp4"):
        result["status"] = "unsupported"
        return result
    try:
        meta = drive.files().get(fileId=reference["file_id"], supportsAllDrives=True,
            fields="id,name,mimeType,size,modifiedTime,version,md5Checksum,capabilities/canDownload,webViewLink").execute(num_retries=0)
        result.update(title=meta.get("name", result["title"]), url=meta.get("webViewLink", result["url"]))
        if meta.get("mimeType") != "application/pdf":
            result["status"] = "unsupported"
            return result
        if meta.get("capabilities", {}).get("canDownload") is not True:
            result["status"] = "download_not_allowed"
            return result
        if int(meta.get("size", "0")) > MAX_BYTES:
            result["status"] = "size_limit"
            return result
        revision = {k: meta.get(k) for k in ("id", "modifiedTime", "version", "md5Checksum")}
        stamp = hashlib.sha256(json.dumps([EXTRACTION_VERSION, revision], sort_keys=True).encode()).hexdigest()
        cached = cache_dir / (stamp + ".json")
        if cached.exists():
            try:
                result.update(json.loads(cached.read_text(encoding="utf-8")))
                return result
            except (ValueError, OSError):
                pass
        buffer = io.BytesIO()
        download = MediaIoBaseDownload(buffer, drive.files().get_media(fileId=reference["file_id"], supportsAllDrives=True), chunksize=1024 * 1024)
        done = False
        while not done:
            _, done = download.next_chunk(num_retries=0)
            if buffer.tell() > MAX_BYTES:
                result["status"] = "size_limit"
                return result
        extracted = extract_pdf(buffer.getvalue())
        extracted["revision"] = stamp
        cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = cached.with_suffix(".tmp")
        temporary.write_text(json.dumps(extracted, ensure_ascii=False), encoding="utf-8")
        temporary.replace(cached)
        result.update(extracted)
    except HttpError as exc:
        reason = error_reason(exc)
        if reason in ("SERVICE_DISABLED", "accessNotConfigured"):
            result["status"] = "drive_api_disabled"
        elif reason == "ACCESS_TOKEN_SCOPE_INSUFFICIENT":
            result["status"] = "drive_scope_missing"
        else:
            result["status"] = "access_denied" if exc.resp.status in (401, 403, 404) else "download_failed"
    except (OSError, ValueError, TypeError):
        result["status"] = "download_failed"
    return result


def enrich_snapshot(snapshot, drive, cache_dir, checkpoint=None, post_keys=None):
    reused = {}
    counts = {}
    unavailable = None
    last_checkpoint = 0
    for post in snapshot["assignments"] + snapshot["announcements"] + snapshot.get("materials", []):
        if post_keys is not None and f"{post['course_id']}:{post['source']}:{post['id']}" not in post_keys:
            post["attachments"] = references(post)
            for attachment in post["attachments"]:
                counts[attachment["status"]] = counts.get(attachment["status"], 0) + 1
            continue
        attachments = []
        for reference in references(post):
            key = reference["file_id"]
            if key and key in reused:
                attachment = dict(reused[key])
            elif key and unavailable:
                attachment = {**reference, "status": unavailable}
            else:
                attachment = read_attachment(drive, reference, cache_dir)
                if attachment.get("status") in ("drive_api_disabled", "drive_scope_missing"):
                    unavailable = attachment["status"]
                if key:
                    reused[key] = attachment
                    print(f"첨부 확인 중: {len(reused)}개", flush=True)
            attachments.append(attachment)
            counts[attachment["status"]] = counts.get(attachment["status"], 0) + 1
        post["attachments"] = attachments
        if checkpoint and len(reused) - last_checkpoint >= 10:
            snapshot["attachment_summary"] = counts
            checkpoint(snapshot)
            last_checkpoint = len(reused)
    snapshot["attachment_summary"] = counts
    snapshot["pdf_collection_attempted"] = True
    snapshot["pdf_collection_complete"] = all(status in ("text_extracted", "unsupported", "external_link_not_read") for status in counts)
    snapshot["pdf_processing"] = False
    return counts
