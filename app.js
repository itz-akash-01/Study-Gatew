(() => {
  'use strict';
  const $ = (s, root=document) => root.querySelector(s);
  const $$ = (s, root=document) => [...root.querySelectorAll(s)];
  const root = document.documentElement;
  const signedIn = document.body.dataset.signedIn === '1';
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  async function api(method, url, body){
    const res = await fetch(url,{method,credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrfToken},body:body===undefined?undefined:JSON.stringify(body)});
    if(res.status===401){location.reload();throw new Error('signed out')}
    if(!res.ok) throw new Error('request failed');
    return res.status===204?null:res.json();
  }
  $$('form[data-confirm]').forEach(f=>f.addEventListener('submit',e=>{if(!confirm(f.dataset.confirm))e.preventDefault()}));
  const savedTheme = localStorage.getItem('sg-theme');
  root.dataset.theme = savedTheme === 'dark' ? 'dark' : 'light';
  function toggleTheme(){root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';localStorage.setItem('sg-theme',root.dataset.theme)}
  $('#theme')?.addEventListener('click', toggleTheme);
  $('#theme-profile')?.addEventListener('click', toggleTheme);

  function showView(name){
    const view = $('#view-' + name);
    if(!view) return;
    $$('.view').forEach(v=>v.classList.toggle('active',v===view));
    $$('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));
    window.scrollTo({top:0,behavior:'smooth'});
  }
  $$('[data-view]').forEach(b=>b.addEventListener('click',()=>showView(b.dataset.view)));
  $$('[data-go]').forEach(b=>b.addEventListener('click',()=>showView(b.dataset.go)));

  const date = $('#today-date');
  if(date) date.textContent = new Intl.DateTimeFormat(undefined,{weekday:'short',month:'short',day:'numeric'}).format(new Date());

  // Book search and class filter.
  const search=$('#search'), filter=$('#filter'), bookCards=$$('.book'), none=$('#none');
  function applyBookFilter(){let count=0;bookCards.forEach(card=>{const match=(card.dataset.search||'').includes((search?.value||'').toLowerCase())&&(!(filter?.value)||card.dataset.cl===filter.value);card.hidden=!match;if(match)count++});if(none)none.hidden=count>0;}
  search?.addEventListener('input',applyBookFilter);filter?.addEventListener('change',applyBookFilter);

  // AI source picker is intentionally UI-only until an AI backend is configured.
  const sourceFiles=$('#source-files'), fileList=$('#file-list'), sourceCount=$('#source-count');
  let selectedFiles=[];
  function renderFiles(){if(sourceCount)sourceCount.textContent=`${selectedFiles.length} selected`;if(!fileList)return;fileList.innerHTML='';if(!selectedFiles.length){fileList.innerHTML='<div class="file-empty">Your selected sources will appear here.</div>';return}selectedFiles.forEach((file,i)=>{const row=document.createElement('div');row.className='file-row';const icon=document.createElement('span');icon.textContent=file.name.toLowerCase().endsWith('.pdf')?'▤':'↥';const name=document.createElement('b');name.textContent=file.name;name.title=file.name;const size=document.createElement('small');size.textContent=`${Math.max(1,Math.round(file.size/1024))} KB`;const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.setAttribute('aria-label',`Remove ${file.name}`);remove.addEventListener('click',()=>{selectedFiles.splice(i,1);renderFiles()});row.append(icon,name,size,remove);fileList.append(row)})}
  sourceFiles?.addEventListener('change',()=>{const incoming=[...sourceFiles.files];const max=40*1024*1024;const allowed=/\.(pdf|png|jpe?g|webp|txt|docx|zip)$/i;const invalid=incoming.filter(f=>!allowed.test(f.name)||f.size>max);if(invalid.length){showAiMessage('Some files were skipped. Supported types: PDF, PNG/JPG/WEBP, TXT, DOCX and ZIP; maximum 40 MB per file.');}incoming.filter(f=>allowed.test(f.name)&&f.size<=max).forEach(f=>{if(!selectedFiles.some(existing=>existing.name===f.name&&existing.size===f.size))selectedFiles.push(f)});renderFiles();sourceFiles.value=''});
  const dropZone=$('.drop-zone');
  if(dropZone){['dragenter','dragover'].forEach(type=>dropZone.addEventListener(type,e=>{e.preventDefault();dropZone.style.borderColor='var(--purple)'}));['dragleave','drop'].forEach(type=>dropZone.addEventListener(type,e=>{e.preventDefault();dropZone.style.borderColor='';if(type==='drop'){const dropped=[...(e.dataTransfer?.files||[])];dropped.forEach(f=>{if(/\.(pdf|png|jpe?g|webp|txt|docx|zip)$/i.test(f.name)&&f.size<=40*1024*1024&&!selectedFiles.some(x=>x.name===f.name&&x.size===f.size))selectedFiles.push(f)});renderFiles()}}))}
  let selectedOutput='notes';$$('[data-output]').forEach(btn=>btn.addEventListener('click',()=>{selectedOutput=btn.dataset.output;$$('[data-output]').forEach(b=>b.classList.toggle('selected',b===btn))}));
  function showAiMessage(message){const el=$('#ai-message');if(el){el.textContent=message;el.hidden=false}}
  $('#generate-button')?.addEventListener('click',()=>{const pasted=$('#source-text')?.value.trim();const custom=$('#custom-request')?.value.trim();if(!selectedFiles.length&&!pasted){showAiMessage('Add at least one source file or paste study text before preparing a request.');return}const outputNames={notes:'Smart notes',mcqs:'MCQs and quizzes',qa:'Question answers',mindmap:'Mind map',ppt:'PowerPoint',workflow:'Study workflow'};let detail=`Your request is ready: ${outputNames[selectedOutput]||'Custom educational output'}. `;detail+=selectedFiles.length?`${selectedFiles.length} file(s) selected. `:'';detail+=pasted?`${pasted.length} characters of text added. `:'';detail+=custom?`Custom instructions: “${custom.slice(0,180)}${custom.length>180?'…':''}”. `:'';detail+='Actual generation is not connected yet. Configure an AI provider and backend endpoint before using this request with a model.';showAiMessage(detail)});

  // Local planner storage. This is device/browser-local, not account sync.
  const STORE_KEY='sg-planner-v1';
  function loadData(){try{return JSON.parse(localStorage.getItem(STORE_KEY))||{tasks:[],focusMinutes:0,sessions:0}}catch{return{tasks:[],focusMinutes:0,sessions:0}}}
  let data=signedIn?{tasks:[],focusMinutes:0,sessions:0}:loadData();if(!Array.isArray(data.tasks))data.tasks=[];if(!Number.isFinite(data.focusMinutes))data.focusMinutes=0;if(!Number.isFinite(data.sessions))data.sessions=0;
  function saveData(){if(!signedIn)localStorage.setItem(STORE_KEY,JSON.stringify(data));renderTasks();renderStats()}
  function loadFromServer(){api('GET','/api/planner').then(d=>{data={tasks:Array.isArray(d.tasks)?d.tasks:[],focusMinutes:Number(d.focusMinutes)||0,sessions:Number(d.sessions)||0};renderTasks();renderStats()}).catch(()=>{})}
  const taskList=$('#task-list');
  function renderTasks(){if(!taskList)return;taskList.innerHTML='';const count=$('#task-count');if(count)count.textContent=`${data.tasks.length} task${data.tasks.length===1?'':'s'}`;if(!data.tasks.length){taskList.innerHTML='<div class="task-empty">No tasks yet. Add one small goal to get started.</div>';return}data.tasks.forEach(task=>{const row=document.createElement('div');row.className='task-row'+(task.done?' done':'');const check=document.createElement('input');check.type='checkbox';check.className='task-check';check.checked=!!task.done;check.setAttribute('aria-label',`Complete ${task.title}`);check.addEventListener('change',()=>{task.done=check.checked;saveData();if(signedIn)api('PATCH','/api/tasks/'+task.id,{done:task.done}).catch(loadFromServer)});const main=document.createElement('div');main.className='task-main';const title=document.createElement('b');title.textContent=task.title;const subject=document.createElement('small');subject.textContent=task.subject;main.append(title,subject);const del=document.createElement('button');del.className='task-delete';del.type='button';del.textContent='×';del.setAttribute('aria-label',`Delete ${task.title}`);del.addEventListener('click',()=>{data.tasks=data.tasks.filter(t=>t.id!==task.id);saveData();if(signedIn)api('DELETE','/api/tasks/'+task.id).catch(loadFromServer)});row.append(check,main,del);taskList.append(row)})}
  $('#task-form')?.addEventListener('submit',e=>{e.preventDefault();const input=$('#task-input');const title=input?.value.trim();if(!title)return;const subject=$('#task-subject')?.value||'General';input.value='';if(signedIn){api('POST','/api/tasks',{title,subject}).then(t=>{data.tasks.unshift(t);saveData()}).catch(()=>{})}else{data.tasks.unshift({id:Date.now().toString(36)+Math.random().toString(36).slice(2,7),title,subject,done:false});saveData()}});
  function renderStats(){const done=data.tasks.filter(t=>t.done).length,total=data.tasks.length;const statTasks=$('#stat-tasks');if(statTasks)statTasks.innerHTML=`${done} <small>/ ${total}</small>`;const taskProgress=$('#task-progress');if(taskProgress)taskProgress.style.width=(total?done/total*100:0)+'%';const statGoal=$('#stat-goal');if(statGoal)statGoal.innerHTML=`${data.focusMinutes} <small>min</small>`;const goalProgress=$('#goal-progress');if(goalProgress)goalProgress.style.width=Math.min(100,data.focusMinutes/120*100)+'%';const statSessions=$('#stat-sessions');if(statSessions)statSessions.textContent=data.sessions;const focusTotal=$('#focus-total');if(focusTotal)focusTotal.textContent=data.focusMinutes;const pm=$('#progress-minutes');if(pm)pm.textContent=data.focusMinutes;const pc=$('#progress-completed');if(pc)pc.textContent=done;const ps=$('#progress-sessions');if(ps)ps.textContent=data.sessions;const ring=$('#goal-ring');if(ring)ring.style.background=`conic-gradient(var(--purple) ${Math.min(360,data.focusMinutes/120*360)}deg, color-mix(in srgb,var(--purple) 12%,transparent) 0deg)`}
  renderTasks();renderStats();if(signedIn)loadFromServer();
  $$('[data-planner-tab]').forEach(btn=>btn.addEventListener('click',()=>{const tab=btn.dataset.plannerTab;$$('[data-planner-tab]').forEach(b=>b.classList.toggle('active',b===btn));$$('.planner-subview').forEach(v=>v.classList.toggle('active',v.id==='planner-'+tab))}));

  // Focus timer with pause/resume/reset and session completion tracking.
  let duration=25*60, remaining=duration, timerInterval=null, running=false;
  const display=$('#timer-display'), startButton=$('#timer-start'), timerLabel=$('#timer-label');
  function fmt(seconds){return `${Math.floor(seconds/60).toString().padStart(2,'0')}:${(seconds%60).toString().padStart(2,'0')}`}
  function renderTimer(){if(display)display.textContent=fmt(remaining);const ring=$('#timer-ring');if(ring){const passed=duration?1-remaining/duration:0;ring.style.background=`conic-gradient(var(--purple) ${passed*360}deg, color-mix(in srgb,var(--purple) 12%,transparent) 0deg)`}if(startButton)startButton.innerHTML=running?'Pause timer <span>Ⅱ</span>':(remaining===duration?'Start focus <span>▶</span>':'Resume timer <span>▶</span>')}
  function stopInterval(){if(timerInterval!==null){clearInterval(timerInterval);timerInterval=null}running=false}
  function chooseDuration(minutes,button){stopInterval();duration=minutes*60;remaining=duration;$$('.timer-mode').forEach(b=>b.classList.toggle('active',b===button));if(timerLabel)timerLabel.textContent=minutes===25?'Ready to focus?':minutes===5?'Take a short break':'Take a long break';renderTimer()}
  $$('.timer-mode').forEach(b=>b.addEventListener('click',()=>chooseDuration(Number(b.dataset.minutes)||25,b)));
  startButton?.addEventListener('click',()=>{if(running){stopInterval();renderTimer();return}if(remaining<=0)remaining=duration;running=true;renderTimer();timerInterval=setInterval(()=>{remaining=Math.max(0,remaining-1);renderTimer();if(remaining===0){stopInterval();if(duration>=10*60){const mins=Math.round(duration/60);if(signedIn){api('POST','/api/focus',{minutes:mins}).then(r=>{data.focusMinutes=Number(r.focusMinutes)||0;data.sessions=Number(r.sessions)||0;saveData()}).catch(()=>{})}else{data.focusMinutes+=mins;data.sessions+=1;saveData()}if(timerLabel)timerLabel.textContent='Session complete — well done!';}else if(timerLabel){timerLabel.textContent='Break complete — ready when you are.'}renderTimer()}},1000)});
  $('#timer-reset')?.addEventListener('click',()=>{stopInterval();remaining=duration;if(timerLabel)timerLabel.textContent='Timer reset. Ready when you are.';renderTimer()});
  renderTimer();
})();
