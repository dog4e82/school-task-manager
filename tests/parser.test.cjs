const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { parse, dates, keywords, upgradeTask } = require('../dist/parser.js');
const task = text => parse(text, 2026)[0];
const day = (m,d,time='23:59:59') => `2026-${m}-${d}T${time}+09:00`;

for (const [input, expected] of [
 ['10.14.(수) 진로특강1 보고서 제출', day('10','14')],
 ['과제: 10.14.(수) 진로특강1 보고서 제출', day('10','14')],
 ['제목: 2026.10.14.(수) 진로특강1 보고서 제출', day('10','14')],
 ['10월 14일 진로특강1 보고서 제출', day('10','14')],
 ['10/14 진로특강1 보고서 제출', day('10','14')],
 ['2026-10-14 진로특강1 보고서 제출', day('10','14')],
 ['과제: 보고서\n제출기한: 2026.11.01.(일) 23:59:59', day('11','01')],
 ['과제: 보고서\n제출기한:\n11월 3일 오후 5시', day('11','03','17:00:00')],
 ['과제: 보고서\n마감: 11월 3일 오전 12시', day('11','03','00:00:00')],
 ['과제: 보고서\n마감: 11월 3일 오후 12시', day('11','03','12:00:00')],
 ['과제: 보고서\n마감: 11월 3일 00:00:00', day('11','03','00:00:00')],
]) test(input.replaceAll('\n',' / '),()=>assert.equal(task(input).due,expected));

test('title date is marked as inferred and retains original evidence',()=>{
 const t=task('10.14.(수) 진로특강1 보고서 제출');
 assert.equal(t.dueSource,'title'); assert.match(t.warnings.join(' '),/행사일/);
 assert.equal(t.dateEvidence,'10.14.(수) 진로특강1 보고서 제출');
});
test('explicit deadline overrides lecture date in title',()=>{
 const t=task('10.14.(수) 진로특강1 보고서 제출\n제출기한: 10월 21일');
 assert.equal(t.due,day('10','21')); assert.equal(t.dueSource,'explicit');
});
test('do not treat an event-only title as a deadline',()=>assert.equal(task('10.14.(수) 진로특강 안내').due,''));
test('do not reuse old title date when an unspecified extension is announced',()=>assert.equal(task('과제: 10.14.(수) 보고서 제출\n마감기한 연장').due,''));
test('creation and event dates do not override deadline',()=>{
 const t=task('생성일: 10월 1일\n과제: 보고서\n행사일: 10월 14일\n제출기한: 10월 21일');
 assert.equal(t.due,day('10','21'));
});
test('conflicting deadlines require confirmation',()=>{
 assert.match(task('과제: 보고서\n마감: 11월 1일\n변경 마감: 11월 3일').warnings.join(' '),/서로 다른/);
});
for(const range of ['11월 9일부터 11월 17일','11월 9일~17일']) test('range '+range,()=>{
 const t=task('과제: 구글 폼 신청\n접수 기간: '+range);
 assert.equal(t.start,day('11','09','00:00:00')); assert.equal(t.due,day('11','17'));
});
for(const bad of ['2026.02.30','2026.02.29','2026.13.01','2026.11.31','2026.11.01 25:00','2026.11.01 23:60']) test('invalid date '+bad,()=>assert.equal(dates(bad,2026).length,0));
test('leap day is accepted in leap year',()=>assert.equal(dates('2028.02.29',2026)[0].iso,'2028-02-29T23:59:59+09:00'));
test('URL dates are not deadlines',()=>assert.equal(task('과제: 보고서\n참고 마감 설명 https://example.com/2026/11/03').due,''));
test('late classroom title and duplicate posting metadata',()=>{
 const ts=parse('(마감기한 연장)\n신청서.png 표시 중\nassignment\n과제: ‘화이트햇 2026 콘테스트 개최 및 참가 접수 안내 ’\n황지영님이 새 과제 게시: 화이트햇 2026 콘테스트 개최 및 참가 접수 안내',2026);
 assert.equal(ts.length,1); assert.equal(ts[0].title,'화이트햇 2026 콘테스트 개최 및 참가 접수 안내');assert.equal(ts[0].due,'');
});
test('separate classroom tasks stay separate',()=>assert.equal(parse('과제: 가\n마감 11월 3일\n김님이 새 과제 게시: 가\n과제: 나\n마감 11월 4일',2026).length,2));
test('original 20 assignments retain deadlines and separation',()=>{
 const ts=parse(fs.readFileSync('dist/sample.txt','utf8'),2026);
 assert.equal(ts.length,20);assert.equal(ts.filter(t=>!t.due).length,2);
 assert.equal(ts.find(t=>t.title.includes('노래')).due,day('11','01'));
 assert.equal(ts.find(t=>t.title.includes('뉴스')).due,day('11','29'));
 assert.equal(ts.filter(t=>t.title.includes('괄호')).length,2);
});
test('search terms are exact substrings suitable for browser find',()=>{
 const raw='10.14.(수) 진로특강1 보고서 제출';const terms=keywords(raw,raw);
 assert(terms.includes('진로특강1'));assert(terms.includes('진로특강1 보고서 제출'));terms.forEach(t=>assert(raw.includes(t)));
});
test('migration fills missing date while retaining ID, completion, checklist and title',()=>{
 const t={id:'old',title:'10.14.(수) 진로특강1 보고서 제출',raw:'과제: 10.14.(수) 진로특강1 보고서 제출',due:'',done:true,checks:{0:true},warnings:[]};
 assert(upgradeTask(t,2026));assert.equal(t.due,day('10','14'));assert.equal(t.id,'old');assert.equal(t.done,true);assert.deepEqual(t.checks,{0:true});assert.equal(upgradeTask(t,2026),false);
});
test('migration preserves a manually cleared date',()=>{
 const t={title:'10.14.(수) 진로특강1 보고서 제출',raw:'10.14.(수) 진로특강1 보고서 제출',due:'',dueEdited:true,warnings:[]};upgradeTask(t,2026);assert.equal(t.due,'');
});
test('migration preserves already entered deadline',()=>{
 const t={title:'10.14.(수) 진로특강1 보고서 제출',raw:'10.14.(수) 진로특강1 보고서 제출',due:day('10','21'),warnings:[]};upgradeTask(t,2026);assert.equal(t.due,day('10','21'));
});
test('adjacent date-leading tasks are separate',()=>{
 const ts=parse('10.14.(수) 진로특강1 보고서 제출\n10.21.(수) 진로특강2 보고서 제출',2026);
 assert.equal(ts.length,2);assert.equal(ts[0].due,day('10','14'));assert.equal(ts[1].due,day('10','21'));
});
test('date-leading title and its exported duplicate produce one task',()=>{
 assert.equal(parse('10.14.(수) 진로특강1 보고서 제출\n과제: 10.14.(수) 진로특강1 보고서 제출',2026).length,1);
});
