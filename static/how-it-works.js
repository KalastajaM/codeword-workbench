(function(){
if(typeof document==='undefined')return;
const WORDS='A I AN AS AT BE BY DO GO HE IF IN IS IT ME MY NO OF ON OR SO TO UP US WE CAT DOG DAD DID MOM SUN SEA SKY CAR BUS MAP PEN RED ART EAT TEA ATE RAT TAR EAR ARE ERA TEN NET ONE TWO BAT BAR TAB BOAT BOOK CODE WORD HOME HOUSE WATER CROSS PUZZLE LETTER NUMBER HELLO WORLD TEST TREE ROAD STAR MOON LIGHT NIGHT DAY PLAY READ WRITE'.split(' ');
// Letter-model scores from solver._score with the model adapted to this list.
const SCORE={ARE:5.38,ART:5.29,ATE:5.79,BAR:6.55,BAT:4.09,BUS:5.14,CAR:5.24,CAT:3.71,DAD:3.84,DAY:5.44,DID:4.46,DOG:4.13,EAR:4.89,EAT:1.45,ERA:2.27,MAP:0.12,MOM:-3.25,NET:4.29,ONE:4.95,PEN:5.89,RAT:2.72,RED:8.42,SEA:3.72,SKY:5.39,SUN:4.29,TAB:0.51,TAR:5.03,TEA:4.16,TEN:6.12,TWO:-1.5};
const ANSWER='SEAEARART',NUMS=[1,2,3,2,3,4,3,4,5];
let given=new Set([3]);  // number 3 = A confirmed
let run,step=0,timer=null;
const $=id=>document.getElementById(id);
function puzzle(){return {rows:3,cols:3,cells:NUMS.map((n,i)=>({number:n,letter:given.has(n)&&[...ANSWER].findIndex((_,k)=>NUMS[k]===n)===i?ANSWER[i]:''}))}}
function rerun(){stop();run=solve(puzzle(),WORDS,SCORE);step=0;$('scrub').max=run.trace.length-1;render()}
const lbl=(s)=>`${s.dir} r${Math.floor(s.cells[0]/3)+1}c${s.cells[0]%3+1}`;
function cellsText(list){return list.map(i=>`r${Math.floor(i/3)+1}c${i%3+1}`).join(', ')}
function narrate(t){
  const s=t.slot!=null?run.slots[t.slot]:null;
  switch(t.type){
    case 'candidates':{const i=t.info[0];return ['Candidates',`The index holds ${i.byLen} three-letter words. Every slot here has three different numbers, so the repeated-letter pattern drops words like DAD and MOM, leaving ${i.byPat}. Words that clash with confirmed letters or claim a confirmed letter for another number go next. Each slot's list is ranked by letter-model score.`]}
    case 'propagate':{const gone=t.removed.reduce((a,r)=>a+r.length,0);
      const forcedTxt=t.newly.length?` Forced: ${t.newly.map(i=>`${t.letters[i]} at r${Math.floor(i/3)+1}c${i%3+1}`).join(', ')}.`:'';
      return ['Propagation',`Depth ${t.depth}, round ${t.round}. ${gone?`${gone} candidate${gone>1?'s':''} no longer fit the crossings or number mappings and were removed.`:'Nothing changed, so propagation reached a fixed point.'} Each number keeps only letters that every slot containing it can still supply.${forcedTxt}`]}
    case 'choose':return ['Branch point',`No letter is forced yet. The solver branches on the slot with the fewest candidates (ties go to the longer, then earlier slot): ${lbl(s)}, with ${t.options.length} options tried in score order: ${t.options.join(', ')}.`];
    case 'branch':return ['Try a word',`Place ${t.word} in ${lbl(s)} as a hypothesis, then propagate its consequences.`];
    case 'dead':return ['Contradiction',`Propagation failed: ${t.reason}. This branch is abandoned and the search backtracks to the next queued option.`];
    case 'solution':return ['Solution',`Every slot holds a listed word and every number has one letter. Recorded as alternative ${t.index}; the search continues until the queue is empty or 12 alternatives are found.`];
    case 'done':return ['Search finished',`The queue is empty after ${t.nodes} search nodes and ${t.rounds} propagation rounds, with ${t.solutions} solution${t.solutions===1?'':'s'}. Nothing was truncated, so for this word list the search is exhaustive.`];
  }}
function render(){
  const t=run.trace[step];const prev=run.trace[step-1];
  // grid
  const g=$('grid');g.textContent='';
  const hot=new Set(t.slot!=null&&t.type!=='done'?run.slots[t.slot].cells:[]);
  const fresh=new Set(t.newly||[]);
  NUMS.forEach((n,i)=>{const b=document.createElement('button');b.className='cell';b.type='button';
    const isGiven=given.has(n);if(isGiven)b.classList.add('given');if(hot.has(i))b.classList.add('hot');if(fresh.has(i))b.classList.add('new');
    b.innerHTML=`<span class="n">${n}</span>${t.letters[i]||''}`;
    b.setAttribute('aria-label',`Row ${Math.floor(i/3)+1} column ${i%3+1}, number ${n}, ${t.letters[i]||'empty'}${isGiven?', confirmed':''}. Toggle confirmation.`);
    b.onclick=()=>{given.has(n)?given.delete(n):given.add(n);rerun()};g.appendChild(b)});
  // support
  const nums=[1,2,3,4,5];$('supH').innerHTML='<th>No.</th>'+nums.map(n=>`<th>${n}</th>`).join('');
  $('supB').innerHTML='<th>Can be</th>'+nums.map(n=>{const fixed=NUMS.findIndex((m,i)=>m===n&&t.letters[i]);
    const v=fixed>=0?t.letters[fixed]:(t.support&&t.support[n])||'?';return `<td class="${v.length===1&&v!=='?'?'one':''}">${v}</td>`}).join('');
  // slots
  const box=$('slots');box.textContent='';
  run.slots.forEach((s,j)=>{const d=document.createElement('div');d.className='slot';
    if(hot.has(s.cells[0])&&t.slot===j)d.classList.add('hot');if(t.type==='dead'&&t.slot===j)d.classList.add('fail');
    const dom=t.domains[j];const rem=(t.removed&&t.removed[j])||[];
    const word=s.cells.map(i=>t.letters[i]||'·').join('');
    let body;
    if(!dom){body=t.type==='candidates'?'':`<span class="done">${s.cells.every(i=>t.letters[i])?`filled: ${word}`:'assigned'}</span>`}
    else body=`<div class="words">${dom.map(w=>`<span class="w${t.type==='branch'&&t.slot===j&&w===t.word?' try':''}">${w}</span>`).join('')}${rem.map(w=>`<span class="w gone">${w}</span>`).join('')}</div>`;
    if(t.type==='branch'&&t.slot===j)body=`<div class="words"><span class="w try">${t.word}</span></div>`;
    d.innerHTML=`<h4>${lbl(s)}<span>${dom?dom.length+' left':''}</span></h4>${body}`;box.appendChild(d)});
  // narration
  const [tag,text]=narrate(t);const n=$('narr');n.className='narr '+t.type;n.innerHTML=`<span class="tag">${tag}</span><p>${text}</p>`;
  $('count').textContent=`step ${step+1} / ${run.trace.length}`;$('scrub').value=step;
  $('prev').disabled=$('first').disabled=step===0;$('next').disabled=step===run.trace.length-1;
  // stats so far
  const seen=run.trace.slice(0,step+1);
  $('stats').innerHTML=`<span>Nodes <b>${seen.filter(x=>x.type==='branch').length+1}</b></span><span>Propagation rounds <b>${seen.filter(x=>x.type==='propagate').length+seen.filter(x=>x.type==='dead').length}</b></span><span>Dead ends <b>${seen.filter(x=>x.type==='dead').length}</b></span><span>Solutions <b>${seen.filter(x=>x.type==='solution').length}</b></span>`;
  drawTree(seen);
}
function drawTree(seen){
  // Build tree from all choose events; colour nodes by what has been revealed so far.
  const nodes={0:{id:0,label:'start',kids:[],depth:0}};
  for(const t of run.trace)if(t.type==='choose')for(const k of t.kids)nodes[k.id]={id:k.id,label:k.word,kids:[],depth:t.depth+1,parent:t.node},nodes[t.node].kids.push(k.id);
  const state={};for(const t of seen){if(t.node==null)continue;
    if(t.type==='branch')state[t.node]='try';if(t.type==='dead')state[t.node]='dead';if(t.type==='solution')state[t.node]='ok';if(t.type==='choose'||t.type==='propagate')state[t.node]=state[t.node]||'open'}
  state[0]=state[0]||'open';
  const cur=seen[seen.length-1].node;
  let leaf=0;const pos={};
  (function place(id){const nd=nodes[id];if(!nd.kids.length){pos[id]=leaf++;return}nd.kids.forEach(place);pos[id]=(pos[nd.kids[0]]+pos[nd.kids[nd.kids.length-1]])/2})(0);
  const maxD=Math.max(...Object.values(nodes).map(n=>n.depth));const dx=78,dy=58,W=Math.max(320,leaf*dx+20),H=(maxD+1)*dy+16;
  const X=id=>10+dx/2+pos[id]*dx,Y=id=>22+nodes[id].depth*dy;
  const col={try:'var(--focus)',dead:'var(--dead)',ok:'var(--ok)',open:'var(--teal)'};
  let svg=`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Search tree">`;
  for(const n of Object.values(nodes))if(n.parent!=null)svg+=`<line x1="${X(n.parent)}" y1="${Y(n.parent)+11}" x2="${X(n.id)}" y2="${Y(n.id)-11}" stroke="var(--rule)" stroke-width="1.5"/>`;
  for(const n of Object.values(nodes)){const s=state[n.id];const c=s?col[s]:'var(--rule)';const fill=s&&s!=='open'?c:'var(--sheet)';
    svg+=`<g><rect x="${X(n.id)-32}" y="${Y(n.id)-11}" width="64" height="22" rx="11" fill="${fill}" stroke="${c}" stroke-width="${n.id===cur?3:1.5}"/>`+
      `<text x="${X(n.id)}" y="${Y(n.id)+4}" text-anchor="middle" font-family="ui-monospace,Menlo,Consolas,monospace" font-size="12" font-weight="600" fill="${s&&s!=='open'?'var(--sheet)':(s?'var(--ink)':'var(--muted)')}">${n.label}</text></g>`}
  $('tree').innerHTML=svg+'</svg>';
}
function stop(){if(timer){clearInterval(timer);timer=null}$('play').textContent='Play'}
$('next').onclick=()=>{stop();if(step<run.trace.length-1){step++;render()}};
$('prev').onclick=()=>{stop();if(step>0){step--;render()}};
$('first').onclick=()=>{stop();step=0;render()};
$('scrub').oninput=e=>{stop();step=+e.target.value;render()};
$('play').onclick=()=>{if(timer)return stop();if(step>=run.trace.length-1)step=0;$('play').textContent='Pause';
  timer=setInterval(()=>{if(step>=run.trace.length-1)return stop();step++;render()},1400);render()};
document.addEventListener('keydown',e=>{if(e.target.closest&&e.target.closest('input'))return;if(e.key==='ArrowRight')$('next').click();if(e.key==='ArrowLeft')$('prev').click()});
rerun();

// Charts, drawn to scale from the solver constants.
function annealChart(){const W=420,H=190,L=40,R=36,T=14,B=34,w=W-L-R,h=H-T-B;
  const x=s=>L+s/1200*w,yT=v=>T+h-(v/6)*h,yP=v=>T+h-v*h;
  let s='';for(let v=0;v<=6;v+=2)s+=`<line x1="${L}" x2="${L+w}" y1="${yT(v)}" y2="${yT(v)}" stroke="var(--rule)"/><text x="${L-6}" y="${yT(v)+4}" text-anchor="end">${v}</text>`;
  for(const p of [0,.5,1])s+=`<text x="${L+w+6}" y="${yP(p)+4}">${p}</text>`;
  for(const st of [0,300,600,900,1200])s+=`<text x="${x(st)}" y="${H-16}" text-anchor="middle">${st}</text>`;
  s+=`<text x="${L+w/2}" y="${H-2}" text-anchor="middle">step within a run</text>`;
  const path=f=>Array.from({length:61},(_,k)=>{const st=k*20;return `${k?'L':'M'}${x(st).toFixed(1)},${f(st).toFixed(1)}`}).join('');
  const temp=st=>0.3+5*(1-st/1200);
  s+=`<path d="${path(st=>yT(temp(st)))}" fill="none" stroke="var(--ink)" stroke-width="2"/>`;
  s+=`<path d="${path(st=>yP(Math.exp(-1/temp(st))))}" fill="none" stroke="var(--teal)" stroke-width="2"/>`;
  s+=`<path d="${path(st=>yP(Math.exp(-4/temp(st))))}" fill="none" stroke="var(--focus)" stroke-width="2" stroke-dasharray="5 4"/>`;
  s+=`<text x="${L+8}" y="${yT(temp(0))-6}" style="fill:var(--ink)">temperature T (left axis)</text>`;
  s+=`<text x="${x(470)}" y="${yP(Math.exp(-1/temp(470)))-8}" style="fill:var(--teal)">accept Δ = −1</text>`;
  s+=`<text x="${x(560)}" y="${yP(Math.exp(-4/temp(560)))+18}" style="fill:var(--focus)">accept Δ = −4</text>`;
  $('annealchart').innerHTML=s}
function capChart(){const W=420,H=190,L=40,R=14,T=14,B=34,w=W-L-R,h=H-T-B;
  // Schematic: caps 1 → 2 → 3 with no hypothesis, then a hypothesis of cost 3 found, restart at cap 2, improve to 2, restart at cap 1, no improvement.
  const phases=[{c:1,n:1,f:null},{c:2,n:1,f:null},{c:3,n:1.3,f:3},{c:2,n:1.5,f:2},{c:1,n:2.2,f:null}];
  const total=phases.reduce((a,p)=>a+p.n,0);const x=v=>L+v/total*w,y=v=>T+h-v/4*h;
  let s='';for(let v=0;v<=4;v++)s+=`<line x1="${L}" x2="${L+w}" y1="${y(v)}" y2="${y(v)}" stroke="var(--rule)"/><text x="${L-6}" y="${y(v)+4}" text-anchor="end">${v}</text>`;
  let at=0;phases.forEach((p,k)=>{s+=`<rect x="${x(at)+1}" y="${y(p.c)}" width="${x(at+p.n)-x(at)-2}" height="${y(0)-y(p.c)}" fill="var(--teal-soft)" stroke="var(--teal)"/>`;
    if(p.f!=null)s+=`<circle cx="${x(at+p.n*.8)}" cy="${y(p.f)}" r="5" fill="var(--focus)"/>`;
    s+=`<text x="${(x(at)+x(at+p.n))/2}" y="${H-16}" text-anchor="middle">${k===0?'start':p.f!=null?'found '+p.f:k===4?'no gain':'widen'}</text>`;at+=p.n});
  s+=`<text x="${L+w/2}" y="${H-2}" text-anchor="middle">phases (schematic) · bars: cap · dots: best hypothesis</text>`;
  s+=`<text x="${L+4}" y="${T+10}">unsupported words</text>`;
  $('capchart').innerHTML=s}
annealChart();capChart();
})();
