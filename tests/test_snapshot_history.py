from copy import deepcopy
import unittest

from snapshot_history import MAX_CHANGES, with_history


def snapshot(due='2026-11-10T18:00:00+09:00', text='보고서를 제출하세요.', ident='p'):
    return {'fetched_at': '2026-11-08T11:00:00Z', 'assignments': [
        {'id': ident, 'course_id': 'c', 'source': 'coursework', 'title': '보고서', 'text': text, 'due_at': due}],
        'announcements': [], 'materials': []}


class SnapshotHistoryTests(unittest.TestCase):
    def test_first_snapshot_and_unchanged_pdf_checkpoints_do_not_invent_changes(self):
        first = with_history(None, snapshot())
        self.assertEqual(first['change_history'], [])
        checkpoint = deepcopy(first)
        checkpoint['assignments'][0]['attachments'] = [{'status': 'text_extracted'}]
        self.assertEqual(with_history(first, checkpoint)['change_history'], [])

    def test_deadline_extension_and_removal_keep_exact_previous_and_current_values(self):
        old = snapshot()
        new = with_history(old, snapshot('2026-11-12T20:00:00+09:00'))
        entry = new['change_history'][0]
        self.assertEqual(entry['kind'], 'registered_deadline')
        self.assertEqual(entry['before'], old['assignments'][0]['due_at'])
        self.assertEqual(entry['after'], '2026-11-12T20:00:00+09:00')
        removed = with_history(new, snapshot(None))
        self.assertIsNone(removed['change_history'][-1]['after'])
        self.assertEqual(len(with_history(removed, snapshot(None))['change_history']), 2)

    def test_body_update_does_not_infer_a_new_deadline_or_store_notice_copies(self):
        old = snapshot()
        new = with_history(old, snapshot(text='다음 주 금요일 제출로 변경합니다.'))
        entry = new['change_history'][0]
        self.assertEqual(entry['kind'], 'body')
        self.assertNotIn('before', entry)
        self.assertNotIn('after', entry)
        self.assertNotIn('다음', str(entry))
        self.assertEqual(new['assignments'][0]['due_at'], old['assignments'][0]['due_at'])
        self.assertNotIn('change_history', old)

    def test_history_is_bounded_and_removed_courses_are_not_exposed(self):
        current = snapshot()
        for index in range(MAX_CHANGES + 5):
            current = with_history(current, snapshot(f'2026-11-{10 + index % 2}'))
        self.assertEqual(len(current['change_history']), MAX_CHANGES)
        other = with_history(current, snapshot(ident='other'))
        self.assertEqual(other['change_history'], [])


if __name__ == '__main__':
    unittest.main()
