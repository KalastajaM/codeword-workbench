// Compact port of _domain_propagation and _constraint_search for standard rules.
function slotsOf(p){const S=[];for(const dir of ['Across','Down']){const lines=[];
  if(dir==='Across')for(let r=0;r<p.rows;r++)lines.push([...Array(p.cols)].map((_,c)=>r*p.cols+c));
  else for(let c=0;c<p.cols;c++)lines.push([...Array(p.rows)].map((_,r)=>r*p.cols+c));
  for(const line of lines){let seg=[];for(const i of [...line,null]){if(i!==null&&!p.cells[i].black){seg.push(i);continue}if(seg.length>=2)S.push({cells:seg,dir});seg=[]}}}
  return S}
function shape(items){const m=new Map();return items.map(x=>{if(!m.has(x))m.set(x,m.size);return m.get(x)}).join(',')}
function solve(p,words,score,limit=12){
  const cells=p.cells,slots=slotsOf(p),trace=[];let rounds=0;
  const num=i=>cells[i].number;
  const label=j=>`${slots[j].dir} r${Math.floor(slots[j].cells[0]/p.cols)+1}c${slots[j].cells[0]%p.cols+1}`;
  const forced=L=>{const k={};cells.forEach((c,i)=>{if(!c.black&&L[i])k[c.number]=L[i]});return cells.map((c,i)=>c.black?'':(k[c.number]||L[i]))};
  const okMap=L=>{const g={},o={};for(let i=0;i<cells.length;i++){const l=L[i];if(!l||cells[i].black)continue;const n=num(i);if(g[n]&&g[n]!==l)return false;if(o[l]&&o[l]!==n)return false;g[n]=l;o[l]=n}return true};
  const compat=(s,w,L)=>{const T=L.slice();for(let q=0;q<w.length;q++){const i=s.cells[q];if(T[i]&&T[i]!==w[q])return false;T[i]=w[q]}return okMap(forced(T))};
  const base=forced(cells.map(c=>c.black?'':(c.letter||'')));
  const rank=(a,b)=>(score[b]??0)-(score[a]??0)||(a<b?-1:1);
  const info=slots.map(s=>{const want=shape(s.cells.map(num));const len=words.filter(w=>w.length===s.cells.length);const pat=len.filter(w=>shape([...w])===want);
    return {byLen:len.length,byPat:pat.length,kept:pat.filter(w=>compat(s,w,base)).sort(rank)}});
  trace.push({type:'candidates',letters:base.slice(),domains:info.map(d=>d.kept),info,removed:slots.map(()=>[])});
  function propagate(L,D,depth){D=D.map(d=>d&&d.slice());
    for(let round=1;;round++){rounds++;L=forced(L);
      const removed=D.map(()=>[]);const sup={};
      const fail=(why,slot)=>({fail:why,slot,D,removed,L});
      if(!okMap(L))return fail('two numbers would share a letter');
      for(let j=0;j<slots.length;j++){if(!D[j])continue;const k=[];for(const w of D[j])(compat(slots[j],w,L)?k:removed[j]).push(w);D[j]=k;
        if(!k.length)return fail(`no candidate is left for ${label(j)}`,j);
        slots[j].cells.forEach((i,q)=>{const v=new Set(k.map(w=>w[q]));const n=num(i);sup[n]=sup[n]?new Set([...sup[n]].filter(x=>v.has(x))):v});
        for(const n in sup)if(!sup[n].size)return fail(`number ${n} has no letter left`,j)}
      const own={};cells.forEach((c,i)=>{if(!c.black&&L[i])own[L[i]]=c.number});
      for(const n in sup)if(sup[n].size===1){const l=[...sup[n]][0];if(own[l]&&own[l]!=n)return fail(`letter ${l} would belong to two numbers`);own[l]=+n}
      for(const n in sup){sup[n]=new Set([...sup[n]].filter(v=>!own[v]||own[v]==n));if(!sup[n].size)return fail(`number ${n} has no letter left`)}
      const newly=[];
      cells.forEach((c,i)=>{if(c.black)return;const v=sup[c.number];if(v&&!L[i]&&v.size===1){L[i]=[...v][0];newly.push(i)}});
      let changed=newly.length>0||removed.some(r=>r.length);
      for(let j=0;j<slots.length;j++){if(!D[j])continue;const k=D[j].filter(w=>slots[j].cells.every((i,q)=>!sup[num(i)]||sup[num(i)].has(w[q])));
        if(k.length!==D[j].length){changed=true;removed[j].push(...D[j].filter(w=>!k.includes(w)))}D[j]=k;if(!k.length)return fail(`no candidate is left for ${label(j)}`,j)}
      const support={};for(const n in sup)support[n]=[...sup[n]].sort().join('');
      trace.push({type:'propagate',depth,round,letters:L.slice(),domains:D.map(d=>d&&d.slice()),removed,newly,support,changed});
      if(!changed)return {L,D}}}
  // Keeps the `limit` highest-scoring solutions; a branch whose best possible
  // score (each open slot's top candidate) cannot beat the weakest is cut.
  const wordScore=w=>score[w]??0,total=L=>slots.reduce((a,s)=>a+wordScore(s.cells.map(i=>L[i]).join('')),0);
  const cut=(L,D)=>{if(sols.length<limit)return false;
    const bound=slots.reduce((a,s,j)=>a+(D[j]&&!s.cells.every(i=>L[i])?wordScore(D[j][0]):wordScore(s.cells.map(i=>L[i]).join(''))),0);
    return bound<=Math.min(...sols.map(x=>x.score))};
  const bounded=(st,L,D)=>{trace.push({type:'bound',depth:st.depth,node:st.id,letters:L.slice(),domains:D,removed:slots.map(()=>[])})};
  const stack=[{L:base.slice(),D:info.map(d=>d.kept),depth:0,id:0,parent:null}];const sols=[];let nodes=0,nextId=1,found=0;
  while(stack.length){const st=stack.pop();nodes++;
    if(st.via)trace.push({type:'branch',depth:st.depth,node:st.id,slot:st.via.slot,word:st.via.word,letters:st.L.slice(),domains:st.D,removed:slots.map(()=>[])});
    if(cut(st.L,st.D)){bounded(st,st.L,st.D);continue}
    const r=propagate(st.L,st.D,st.depth);
    if(r.fail){trace.push({type:'dead',depth:st.depth,node:st.id,reason:r.fail,slot:r.slot,letters:r.L.slice(),domains:r.D,removed:r.removed});continue}
    let {L,D}=r;
    if(cut(L,D)){bounded(st,L,D);continue}const filled=D.map((d,j)=>!!d&&slots[j].cells.every(i=>L[i]));D=D.map((d,j)=>filled[j]?null:d);
    const open=D.map((d,j)=>d?j:-1).filter(j=>j>=0);
    if(open.length){const best=open.sort((a,b)=>D[a].length-D[b].length||slots[b].cells.length-slots[a].cells.length||a-b)[0];
      const rest=D.map((d,j)=>j===best?null:d);
      const kids=D[best].map(w=>{const T=L.slice();slots[best].cells.forEach((i,q)=>T[i]=w[q]);return {L:T,D:rest,depth:st.depth+1,id:nextId++,parent:st.id,via:{slot:best,word:w}}});
      trace.push({type:'choose',depth:st.depth,node:st.id,slot:best,options:D[best].slice(),letters:L.slice(),domains:D,removed:slots.map(()=>[]),kids:kids.map(k=>({id:k.id,word:k.via.word}))});
      stack.push(...kids.slice().reverse());continue}
    sols.push({L,score:total(L)});found++;
    if(sols.length>limit){let w=0;sols.forEach((x,k)=>{if(x.score<sols[w].score)w=k});sols.splice(w,1)}
    trace.push({type:'solution',depth:st.depth,node:st.id,letters:L.slice(),index:found,domains:D,removed:slots.map(()=>[])})}
  sols.sort((a,b)=>b.score-a.score);
  trace.push({type:'done',nodes,rounds,solutions:sols.length,letters:sols[0]?sols[0].L:base,domains:info.map(()=>null),removed:slots.map(()=>[])});
  return {slots,trace,sols:sols.map(x=>x.L),nodes,rounds}}
if(typeof module!=='undefined')module.exports={solve,slotsOf};
