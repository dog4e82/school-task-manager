from datetime import date
import unittest
from analysis_selection import expired_for_analysis


def post(text='',due=None,source='coursework'):
    return {'id':'p','course_id':'c','source':source,'title':'안내','text':text,'due_at':due,
            'raw':{'creationTime':'2026-10-01T00:00:00Z'}}


class SelectionTests(unittest.TestCase):
    today=date(2026,11,8)
    def test_registered_expired_submission_is_excluded(self):
        self.assertTrue(expired_for_analysis(post('보고서를 제출하세요.','2026-10-20T18:00:00+09:00'),self.today))
    def test_mixed_old_and_future_work_stays_in_queue(self):
        p=post('[과제1] 보고서\n제출 기한: 2026.10.20.\n보고서 제출\n'
               '[과제2] 코드\n제출 기한: 2026.11.12.\n코드 제출','2026-10-20T18:00:00+09:00')
        self.assertFalse(expired_for_analysis(p,self.today))
    def test_undated_child_or_pending_changed_deadline_is_not_discarded(self):
        for text in ('[과제1] 보고서\n제출 기한: 2026.10.20.\n보고서 제출\n[과제2] 코드\n코드 제출',
                     '제출 마감은 추후 공지합니다.','마감 연장 안내를 확인하세요.'):
            self.assertFalse(expired_for_analysis(post(text,'2026-10-20T18:00:00+09:00'),self.today))
    def test_application_end_date_is_used_but_old_publication_date_is_not(self):
        self.assertTrue(expired_for_analysis(post('희망자는 신청하세요. 접수기간: 2026.10.1.~2026.10.31.',source='announcement'),self.today))
        self.assertFalse(expired_for_analysis(post('2026.10.1. 게시된 안내입니다. 보고서를 제출하세요.',source='announcement'),self.today))
    def test_date_unknown_notice_is_kept_even_if_very_old(self):
        p=post('과제를 제출하세요. 마감은 아직 정하지 않았습니다.',source='announcement')
        p['raw']['creationTime']='2025-01-01T00:00:00Z'
        self.assertFalse(expired_for_analysis(p,self.today))

if __name__=='__main__':unittest.main()
