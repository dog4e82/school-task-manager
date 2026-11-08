from datetime import date
import unittest
from unittest.mock import Mock

from task_extraction import derive_items, blocks
from task_report import gather
from ui_data import build_data


def post(text, ident="p", source="announcement", due=None, course="c"):
    return {"id":ident,"course_id":course,"course_name":"시험 수업","source":source,
            "title":"안내","text":text,"due_at":due,"original_url":"https://classroom.google.com/test/"+ident,
            "raw":{"creationTime":"2026-10-20T01:00:00Z"}}


def item(title, quote, kind="submission", schedule=None, source="post", status="required"):
    return {"title":title,"task_status":status,"proposed_task_status":status,"deadline_kind":kind,
            "task_evidence":quote,"task_evidence_source":source,"deadline_evidence":schedule,
            "deadline_evidence_source":source,"review_flags":[]}


class TaskExtractionTests(unittest.TestCase):
    def test_distinct_tasks_get_their_own_deadlines_and_stable_ids(self):
        text="[과제1] 보고서\n제출 기한: 2026.11.10. 18시\nPDF를 제출하세요.\n[과제2] 코드\n제출 기한: 2026.11.17. 20시\n코드를 제출하세요."
        p=post(text,source="coursework",due="2026-11-10T18:00:00+09:00")
        snapshot={"courses":[],"assignments":[p],"announcements":[]}
        cache=Mock();cache.get.return_value=None
        result=build_data(snapshot,cache,"",date(2026,11,6))
        tasks=sorted(result["tasks"],key=lambda t:t["due"])
        self.assertEqual(len(tasks),2)
        self.assertEqual([t["due"] for t in tasks],["2026-11-10T18:00:00+09:00","2026-11-17T20:00:00+09:00"])
        self.assertEqual(len({t["id"] for t in tasks}),2)
        before={t["title"]:t["id"] for t in tasks}
        snapshot["assignments"].insert(0,post("별도 과제",ident="other",source="coursework"))
        after=build_data(snapshot,cache,"",date(2026,11,6))
        self.assertTrue(all(before[t["title"]]==t["id"] for t in after["tasks"] if t["title"] in before))
        self.assertTrue(all(t["sourceExtracted"] and not t["analyzed"] for t in tasks))

    def test_instruction_checklist_is_not_split_into_assignments(self):
        self.assertEqual(blocks("과제: 보고서\n조건1. PDF로 제출\n조건2. 이름 표시\n조건3. 2페이지 이내"),[])
        self.assertEqual(blocks("[수업자료]\n1. 입력\n2. 출력\n[참고자료]\n영상"),[])
        self.assertEqual(blocks("보고서 제출\n1. 보고서 PDF로 제출\n2. 자료 출처 표시\n제출 기한: 2026.11.20."), [])

    def test_numbered_work_has_separate_dates_without_ai(self):
        p = post("1. 탐구 보고서 제출\n제출 기한: 2026.11.12.\n보고서를 제출하세요.\n"
                 "2. 프로그램 코드 제출\n제출 기한: 2026.11.19.\n코드를 제출하세요.", source='coursework')
        rows = derive_items(p, [], [p])
        self.assertEqual([r['title'] for r in rows], ['탐구 보고서 제출', '프로그램 코드 제출'])
        self.assertEqual([r['resolved_due'] for r in rows], ['2026-11-12', '2026-11-19'])

    def test_splitting_dated_work_does_not_drop_an_undated_child(self):
        p = post('1. 보고서 제출\n제출 기한: 2026.11.12.\n보고서를 제출하세요.\n'
                 '2. 코드 제출\n제출 기한: 2026.11.19.\n코드를 제출하세요.\n'
                 '3. 탐구 자료 제출\n자료를 제출하세요. 마감은 추후 공지합니다.', source='coursework')
        rows = derive_items(p, [], [p])
        self.assertEqual(len(rows), 3)
        self.assertIsNone(rows[2]['resolved_due'])

    def test_distinct_ai_deadline_kinds_never_share_a_completion_id(self):
        p = post('참여 희망자는 교내 신청과 외부 접수를 해주세요.')
        children = [item('참여 신청', p['text'], kind=kind, status='optional')
                    for kind in ('registration', 'local_signup')]
        cache = Mock()
        cache.get.return_value = {'status': 'success', 'result': {'items': children}}
        result = build_data({'courses': [], 'assignments': [], 'announcements': [p]}, cache, '', date(2026, 11, 6))
        self.assertEqual(len(result['tasks']), 2)
        self.assertEqual(len({t['id'] for t in result['tasks']}), 2)

    def test_repeated_assessment_fields_split_one_notice(self):
        text=("[수행평가]\n1) 평가영역(주제): 정렬과 탐색\n2) 일시: 5월 마지막주 수업 시간\n3) 평가내용: 정렬 코드 제출\n"
              "1) 평가영역(주제): 데이터 시각화\n2) 일시: 5월 마지막주 수업 시간\n3) 평가내용: 그래프 제출\n"
              "[프로젝트 수행평가]\n1) 주제: API 웹 개발\n2) 평가영역: 데이터 활용\n3) 평가내용: 공유 링크 제출\n"
              "1) 평가영역: 온라인 문제해결\n2) 일시: 5월 마지막주 수업 시간\n3) 평가내용: 음원 제출")
        rows=derive_items(post(text),[],[])
        self.assertEqual(len(rows),4)
        self.assertEqual(len({r['source_item_key'] for r in rows}),4)
        self.assertEqual(rows[0]["schedule_text"],"5월 마지막주 수업 시간")

    def test_existing_ai_children_are_not_duplicated_or_mutated(self):
        p=post("[과제1] 보고서\n보고서를 제출하세요.\n[과제2] 코드\n코드를 제출하세요.")
        original=[item("보고서 제출","보고서를 제출하세요."),item("코드 제출","코드를 제출하세요.")]
        rows=derive_items(p,original,[p])
        self.assertEqual(len(rows),2)
        self.assertTrue(all('_block_text' not in i and 'resolved_due' not in i for i in original))

    def test_body_schedule_and_classroom_time_conflict_stays_visible(self):
        p=post("발표 자료 제출 : 11.30(월) 13시 00분 까지",source="coursework",due="2026-11-30T12:30:00+09:00")
        row=derive_items(p,[item("자료 제출",p['text'],schedule=p['text'])],[p])[0]
        self.assertEqual(row['resolved_due'],p['due_at'])
        self.assertEqual(row['deadline_alternatives'],['2026-11-30T13:00:00+09:00'])
        self.assertFalse(row['resolved_confirmed'])

    def test_exam_window_does_not_inherit_report_submission_deadline(self):
        text="과정1. 보고서\n제출마감 : 11.5(목) 18시30분\n보고서 제출\n과정2. 서술평가 : 11.9(월)~11.13(금) 중 1시간\n설명 작성 후 제출."
        p=post(text,source="coursework",due="2026-11-05T18:30:00+09:00")
        rows=derive_items(p,[item("보고서 제출","보고서 제출",schedule="제출마감 : 11.5(목) 18시30분"),
                             item("수업 중 서술평가 작성·제출","설명 작성 후 제출.",kind="event",schedule="서술평가 : 11.9(월)~11.13(금) 중 1시간")],[p])
        event=next(r for r in rows if r['deadline_kind']=='event')
        self.assertEqual(event['resolved_due'],'2026-11-13')
        self.assertEqual(event['schedule_start'],'2026-11-09')
        self.assertEqual(event['schedule_type'],'window')
        self.assertIn('중 1시간',event['deadline_expression'])
        self.assertFalse(event['api_due'])

    def test_pdf_deadline_not_nearby_final_event_date(self):
        p=post("PDF 참고")
        quote="본선(11. 28.) 전 고도화 서류 제출 마감일: 11. 26.(목)"
        p['attachments']=[{'file_id':'f','pages':[{'page':2,'text':quote}]}]
        row=derive_items(p,[item("고도화 서류 제출",quote,schedule=quote,source="pdf:f:2")],[p])[0]
        self.assertEqual(row['resolved_due'],'2026-11-26')
        self.assertFalse(row['resolved_confirmed'])
        self.assertEqual(row['deadline_evidence_source'],'pdf:f:2')

    def test_ongoing_activity_is_not_given_an_invented_date(self):
        for quote in ('발표 : 수시로 희망에 따라 진행함.','틈날때 마다 수행해보세요.'):
            p=post(quote,source="coursework",due="2026-11-30T12:30:00+09:00")
            row=derive_items(p,[item("발표 참여",quote,kind="event",schedule=quote)],[p])[0]
            self.assertIsNone(row['resolved_due'])
            self.assertEqual(row['schedule_type'],'ongoing')

    def test_api_deadline_separate_from_uncertain_obligation_for_shared_submission(self):
        p=post("자료 첨부하면 참고합니다. 요약은 선택입니다.",source="coursework",due="2026-11-30T23:59:00+09:00")
        rows=derive_items(p,[item('자료 첨부','자료 첨부하면 참고합니다.',status='unknown'),
                             item('요약 첨부','요약은 선택입니다.',status='optional')],[p])
        self.assertTrue(all(r['resolved_due']==p['due_at'] and r['api_due'] for r in rows))
        self.assertEqual(rows[0]['task_status'],'unknown')

    def test_ui_keeps_task_confirmation_separate_from_registered_deadline(self):
        p=post('자료를 첨부하면 참고합니다.',source='coursework',due='2026-11-30T23:59:00+09:00')
        child=item('자료 첨부',p['text'],status='unknown')
        child['proposed_task_status']='required'
        cache=Mock();cache.get.return_value={'status':'success','result':{'items':[child]}}
        data=build_data({'courses':[],'assignments':[p],'announcements':[]},cache,'',date(2026,11,8))
        self.assertFalse(data['tasks'][0]['taskConfirmed'])
        self.assertTrue(data['tasks'][0]['deadlineConfirmed'])

    def test_related_report_is_only_a_proposal_and_same_course(self):
        quote="캡처 후 최종 보고서 제출할 때 함께 제출하세요."
        p=post("주식 종목 변경\n"+quote)
        target=post("주식투자",ident="report",source="coursework",due="2026-11-13T23:59:00+09:00")
        target['title']='모의주식 투자 탐구'
        child=item('캡처 제출',quote)
        row=derive_items(p,[child],[p,target])[0]
        self.assertEqual(row['resolved_due'],target['due_at'])
        self.assertFalse(row['resolved_confirmed'])
        self.assertEqual(row['related_deadline']['url'],target['original_url'])
        target['course_id']='other'
        self.assertIsNone(derive_items(p,[child],[p,target])[0]['resolved_due'])
        target['course_id']='c'
        self.assertIsNone(derive_items(p,[child],[p,target,{**target,'id':'duplicate'}])[0]['resolved_due'])

    def test_korean_from_to_uses_range_end(self):
        p=post("[과제1] 웹\n제출 기간: 2026년 11월6(금)부터 11월8(일)\n링크 제출\n[과제2] 보고서\n제출일: 2026.11.20.\n보고서 제출")
        rows=derive_items(p,[],[p])
        self.assertEqual(rows[0]['resolved_due'],'2026-11-08')
        self.assertEqual(rows[0]['schedule_start'],'2026-11-06')

    def test_separate_assessment_block_keeps_its_execution_period(self):
        p=post("1) 주제: 웹 개발\n2) 평가내용: 링크 제출\n3) 실시기간: 2026년 11월6(금)부터 11월8(일) 수업시간\n"
               "1) 평가영역: 음원 제작\n2) 평가내용: 음원 제출\n3) 일시: 11월 마지막주 정보수업 시간")
        rows=derive_items(p,[],[p])
        self.assertEqual(rows[0]['resolved_due'],'2026-11-08')
        self.assertEqual(rows[0]['schedule_start'],'2026-11-06')
        self.assertEqual(rows[0]['schedule_type'],'window')
        self.assertIsNone(rows[1]['resolved_due'])
        self.assertEqual(rows[1]['schedule_type'],'period')


if __name__ == '__main__':
    unittest.main()
