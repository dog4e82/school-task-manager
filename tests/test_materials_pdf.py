import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from googleapiclient.errors import HttpError
from httplib2 import Response
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import classroom_pdf
from classroom_data import collect_snapshot
from notice_ai import DEFAULT_MODEL, prepare, validate, grounded_date, relative_date


def pdf_bytes(text="Apply by 2026-11-13", blank_second=False, password=None):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    if text:
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(content)
    if blank_second:
        writer.add_blank_page(width=300, height=200)
    if password:
        writer.encrypt(password)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


class MaterialsAndPdfTests(unittest.TestCase):
    def test_materials_detail_body_and_all_pages_collected(self):
        service = Mock()
        service.courses.return_value.courseWork.return_value.list.return_value.execute.return_value = {}
        service.courses.return_value.announcements.return_value.list.return_value.execute.return_value = {}
        resource = service.courses.return_value.courseWorkMaterials.return_value
        resource.list.return_value.execute.side_effect = [
            {"courseWorkMaterial": [{"id": "m1", "title": "대회 안내", "description": "참가 신청 상세 기한"}], "nextPageToken": "next"},
            {"courseWorkMaterial": [{"id": "m2", "title": "두 번째 자료", "description": "본문"}]},
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            snapshot = collect_snapshot(service, [{"id": "c"}], include_materials=True)
        self.assertEqual(len(snapshot["materials"]), 2)
        self.assertEqual(snapshot["materials"][0]["text"], "참가 신청 상세 기한")
        self.assertEqual(snapshot["materials"][0]["source"], "material")
        self.assertEqual(resource.list.call_args.kwargs["pageToken"], "next")

    def test_real_pdf_text_extraction_keeps_page_number(self):
        result = classroom_pdf.extract_pdf(pdf_bytes())
        self.assertEqual(result["status"], "text_extracted")
        self.assertEqual(result["pages"][0]["page"], 1)
        self.assertIn("2026-11-13", result["pages"][0]["text"])

    def test_scanned_blank_and_partly_unreadable_pdf_not_marked_complete(self):
        self.assertEqual(classroom_pdf.extract_pdf(pdf_bytes(text=""))["status"], "ocr_needed")
        result = classroom_pdf.extract_pdf(pdf_bytes(blank_second=True))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["unread_pages"], [2])

    def test_encrypted_or_broken_pdf_returns_explicit_failure(self):
        self.assertEqual(classroom_pdf.extract_pdf(pdf_bytes(password="private"))["status"], "encrypted")
        self.assertEqual(classroom_pdf.extract_pdf(b"not a pdf")["status"], "parse_failed")

    def test_external_links_are_not_fetched(self):
        drive = Mock()
        ref = {"file_id": None, "title": "외부 사이트", "url": "https://example.invalid/a.pdf", "status": "external_link_not_read"}
        result = classroom_pdf.read_attachment(drive, ref, Path("unused-cache"))
        self.assertEqual(result["status"], "external_link_not_read")
        drive.files.assert_not_called()

    def test_pdf_download_reused_by_drive_revision(self):
        drive = Mock()
        drive.files.return_value.get.return_value.execute.return_value = {
            "id": "file", "name": "guide.pdf", "mimeType": "application/pdf", "size": "1000",
            "version": "1", "capabilities": {"canDownload": True}}
        ref = {"file_id": "file", "title": "guide.pdf", "url": "https://drive.google.com/file/d/file/view", "status": "not_read"}

        def downloader(buffer, request, chunksize):
            def chunk(num_retries):
                buffer.write(pdf_bytes())
                return None, True
            return Mock(next_chunk=chunk)

        with TemporaryDirectory() as directory, patch.object(classroom_pdf, "MediaIoBaseDownload", side_effect=downloader):
            first = classroom_pdf.read_attachment(drive, ref, Path(directory))
            second = classroom_pdf.read_attachment(drive, ref, Path(directory))
        self.assertEqual(first["pages"], second["pages"])
        self.assertEqual(first["status"], "text_extracted")
        drive.files.return_value.get_media.assert_called_once()

    def test_non_pdf_and_large_pdf_never_downloaded(self):
        drive = Mock()
        ref = {"file_id": "file", "title": "guide.hwpx", "url": None, "status": "not_read"}
        self.assertEqual(classroom_pdf.read_attachment(drive, ref, Path("unused"))["status"], "unsupported")
        ref["title"] = "guide.pdf"
        drive.files.return_value.get.return_value.execute.return_value = {
            "mimeType": "application/pdf", "size": str(classroom_pdf.MAX_BYTES + 1), "capabilities": {"canDownload": True}}
        self.assertEqual(classroom_pdf.read_attachment(drive, ref, Path("unused"))["status"], "size_limit")
        drive.files.return_value.get_media.assert_not_called()

    def test_drive_api_disabled_diagnosed_without_error_body(self):
        drive = Mock()
        drive.files.return_value.get.return_value.execute.side_effect = HttpError(Response({"status": "403"}), b'{"error":{"message":"private-token","details":[{"reason":"SERVICE_DISABLED"}]}}')
        ref = {"file_id": "file", "title": "guide.pdf", "url": None, "status": "not_read"}
        result = classroom_pdf.read_attachment(drive, ref, Path("unused"))
        self.assertEqual(result["status"], "drive_api_disabled")
        self.assertNotIn("private-token", json.dumps(result))


class AnswerFirstTests(unittest.TestCase):
    def payload(self, text="본문", pages=None):
        material = {"id": "m", "course_id": "c", "source": "material", "title": "대회 안내", "text": text,
                    "raw": {"creationTime": "2026-10-20T02:00:00Z"}, "attachments": pages or []}
        return prepare({"assignments": [], "announcements": [], "materials": [material]}, DEFAULT_MODEL, "https://example.invalid")[0]

    def test_registration_period_end_is_not_confused_with_event_date(self):
        evidence = "신청기간: 2026. 10. 5.(월) - 2026. 10. 25.(일)"
        self.assertTrue(grounded_date("2026-10-25", evidence, "registration"))
        self.assertFalse(grounded_date("2026-10-05", evidence, "registration"))
        self.assertFalse(grounded_date("2026-10-25", "행사일: 2026. 10. 25.", "event"))

    def test_user_example_offers_registration_date_and_separate_local_relative_date(self):
        registration = "신청기간: 2026. 10. 5.(월) - 2026. 10. 25.(일)"
        local = "참여를 원하는 학생은 이번주 금요일까지 선생님께 말해주세요"
        job = self.payload(registration + "\n" + local)
        result = validate(json.dumps({"items": [
            {"title": "대회 온라인 신청", "action": "희망자는 온라인으로 대회를 신청하세요.", "task_status": "optional",
             "task_evidence": local, "deadline": "2026-10-25", "deadline_status": "confirmed", "deadline_kind": "registration", "deadline_evidence": registration},
            {"title": "교내 참여 의사 전달", "action": "참여를 원하는 학생은 선생님께 참여 의사를 전하세요.", "task_status": "optional",
             "task_evidence": local, "deadline": None, "deadline_status": "unknown", "deadline_kind": "local_signup", "deadline_expression": "이번주 금요일", "deadline_evidence": local},
        ]}, ensure_ascii=False), job["payload"])
        first, second = result["items"]
        self.assertEqual(first["deadline"], "2026-10-25")
        self.assertFalse(first["review_required"])
        self.assertEqual(second["task_status"], "optional")
        self.assertEqual(second["proposed_deadline"], "2026-10-23")
        self.assertIsNone(second["deadline"])
        self.assertEqual(second["deadline_expression"], "이번주 금요일")

    def test_pdf_evidence_keeps_actual_page_and_whitespace(self):
        evidence = "보고서를 2026년 11월 13일까지 제출하세요."
        attachment = {"file_id": "pdf-id", "title": "guide.pdf", "status": "text_extracted", "revision": "1", "pages": [{"page": 2, "text": evidence.replace(" ", "\n")} ]}
        job = self.payload(pages=[attachment])
        entry = {"title": "보고서 제출", "task_status": "required", "task_evidence": evidence, "task_evidence_source": "pdf:pdf-id:2",
                 "deadline": "2026-11-13", "deadline_kind": "submission", "deadline_evidence": evidence, "deadline_evidence_source": "pdf:pdf-id:2"}
        result = validate(json.dumps({"items": [entry]}, ensure_ascii=False), job["payload"])["items"][0]
        self.assertEqual(result["task_evidence_source"], "pdf:pdf-id:2")
        self.assertIn("\n", result["task_evidence"])
        self.assertFalse(result["review_required"])
        changed = self.payload(pages=[{**attachment, "revision": "2"}])
        self.assertNotEqual(job["key"], changed["key"])

    def test_unsupported_model_date_kept_as_proposal_for_cross_check(self):
        job = self.payload("보고서는 11월 13일까지 제출하세요.")
        entry = {"title": "보고서 제출", "action": "보고서를 제출하세요.", "task_status": "required", "task_evidence": "보고서는 11월 13일까지 제출하세요.",
                 "deadline": "2026-11-13", "deadline_evidence": "보고서는 11월 13일까지 제출하세요."}
        result = validate(json.dumps({"items": [entry]}, ensure_ascii=False), job["payload"])["items"][0]
        self.assertEqual(result["proposed_deadline"], "2026-11-13")
        self.assertIsNone(result["deadline"])
        self.assertTrue(result["deadline_needs_confirmation"])
        self.assertEqual(result["action"], "보고서를 제출하세요.")

    def test_relative_dates_use_original_korean_post_day(self):
        self.assertEqual(relative_date("이번주 금요일", "2026-10-19T18:00:00Z"), "2026-10-23")
        self.assertEqual(relative_date("내일", "2026-10-19T18:00:00Z"), "2026-10-21")
        self.assertIsNone(relative_date("다음에", "2026-10-20T00:00:00Z"))


if __name__ == "__main__":
    unittest.main()
