(function(root){
function clean(s){return s.replace(/\[([^\]]+)\]\((https?:[^\s)]+)\)/g,'$1 $2').replace(/\*\*|\\(?=[.&,~])/g,'').replace(/\u00a0/g,' ').replace(/^#{1,6}\s*/, '').trim()}
// Parse dates independently from deciding whether they are deadlines.
function dates(text, year) {
  const s = text.replace(/https?:\/\/\S+/g, '');
  const out = [];
  const re = /(?<!\d)(?:(20\d{2})\s*[.년/-]\s*)?(\d{1,2})\s*[.월/-]\s*(\d{1,2})(?:\s*[.일])?(?:\s*\([월화수목금토일](?:요일)?\))?(?:\s*(오전|오후)\s*)?(?:\s*(\d{1,2})\s*[:시]\s*(\d{2})?\s*(?:분)?(?::(\d{2}))?)?(?!\d)/g;
  let m;
  while ((m = re.exec(s))) {
    const y = +(m[1] || year), mo = +m[2], d = +m[3];
    let h = m[5] === undefined ? 23 : +m[5];
    const mi = m[5] === undefined ? 59 : +(m[6] || 0);
    const sec = m[5] === undefined ? 59 : +(m[7] || 0);
    if (m[4] && (h < 1 || h > 12)) continue;
    if (m[4] === '오후' && h < 12) h += 12;
    if (m[4] === '오전' && h === 12) h = 0;
    if (mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || sec > 59) continue;
    const day = `${y}-${String(mo).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    if (new Date(day+'T00:00:00Z').getUTCDate() !== d) continue;
    out.push({iso: day+`T${String(h).padStart(2,'0')}:${String(mi).padStart(2,'0')}:${String(sec).padStart(2,'0')}+09:00`,
      assumed: m[5] === undefined, yearAssumed: !m[1], index:m.index, text:m[0]});
  }
  return out;
}

// Expand a same-month range such as 11월 9일~17일 before parsing it.
function rangeDates(line, year) {
  const expanded = line.replace(/(\d{1,2})\s*월\s*(\d{1,2})\s*일?\s*(~|∼|–|부터)\s*(\d{1,2})\s*일(?!\s*\d)/g,
    '$1월 $2일 $3 $1월 $4일');
  return dates(expanded, year);
}

function resolveDeadline(lines, title, year) {
  const marker = /기한|기일|마감|접수\s*기간|신청\s*기간|제출\s*기간|까지/;
  let evidence = [];
  lines.forEach((line, i) => {
    if (/^(?:생성일|게시일|게시\s*날짜|수정일)/.test(line)) return;
    if (!marker.test(line)) return;
    let ds = rangeDates(line, year);
    // An exported label may put its date on the following line.
    if (!ds.length && /^(?:\d+[.．]\s*)?(?:제출\s*기한|제출\s*기일|마감일?|접수\s*기간|신청\s*기간|제출\s*기간)\s*[:：]?\s*$/.test(line)) {
      ds = rangeDates(lines[i+1] || '', year);
      line += '\n' + (lines[i+1] || '');
    }
    if (ds.length) evidence.push({line, dates:ds, range: /부터|~|∼|–/.test(line) && ds.length >= 2});
  });
  // A date range can also be present in a form title without a deadline label.
  if (!evidence.length && /구글\s*폼|접수|신청/.test(title)) {
    const ds = rangeDates(title, year);
    if (ds.length >= 2 && /부터|~|∼|–/.test(title)) evidence.push({line:title,dates:ds,range:true});
  }
  let dueSource = evidence.length ? 'explicit' : '';
  // Do not silently treat an old title date as the newly extended deadline.
  if (!evidence.length && /제출|신청|접수|마감/.test(title) && !lines.some(l=>/연장/.test(l))) {
    const ds = dates(title, year);
    if (ds.length) { evidence.push({line:title,dates:ds,range:false}); dueSource='title'; }
  }
  const unique = [...new Map(evidence.flatMap(e=>e.dates).map(d=>[d.iso,d])).values()];
  const due = unique.at(-1) || null;
  const period = evidence.length === 1 && evidence[0].range;
  const start = period ? unique[0].iso.replace(/T.*$/, 'T00:00:00+09:00') : null;
  const warnings = [];
  if (!due) warnings.push('정확한 마감일 확인 필요');
  if (!due && lines.some(l=>/연장/.test(l))) warnings.push('마감 연장 안내가 있지만 변경된 날짜는 원문에 없습니다.');
  if (dueSource==='title') warnings.push('제목에서 가져온 날짜 · 행사일인지 제출 마감일인지 확인해 주세요.');
  if (due?.assumed) warnings.push('마감 시각 미기재 · 23:59:59로 정렬');
  if (due?.yearAssumed) warnings.push(`${year}년으로 해석 · 기준 연도 확인`);
  if (unique.length>1 && !period) warnings.push('서로 다른 마감일 발견 · 직접 확인 필요');
  return {due:due?.iso || '', start, warnings, dueSource, dateEvidence:evidence.map(e=>e.line).join('\n')};
}

// Every suggested term must occur verbatim in the saved notice, for Ctrl+F.
function keywords(title, raw) {
  const source = raw || title;
  const core = title.replace(/^(?:(?:20\d{2})[.년/-]\s*)?\d{1,2}[.월/-]\s*\d{1,2}[.일]?\s*(?:\([월화수목금토일](?:요일)?\))?\s*/, '').trim();
  const parts = core.match(/[가-힣A-Za-z][가-힣A-Za-z0-9_-]{2,}/g) || [];
  const values = [core, ...parts, title];
  return [...new Set(values)].filter(x=>x.length>=3 && source.includes(x) && !/^(?:제출하기|작성하기|만들기|안내|보고서|제출|알고리즘|프로그래밍)$/.test(x)).slice(0,3);
}

function upgradeTask(task, year) {
  if (task.parserVersion >= 3) return false;
  const baseYear = task.baseYear || +(task.warnings?.join(' ').match(/(20\d{2})년으로/)?.[1] || year);
  const fresh = parse(task.raw || task.title, baseYear)[0];
  if (!fresh) return false;
  if (!task.titleEdited && /^\(?마감$|^\(?마감기한\s*연장\)?$/.test(task.title.replace(/^#{1,6}\s*/, '').trim())) {
    task.title=fresh.title; task.kind=fresh.kind;
  }
  if (!task.due && !task.dueEdited) {
    const resolved=resolveDeadline((task.raw||'').split('\n').map(clean), task.title, baseYear);
    if (resolved.due) Object.assign(task, resolved);
  }
  task.searchKeywords=keywords(task.title,task.raw);
  task.baseYear=baseYear; task.parserVersion=3;
  return true;
}
const titleTrim=s=>s.trim().replace(/^[‘’“”"'\s]+|[‘’“”"'\s]+$/g,'').trim();
function explicitTitle(l){let m=l.match(/^(?:#{1,6}\s*)?과제\s*[:：]\s*(.+)$/)||l.match(/새\s*과제\s*게시\s*[:：]\s*(.+)$/)||l.match(/^(?:탐구주제|과제명|대회명|공모명|제목)\s*[:：]\s*(.+)$/);return m?titleTrim(m[1]):null}
function noise(l){return /^(?:assignment|공지|첨부파일|더보기|댓글|김인수|게시일:|생성일:)$/.test(l)||/\.(?:png|jpg|jpeg|pdf)\s*(?:표시 중)?$/i.test(l)||/^https?:/.test(l)}
function titleOf(lines){let titled=lines.map(l=>({l,t:explicitTitle(l)})).filter(x=>x.t);let preferred=titled.find(x=>/^과제\s*[:：]/.test(x.l))||titled.find(x=>/^탐구주제/.test(x.l))||titled[0];if(preferred)return preferred.t;let numbered=lines.find(l=>/^\[과제\s*\d+\]/.test(l));if(numbered)return numbered.replace(/^\[과제\s*\d+\]\s*/,'');let first=lines.find(l=>!noise(l)&&!/^\d+번\s*[.．]?\s*\[/.test(l)&&!/^\(?\s*(?:마감|제출)?기한\s*연장\s*\)?$/.test(l)&&!/^\(?마감기한\s*연장\)?/.test(l)&&!/^\d*[.．]?\s*(?:제출기일|제출기한|마감일|신청기간)\s*[:：]/.test(l));return first?first.replace(/\s*https?:\/\/\S+/g,'').replace(/\s+(?:제출기한|기한)\s*[:：]?.*$/,'').trim():'제목 확인이 필요한 과제'}
function parse(text,year){const lines=clean(text).split(/\n/).map(clean).filter(Boolean);let blocks=[],current=null;const flush=()=>{if(current)blocks.push(current);current=null};for(let l of lines){if(/^(?:#{1,6}\s*)?(?:게시일|생성일):/.test(l)||/^\[(?:주제발표|프로그래밍 영역)/.test(l)){flush();continue}if(/^참고자료\s*[-–]/.test(l)){flush();continue}let numbered=/^\[과제\s*\d+\]/.test(l)||/^\d+번\s*[.．]?\s*\[/.test(l);let single=(!current||current.standalone||!current.explicit)&&/기한/.test(l)&&dates(l,year).length>0&&!/^(?:\d+\s*[.．]\s*)?(?:제출기|마감기)/.test(l);let period=/구글\s*폼/.test(l)&&/\d+월\s*\d+일/.test(l);let label=/^과제\s*[:：]/.test(l)||/새\s*과제\s*게시\s*[:：]/.test(l);let datedTitle=/^(?:(?:20\d{2})[.년/-]\s*)?\d{1,2}[.월/-]\s*\d{1,2}/.test(l)&&/제출|신청|접수/.test(l)&&dates(l,year).length>0;if(numbered||single||period||datedTitle){flush();current={lines:[l],standalone:single||period,explicit:numbered||datedTitle}}else if(label){let t=explicitTitle(l);let previous=current&&current.lines.map(explicitTitle).filter(Boolean);if(current&&(current.explicit||previous.length)&&!previous?.includes(t)&&titleOf(current.lines)!==t){flush()}if(!current)current={lines:[],standalone:false,explicit:true};current.lines.push(l);current.explicit=true}else if(current){current.lines.push(l)}else if(!noise(l)&&!/^참고|학습자료|학습문제|문제풀이|성취도 평가\s*http/.test(l)){current={lines:[l],standalone:false,explicit:false}}}flush();
if(!blocks.length&&text.trim())blocks=[{lines,standalone:false}];
return blocks.filter(b=>blocks.length===1||b.explicit||b.standalone||b.lines.some(l=>/(?:기한|기일|마감)/.test(l)&&dates(l,year).length)).map((b,i)=>{let raw=b.lines.join('\n'),title=titleOf(b.lines);const resolved=resolveDeadline(b.lines,title,year);const {due,start,warnings,dueSource,dateEvidence}=resolved;if(/1차고사|2차고사/.test(raw)&&!due)warnings.push('학교 시험 일정 입력 필요');if(title==='제목 확인이 필요한 과제')warnings.push('과제명을 직접 입력해 주세요');let links=[...new Set(raw.match(/https?:\/\/[^\s<>\])]+/g)||[])];let email=raw.match(/[\w.+-]+@[\w.-]+\.[a-z]{2,}/i)?.[0]||'';let kind=/수행평가\s*아님/.test(raw)?'평가 외 활동':/절대평가|수행평가/.test(raw)?'절대평가':/상대평가/.test(raw)?'상대평가':/대회|콘테스트|참가\s*접수/.test(title)?'대회·신청':'과제';return {id:'task-'+i+'-'+title,title,raw,due,start,kind,warnings,links,email,done:false,checks:{},dueSource,dateEvidence,baseYear:year,parserVersion:3,searchKeywords:keywords(title,raw)}}).filter(t=>t.title)}
if(typeof module!=='undefined')module.exports={parse,dates,titleOf,resolveDeadline,keywords,upgradeTask};root.NoticeParser={parse,dates,keywords,upgradeTask};
})(typeof window!=='undefined'?window:globalThis);
