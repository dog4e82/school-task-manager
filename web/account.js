(() => {
  'use strict';
  const data=JSON.parse(document.querySelector('#account-data').textContent);
  if(data.page!=='setup')return;
  const $=s=>document.querySelector(s);
  const message=value=>{$('#account-message').hidden=false;$('#account-message').textContent=value;};
  async function api(url,options={}){const response=await fetch(url,{credentials:'same-origin',...options,headers:{'Content-Type':'application/json','X-CSRF-Token':data.csrf,...options.headers}});const value=await response.json();if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:'요청을 확인하지 못했어요. 다시 시도해 주세요.');return value;}
  const selected=()=>[...document.querySelectorAll('[name=course]:checked')].map(e=>e.value);
  const refreshButton=()=>{const count=selected().length;$('#sync-courses').disabled=running||!count;$('#sync-courses').setAttribute('aria-busy',String(running));$('#sync-courses').textContent=running?'과제 불러오는 중…':count?'내 과제 보기 →':'수업을 먼저 선택해 주세요';$('#selection-hint').textContent=running?'불러오면 대시보드로 자동 이동해요.':count?`${count}개 수업 선택됨 · 아래 버튼을 눌러 주세요.`:'수업 선택 후 아래 버튼을 눌러 주세요.';};
  let running=false;
  async function watch(id){running=true;refreshButton();$('#job-progress').hidden=false;try{for(let i=0;i<3600;i++){const job=await api('/api/jobs/'+encodeURIComponent(id));$('#job-stage').textContent=job.stage;if(job.status==='running'&&job.result?.snapshot_ready){location.assign('/app');return;}if(job.status==='done'){location.assign('/app');return;}if(job.status==='stopped'){message(job.stage);setTimeout(()=>location.assign('/app'),2000);return;}if(!['queued','running'].includes(job.status)){message(job.stage);return;}await new Promise(resolve=>setTimeout(resolve,3000));}message('작업이 계속 진행 중입니다. 이 페이지를 다시 열면 진행 상태를 확인할 수 있어요.');}catch(error){message(error.message);}finally{running=false;refreshButton();}}
  $('#select-all').addEventListener('click',()=>{document.querySelectorAll('[name=course]').forEach(e=>e.checked=true);refreshButton();});
  $('#select-none').addEventListener('click',()=>{document.querySelectorAll('[name=course]').forEach(e=>e.checked=false);refreshButton();});
  $('#include-pdf')?.addEventListener('change',refreshButton);
  $('#auto-analyze')?.addEventListener('change',refreshButton);
  $('#sync-courses').addEventListener('click',async()=>{if(running||!selected().length)return;running=true;refreshButton();try{const job=await api('/api/sync',{method:'POST',body:JSON.stringify({course_ids:selected(),include_pdf:false,analyze_after_sync:!!$('#auto-analyze')?.checked})});watch(job.job_id);}catch(error){running=false;message(error.message);refreshButton();}});
  $('#logout').addEventListener('click',async()=>{try{await api('/api/logout',{method:'POST'});location.assign('/');}catch(error){message(error.message);}});
  Promise.all([api('/api/courses'),api('/api/jobs/latest')]).then(([value,state])=>{const options=$('#course-options');options.replaceChildren();for(const course of value.courses){const label=document.createElement('label');label.className='course-option';const input=document.createElement('input');input.type='checkbox';input.name='course';input.value=course.id;input.checked=data.selected.includes(course.id);input.addEventListener('change',refreshButton);const text=document.createElement('span');text.textContent=course.name;if(course.state==='ARCHIVED'){const status=document.createElement('small');status.textContent='보관된 수업';text.append(status);}label.append(input,text);options.append(label);}if(!value.courses.length)options.textContent='이 계정에서 조회할 수 있는 수업이 없어요. Classroom을 사용하는 계정인지 확인하세요.';refreshButton();if(state.job&&['queued','running'].includes(state.job.status))watch(state.job.id);}).catch(error=>message(error.message));
})();
