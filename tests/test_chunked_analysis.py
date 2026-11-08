from pathlib import Path
from tempfile import TemporaryDirectory
import contextlib
import io
import json
import unittest
from unittest.mock import Mock

from chunked_analysis import run_extended_analysis, split_job
from notice_ai import Cache, DEFAULT_MODEL, MAX_CHARS, prepare


def job():
    post={'id':'long','course_id':'c','source':'announcement','title':'긴 안내',
          'text':('참고 설명입니다.\n'*8000)+'보고서를 제출하세요.', 'due_at':None,
          'raw':{'creationTime':'2026-11-08T00:00:00Z'}}
    return prepare({'assignments':[],'announcements':[post]}, DEFAULT_MODEL,'https://example.invalid')[0]


def client():
    value=Mock(key='synthetic-private-key')
    value.models.return_value={'data':[{'id':DEFAULT_MODEL,'type':'llm'}]}
    value.balance.return_value={'total':{'remaining':9000}}
    value.request.return_value={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'items':[],'relations':[]})}}]}
    return value


class ChunkedAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.cache=Cache(Path(self.temp.name)/'analysis.sqlite3')
        self.silent=contextlib.redirect_stdout(io.StringIO());self.silent.__enter__()
    def tearDown(self):
        self.silent.__exit__(None,None,None);self.cache.close();self.temp.cleanup()
    def test_long_notice_is_planned_instead_of_skipped_and_every_part_is_bounded(self):
        source=job();parts=split_job(source)
        self.assertGreater(len(parts),1)
        self.assertTrue(all(len(json.dumps(part['payload']['current'],ensure_ascii=False))<=MAX_CHARS for part in parts))
        obj=client()
        report=run_extended_analysis(obj,self.cache,[source],DEFAULT_MODEL,dry_run=True)
        self.assertEqual((report['pending'],report['skipped']),(1,0))
        obj.request.assert_not_called()
    def test_parent_completes_and_reuses_all_saved_children(self):
        source=job();obj=client()
        first=run_extended_analysis(obj,self.cache,[source],DEFAULT_MODEL)
        self.assertGreater(first['calls'],1)
        self.assertEqual(self.cache.get(source['key'])['status'],'success')
        calls=obj.request.call_count
        second=run_extended_analysis(obj,self.cache,[source],DEFAULT_MODEL)
        self.assertEqual(second['cached'],1)
        self.assertEqual(obj.request.call_count,calls)
    def test_partial_parent_resumes_without_repeating_a_completed_chunk(self):
        source=job();obj=client()
        first=run_extended_analysis(obj,self.cache,[source],DEFAULT_MODEL,limit=1)
        self.assertEqual(first['calls'],1)
        self.assertEqual(self.cache.get(source['key'])['status'],'partial')
        second=run_extended_analysis(obj,self.cache,[source],DEFAULT_MODEL)
        self.assertEqual(self.cache.get(source['key'])['status'],'success')
        self.assertEqual(1+second['calls'],len({part['key'] for part in split_job(source)}))
    def test_credit_floor_stops_chunks_and_preserves_partial_parent(self):
        source=job();obj=client()
        obj.balance.side_effect=[{'total':{'remaining':value}} for value in (2010,1999,1999)]
        result=run_extended_analysis(obj,self.cache,[source],DEFAULT_MODEL,minimum_credits=2000)
        self.assertEqual(result['calls'],1)
        self.assertEqual(result['stopped'],'low_credits')
        self.assertEqual(self.cache.get(source['key'])['status'],'partial')

    def test_long_pdf_keeps_each_action_and_original_page_provenance(self):
        source=job();post=source['post']
        post['text']='첨부 PDF를 참고하세요.'
        sentences={1:'보고서를 2026년 11월 10일까지 제출하세요.', 2:'코드를 2026년 11월 12일까지 제출하세요.'}
        post['attachments']=[{'file_id':'f','title':'안내.pdf','status':'text_extracted','pages':[
            {'page':number,'text':'배경 설명입니다.\n'*6000+sentence} for number,sentence in sentences.items()]}]
        source=prepare({'assignments':[],'announcements':[post]},DEFAULT_MODEL,'https://example.invalid')[0]
        obj=client()
        def respond(path,payload):
            items=[]
            for doc in payload['messages'] and json.loads(payload['messages'][1]['content'])['current']['documents']:
                for page in doc['pages']:
                    sentence=sentences[page['page']]
                    if sentence in page['text']:
                        items.append({'title':'보고서' if page['page']==1 else '코드','task_status':'required',
                                      'task_evidence':sentence,'task_evidence_source':f"pdf:f:{page['page']}",
                                      'deadline_status':'confirmed','deadline_kind':'submission',
                                      'deadline':'2026-11-10' if page['page']==1 else '2026-11-12',
                                      'deadline_evidence':sentence,'deadline_evidence_source':f"pdf:f:{page['page']}"})
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'items':items,'relations':[]})}}]}
        obj.request.side_effect=respond
        run_extended_analysis(obj,self.cache,[source],DEFAULT_MODEL)
        result=self.cache.get(source['key'])['result']
        self.assertEqual(len(result['items']),2)
        self.assertEqual({i['deadline_evidence_source'] for i in result['items']},{'pdf:f:1','pdf:f:2'})
        self.assertEqual({i['deadline'] for i in result['items']},{'2026-11-10','2026-11-12'})

if __name__=='__main__':unittest.main()
