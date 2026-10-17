'use strict';
const $ = id => document.getElementById(id);
const flags = {'open-before-across':'openBeforeAcross','open-after-across':'openAfterAcross','open-before-down':'openBeforeDown','open-after-down':'openAfterDown'};
// Guided demo state (see watch-demo below); declared early because setPuzzle reads it.
let demoRun=0,demoActive=false;
let puzzle, selected=0, editMode=true, solutionIndex=0, revision=0, validateTimer, ocrAvailable=false, dictionaryLanguage='en', loadToken=0;
const rules = () => ({maxLettersPerNumber:1, uniqueLetters:true, forbiddenPatterns:[], discouragedPatterns:[]});
function fresh(rows=7,cols=7,language='en') {return {name:'Untitled puzzle',rows,cols,language,useDictionary:true,rules:rules(),cells:Array.from({length:rows*cols},PuzzleState.blankCell)};}
let numericEntry=null,alignmentDirty=false,fitMode='width',viewScale=1;
const acceptanceHistory=PuzzleState.acceptanceHistory();
let wordDirection='Across',lastClickedCell=null;
let candidateKeys=new Set(),candidateResult=null,candidateBusy=false,candidateRequest=0;
let solvedWordFilter='all',solvedWordSort='uncertain';
function notify(message,error=false){$('notice').textContent=message;$('notice').classList.toggle('error',error);$('notice').hidden=false;}
let confirmPending=null;
function confirmAction(message,title="Replace current work?",labels={}){
 if(confirmPending)return Promise.resolve(false);
 const dialog=$('confirm-dialog');
 $('confirm-title').textContent=title;$('confirm-message').textContent=message;
 $('confirm-continue').textContent=labels.confirm||'Continue';$('confirm-cancel').textContent=labels.cancel||'Cancel';
 dialog.returnValue='';
 return new Promise(resolve=>{confirmPending={resolve,puzzle,revision};dialog.showModal();});
}
$('confirm-cancel').onclick=()=>$('confirm-dialog').close('cancel');
$('confirm-continue').onclick=()=>$('confirm-dialog').close('continue');
$('confirm-dialog').addEventListener('close',()=>{
 const pending=confirmPending;confirmPending=null;
 if(!pending)return;
 const current=pending.puzzle===puzzle&&pending.revision===revision;
 const accepted=$('confirm-dialog').returnValue==='continue';
 if(accepted&&!current)notify('The workspace changed while you were reviewing this action. Please try again.');
 pending.resolve(accepted&&current);
});
// Image import and recognition run behind a modal progress dialog, so nothing
// else can change the workspace while they work. Cancel (or Escape) aborts
// the request; the task then stops at its next step.
let busyTask=null;
function startBusyTask(title,cancelLabel){
 const controller=new AbortController();
 const task={signal:controller.signal,
  get cancelled(){return controller.signal.aborted;},
  step(message){if(busyTask===task)$('busy-message').textContent=message;},
  cancel(){if(task.cancelled)return;controller.abort();task.finish();},
  finish(){if(busyTask!==task)return;busyTask=null;if($('busy-dialog').open)$('busy-dialog').close();}};
 busyTask?.cancel();busyTask=task;
 $('busy-title').textContent=title;$('busy-message').textContent='';$('busy-cancel').textContent=cancelLabel;
 $('busy-dialog').showModal();
 return task;
}
$('busy-cancel').onclick=()=>busyTask?.cancel();
$('busy-dialog').addEventListener('close',()=>{if(!$('busy-dialog').open)busyTask?.cancel();});
async function api(path,body,method,signal){const response=await fetch(path,{method:method||(body?'POST':'GET'),headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal});const result=await response.json();if(!response.ok){if(response.status===401&&result.signIn&&session.mode!=='signed-out')applySession({...session,mode:'signed-out'});throw new Error(result.error||'Request failed');}return result;}
// Access level from the server. Guests keep their work in this browser; user
// mode (shared password) saves puzzles and dictionaries on the server.
let session={mode:'local'},modeView=PuzzleState.workspaceModeView(session),healthLoaded=false,afterSignIn=null;
function applySession(info){
 const changed=info.mode!==session.mode;session=info;modeView=PuzzleState.workspaceModeView(info);
 $('mode-label').textContent=modeView.label;$('mode-tag').classList.toggle('hosted',modeView.mode!=='local');
 $('save').hidden=$('load').hidden=!modeView.serverStorage;
 $('user-mode').hidden=!modeView.modeButton;$('user-mode').textContent=modeView.modeButton||'';
 $('dictionary-mode-note').hidden=!modeView.dictionaryNote;$('dictionary-mode-note').textContent=modeView.dictionaryNote;
 if(changed&&typeof dictionaryEditor!=='undefined'){
  // Another dictionary applies now: drop dictionary checks made with the old one.
  dictionaryEditor.cancel();$('dictionary-dialog').close();$('load-dialog').close();wordChecks.clear();render();
 }
 if(modeView.mode==='signed-out')return openSignIn();
 loadHealth();if(afterSignIn){const resume=afterSignIn;afterSignIn=null;resume();}
}
function openSignIn(){
 const required=session.mode==='signed-out';
 $('signin-message').textContent=required?'This workspace needs the access password.':'User mode saves puzzles and dictionaries on the server. Everyone with the password shares them. Your current puzzle stays open.';
 $('signin-cancel').hidden=required;$('signin-error').textContent='';$('signin-password').value='';
 if(!$('signin-dialog').open)$('signin-dialog').showModal();$('signin-password').focus();
}
$('signin-form').onsubmit=async event=>{event.preventDefault();$('signin-submit').disabled=true;
 try{const info=await api('/api/login',{password:$('signin-password').value});$('signin-dialog').close();applySession(info);notify('User mode: Save puzzle and dictionary changes now go to the server.');}
 catch(error){$('signin-error').textContent=error.message;}
 finally{$('signin-submit').disabled=false;}};
$('signin-cancel').onclick=()=>$('signin-dialog').close();
$('signin-dialog').addEventListener('cancel',event=>{if(session.mode==='signed-out')event.preventDefault();});
$('user-mode').onclick=protect(async()=>{
 if(session.mode!=='user')return openSignIn();
 applySession(await api('/api/logout',{}));
 if(session.mode==='guest')notify('Guest mode: your work stays in this browser. Use Export JSON to keep a copy.');
});
function protect(fn){return async(...args)=>{try{await fn(...args);}catch(error){notify(error.message,true);}};}
function invalidate(keepSuggestions=false){clearCandidateResults();clearLookup();acceptanceHistory.clear();if($('solve-status').textContent)$('solve-status').textContent='Puzzle changed. Solve again for current suggestions.';solveJob.cancel();revision++;if(!keepSuggestions)delete puzzle.suggestions;PuzzleState.refreshDeductions(puzzle,keepSuggestions);solutionIndex=keepSuggestions?Math.min(solutionIndex,Math.max(0,(puzzle.suggestions?.solutions?.length||1)-1)):0;clearTimeout(validateTimer);validateTimer=setTimeout(validate,180);}
// A corrected number keeps the suggestions, adjusted to the new number, so a
// typo found after solving does not throw the result away.
function changeNumber(index,number){
 const had=!!(puzzle.suggestions?.solutions?.length||puzzle.suggestions?.partialLetters);
 if(!PuzzleState.renumberCell(puzzle,index,number))return;
 invalidate(true);
 if(had)$('solve-status').textContent=puzzle.suggestions?.solutions?.length||puzzle.suggestions?.partialLetters?'Number changed. The suggestions now use the new number; solve again to check them.':'Number changed. No suggestion fits the confirmed letters any more; solve again.';
}
async function validate(){const version=revision;try{const result=await api('/api/validate',puzzle);if(version===revision){$('conflicts').textContent=result.conflicts.join(' · ');eliminationSuggestions=result.valid&&Array.isArray(result.suggestedEliminations)?result.suggestedEliminations:[];renderEliminations();}}catch(error){if(version===revision){$('conflicts').textContent=error.message;eliminationSuggestions=[];renderEliminations();}}}
function solution(){return puzzle.suggestions?.solutions?.[solutionIndex];}
// Best unverified mapping streamed by a running dictionary-free search; cleared when it ends.
let livePreview=null,livePreviewMargins=null;
// Recorded improvements of the latest dictionary-free solve, for replay. Kept
// out of puzzle.suggestions so saved puzzles stay small; valid only while the
// result it came with is still displayed.
let replay=null,replayFor=null,replayIndex=null,replayTimer=null;
const replaying=()=>replayIndex!==null&&!!replay&&replayFor===puzzle.suggestions;
const showingPreview=()=>!!livePreview&&(!$('cancel-solve').hidden||replaying());
function showReplayStep(k){
 replayIndex=Math.max(0,Math.min(k,replay.length-1));const frame=replay[replayIndex];
 livePreview=frame.letters;livePreviewMargins=frame.numberMargins||null;renderGrid();
}
function stopReplayTimer(){if(replayTimer){clearInterval(replayTimer);replayTimer=null;}}
function exitReplay(){stopReplayTimer();if(replayIndex===null)return;replayIndex=null;livePreview=null;livePreviewMargins=null;renderGrid();}
// Score (dictionary-free) or filled cells (dictionary) per replay step: a
// single teal line, the current step marked; hover reads a step, click jumps.
const SVG_NS='http://www.w3.org/2000/svg';
function replayValues(){const dictionary=replay.some(f=>f.kind);return {dictionary,values:replay.map(f=>dictionary?f.letters.filter(Boolean).length:f.score)};}
function replayChartLabel(k){
 const {dictionary,values}=replayValues();
 if(k===null)return dictionary?`Cells filled: ${values[0]} → ${values[values.length-1]}`:`Pattern score: ${values[0].toFixed(0)} → ${values[values.length-1].toFixed(0)}`;
 return `Step ${k+1}: ${dictionary?values[k]+' cells filled':'score '+values[k].toFixed(1)}`;
}
function renderReplayChart(){
 const svg=$('replay-chart');[...svg.querySelectorAll(':not(title)')].forEach(e=>e.remove());
 if(!replay)return;
 const {dictionary,values}=replayValues(),W=240,H=56,P=6,n=values.length;
 $('replay-chart-title').textContent=(dictionary?'Cells filled':'Pattern score')+' per replay step';
 const min=Math.min(...values),max=Math.max(...values),x=i=>P+i*(W-2*P)/Math.max(1,n-1),y=v=>H-P-(v-min)/((max-min)||1)*(H-2*P);
 const el=(tag,attrs)=>{const e=document.createElementNS(SVG_NS,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);svg.append(e);return e;};
 el('line',{x1:P,x2:W-P,y1:H-P,y2:H-P,class:'replay-chart-axis'});
 el('path',{d:values.map((v,i)=>`${i?'L':'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(''),class:'replay-chart-line'});
 const guide=el('line',{x1:0,x2:0,y1:P,y2:H-P,class:'replay-chart-guide',visibility:'hidden'});
 const k=replayIndex??n-1;el('circle',{cx:x(k),cy:y(values[k]),r:4,class:'replay-chart-point'});
 const nearest=event=>{const box=svg.getBoundingClientRect();return Math.max(0,Math.min(n-1,Math.round(((event.clientX-box.left)/box.width*W-P)/((W-2*P)/Math.max(1,n-1)))));};
 svg.onpointermove=event=>{const i=nearest(event);guide.setAttribute('x1',x(i));guide.setAttribute('x2',x(i));guide.setAttribute('visibility','visible');$('replay-chart-label').textContent=replayChartLabel(i);};
 svg.onpointerleave=()=>{guide.setAttribute('visibility','hidden');$('replay-chart-label').textContent=replayChartLabel(replayIndex);};
 svg.onclick=event=>{stopReplayTimer();showReplayStep(nearest(event));};
 $('replay-chart-label').textContent=replayChartLabel(replayIndex);
}
function renderReplay(){
 const available=!!replay&&replayFor===puzzle.suggestions;
 $('replay-controls').hidden=!available;if(!available){stopReplayTimer();replayIndex=null;return;}
 const range=$('replay-range');range.max=String(replay.length-1);range.value=String(replayIndex??replay.length-1);
 $('replay-play').textContent=replayTimer?'Pause':replayIndex===null?'Replay search':'Play';$('replay-exit').hidden=replayIndex===null;
 const frame=replay[replayIndex??replay.length-1];
 const kind={step:' · word placed',dead:' · dead end, backing up',solution:' · complete grid',partial:' · grid with unresolved cells',result:' · result'}[frame.kind]||'';
 renderReplayChart();
 $('replay-label').textContent=replayIndex===null?`${replay.length} steps recorded`:`Step ${replayIndex+1} of ${replay.length} · ${frame.seconds.toFixed(2)} s into the search${kind}`;
}
function suggestion(i){if(showingPreview()&&!puzzle.cells[i]?.letter)return livePreview[i]||'';return PuzzleState.suggestedLetter(puzzle,i,solutionIndex);}
function isDeduction(i){const forced=puzzle.suggestions?.forcedLetters?.[i];return !!forced&&suggestion(i)===forced;}
function normalize(text){return text.normalize('NFC').toUpperCase();}
function setPuzzle(value,editing=true){if(!demoActive)demoCaption('');straightenHandles=null;layoutTarget=null;placedLayout=null;clearLookup();if(typeof dictionaryEditor!=='undefined'){dictionaryEditor.cancel();$('dictionary-dialog').close();}wordDirection='Across';lastClickedCell=null;editMode=editing;clearCandidateResults(true);$('solve-status').textContent='';fitMode='width';acceptanceHistory.clear();numericEntry=null;puzzle=PuzzleState.canonicalPuzzle(value);PuzzleState.refreshDeductions(puzzle);selected=0;solutionIndex=0;solveJob.cancel();revision++;syncControls();render();validate();savedFingerprint=workspaceFingerprint();}
function syncControls(){$('number-position').value=puzzle.numberPosition;$('search-mode').value=puzzle.searchMode;$('allow-unknown-words').checked=puzzle.allowUnknownWords;alignmentDirty=false;$('alignment-status').textContent='';for(const key of ['name','rows','cols','language'])$(key).value=puzzle[key];$('use-dictionary').checked=puzzle.useDictionary;$('capacity').value=puzzle.rules.maxLettersPerNumber;$('forbidden').value=puzzle.rules.forbiddenPatterns.join('\n');$('discouraged').value=puzzle.rules.discouragedPatterns.join('\n');const bounds=puzzle.imageBounds||{x:0,y:0,width:1,height:1};for(const key of ['x','y','width','height'])$('bound-'+key).value=Math.round(bounds[key]*1000)/10;}
// Any full render follows a user action or a new result: leave the replay.
function render(){stopReplayTimer();if(replayIndex!==null){replayIndex=null;livePreview=null;livePreviewMargins=null;}renderGrid();renderStraighten();renderInspector();renderMapping();renderResults();renderCandidatePanel();renderEditMode();renderGenerated();}
function renderGrid(){const grid=$('grid'), stage=$('board-stage'),image=$('puzzle-image');renderReplay();const live=showingPreview(),certaintyAvailable=live?!!livePreviewMargins:!!puzzle.suggestions?.solutions?.[solutionIndex]?.numberMargins;$('certainty-controls').hidden=!certaintyAvailable;const certainty=certaintyAvailable&&$('show-certainty').checked?PuzzleState.letterCertainty(puzzle,solutionIndex,live?livePreviewMargins:undefined):null;$('certainty-legend').hidden=!certainty;const wrongLetters=currentAnswerMarks();$('review-legend').hidden=!puzzle.cells.some(c=>!c.black&&(c.numberReview==='check'&&c.number||c.numberReview==='missing'&&!c.number));grid.dataset.numberPosition=PuzzleState.displayNumberPosition(puzzle);grid.replaceChildren();grid.style.gridTemplateColumns=`repeat(${puzzle.cols}, 1fr)`;grid.style.gridTemplateRows=`repeat(${puzzle.rows}, 1fr)`;stage.classList.toggle('image-mode',!!puzzle.image);image.hidden=!puzzle.image;$('image-controls').hidden=!puzzle.image;$('grid-summary').textContent=`${puzzle.rows} × ${puzzle.cols} · ${PuzzleState.languagePresentation(puzzle).name} · ${PuzzleState.layoutSummaryText(PuzzleState.layoutSummary(puzzle))} · ${puzzle.cells.filter(c=>!c.black&&c.letter).length} confirmed`;if(puzzle.image){if(image.src!==puzzle.image)image.src=puzzle.image;const b=puzzle.imageBounds||{x:0,y:0,width:1,height:1};Object.assign(grid.style,{left:b.x*100+'%',top:b.y*100+'%',width:b.width*100+'%',height:b.height*100+'%'});}else{stage.style.width='';for(const key of ['left','top','width','height'])grid.style[key]='';}
puzzle.cells.forEach((cell,i)=>{const rival=certainty?.[i];const button=document.createElement('button');button.className='cell'+(rival&&rival.level!=='clear'?' certainty-'+rival.level:'')+(wrongLetters?.has(i)?' wrong':'')+(cell.black?' black':'')+(cell.clue?' clue':'')+(cell.highlight?' highlight':'')+(selected===i?' selected':'');button.type='button';button.setAttribute('role','gridcell');button.setAttribute('aria-selected',String(selected===i));button.tabIndex=selected===i?0:-1;button.setAttribute('aria-label',`Row ${Math.floor(i/puzzle.cols)+1}, column ${i%puzzle.cols+1}, ${cell.clue?'image clue area':cell.black?'black':`number ${cell.number||'none'}${cell.numberReview==='check'&&cell.number?' (check recognition)':cell.numberReview==='missing'&&!cell.number?' (not recognized)':''}, ${cell.letter?'confirmed '+cell.letter:suggestion(i)?'suggested '+suggestion(i):'empty'}`}`);if(rival)button.setAttribute('aria-description',button.title=`${{close:'Close rival',moderate:'Moderate lead',clear:'Clear lead'}[rival.level]}: next-best letter for number ${rival.number} is ${rival.alternative}, ${rival.margin} points lower`);if(!cell.black){const number=document.createElement('span'),review=cell.numberReview==='missing'&&!cell.number?'missing':cell.numberReview==='check'&&cell.number?'check':'';number.className='number'+(review?' review-'+review:'');number.textContent=review==='missing'?'?':cell.number;if(review)number.title=review==='missing'?'No number recognized here. Enter it from the image.':'Recognized number may be wrong. Check it against the image.';const letter=document.createElement('span');letter.className='letter'+(!cell.letter?(showingPreview()?' provisional live':isDeduction(i)?' deduction':' provisional'):'');letter.textContent=cell.letter||suggestion(i);button.append(number,letter);for(const [flag,side] of [['openBeforeAcross','left'],['openAfterAcross','right'],['openBeforeDown','top'],['openAfterDown','bottom']]){if(cell[flag]&&isEndpoint(i,side)){const mark=document.createElement('i');mark.className='boundary '+side;button.append(mark);}}}button.onclick=()=>{numericEntry=null;const word=PuzzleState.cellWord(puzzle,i,i===lastClickedCell?wordDirection:'Across',i===lastClickedCell,solutionIndex);selected=i;lastClickedCell=i;wordDirection=word?.direction||'Across';render(); $('grid').children[selected].focus();};button.onkeydown=e=>gridKey(e);grid.append(button);});renderWordHighlights();updateView();}
function isEndpoint(i,side){const r=Math.floor(i/puzzle.cols),c=i%puzzle.cols;return side==='left'?(c===0||puzzle.cells[i-1].black):side==='right'?(c===puzzle.cols-1||puzzle.cells[i+1].black):side==='top'?(r===0||puzzle.cells[i-puzzle.cols].black):(r===puzzle.rows-1||puzzle.cells[i+puzzle.cols].black);}
function renderInspector(){const c=puzzle.cells[selected];$('cell-position').textContent=`${Math.floor(selected/puzzle.cols)+1}, ${selected%puzzle.cols+1}`;$('cell-black').checked=c.black;$('cell-clue').checked=!!c.clue;$('cell-highlight').checked=!!c.highlight&&!c.black;$('cell-number').value=c.number;$('cell-letter').value=c.letter||suggestion(selected)||'';$('cell-number').disabled=c.black||!editMode;$('cell-letter').disabled=c.black||(!editMode&&c.prefilled);for(const [id,key]of Object.entries(flags)){$(id).checked=!!c[key];$(id).disabled=!editMode||c.black||!isEndpoint(selected,{'open-before-across':'left','open-after-across':'right','open-before-down':'top','open-after-down':'bottom'}[id]);}$('cell-suggestion').textContent=!c.letter&&suggestion(selected)?`${PuzzleState.suggestionLabel(puzzle,selected,solutionIndex)}: ${suggestion(selected)}`:'';$('cell-confirmed').checked=!!c.letter;$('cell-confirmed').disabled=c.black||(!c.letter&&!suggestion(selected))||(!editMode&&c.prefilled);renderCellRuledOut();}

function renderMapping(){
 renderEliminations();
 const map=new Map();
 puzzle.cells.forEach((cell,i)=>{if(cell.black||!cell.number)return;if(!map.has(cell.number))map.set(cell.number,{known:new Set(),proposed:new Set()});if(cell.letter)map.get(cell.number).known.add(cell.letter);else if(suggestion(i))map.get(cell.number).proposed.add(suggestion(i));});
 const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ'+(PuzzleState.nordicLetters(puzzle.language)?'ÅÄÖ':'');
 const matched=new Set([...map.values()].flatMap(sets=>[...sets.known,...sets.proposed]));
 const unmatched=[...alphabet].filter(letter=>!matched.has(letter));
 const unmatchedRoot=$('unmatched-letters');unmatchedRoot.replaceChildren();
 const unmatchedZone=unmatchedRoot.parentElement;
 unmatchedZone.ondragover=event=>{if(draggedAssigned&&assignmentCurrent(draggedAssigned)){event.preventDefault();event.dataTransfer.dropEffect='move';unmatchedZone.classList.add('drag-over');}};
 unmatchedZone.ondragleave=event=>{if(!unmatchedZone.contains(event.relatedTarget))unmatchedZone.classList.remove('drag-over');};
 unmatchedZone.ondrop=protect(async event=>{event.preventDefault();unmatchedZone.classList.remove('drag-over');const source=draggedAssigned;draggedAssigned=null;if(!source||!assignmentCurrent(source))return;await removeNumberAssignment(source);});
 if(pickedUnmatched&&(!assignmentCurrent(pickedUnmatched)||!unmatched.includes(pickedUnmatched.letter)))pickedUnmatched=null;
 if(!unmatched.length)unmatchedRoot.textContent='None. All letters have a match.';
 unmatched.forEach(letter=>{const button=document.createElement('button');button.type='button';button.className='unmatched-letter';button.textContent=letter;button.draggable=true;button.setAttribute('aria-label',`Select ${letter}, then choose an empty number box`);button.setAttribute('aria-pressed',String(pickedUnmatched?.letter===letter));
  button.onclick=()=>{pickedUnmatched=pickedUnmatched?.letter===letter?null:{...assignmentContext(),letter};renderMapping();};
  button.ondragstart=event=>{draggedAssigned=null;draggedUnmatched={...assignmentContext(),letter};event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',letter);};
  button.ondragend=()=>{draggedUnmatched=null;document.querySelectorAll('.map-item.drag-over').forEach(tile=>tile.classList.remove('drag-over'));};unmatchedRoot.append(button);
 });
 const root=$('mapping');root.replaceChildren();
 if(!map.size){root.textContent='Add numbers to build your mapping.';root.className='hint';return;}
 root.className='mapping-grid';
 [...map].sort((a,b)=>Number(a[0])-Number(b[0])).forEach(([num,sets])=>{
  const tile=document.createElement('div');tile.className='map-item';let suppressClickUntil=0;
  const letters=[...new Set([...sets.known,...sets.proposed])];
  tile.ondragover=event=>{const source=draggedAssigned||draggedUnmatched;if(source&&assignmentCurrent(source)&&(draggedAssigned||unmatched.includes(source.letter))){event.preventDefault();event.dataTransfer.dropEffect='move';tile.classList.add('drag-over');}};
  tile.ondragleave=()=>tile.classList.remove('drag-over');
  tile.ondrop=protect(async event=>{event.preventDefault();tile.classList.remove('drag-over');const assigned=draggedAssigned,source=assigned||draggedUnmatched;draggedAssigned=null;draggedUnmatched=null;if(!source||!assignmentCurrent(source))return;if(assigned)await moveNumberAssignment(source,num);else if(unmatched.includes(source.letter))await applyNumberAssignment({...source,number:num},source.letter);});
  const startDrag=letter=>event=>{event.stopPropagation();suppressClickUntil=Infinity;draggedUnmatched=null;draggedAssigned={...assignmentContext(),number:num,letter};event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',letter);};
  const endDrag=()=>{suppressClickUntil=Date.now()+300;draggedAssigned=null;unmatchedZone.classList.remove('drag-over');document.querySelectorAll('.map-item.drag-over').forEach(item=>item.classList.remove('drag-over'));};
  if(letters.length!==1){const number=document.createElement('span');number.className='map-number';number.textContent=num;tile.append(number);}
  if(!letters.length){const empty=document.createElement('button');empty.type='button';empty.className='map-assign';empty.textContent='·';empty.setAttribute('aria-label',`Assign a letter to number ${num}, empty`);empty.onclick=()=>openNumberAssignment(num);tile.append(empty);}
  letters.forEach(letter=>{
   const info=PuzzleState.mappingLetterInfo(puzzle,num,letter,solutionIndex),button=document.createElement('button');button.type='button';button.className='map-assign '+info.status;button.dataset.number=num;button.dataset.letter=letter;
   if(letters.length===1){const number=document.createElement('span');number.className='map-number';number.textContent=num;button.append(number);}
   const value=document.createElement('span');value.className='map-assignment-letters '+info.status;value.textContent=letter;button.append(value);
   const next=info.status==='confirmed'?'suggested':info.status==='suggested'&&puzzle.rules.maxLettersPerNumber===1?'mapping':'confirmed';
   const status=info.status==='mapping'?'mapping deduction':info.status;
   button.title=`${letter}: ${status}. Click to make ${next}. Delete or Backspace removes this letter.${puzzle.rules.maxLettersPerNumber!==1?' Mapping is unavailable when a number allows multiple letters.':''}`;
   button.setAttribute('aria-label',`Number ${num}, ${letter}, ${status}. Change to ${next}. Press Delete or Backspace to remove.`);
   button.onclick=protect(async()=>{if(Date.now()>=suppressClickUntil)await cycleMappingLetter({...assignmentContext(),number:num,letter});});
   button.onkeydown=protect(async event=>{if(['Delete','Backspace'].includes(event.key)){event.preventDefault();event.stopPropagation();await removeNumberAssignment({...assignmentContext(),number:num,letter});}});
   button.draggable=true;button.ondragstart=startDrag(letter);button.ondragend=endDrag;tile.append(button);
  });
  root.append(tile);
 });
}
// Ruled-out letters and rejected words are hard rules for this puzzle, so a
// change invalidates suggestions like any other constraint edit.
let eliminationSuggestions=[];
function alphabetLetters(){return 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'+(PuzzleState.nordicLetters(puzzle.language)?'ÅÄÖ':'');}
function ruleOut(number,letters,ruledOut=true){if(!PuzzleState.setRuledOut(puzzle,number,letters,ruledOut))return;invalidate();render();$('solve-status').textContent=ruledOut?`Number ${Number(number)} is not ${letters.join(', ')}. Solve again to use this.`:`${letters.join(', ')} allowed again for number ${Number(number)}.`;}
function ruledOutButton(number,letter){const button=document.createElement('button');button.type='button';button.className='ruled-out-letter';button.textContent=letter;button.title=`Allow ${letter} for number ${Number(number)} again`;button.setAttribute('aria-label',button.title);button.onclick=()=>ruleOut(number,[letter],false);return button;}
function renderCellRuledOut(){
 const c=puzzle.cells[selected],box=$('cell-ruled-out'),entry=c.number&&PuzzleState.visibleRuledOut(puzzle,solutionIndex).find(item=>item.number===String(Number(c.number)));
 // A number that shows a letter needs no ruling out, unless a confirmed letter is itself ruled out.
 box.hidden=c.black||!c.number||(!PuzzleState.numberIsOpen(puzzle,c.number,solutionIndex)&&!entry);if(box.hidden)return;
 $('cell-ruled-out-title').textContent=`Number ${Number(c.number)} is not`;
 const list=$('cell-ruled-out-letters'),letters=entry?entry.letters:[];list.replaceChildren();
 $('cell-ruled-out-summary').textContent=`Rule out letters for number ${Number(c.number)}`+(letters.length?` · ${letters.length} ruled out`:'');
 if(!letters.length)list.textContent='No letters ruled out.';
 for(const letter of letters)list.append(ruledOutButton(c.number,letter));
}
$('rule-out-add').onclick=()=>{const c=puzzle.cells[selected],letter=normalize($('rule-out-letter').value.trim());if(c.black||!c.number||!letter)return;if(letter.length!==1||!alphabetLetters().includes(letter)){notify('Enter one letter of the selected alphabet.',true);return;}$('rule-out-letter').value='';ruleOut(c.number,[letter]);};
$('rule-out-letter').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();$('rule-out-add').click();}};
function renderEliminations(){
 const list=$('ruled-out-list');list.replaceChildren();
 const entries=PuzzleState.visibleRuledOut(puzzle,solutionIndex).map(entry=>[entry.number,entry.letters]);
 if(!entries.length)list.textContent='None.';
 for(const [number,letters] of entries){const row=document.createElement('span');row.className='ruled-out-row';const label=document.createElement('span');label.textContent=`${number} ≠`;row.append(label,...letters.map(letter=>ruledOutButton(number,letter)));list.append(row);}
 const groups=PuzzleState.eliminationSuggestionGroups(puzzle,eliminationSuggestions,solutionIndex),root=$('elimination-suggestions'),language=PuzzleState.languagePresentation(puzzle).name;root.replaceChildren();
 $('rule-out-all').hidden=!groups.length;
 const ruledCount=entries.reduce((sum,[,letters])=>sum+letters.length,0),suggestedCount=groups.reduce((sum,group)=>sum+group.letters.length,0);
 $('ruled-out-summary').textContent='Ruled-out letters'+(ruledCount?` · ${ruledCount} ruled out`:'')+(suggestedCount?` · ${suggestedCount} suggested`:'');
 if(!groups.length){root.className='hint';root.textContent='No suggestions. They appear when known letters sit next to a number without a letter.';return;}
 root.className='';
 for(const group of groups){
  const row=document.createElement('div');row.className='ruled-out-row';const label=document.createElement('span');label.textContent=`${group.number} ≠`;row.append(label);
  for(const {letter,run} of group.letters){const button=document.createElement('button');button.type='button';button.className='suggested-elimination';button.textContent=letter;button.title=`Rule out ${letter} for number ${group.number}: ${run} practically never occurs in ${language} words.`;button.setAttribute('aria-label',button.title);button.onclick=()=>ruleOut(group.number,[letter]);row.append(button);}
  if(group.letters.length>1){const all=document.createElement('button');all.type='button';all.className='rule-out-group';all.textContent='All';all.title=`Rule out all ${group.letters.length} suggested letters for number ${group.number}`;all.setAttribute('aria-label',all.title);all.onclick=()=>ruleOut(group.number,group.letters.map(item=>item.letter));row.append(all);}
  root.append(row);
 }
}
$('rule-out-all').onclick=()=>{const groups=PuzzleState.eliminationSuggestionGroups(puzzle,eliminationSuggestions,solutionIndex);let count=0;for(const group of groups)if(PuzzleState.setRuledOut(puzzle,group.number,group.letters.map(item=>item.letter)))count+=group.letters.length;if(!count)return;invalidate();render();$('solve-status').textContent=`Ruled out ${count} suggested letters for ${groups.length} number${groups.length===1?'':'s'}. Solve again to use them.`;};
function rejectWord(slot,word,rejected=true){if(!PuzzleState.setWordRejected(puzzle,slot,word,rejected))return;invalidate();render();$('solve-status').textContent=rejected?`${word} rejected for this word. Solve again for other suggestions.`:`${word} allowed again for this word.`;}
function renderCurrentWordRejection(current){
 const box=$('current-word-rejection'),full=PuzzleState.completeWordText(puzzle,current,solutionIndex),rejected=PuzzleState.rejectedWordsFor(puzzle,current),canReject=!!(full&&full.provisional);
 const button=$('reject-current-word');button.hidden=!current||!canReject;if(!button.hidden){button.textContent=`${full.text} is wrong here`;button.onclick=()=>rejectWord(current,full.text);}
 box.hidden=!current||!rejected.length;if(box.hidden)return;
 const list=$('current-rejected-words');list.replaceChildren();list.hidden=!rejected.length;
 if(rejected.length)list.append('Rejected here:');
 for(const word of rejected){const restore=document.createElement('button');restore.type='button';restore.className='ruled-out-letter';restore.textContent=word;restore.title=`Allow ${word} here again`;restore.setAttribute('aria-label',restore.title);restore.onclick=()=>rejectWord(current,word,false);list.append(restore);}
}
let numberPending=null,draggedUnmatched=null,draggedAssigned=null,pickedUnmatched=null;
function assignmentContext(){return {puzzle,revision,editMode,solutionIndex,suggestions:puzzle.suggestions};}
function assignmentCurrent(context){return (!context.dialog||numberPending===context)&&context.puzzle===puzzle&&context.revision===revision&&context.editMode===editMode&&context.solutionIndex===solutionIndex&&context.suggestions===puzzle.suggestions;}
function openNumberAssignment(number){
 numberPending={...assignmentContext(),number,dialog:true};
 $('assign-number-title').textContent=`Assign a letter to number ${number}`;
 $('assign-number-letter').value=pickedUnmatched&&assignmentCurrent(pickedUnmatched)?pickedUnmatched.letter:'';
 pickedUnmatched=null;$('assign-number-error').textContent='';$('assign-number-apply').disabled=false;
 $('assign-number-status').value='confirmed';$('assign-number-status').querySelector('[value="mapping"]').disabled=puzzle.rules.maxLettersPerNumber!==1;$('assign-number-status-help').textContent=puzzle.rules.maxLettersPerNumber!==1?'Mapped is unavailable when a number allows multiple letters.':'Mapped keeps one fixed anchor and derives the other occurrences.';
 $('assign-number-dialog').showModal();$('assign-number-letter').focus();
}
async function applyNumberAssignment(context,letter,status='confirmed'){
 if(!assignmentCurrent(context))throw new Error('The puzzle changed. Please select the number again.');
 const plan=PuzzleState.numberAssignmentPlan(puzzle,context.number,letter,solutionIndex,editMode,status);
 const warnings=[];
 if(plan.previous.length)warnings.push(`Number ${plan.number} already contains ${plan.previous.join(', ')}. Replace these letters with ${plan.letter} in every occurrence?`);
 if(plan.owners.length)warnings.push(`${plan.letter} is already assigned to number${plan.owners.length>1?'s':''} ${plan.owners.join(', ')}. Remove that letter from those numbers and move it to number ${plan.number}?`);
 if(warnings.length&&!await confirmAction(warnings.join(' '),'Replace number assignment?'))return false;
 if(!assignmentCurrent(context))throw new Error('The puzzle changed. Please select the number again.');
 const validation=await api('/api/validate',plan.trial);
 if(!assignmentCurrent(context))throw new Error('The puzzle changed. Please select the number again.');
 if(!validation.valid)throw new Error(validation.conflicts.join(' · '));
 solveJob.cancel();puzzle.cells=plan.trial.cells;
 if(plan.trial.suggestions)puzzle.suggestions=plan.trial.suggestions;else delete puzzle.suggestions;
 clearCandidateResults();clearLookup();acceptanceHistory.push(plan.snapshot);revision++;solutionIndex=0;numericEntry=null;
 $('solve-status').textContent=`${plan.letter} assigned to number ${plan.number} as ${plan.status==='mapping'?'mapped':plan.status}. Undo is available.`;
 render();validate();return true;
}
async function removeNumberAssignment(context){
 if(!assignmentCurrent(context))throw new Error('The puzzle changed. Please drag the letter again.');
 const plan=PuzzleState.numberRemovalPlan(puzzle,context.number,context.letter,solutionIndex,editMode);
 if(!await confirmAction(`Remove ${plan.letter} from every occurrence of number ${plan.number}? Numbers and other letters stay. You can undo this change.`,'Remove number assignment?'))return false;
 if(!assignmentCurrent(context))throw new Error('The puzzle changed. Please drag the letter again.');
 solveJob.cancel();puzzle.cells=plan.trial.cells;
 if(plan.trial.suggestions)puzzle.suggestions=plan.trial.suggestions;else delete puzzle.suggestions;
 clearCandidateResults();clearLookup();acceptanceHistory.push(plan.snapshot);revision++;solutionIndex=0;numericEntry=null;
 $('solve-status').textContent=`Removed ${plan.letter} from number ${plan.number}. Undo is available.`;
 render();validate();return true;
}
$('assign-number-dialog').addEventListener('close',()=>{numberPending=null;});
$('assign-number-form').onsubmit=async event=>{
 event.preventDefault();const pending=numberPending;if(!pending)return;
 $('assign-number-error').textContent='';$('assign-number-apply').disabled=true;
 try{if(await applyNumberAssignment(pending,$('assign-number-letter').value,$('assign-number-status').value))$('assign-number-dialog').close();}
 catch(error){if(numberPending===pending)$('assign-number-error').textContent=error.message;}
 finally{if(numberPending===pending)$('assign-number-apply').disabled=false;}
};
async function cycleMappingLetter(context){
 if(!assignmentCurrent(context))return false;
 const plan=PuzzleState.mappingCyclePlan(puzzle,context.number,context.letter,solutionIndex,editMode);
 const validation=await api('/api/validate',plan.trial);
 if(!assignmentCurrent(context))return false;
 if(!validation.valid&&plan.action!=='suggested')throw new Error(validation.conflicts.join(' · '));
 solveJob.cancel();puzzle.cells=plan.trial.cells;
 if(plan.trial.suggestions)puzzle.suggestions=plan.trial.suggestions;else delete puzzle.suggestions;
 clearCandidateResults();clearLookup();acceptanceHistory.push(plan.snapshot);revision++;solutionIndex=0;numericEntry=null;
 $('solve-status').textContent=`Number ${plan.number}: ${plan.letter} is now ${plan.action}. Undo is available.`;
 render();validate();
 const control=[...$('mapping').querySelectorAll('button')].find(button=>button.dataset.number===plan.number&&button.dataset.letter===plan.letter);control?.focus();
 return true;
}
async function moveNumberAssignment(context,target){
 if(!assignmentCurrent(context))return false;
 const plan=PuzzleState.numberMovePlan(puzzle,context.number,target,context.letter,solutionIndex,editMode);
 if(!plan)return false;
 const occupied=plan.previous.length?` Number ${target} already contains ${plan.previous.join(', ')}; replace those letters?`:'';
 const owners=plan.owners.length?` Also remove ${plan.letter} from number${plan.owners.length>1?'s':''} ${plan.owners.join(', ')} to keep distinct letters.`:'';
 if(!await confirmAction(`Move ${plan.letter} from number ${context.number} to number ${target}? This removes that letter from the source and confirms it in every target cell.${occupied}${owners}`,'Move number assignment?'))return false;
 if(!assignmentCurrent(context))return false;
 const validation=await api('/api/validate',plan.trial);
 if(!assignmentCurrent(context))return false;
 if(!validation.valid)throw new Error(validation.conflicts.join(' · '));
 solveJob.cancel();puzzle.cells=plan.trial.cells;
 if(plan.trial.suggestions)puzzle.suggestions=plan.trial.suggestions;else delete puzzle.suggestions;
 clearCandidateResults();clearLookup();acceptanceHistory.push(plan.snapshot);revision++;solutionIndex=0;numericEntry=null;
 $('solve-status').textContent=`Moved ${plan.letter} from number ${context.number} to number ${target}. Undo is available.`;
 render();validate();return true;
}
$('reset-suggestions').onclick=()=>{
 solveJob.cancel();clearCandidateResults();acceptanceHistory.clear();numericEntry=null;
 PuzzleState.resetSuggestions(puzzle);solutionIndex=0;revision++;clearTimeout(validateTimer);
 $('solve-status').textContent='Suggestions reset. Confirmed letters and their mapping deductions are kept.';render();validate();
};
$('reset-progress').onclick=protect(async()=>{
 if(!await confirmAction('Clear answer letters, suggestions, pencil marks, ruled-out letters and rejected words? Prefilled letters are kept in Puzzle mode and cleared in Edit mode. The grid, numbers, image and settings will stay. This clears undo history. Saved puzzles are unchanged until you save.','Reset puzzle?'))return;
 solveJob.cancel();clearCandidateResults(true);acceptanceHistory.clear();numericEntry=null;
 const givens=!editMode?puzzle.cells.map(c=>c.prefilled?c.letter:''):[];
 PuzzleState.resetProgress(puzzle);puzzle.cells.forEach((c,i)=>{c.letter=givens[i]||'';c.prefilled=!!c.letter;});solutionIndex=0;revision++;clearTimeout(validateTimer);
 $('solve-status').textContent='Puzzle reset. The puzzle is ready to start again.';render();validate();
});
function renderResults(){setUndoAvailable(acceptanceHistory.length>0);const data=puzzle.suggestions,current=solution(),gridWords=PuzzleState.displayedPuzzleWords(puzzle,solutionIndex).map(word=>PuzzleState.assessedWord(word,wordChecks.ensure(puzzle,word))),deductions=(data?.forcedLetters||[]).filter((l,i)=>l&&!puzzle.cells[i]?.letter&&!puzzle.cells[i]?.black).length;$('deduction-results').hidden=!deductions;$('deduction-count').textContent=`${deductions} mapping deductions from confirmed number–letter pairs. These remain provisional until accepted.`;$('solver-mode').textContent=puzzle.useDictionary?'Dictionary mode: editable words'+(puzzle.language==='fi'&&puzzle.useMorphology!==false?' and local Finnish morphology':'')+(puzzle.allowUnknownWords?'; missing words allowed as unverified guesses.':'.'):'Dictionary-free mode: language-pattern guesses can include invented words.';$('retry-word-checks').hidden=!gridWords.some(word=>word.assessmentStatus==='error');$('result-empty').hidden=!!current;$('result-content').hidden=!gridWords.length&&!current;$('result-alternatives').hidden=!current;$('accept-all').disabled=!current;$('diagnostics').textContent=data?.diagnostics?.join(' · ')||'';if(data&&!current){$('result-empty').hidden=false;$('result-empty').textContent=data.partialLetters?.some((letter,i)=>letter&&!puzzle.cells[i].letter)?'Partial hypothesis displayed on the grid. It is unverified and is not a complete solution. Review or confirm individual cells and words.':deductions?'No full suggestion found. Mapping deductions are available on the grid.':'No suggestions found in this search. Review the diagnostics, dictionary, and constraints.';}else if(!data)$('result-empty').textContent='Words currently displayed in the grid. Complete words are checked automatically.';if(!gridWords.length&&!current)$('result-empty').textContent='No Across or Down words of two or more cells in this grid. Add connected cells to see word rows.';const alternatives=$('alternatives');alternatives.replaceChildren();(current?data.solutions:[]).forEach((s,i)=>{const opt=document.createElement('option');opt.value=i;opt.textContent=`${i+1} of ${data.solutions.length} · score ${Number(s.score).toFixed(2)}`;alternatives.append(opt);});alternatives.value=solutionIndex;$('result-meta').textContent=current?`${PuzzleState.solveStopExplanation(data.status,data.stats)} ${data.stats?.exhaustive?'Search completed for the current dictionary and constraints.':'Bounded search; alternatives are not exhaustive.'} ${puzzle.useDictionary?'Word sources are labelled below. Fragments and words without vocabulary evidence remain unverified.':'Generated candidates are unverified and may not be real words.'}`:'Complete words are checked against the dictionary and letter patterns. Unknown letters are shown as ·.';const words=$('word-results');words.replaceChildren();const visibleWords=PuzzleState.solvedWordsView(gridWords,solvedWordFilter,solvedWordSort,puzzle.language);$('solved-word-count').textContent=gridWords.length?`Showing ${visibleWords.length} of ${gridWords.length} words${visibleWords.length?'':'. No words match this filter.'}`:'No Across or Down words of two or more cells in this grid.';visibleWords.forEach(word=>{const row=document.createElement('div');row.className='word-row';const text=document.createElement('button');text.type='button';text.className='word-jump';text.textContent=word.text;const location=PuzzleState.solvedWordSelection(puzzle,word);text.disabled=!location;text.setAttribute('aria-label',location?`Select ${word.text}, ${location.direction}, row ${Math.floor(location.index/puzzle.cols)+1}, column ${location.index%puzzle.cols+1}`:`${word.text}, no matching grid word`);text.onclick=()=>jumpToSolvedWord(word);const state=document.createElement('small');const confirmed=word.cells.filter(i=>puzzle.cells[i].letter).length;const pattern=word.assessmentStatus==='ready'?(PuzzleState.plausibilityLabel(word.plausibility)||'Pattern unassessed'):'';state.textContent=PuzzleState.assessedWordLabel(word)+(pattern?' · '+pattern:'')+' · '+(confirmed===word.cells.length?'Confirmed':`${confirmed}/${word.cells.length} confirmed`);state.title=PuzzleState.plausibilityDetail(word.plausibility);const score=document.createElement('small');score.className='solved-pattern-score';score.textContent=PuzzleState.solvedWordPatternScore(word);score.title='Lower (more negative) pattern scores mean less typical letter sequences. This is not a probability, dictionary check or proof of the answer.';const statusGroup=document.createElement('div');statusGroup.className='word-status';statusGroup.append(state,score);row.append(text,statusGroup);const actionGroup=document.createElement('div');actionGroup.className='word-actions';const actions=PuzzleState.solvedWordActions(puzzle,word,solutionIndex,editMode);if(actions.confirm){const button=document.createElement('button');button.type='button';button.textContent=actions.confirmLabel;button.dataset.help='Confirm the remaining suggested letters in this word. Already confirmed letters stay unchanged.';button.onclick=()=>accept(word.cells);actionGroup.append(button);}if(actions.unconfirm){const revoke=document.createElement('button');revoke.type='button';revoke.textContent=actions.unconfirmLabel;revoke.dataset.help='Unconfirm the currently confirmed letters in this word and keep them as provisional notes. Prefilled letters stay locked in Puzzle mode.';revoke.onclick=()=>unconfirm(word.cells);actionGroup.append(revoke);}if(!word.unknownCount&&word.cells.some(i=>!puzzle.cells[i].letter)){const reject=document.createElement('button');reject.type='button';reject.textContent='Wrong';reject.dataset.help=`Reject ${word.text} for this position, for example when it does not fit the clue. Solving and word searches will not suggest it here again. The dictionary is unchanged.`;reject.onclick=()=>rejectWord(word,word.text);actionGroup.append(reject);}if(actionGroup.children.length)row.append(actionGroup);const details=word.analyses||word.evidence||word.details;if(Array.isArray(details)&&details.length){const evidence=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Word evidence';evidence.append(summary);for(const entry of details){const description=document.createElement('p');description.className='hint';description.textContent=[entry.lemma,entry.description||entry.analysis,entry.source].filter(Boolean).join(' · ');evidence.append(description);}row.append(evidence);}words.append(row);});}
function setUndoAvailable(available){$('undo-acceptance').setAttribute('aria-disabled',String(!available));}
function jumpToSolvedWord(word){
 const location=PuzzleState.solvedWordSelection(puzzle,word);if(!location)return;
 selected=location.index;wordDirection=location.direction;lastClickedCell=selected;numericEntry=null;
 render();const cell=$('grid').children[selected];cell.scrollIntoView({block:'center',inline:'nearest'});cell.focus({preventScroll:true});
}
$('solved-word-filter').onchange=()=>{solvedWordFilter=$('solved-word-filter').value;renderResults();};
$('solved-word-sort').onchange=()=>{solvedWordSort=$('solved-word-sort').value;renderResults();};
function toggleBlack(){if(!editMode)return;const cell=puzzle.cells[selected];numericEntry=null;cell.clue=false;cell.black=!cell.black;delete cell.numberReview;if(cell.black){cell.highlight=false;cell.number='';cell.letter='';cell.guess='';cell.mappingAnchor=false;}invalidate();render();}
function currentSelectedWord(){const word=PuzzleState.cellWord(puzzle,selected,wordDirection,false,solutionIndex);if(word)wordDirection=word.direction;return word;}

function accept(indices){
 const current=solution(),snapshot=PuzzleState.confirmCells(puzzle,indices,solutionIndex);if(!snapshot)return;
 clearCandidateResults();acceptanceHistory.push(snapshot);solutionIndex=Math.max(0,(puzzle.suggestions?.solutions||[]).indexOf(current));solveJob.cancel();revision++;render();validate();
}
function unconfirm(indices){
 if(!editMode)indices=indices.filter(i=>!puzzle.cells[i].prefilled);
 if(!PuzzleState.unconfirmCells(puzzle,indices))return;
 for(const i of indices)if(!puzzle.cells[i].letter)puzzle.cells[i].prefilled=false;
 clearCandidateResults();acceptanceHistory.clear();solveJob.cancel();revision++;$('solve-status').textContent='Letters unconfirmed. Existing alternatives remain provisional; solve again to explore the relaxed constraints.';render();validate();
}
$('cell-confirmed').onchange=()=>{if($('cell-confirmed').checked)accept([selected]);else unconfirm([selected]);};
$('undo-acceptance').onclick=()=>{if(!acceptanceHistory.length)return;const snapshot=acceptanceHistory.pop();if(!PuzzleState.undoConfirmation(puzzle,snapshot))return;clearCandidateResults();solutionIndex=snapshot.solutionIndex;solveJob.cancel();revision++;$('solve-status').textContent='Last letter change undone. Earlier provisional alternatives restored.';render();validate();};

function clearCandidateResults(clearSelection=false){candidateResult=null;candidateBusy=false;candidateRequest++;if(clearSelection)candidateKeys=new Set();$('candidate-status').textContent='';}
function renderWordHighlights(choices=PuzzleState.wordChoices(puzzle,solutionIndex)){
 const active=new Set(currentSelectedWord()?.cells||[]);
 const cells=new Set(choices.filter(word=>candidateKeys.has(word.key)).flatMap(word=>word.cells));
 [...$('grid').children].forEach((cell,i)=>{
  const highlighted=cells.has(i)&&!puzzle.cells[i].black;
  cell.classList.toggle('candidate-selected',highlighted);
  cell.classList.toggle('word-focused',active.has(i));
  cell.setAttribute('aria-selected',String(highlighted||active.has(i)||i===selected));
 });
}
function candidateLabel(word){return `${word.direction} · row ${word.row}, column ${word.col}`;}
function renderCandidatePanel(){
 const choices=PuzzleState.wordChoices(puzzle,solutionIndex),keys=new Set(choices.map(word=>word.key));candidateKeys=new Set([...candidateKeys].filter(key=>keys.has(key)));
 renderWordHighlights(choices);
 const current=currentSelectedWord();
 $('candidate-current-pattern').textContent=current?`${candidateLabel(current)} · ${current.pattern}`:'No word at this cell.';renderCurrentWordCheck(current);renderCurrentWordRejection(current);
 $('add-current-word').disabled=!current||candidateKeys.has(current.key)||candidateKeys.size>=8;
 $('add-current-word').textContent=current&&candidateKeys.has(current.key)?'Added':'Add to list';
 const body=$('candidate-word-table');body.replaceChildren();
 for(const word of choices.filter(word=>candidateKeys.has(word.key))){
  const row=document.createElement('tr'),selection=document.createElement('td'),remove=document.createElement('button');remove.type='button';remove.className='icon-button';remove.textContent='×';remove.setAttribute('aria-label','Remove '+candidateLabel(word));remove.title='Remove '+candidateLabel(word);
  remove.onclick=()=>{clearCandidateResults();candidateKeys.delete(word.key);renderCandidatePanel();renderInspector();};selection.append(remove);
  const location=document.createElement('td'),focus=document.createElement('button');focus.type='button';focus.className='word-location';focus.textContent=candidateLabel(word);focus.onclick=()=>{selected=word.cells[0];numericEntry=null;wordDirection=word.direction;lastClickedCell=selected;render();$('grid').children[selected].focus({preventScroll:true});};location.append(focus);
  const pattern=document.createElement('td');pattern.className='word-pattern';pattern.textContent=word.pattern;pattern.title=word.provisionalCount?`${word.provisionalCount} provisional letters used as search constraints only`:'Confirmed letters only';
  row.append(selection,location,pattern);body.append(row);
 }
 $('candidate-empty').hidden=candidateKeys.size>0;$('candidate-word-table').closest('.candidate-table-scroll').hidden=!candidateKeys.size;$('candidate-selection-count').textContent=`${candidateKeys.size} selected`;
 $('find-candidates').disabled=candidateBusy||!candidateKeys.size;$('find-candidates').textContent=candidateBusy?'Finding candidates…':'Find candidates';
 $('morphology-settings').hidden=!PuzzleState.languagePresentation(puzzle).showMorphology;$('use-morphology').checked=puzzle.useMorphology!==false;$('use-morphology').disabled=puzzle.language!=='fi'||!puzzle.useDictionary;
 const output=$('candidate-results');output.replaceChildren();if(!candidateResult)return;
 const explanation=document.createElement('p');explanation.className='hint';explanation.textContent=PuzzleState.languagePresentation(puzzle).candidateExplanation;output.append(explanation);
 for(const word of candidateResult.words||[]){const section=document.createElement('section');section.className='local-candidate-list';const heading=document.createElement('h3');const original=choices.find(choice=>choice.slotId===word.slotId);heading.textContent=original?candidateLabel(original):`Word ${word.slotId+1}`;const list=document.createElement('p');list.className='candidate-words';list.textContent=word.candidates?.length?word.candidates.map(text=>PuzzleState.candidateDisplay(text,word.candidatePlausibility?.[text])).join(' · '):'No local candidate found within this search.';section.append(heading,list);if(word.candidates?.length){const evidence=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Dictionary status, base words and pattern scores';evidence.append(summary);appendWordEvidence(evidence,word.candidates,word);section.append(evidence);}if(word.truncated){const note=document.createElement('p');note.className='hint';note.textContent='Candidate list limited by the search budget.';section.append(note);}output.append(section);}
 if(candidateKeys.size>1){const section=document.createElement('section');section.className='candidate-combinations';const title=document.createElement('h3');title.textContent='Jointly compatible selected words';const note=document.createElement('p');note.className='hint';note.textContent='These combinations fit the selected group and current constraints. They are not complete-grid solutions.';section.append(title,note);const combinations=candidateResult.combinations||[];if(!combinations.length){const empty=document.createElement('p');empty.textContent='No compatible combination found in this bounded search. Local candidate lists above remain available.';section.append(empty);}else{const list=document.createElement('ol');for(const combination of combinations){const item=document.createElement('li');item.textContent=combination.words.map(word=>{const original=choices.find(choice=>choice.slotId===word.slotId);return `${original?candidateLabel(original):'Word '+(word.slotId+1)}: ${word.text}`;}).join(' / ');list.append(item);}section.append(list);}output.append(section);}
 const diagnostics=document.createElement('p');diagnostics.className='hint';diagnostics.textContent=(candidateResult.diagnostics||[]).join(' · ');output.append(diagnostics);
}
// Fully filled selected words are checked automatically, so a solved grid
// can be reviewed word by word. Results are cached per language and word.
const wordChecks=PuzzleState.wordAssessmentQueue(api,()=>{renderResults();renderCurrentWordCheck(currentSelectedWord());});
$('retry-word-checks').onclick=()=>{wordChecks.retryErrors();renderResults();renderCurrentWordCheck(currentSelectedWord());};
function renderCurrentWordCheck(current){
 const output=$('candidate-current-check'),full=PuzzleState.completeWordText(puzzle,current,solutionIndex);
 if(!current){output.hidden=true;output.textContent='';return;}
 output.hidden=false;
 if(!full){output.textContent='Incomplete word. Fill every letter to check its dictionary status and pattern.';return;}
 if(full.partial){output.textContent='Open word fragment. Use Find candidates to match it against longer listed words.';return;}
 const assessment=wordChecks.ensure(puzzle,{text:full.text,unknownCount:0});
 output.textContent=assessment.status==='ready'?PuzzleState.selectedWordCheckText(assessment.result,full):assessment.status==='error'?`Word check failed: ${assessment.error}. Use Retry word checks in Explore possibilities.`:`Checking ${full.text}…`;
}
// Each word: dictionary status and pattern score, then any base-word analyses.
function appendWordEvidence(container,texts,data){for(const text of texts){const row=document.createElement('div');row.className='candidate-evidence lookup-item';const title=document.createElement('strong');title.textContent=text;const status=document.createElement('p');status.className='hint';status.textContent=PuzzleState.candidateEvidenceText(data.candidateEvidence?.[text],data.candidatePlausibility?.[text],puzzle.language);row.append(title,status);for(const entry of data.candidateDetails?.[text]||[]){if(entry.analysis==='Listed surface form')continue;const description=document.createElement('p');description.className='hint';description.textContent=[entry.lemma,entry.description||entry.analysis,entry.source].filter(Boolean).join(' · ');row.append(description);}container.append(row);}}
let lookupRequest=0;
function clearLookup(){lookupRequest++;$('lookup-run').disabled=false;$('lookup-status').textContent='';$('lookup-results').replaceChildren();}
$('lookup-clear').onclick=()=>{clearLookup();$('lookup-query').value='';$('lookup-query').focus();};
function renderLookup(result){const output=$('lookup-results');output.replaceChildren();output.className='lookup-results';
 if(result.kind==='word'){const row=document.createElement('div');row.className='lookup-item';const title=document.createElement('strong');title.textContent=result.word;const status=document.createElement('p');status.className='hint';status.textContent=PuzzleState.wordLookupText(result);row.append(title,status);for(const entry of result.analyses||[]){const description=document.createElement('p');description.className='hint';description.textContent=[entry.lemma,entry.description||entry.analysis,entry.source].filter(Boolean).join(' · ');row.append(description);}output.append(row);}
 else appendWordEvidence(output,result.candidates||[],result);
 const diagnostics=document.createElement('p');diagnostics.className='hint';diagnostics.textContent=(result.diagnostics||[]).join(' · ');output.append(diagnostics);}
$('lookup-current').onclick=()=>{const word=currentSelectedWord();if(!word)return notify('Select a word in the grid first.');clearLookup();$('lookup-query').value=PuzzleState.lookupPattern(puzzle,word.cells);$('lookup-query').focus();};
$('lookup-query').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();$('lookup-run').click();}};
$('lookup-run').onclick=protect(async()=>{const query=$('lookup-query').value.trim();if(!query)return notify('Type a word or a pattern such as A 12 12 K 5.');
 const token=++lookupRequest,version=revision;$('lookup-run').disabled=true;$('lookup-status').textContent='Looking up…';$('lookup-results').replaceChildren();
 try{const result=await api('/api/lookup',{puzzle,query,useMappings:$('lookup-mappings').checked});if(token!==lookupRequest)return;if(version!==revision){$('lookup-status').textContent='The puzzle changed during lookup. Look up again.';return;}
  $('lookup-status').textContent=result.kind==='word'?'Word checked.':`${result.candidates.length} matching ${result.candidates.length===1?'word':'words'} for ${result.pattern}${result.truncated?' (list limited by the search budget)':''}.`;renderLookup(result);}
 catch(error){if(token===lookupRequest){$('lookup-status').textContent='Lookup failed: '+error.message;throw error;}}
 finally{if(token===lookupRequest)$('lookup-run').disabled=false;}});
$('use-morphology').onchange=()=>{puzzle.useMorphology=$('use-morphology').checked;invalidate();render();};
$('add-current-word').onclick=()=>{const word=currentSelectedWord();if(!word||candidateKeys.has(word.key)||candidateKeys.size>=8)return;clearCandidateResults();candidateKeys.add(word.key);renderCandidatePanel();};
$('clear-candidate-selection').onclick=()=>{clearCandidateResults(true);renderCandidatePanel();renderInspector();};
$('find-candidates').onclick=protect(async()=>{
 const slotIds=PuzzleState.candidateSelection(PuzzleState.wordChoices(puzzle,solutionIndex),candidateKeys);if(!slotIds.length||candidateBusy)return;
 const version=revision,token=++candidateRequest;candidateBusy=true;candidateResult=null;renderCandidatePanel();$('candidate-status').textContent=`Finding candidates for ${slotIds.length} selected word${slotIds.length===1?'':'s'}…`;
 try{const result=await api('/api/candidates',{puzzle:PuzzleState.candidateSearchPuzzle(puzzle,slotIds,solutionIndex),slotIds});if(token!==candidateRequest)return;if(version!==revision){$('candidate-status').textContent='The puzzle changed during search. Find candidates again for current constraints.';return;}candidateResult=result;const count=(result.words||[]).reduce((sum,word)=>sum+(word.candidates?.length||0),0);$('candidate-status').textContent=`Selected-word search ${result.status==='budget_exhausted'?'reached its limit':'complete'}: ${count} local candidates. These are not complete-grid solutions.`;}
 catch(error){if(token===candidateRequest){$('candidate-status').textContent='Candidate search failed: '+error.message;throw error;}}
 finally{if(token===candidateRequest){candidateBusy=false;renderCandidatePanel();}}
});

function updateView(){
 const stage=$('board-stage'),viewport=$('board-viewport'),image=$('puzzle-image');
 const bounds=puzzle.imageBounds||{width:1};
 const baseWidth=puzzle.image?puzzle.cols*46/bounds.width:puzzle.cols*47+3;
 const ratio=puzzle.image?(image.naturalWidth?image.naturalHeight/image.naturalWidth:1):(puzzle.rows*47+3)/baseWidth;
 // While straightening, leave room around the photo for handles placed just outside it.
 const room=straightenHandles?80:0,availableWidth=Math.max(1,viewport.clientWidth-22-room),availableHeight=Math.max(120,Math.min(window.innerHeight*.78-42,window.innerHeight-Math.max(0,viewport.getBoundingClientRect().top)-60)-room);
 if(fitMode)viewScale=PuzzleState.fitScale(baseWidth,baseWidth*ratio,availableWidth,availableHeight,fitMode);
 if(puzzle.image){stage.style.width=baseWidth*viewScale+'px';stage.style.setProperty('--image-letter-size',Math.max(6,23*viewScale)+'px');stage.style.setProperty('--image-number-size',Math.max(4,10*viewScale)+'px');}
 else{stage.style.width='';stage.style.setProperty('--cell',46*viewScale+'px');stage.style.setProperty('--view-scale',viewScale);}
 $('zoom-level').textContent=Math.round(viewScale*100)+'%';$('zoom-range').value=Math.round(viewScale*100);for(const mode of ['puzzle','height','width'])$('fit-'+mode).setAttribute('aria-pressed',String(fitMode===mode));
}
function zoomTo(scale){fitMode=null;viewScale=Math.max(.05,Math.min(3,scale));updateView();}
$('zoom-in').onclick=()=>zoomTo(viewScale*1.25);$('zoom-out').onclick=()=>zoomTo(viewScale/1.25);
$('zoom-range').oninput=()=>zoomTo(Number($('zoom-range').value)/100);
for(const mode of ['puzzle','height','width'])$('fit-'+mode).onclick=()=>{fitMode=mode;updateView();$('board-viewport').scrollTop=0;$('board-viewport').scrollLeft=0;};
$('puzzle-image').onload=()=>updateView();window.addEventListener('resize',()=>updateView());
let viewFrame=0;window.addEventListener('scroll',()=>{if(!fitMode||viewFrame)return;viewFrame=requestAnimationFrame(()=>{viewFrame=0;updateView();});},{passive:true});

let pendingLetterConflict=null;
$('letter-conflict-keep').onclick=()=>$('letter-conflict-dialog').close();
$('letter-conflict-dialog').addEventListener('close',()=>{pendingLetterConflict=null;renderInspector();});
$('letter-conflict-move').onclick=()=>{
 const pending=pendingLetterConflict;
 if(!pending||pending.puzzle!==puzzle||pending.revision!==revision||pending.editMode!==editMode){$('letter-conflict-dialog').close();return;}
 PuzzleState.moveLetterAssignment(puzzle,pending.index,pending.letter,solutionIndex);
 puzzle.cells[pending.index].prefilled=editMode;
 $('letter-conflict-dialog').close();invalidate();render();
};
function editLetter(letter){
 if(!editMode&&puzzle.cells[selected].prefilled)return;
 // With one letter per number, the other cells of the number would keep
 // showing the letter, so clearing it means removing it from the number
 // (after confirmation, with undo).
 const cell=puzzle.cells[selected],shown=cell.letter||suggestion(selected);
 if(!letter&&cell.number&&shown&&puzzle.rules.maxLettersPerNumber===1&&PuzzleState.mappingLetterInfo(puzzle,cell.number,shown,solutionIndex).indices.length>1){
  void protect(removeNumberAssignment)({...assignmentContext(),number:cell.number,letter:shown});return;
 }
 const owners=PuzzleState.letterOwners(puzzle,selected,letter,solutionIndex);
 if(owners.length){
  if(pendingLetterConflict)return;
  const locked=!editMode&&puzzle.cells.some(c=>owners.includes(c.number)&&c.prefilled&&c.letter===letter);
  pendingLetterConflict={puzzle,revision,editMode,index:selected,letter};
  $('letter-conflict-message').textContent=`${letter} is already assigned to number${owners.length>1?'s':''} ${owners.join(', ')}. Keep that assignment, or remove it and assign ${letter} to number ${puzzle.cells[selected].number}.`+(locked?' This is a prefilled letter. Switch to Edit mode to move it.':'');
  $('letter-conflict-move').disabled=locked;$('letter-conflict-dialog').showModal();return;
 }
 PuzzleState.editConfirmedLetter(puzzle,selected,letter,solutionIndex);
 puzzle.cells[selected].prefilled=editMode&&!!letter;
 invalidate();
 if(puzzle.cells.some(cell=>!cell.black&&!cell.letter&&cell.guess))$('solve-status').textContent='Letter updated. Remaining compatible letters are kept as provisional notes. Solve again to refresh alternatives.';
}
function gridKey(event){
 if(event.ctrlKey||event.metaKey||event.altKey)return;
 const moves={ArrowLeft:-1,ArrowRight:1,ArrowUp:-puzzle.cols,ArrowDown:puzzle.cols},cell=puzzle.cells[selected];
 if(event.key in moves){event.preventDefault();numericEntry=null;lastClickedCell=null;wordDirection='Across';selected=Math.min(puzzle.cells.length-1,Math.max(0,selected+moves[event.key]));}
 else if(!editMode){
  if(event.key.length===1||['Backspace','Delete'].includes(event.key))event.preventDefault();
  if(cell.black||cell.prefilled)return;
  if(['Backspace','Delete'].includes(event.key))editLetter('');
  else if(new RegExp(PuzzleState.nordicLetters(puzzle.language)?'^[a-zåäö]$':'^[a-z]$','i').test(event.key))editLetter(normalize(event.key));
  else return;
 }
 else if(event.key===' '){event.preventDefault();toggleBlack();}
 else if(!cell.black&&(/^[0-9]$/.test(event.key)||event.key==='Backspace')){
  event.preventDefault();const next=PuzzleState.numberEntry(numericEntry,selected,event.key,Date.now());
  if(next){numericEntry=next;changeNumber(selected,next.digits);}else if(event.key==='Backspace'){numericEntry=null;editLetter('');}
 }else if(!cell.black&&event.key==='Delete'){event.preventDefault();numericEntry=null;editLetter('');}
 else if(!cell.black&&new RegExp(PuzzleState.nordicLetters(puzzle.language)?'^[a-zåäö]$':'^[a-z]$','i').test(event.key)){event.preventDefault();numericEntry=null;editLetter(normalize(event.key));}
 else return;
 render();if(!pendingLetterConflict)$('grid').children[selected].focus();
}

$('number-position').onchange=()=>{puzzle.numberPosition=$('number-position').value;$('grid').dataset.numberPosition=PuzzleState.displayNumberPosition(puzzle);};
$('name').oninput=()=>{puzzle.name=$('name').value;};$('new').onclick=async()=>{const rows=Number($('rows').value),cols=Number($('cols').value);if(!Number.isInteger(rows)||!Number.isInteger(cols)||rows<1||cols<1||rows>40||cols>40)return notify('Use whole-number dimensions between 1 and 40.',true);if((puzzle.image||puzzle.cells.some(c=>c.black||c.number||c.letter||c.guess))&&!await confirmAction('Create a new grid? Export or save first to keep this puzzle.'))return;setPuzzle(fresh(rows,cols,$('language').value));};
$('language').onchange=()=>{dictionaryEditor.cancel();$('dictionary-dialog').close();puzzle.language=$('language').value;invalidate();render();};$('use-dictionary').onchange=()=>{puzzle.useDictionary=$('use-dictionary').checked;if(!puzzle.useDictionary&&puzzle.searchMode==='quick'){puzzle.searchMode='deep';$('search-mode').value='deep';notify('Search time set to Deep: without a dictionary, Quick search is usually too short to settle the grid.');}invalidate();render();};
function updateRules(event){
 const capacityChanged=event?.target===$('capacity');
 const capacity=capacityChanged?Number($('capacity').value):puzzle.rules.maxLettersPerNumber;
 if(capacityChanged&&(!Number.isInteger(capacity)||capacity<1||capacity>9)){$('capacity').value=puzzle.rules.maxLettersPerNumber;notify('Letters per number must be a whole number from 1 to 9.',true);return;}
 if(capacity!==1)for(const cell of puzzle.cells)cell.mappingAnchor=false;
 puzzle.rules={...puzzle.rules,maxLettersPerNumber:capacity,forbiddenPatterns:$('forbidden').value.split(/[\n,]+/).map(s=>normalize(s.trim())).filter(Boolean),discouragedPatterns:$('discouraged').value.split(/[\n,]+/).map(s=>normalize(s.trim())).filter(Boolean)};
 invalidate();render();
}
for(const id of ['capacity','forbidden','discouraged'])$(id).onchange=updateRules;
$('edit-tool').onclick=()=>setEditMode(true);$('puzzle-tool').onclick=()=>setEditMode(false);
function setEditMode(value){editMode=value;numericEntry=null;acceptanceHistory.clear();render();}
function renderEditMode(){
 $('edit-tool').classList.toggle('active',editMode);$('puzzle-tool').classList.toggle('active',!editMode);
 $('edit-tool').setAttribute('aria-pressed',String(editMode));$('puzzle-tool').setAttribute('aria-pressed',String(!editMode));
 for(const id of ['cell-black','cell-clue','cell-highlight','cell-number',...Object.keys(flags),'apply-image-dimensions','apply-alignment','ocr','remove-image','straighten-photo','bound-x','bound-y','bound-width','bound-height']){
  if(!editMode)$(id).disabled=true;
  else if(!['cell-number','cell-letter',...Object.keys(flags)].includes(id))$(id).disabled=id==='ocr'&&!ocrAvailable||id==='cell-highlight'&&puzzle.cells[selected].black;
 }
}

$('cell-clue').onchange=()=>{numericEntry=null;const c=puzzle.cells[selected];c.clue=$('cell-clue').checked;c.black=c.clue;if(c.black)c.highlight=false;c.number='';c.letter='';c.guess='';c.mappingAnchor=false;delete c.numberReview;invalidate();render();};$('cell-black').onchange=toggleBlack;$('cell-highlight').onchange=()=>{if(!editMode)return;const c=puzzle.cells[selected];if(c.black)return;c.highlight=$('cell-highlight').checked;render();};$('cell-number').onchange=()=>{const number=$('cell-number').value.trim();if(number&&!/^[1-9][0-9]?$/.test(number)){notify('A number must be a positive integer from 1 to 99.',true);return renderInspector();}changeNumber(selected,number);render();};$('cell-letter').onchange=()=>{const letter=normalize($('cell-letter').value.trim());if(letter&&!new RegExp(PuzzleState.nordicLetters(puzzle.language)?'^[A-ZÅÄÖ]$':'^[A-Z]$').test(letter)){notify('Enter exactly one letter from the selected language alphabet.',true);return renderInspector();}editLetter(letter);render();};for(const[id,key]of Object.entries(flags))$(id).onchange=()=>{puzzle.cells[selected][key]=$(id).checked;invalidate();render();};$('accept-all').onclick=()=>accept(puzzle.cells.map((_,i)=>i));$('accept-deductions').onclick=()=>{const candidates=puzzle.cells.map((_,i)=>i).filter(i=>puzzle.suggestions?.forcedLetters?.[i]);accept(candidates);};$('alternatives').onchange=()=>{clearCandidateResults();solutionIndex=Number($('alternatives').value);render();};
const solveJob=PuzzleState.solveRunner({
 request:api,
 onBusy:busy=>{for(const id of ['solve','solve-grid']){$(id).disabled=busy;$(id).textContent=busy?'Finding possibilities…':'Solve puzzle →';}$('cancel-solve').hidden=!busy;$('cancel-solve').disabled=false;$('cancel-solve').textContent='Cancel search';if(!busy&&stopSearchPrompt)$('confirm-dialog').close('cancel');},
 onStopping:stopping=>{$('cancel-solve').disabled=stopping;$('cancel-solve').textContent=stopping?'Stopping…':'Cancel search';if(stopping)$('solve-status').textContent='Stopping search and keeping its best provisional result…';},
 onUpdate:(state,stopping)=>{
  if(state.status==='running'||state.status==='queued'){const preview=state.progress?.preview;$('solve-status').textContent=PuzzleState.solveProgressText(state.progress,stopping)+(preview?' · the grid shows the best unverified guess so far':'');const margins=state.progress?.previewMargins||null;if(Array.isArray(preview)&&preview.length===puzzle.cells.length&&(preview.join()!==livePreview?.join()||JSON.stringify(margins)!==JSON.stringify(livePreviewMargins))){livePreview=preview;livePreviewMargins=margins;renderGrid();}return;}
  if(livePreview){livePreview=null;livePreviewMargins=null;renderGrid();}
  if(state.status==='failed'){$('solve-status').textContent='Search failed: '+(state.error||'Unknown error');notify($('solve-status').textContent,true);return;}
  const result=state.result;
  if(state.status==='cancelled'&&(!result||PuzzleState.cancelledResult(puzzle,result)!==result)){
   $('solve-status').textContent=PuzzleState.solveStopExplanation('cancelled',result?.stats)+(PuzzleState.hasSolveProgress(puzzle,puzzle.suggestions)?' Previously displayed suggestions remain provisional.':' No provisional progress was found.');notify($('solve-status').textContent);return;
  }
  if(!result)throw new Error('The completed search returned no result.');
  exitReplay();replay=Array.isArray(result.replay)&&result.replay.length>1?result.replay:null;delete result.replay;replayFor=replay?result:null;
  clearCandidateResults();puzzle.suggestions=result;solutionIndex=0;render();
  const count=result.solutions?.length||0,forced=(result.forcedLetters||[]).filter((letter,i)=>letter&&!puzzle.cells[i]?.letter&&!puzzle.cells[i]?.black).length;
  $('solve-status').textContent=PuzzleState.solveSummary(result.status,count,forced,result.stats)+(!count&&result.partialLetters?.some((letter,i)=>letter&&!puzzle.cells[i].letter)?' A partial, unverified hypothesis is displayed on the grid.':'');notify($('solve-status').textContent);
  const check=Samples.compareWithSample(puzzle,result.solutions?.[0]?.letters);if(check)notify(`${$('solve-status').textContent} Showcase check: the top alternative matches the known answer in ${check.correct} of ${check.total} cells. Nothing is confirmed until you accept it.`);
 },
 onError:error=>{$('solve-status').textContent='Search failed: '+error.message;notify($('solve-status').textContent,true);},
 onCancelError:error=>notify('Could not confirm server cancellation: '+error.message+'. The search remains bounded by its time limit.',true)
});
$('solve').onclick=()=>{exitReplay();replay=null;replayFor=null;acceptanceHistory.clear();setUndoAvailable(false);clearCandidateResults();renderCandidatePanel();$('solve-status').textContent='Starting local search…';const {generated,...snapshot}=JSON.parse(JSON.stringify(puzzle));void solveJob.start(snapshot);};
$('solve-grid').onclick=()=>$('solve').click();
// Any change to the puzzle cancels a running search. While one runs, an input
// that would change the puzzle asks first; if the user stops the search, the
// input is then carried out. Safe controls never ask: they only view, zoom,
// explain, look up, save or export, or edit text that is applied separately.
const SEARCH_SAFE=['.help-button','[data-close]','#cancel-solve','#load','#saved-language','#saved-list .icon-button','#rename-dialog','#print-open','#print-dialog','#export','#save','#dictionary','#dictionary-query','#dictionary-filter','#dictionary-search','#dictionary-results-previous','#dictionary-results-next','#dictionary-previous','#dictionary-next','#dictionary-add-words','#dictionary-words','#dictionary-file','#signin-dialog','#confirm-dialog','#busy-dialog','#pdf-dialog','#letter-conflict-keep','#assign-number-letter','#assign-number-status','#name','#rows','#cols','#generate-starters','#generate-difficulty','#generate-include','#generate-unique','#replay-play','#replay-range','#replay-exit','#check-answers','#opacity','#straighten-photo','#straighten-detect','#straighten-cancel','#straighten-overlay','#edit-tool','#puzzle-tool','#zoom-out','#zoom-range','#zoom-in','#fit-puzzle','#fit-height','#fit-width','#number-position','#show-certainty','#add-current-word','#clear-candidate-selection','#find-candidates','#candidate-panel .icon-button','#lookup-query','#lookup-current','#lookup-clear','#lookup-run','#lookup-mappings','#alternatives','#solved-word-filter','#solved-word-sort','#retry-word-checks','.word-jump','#rule-out-letter'].join(',');
let stopSearchPrompt=false,replayingInput=false;
function controlKind(control){
 if(control.matches('select'))return 'select';
 if(control.matches('textarea'))return 'text';
 if(control.matches('input'))return ['checkbox','radio','file','button','submit'].includes(control.type)?'button':['number','range'].includes(control.type)?control.type:'text';
 if(control.matches('button'))return 'button';
 return control.draggable?'drag':'other';
}
// grid is recorded when the input is caught: live previews rebuild the grid
// meanwhile, detaching the original cell.
function replayInput(event,control,grid){
 replayingInput=true;
 try{
  if(event.type==='click')control.click();
  else if(event.type==='keydown'&&grid){const cell=$('grid').children[selected];cell?.focus();cell?.dispatchEvent(new KeyboardEvent('keydown',{key:event.key,code:event.code,shiftKey:event.shiftKey,bubbles:true,cancelable:true}));}
  else{
   control.focus();
   if(event.type==='beforeinput'&&event.inputType==='insertText'&&event.data)try{control.setRangeText(event.data,control.selectionStart,control.selectionEnd,'end');control.dispatchEvent(new Event('input',{bubbles:true}));}catch{}
   if(event.type==='mousedown'&&control.matches('select'))try{control.showPicker();}catch{}
  }
 }finally{replayingInput=false;}
}
async function confirmStopSearch(event,control,grid){
 stopSearchPrompt=true;
 const stop=await confirmAction('A search is running. This change would stop it and discard its unfinished results.','Stop the search?',{confirm:'Stop search and continue',cancel:'Keep searching'});
 stopSearchPrompt=false;
 if(!stop||!solveJob.running)return;
 solveJob.cancel();$('solve-status').textContent='Search stopped before it finished. Its unfinished results were discarded.';
 if(livePreview){livePreview=null;livePreviewMargins=null;renderGrid();}
 replayInput(event,control,grid);
}
for(const type of ['click','mousedown','keydown','beforeinput','dragstart'])document.addEventListener(type,event=>{
 if(replayingInput||!solveJob.running||!(event.target instanceof Element))return;
 const control=event.target.closest('button,input,select,textarea,[draggable="true"]');if(!control)return;
 const grid=!!control.closest('#grid');
 if(!PuzzleState.searchInterruption({type,key:event.key,kind:controlKind(control),safe:!!control.closest(SEARCH_SAFE),grid,modifier:event.ctrlKey||event.metaKey||event.altKey}))return;
 event.preventDefault();event.stopImmediatePropagation();
 if(!stopSearchPrompt)void confirmStopSearch(event,control,grid);
},true);
// Generating fills the drawn grid on the server and opens the result in
// Puzzle mode. The answer stays out of the grid; it is used only by Check my
// letters and the solution sheet.
const generateJob=PuzzleState.solveRunner({
 request:api,path:'/api/generate-jobs',
 onBusy:busy=>{$('generate').disabled=busy;$('generate').textContent=busy?'Generating…':'Generate puzzle';$('cancel-generate').hidden=!busy;$('cancel-generate').disabled=false;},
 onStopping:stopping=>{$('cancel-generate').disabled=stopping;if(stopping)$('generate-status').textContent='Stopping…';},
 onUpdate:state=>{
  if(state.status==='running'||state.status==='queued'){const p=state.progress||{};$('generate-status').textContent=p.stage==='layout'?`Placing black cells… ${Math.round(p.elapsedSeconds||0)} s`+(p.restarts?`, layout ${p.restarts+1}`:'')+'.':p.stage==='checking'||p.stage==='grading'?`${p.stage==='grading'?'Checking the difficulty':'Checking for other answers'}… ${Math.round(p.elapsedSeconds||0)} s.`:`Filling the grid… ${Math.round(p.elapsedSeconds||0)} s, ${(p.nodes||0).toLocaleString()} words tried`+(p.restarts?`, ${p.restarts} restart${p.restarts===1?'':'s'}`:'')+'.';return;}
  if(state.status==='failed')throw new Error(state.error||'Generating failed.');
  const result=state.result||{},notes=(result.diagnostics||[]).join(' ');
  if(result.status!=='generated'){
   const reason=result.stats?.stopReason;
   const text=reason==='cancelled'?'Generating cancelled. The grid is unchanged.':reason==='search_exhausted'?'No fill exists: the search tried every option with the current dictionary. Change the black cells, the fixed letters or the dictionary.':'No fill found within the time limit. That does not mean none exists: try again, or add black cells to shorten long words.';
   $('generate-status').textContent=text+(notes?' '+notes:'');notify($('generate-status').textContent,reason!=='cancelled');return;
  }
  const source=generateSource;generateSource=null;
  if(!source||source.puzzle!==puzzle||source.revision!==revision){$('generate-status').textContent='The grid changed while generating, so the result was not applied. Generate again.';return;}
  const next=JSON.parse(JSON.stringify(puzzle));
  next.cells=next.cells.map((cell,i)=>({...PuzzleState.blankCell(),...(cell.highlight&&!result.cells[i].black?{highlight:true}:{}),...(cell.clue?{clue:true}:{}),...result.cells[i]}));
  next.generated={answer:result.answer,numbers:result.cells.map(c=>c.number),seed:result.stats.seed,...(result.grade?{grade:result.grade}:{})};
  delete next.suggestions;delete next.eliminations;delete next.rejectedWords;delete next.id;
  if(!next.name||next.name==='Untitled puzzle')next.name='Generated puzzle';
  setPuzzle(next,false);savedFingerprint='';
  $('generate-status').textContent=PuzzleState.generatedSummary(result)+(notes?' '+notes:'');
  notify(`Puzzle generated and opened in Puzzle mode. ${$('generate-status').textContent} Use Print or image to print it.`);
 },
 onError:error=>{generateSource=null;$('generate-status').textContent='Generating failed: '+error.message;notify($('generate-status').textContent,true);},
 onCancelError:error=>notify('Could not confirm cancellation: '+error.message+'. Generating stops at its time limit.',true)
});
let generateSource=null;
$('generate').onclick=protect(async()=>{
 const starters=Number($('generate-starters').value),unique=$('generate-unique').checked,difficulty=$('generate-difficulty').value,layout=generateLayout();
 const include=$('generate-include').value.split(/[\s,;]+/).filter(Boolean);
 if(include.length>30)throw new Error('List up to 30 words to include.');
 if(!Number.isInteger(starters)||starters<0||starters>10)throw new Error('Starter letters must be a whole number from 0 to 10.');
 if(puzzle.image)throw new Error('Generating works on a drawn grid. Remove the image first, or create a new grid.');
 if(puzzle.cells.some(c=>!c.black&&!c.prefilled&&c.letter||c.guess)&&!await confirmAction('Generating replaces answer letters and suggestions. Letters entered in Edit mode are kept as given letters.','Generate a new puzzle?'))return;
 const {generated,suggestions,image,...grid}=JSON.parse(JSON.stringify(puzzle));
 // Only letters entered in Edit mode are fixed; answer letters are not.
 grid.cells=(layout?layoutBase(grid.cells):grid.cells).map(cell=>({...cell,letter:cell.prefilled?cell.letter:'',guess:''}));
 generateSource={puzzle,revision};$('generate-status').textContent='Starting…';
 void generateJob.start({puzzle:grid,options:{starters,unique,difficulty,include,...(layout?{layout}:{})}});
});
$('cancel-generate').onclick=()=>generateJob.requestCancel();
// Each difficulty starts from its usual number of starter letters; Easy and
// Medium are solvable by deduction, which already means a single answer.
function syncDifficulty(){const level=$('generate-difficulty').value;$('generate-unique').disabled=level!=='hard';if(level!=='hard')$('generate-unique').checked=true;}
$('generate-difficulty').onchange=()=>{$('generate-starters').value={easy:3,medium:2,hard:1}[$('generate-difficulty').value];syncDifficulty();};
syncDifficulty();
// Wrong letters from the last check, shown while the letters stay as checked.
let answerMarks=null;
const lettersKey=()=>puzzle.cells.map(c=>c.letter||'.').join('');
function currentAnswerMarks(){return answerMarks&&answerMarks.puzzle===puzzle&&answerMarks.letters===lettersKey()?answerMarks.wrong:null;}
function renderGenerated(){$('check-answers').hidden=!PuzzleState.generatedAnswer(puzzle);renderLayout();}
// Word layout target. null while the fields follow the drawn grid; set once
// the user changes a field. placedLayout remembers the black cells before
// Place black cells, so Undo can put them back and a new placement can move
// the cells the app placed while keeping the ones the user drew.
let layoutTarget=null,placedLayout=null;
const blackKey=()=>puzzle.cells.map(c=>c.black?1:0).join('');
const placedCurrent=()=>!!placedLayout&&placedLayout.puzzle===puzzle&&placedLayout.key===blackKey();
function readLayoutTarget(){
 const target={words:Number($('layout-words').value),shortest:Number($('layout-shortest').value),longest:Number($('layout-longest').value)};
 const size=Math.max(puzzle.rows,puzzle.cols);
 if(!Number.isInteger(target.words)||target.words<1)throw new Error('The number of words must be a whole number of at least 1.');
 if(!Number.isInteger(target.shortest)||!Number.isInteger(target.longest)||target.shortest<2||target.shortest>target.longest)throw new Error('Word lengths must be whole numbers, at least 2, with the shortest no longer than the longest.');
 if(target.shortest>size)throw new Error(`A ${puzzle.rows} × ${puzzle.cols} grid has no room for words of ${target.shortest} letters.`);
 return target;
}
function renderLayout(){
 const summary=PuzzleState.layoutSummary(puzzle);
 if(!layoutTarget){$('layout-words').value=summary.words||'';$('layout-shortest').value=Math.min(summary.shortest||3,3);$('layout-longest').value=summary.longest||Math.max(puzzle.rows,puzzle.cols);}
 $('undo-layout').hidden=!placedCurrent();
 for(const id of ['layout-words','layout-shortest','layout-longest','layout-mirror','place-blocks'])$(id).disabled=!editMode;
}
for(const id of ['layout-words','layout-shortest','layout-longest'])$(id).onchange=protect(()=>{layoutTarget={};$('layout-status').textContent='';generateLayout();});
// The target Generate should place black cells for, or null to keep the grid.
function generateLayout(){
 if(!layoutTarget)return null;
 const target=readLayoutTarget(),placed=placedCurrent();
 if(!placed&&PuzzleState.meetsLayout(PuzzleState.layoutSummary(puzzle),target))return null;
 return {...target,mirror:$('layout-mirror').checked,...(placed?{current:puzzle.cells.map(c=>!!c.black)}:{})};
}
// The grid without the black cells the app placed, so a new layout can move them.
function layoutBase(cells){
 if(!placedCurrent())return cells;
 return cells.map((cell,i)=>cell.black&&!placedLayout.previous[i]?{...PuzzleState.blankCell(),...(cell.highlight?{highlight:true}:{})}:cell);
}
function setBlacks(black){
 puzzle.cells.forEach((cell,i)=>{
  if(black[i]===!!cell.black)return;
  if(black[i])Object.assign(cell,{black:true,clue:false,highlight:false,number:'',letter:'',guess:'',mappingAnchor:false});
  else Object.assign(cell,{black:false,number:'',letter:'',guess:''});
  delete cell.numberReview;
 });
}
$('place-blocks').onclick=protect(async()=>{
 if(!editMode)throw new Error('Switch to Edit mode to change the black cells.');
 if(puzzle.image)throw new Error('Placing black cells works on a drawn grid. Remove the image first, or create a new grid.');
 const target={...readLayoutTarget(),mirror:$('layout-mirror').checked},version=revision,current=puzzle;
 const {generated,suggestions,image,...grid}=JSON.parse(JSON.stringify(puzzle));
 const previous=placedCurrent()?placedLayout.previous:puzzle.cells.map(c=>!!c.black);
 grid.cells=layoutBase(grid.cells);
 $('place-blocks').disabled=true;$('layout-status').textContent='Placing black cells…';
 try{
  const result=await api('/api/layout',{puzzle:grid,target});
  if(current!==puzzle||version!==revision){$('layout-status').textContent='The grid changed while placing, so the layout was not applied.';return;}
  if(!result.valid){$('layout-status').textContent='No layout meets these word lengths for this grid. Widen the lengths or change the grid size.';return;}
  layoutTarget=target;setBlacks(result.black);placedLayout={puzzle,previous,key:blackKey()};
  invalidate();render();
  $('layout-status').textContent=result.exact?`Placed: ${result.words} words of ${result.shortest}–${result.longest} letters.`:`The closest layout found has ${result.words} words of ${result.shortest}–${result.longest} letters; you asked for ${target.words}.`;
 }finally{$('place-blocks').disabled=!editMode;}
});
$('undo-layout').onclick=()=>{if(!placedCurrent())return;setBlacks(placedLayout.previous);placedLayout=null;$('layout-status').textContent='Layout undone.';invalidate();render();};
$('check-answers').onclick=()=>{
 const check=PuzzleState.answerCheck(puzzle);
 if(!check)return notify('The black cells or numbers changed since generating, so the answer no longer applies.',true);
 answerMarks={puzzle,letters:lettersKey(),wrong:new Set(check.wrong)};renderGrid();notify(PuzzleState.answerCheckText(check),!!check.wrong.length);
};
// Print sheets: the puzzle, and for a generated puzzle optionally its solution.
function printSheets(){
 const answer=PuzzleState.generatedAnswer(puzzle),key=$('print-key').checked;
 const grade=answer?puzzle.generated.grade:undefined,sheets=[PrintSheet.sheetSvg(puzzle,{key,grade})];
 if(answer&&$('print-solution').checked)sheets.push(PrintSheet.sheetSvg(puzzle,{key,grade,solution:answer}));
 return sheets;
}
function renderPrintPreview(){
 const answer=PuzzleState.generatedAnswer(puzzle);
 $('print-solution').disabled=!answer;if(!answer)$('print-solution').checked=false;
 $('print-note').textContent=(answer?'':'A solution sheet is available for generated puzzles. ')+'The puzzle sheet shows numbers and letters entered in Edit mode; answer letters and suggestions are left out.';
 $('print-preview').innerHTML=printSheets().join('');
}
$('print-open').onclick=()=>{renderPrintPreview();$('print-dialog').showModal();};
for(const id of ['print-key','print-solution'])$(id).onchange=renderPrintPreview;
const sheetFileName=suffix=>(puzzle.name||'puzzle').replace(/[^a-z0-9_-]/gi,'_')+suffix;
function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('print-svg').onclick=()=>printSheets().forEach((svg,k)=>download(new Blob([svg],{type:'image/svg+xml'}),sheetFileName(k?'-solution.svg':'.svg')));
$('print-png').onclick=protect(async()=>{
 for(const [k,svg]of printSheets().entries()){
  const url=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml'}));
  try{
   const image=new Image();await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(new Error('Could not draw the sheet.'));image.src=url;});
   // Three times the SVG size: about 300 dpi for a 13 × 13 grid on A4.
   const scale=3,canvas=document.createElement('canvas');canvas.width=image.width*scale;canvas.height=image.height*scale;
   const context=canvas.getContext('2d');context.scale(scale,scale);context.drawImage(image,0,0);
   const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw new Error('Could not create the PNG.');
   download(blob,sheetFileName(k?'-solution.png':'.png'));
  }finally{URL.revokeObjectURL(url);}
 }
});
$('print-run').onclick=()=>{$('print-sheet').innerHTML=printSheets().join('');$('print-dialog').close();document.body.classList.add('printing');window.print();};
window.addEventListener('afterprint',()=>{document.body.classList.remove('printing');$('print-sheet').replaceChildren();});

$('show-certainty').onchange=()=>renderGrid();
$('replay-play').onclick=()=>{if(replayTimer){stopReplayTimer();renderReplay();return;}
 if(replayIndex===null||replayIndex>=replay.length-1)showReplayStep(0);
 replayTimer=setInterval(()=>{if(!replaying()||replayIndex>=replay.length-1){exitReplay();return;}showReplayStep(replayIndex+1);},450);renderReplay();};
$('replay-range').oninput=()=>{stopReplayTimer();showReplayStep(Number($('replay-range').value));};
$('replay-exit').onclick=()=>exitReplay();
$('cancel-solve').onclick=()=>solveJob.requestCancel();
$('search-mode').onchange=()=>{puzzle.searchMode=$('search-mode').value;invalidate();render();};
$('allow-unknown-words').onchange=()=>{puzzle.allowUnknownWords=$('allow-unknown-words').checked;invalidate();render();};

$('save').onclick=protect(async()=>{if(storageBusy)return;const version=revision,savedPuzzle=puzzle,savedName=puzzle.name,sent=workspaceFingerprint();setStorageBusy(true);try{const result=await api('/api/puzzles',savedPuzzle);if(puzzle===savedPuzzle){const unchanged=workspaceFingerprint()===sent;puzzle.id=result.id;if(unchanged)savedFingerprint=workspaceFingerprint();}notify(`Saved “${result.name}” ${modeView.savedWhere}.`+(puzzle===savedPuzzle&&(version!==revision||puzzle.name!==savedName)?' Newer edits are not saved yet.':''));}finally{setStorageBusy(false);}});$('load').onclick=protect(async()=>{if(storageBusy)return;await refreshSaved();if(!$('load-dialog').open)$('load-dialog').showModal();});
let renameItem=null;
let storageBusy=false;
function setStorageBusy(value){storageBusy=value;$('save').disabled=value;$('load').disabled=value;$('rename-save').disabled=value;for(const button of $('saved-list').querySelectorAll('button'))button.disabled=value;}

let savedPuzzles=[],savedLanguage='';
async function refreshSaved(){
 const token=++loadToken,result=await api('/api/puzzles');if(token!==loadToken)return;
 savedPuzzles=result.puzzles;renderSaved();
}
$('saved-language').onchange=()=>{savedLanguage=$('saved-language').value;renderSaved();};
function renderSaved(){
 const view=PuzzleState.savedPuzzleView(savedPuzzles,savedLanguage),filter=$('saved-language');
 filter.replaceChildren(new Option(`All languages (${savedPuzzles.length})`,''),...view.languages.map(entry=>new Option(`${entry.name} (${entry.count})`,entry.code)));
 filter.value=view.selected;filter.disabled=view.languages.length<2&&!view.selected;
 const list=$('saved-list');list.replaceChildren();if(!view.items.length)list.textContent='No saved puzzles yet.';
 view.items.forEach(item=>{
  const row=document.createElement('div');row.className='saved-row';
  const button=document.createElement('button');button.className='saved-item';
  const name=document.createElement('span');name.textContent=item.name;
  const language=document.createElement('span');language.className='saved-language';language.textContent=item.language?PuzzleState.languagePresentation({language:item.language}).name:'';
  const date=document.createElement('small');date.textContent=new Date(item.updatedAt).toLocaleDateString();button.append(name,language,date);
  button.onclick=protect(async()=>{if(storageBusy)return;if(!await confirmAction('Open this saved puzzle? Unsaved changes in the current puzzle will be replaced.'))return;const token=++loadToken,version=revision;const restored=await restorePuzzle(await api('/api/puzzles/'+encodeURIComponent(item.id)));if(token!==loadToken||version!==revision)return notify('The workspace changed while opening. Open the saved puzzle again.');setPuzzle(restored,false);$('load-dialog').close();notify('Puzzle opened.');});
  const rename=document.createElement('button');rename.className='icon-button';rename.textContent='✎';rename.title='Rename '+item.name;rename.setAttribute('aria-label',rename.title);
  rename.onclick=()=>{if(storageBusy)return;renameItem=item;$('rename-name').value=item.name;$('rename-dialog').showModal();$('rename-name').select();};
  const remove=document.createElement('button');remove.className='icon-button';remove.title='Delete '+item.name;remove.setAttribute('aria-label',remove.title);
  remove.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/></svg>';
  remove.onclick=protect(async()=>{if(storageBusy)return;if(!await confirmAction(`Delete “${item.name}” from saved puzzles? A local recovery copy will be kept.`,'Delete saved puzzle?'))return;if(storageBusy)return;setStorageBusy(true);try{await api('/api/puzzles/'+encodeURIComponent(item.id),null,'DELETE');if(puzzle.id===item.id)delete puzzle.id;await refreshSaved();notify('Saved puzzle deleted.');}finally{setStorageBusy(false);}});
  row.append(button,rename,remove);for(const control of [button,rename,remove])control.disabled=storageBusy;list.append(row);
 });
}
$('rename-form').onsubmit=protect(async event=>{event.preventDefault();if(storageBusy)return;const item=renameItem,name=$('rename-name').value.trim();if(!name)return;const oldName=puzzle.name,currentPuzzle=puzzle;setStorageBusy(true);try{const result=await api('/api/puzzles/'+encodeURIComponent(item.id),{name},'PATCH');if(puzzle===currentPuzzle&&puzzle.id===item.id&&puzzle.name===oldName&&oldName===item.name){puzzle.name=result.name;$('name').value=result.name;}$('rename-dialog').close();await refreshSaved();notify('Saved puzzle renamed.');}finally{setStorageBusy(false);}});

$('export').onclick=()=>{savedFingerprint=workspaceFingerprint();const blob=new Blob([JSON.stringify(puzzle,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=(puzzle.name||'puzzle').replace(/[^a-z0-9_-]/gi,'_')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
async function restorePuzzle(value){
 const restored=PuzzleState.canonicalPuzzle(value),saved=restored.suggestions;
 delete restored.suggestions;
 if(!saved)return restored;
 const savedSolutions=Array.isArray(saved.solutions)?saved.solutions:[];
 // Disabled entries do not count as dictionary evidence.
 const savedDictionary=restored.useDictionary?await api('/api/dictionaries/'+restored.language):null,disabledWords=new Set(savedDictionary?.disabled||[]),dictionary=savedDictionary?savedDictionary.words.filter(word=>!disabledWords.has(word)):[];
 const slots=PuzzleState.slots(restored),solutions=[];
 const baseCheck=await api('/api/validate',restored),forcedLetters=baseCheck.valid?PuzzleState.mappingDeductions(restored):restored.cells.map(()=> '');
 for(const candidate of savedSolutions.slice(0,20)){
  const letters=PuzzleState.candidateLetters(restored,candidate);
  if(!letters)continue;
  const filled={...restored,cells:restored.cells.map((cell,i)=>({...cell,letter:letters[i]}))};
  const check=await api('/api/validate',filled);
  if(!check.valid)continue;
  const words=PuzzleState.restoredWords(restored,letters,dictionary);
  solutions.push({letters,words,score:Number.isFinite(candidate.score)?candidate.score:0});
 }
 let partialLetters;
 if(Array.isArray(saved.partialLetters)&&saved.partialLetters.length===restored.cells.length){
  const alphabet=PuzzleState.nordicLetters(restored.language)?/^[A-ZÅÄÖ]?$/:/^[A-Z]?$/;
  const letters=saved.partialLetters.map(letter=>typeof letter==='string'?normalize(letter.trim()):'?');
  if(letters.every((letter,i)=>alphabet.test(letter)&&(!restored.cells[i].black||!letter)&&(!restored.cells[i].letter||!letter||restored.cells[i].letter===letter))){
   const check=await api('/api/validate',{...restored,cells:restored.cells.map((cell,i)=>({...cell,letter:cell.letter||letters[i]}))});
   if(check.valid)partialLetters=letters;
  }
 }
 restored.suggestions={status:'restored_suggestions',solutions,forcedLetters,partialLetters,stats:{exhaustive:false},diagnostics:['Saved alternatives checked against current constraints'+(restored.useDictionary?'. Current dictionary matches were rechecked; all other words, including saved morphology matches, remain unverified.':'. Language-model candidates remain unverified.')+(solutions.length<savedSolutions.length?' Some saved alternatives were invalid and discarded.':'')]};
 return restored;
}
$('import').onchange=protect(async event=>{const file=event.target.files[0];event.target.value='';if(!file)return;const version=revision;if(file.size>15*1024*1024)throw new Error('Puzzle file is too large (maximum 15 MB).');const value=JSON.parse(await file.text());await api('/api/validate',value);if(!value||!Array.isArray(value.cells)||!value.rules)throw new Error('Invalid puzzle file.');if(!await confirmAction('Import this puzzle and replace the current unsaved workspace?'))return;delete value.id;const restored=await restorePuzzle(value);if(version!==revision)return notify('The workspace changed during import. Import the puzzle again.');setPuzzle(restored,false);notify('Puzzle imported. Saved suggestions were checked against current constraints. Words absent from the current dictionary remain unverified.');});
function fileData(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Could not read the file.'));reader.readAsDataURL(file);});}
function choosePdfPage(pages){
 return new Promise(resolve=>{
  const dialog=$('pdf-dialog');$('pdf-page-count').textContent=`This PDF contains ${pages} pages.`;$('pdf-page').max=pages;$('pdf-page').value=1;
  let chosen=null;
  $('pdf-page-form').onsubmit=event=>{event.preventDefault();const page=Number($('pdf-page').value);if(Number.isInteger(page)&&page>=1&&page<=pages){chosen=page;dialog.close();}};
  $('pdf-cancel').onclick=()=>dialog.close();dialog.onclose=()=>resolve(chosen);dialog.showModal();
 });
}
let imageToken=0,straightenHandles=null,straightenBusy=false;
$('image-upload').onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();$('image').click();}};
const importImageFile=protect(async event=>{
 const file=event.target.files[0];event.target.value='';if(!file)return;
 const isPdf=file.type==='application/pdf'||/\.pdf$/i.test(file.name);
 if(!isPdf&&!['image/png','image/jpeg','image/webp'].includes(file.type))throw new Error('Choose a PDF, PNG, JPEG, or WebP file.');
 if(file.size>8*1024*1024)throw new Error('File is too large (maximum 8 MB).');
 const version=revision,token=++imageToken,task=startBusyTask(isPdf?'Importing PDF':'Importing image','Cancel import');
 let importedPuzzle=null;
 const stale=()=>{if(task.cancelled)return true;if(token===imageToken&&version===revision)return false;task.finish();notify('The workspace changed while loading the image. Add it again.');return true;};
 try{
  task.step('Reading the file…');
  let data=await fileData(file);if(stale())return;
  if(isPdf){
   data='data:application/pdf;base64,'+data.split(',')[1];
   task.step('Reading the PDF locally…');const info=await api('/api/pdf',{pdf:data},undefined,task.signal);
   if(stale())return;
   const page=info.pages===1?1:await choosePdfPage(info.pages);if(page===null){task.finish();notify('PDF import cancelled.');return;}
   if(stale())return;
   task.step(`Rendering PDF page ${page} locally…`);const rendered=await api('/api/pdf',{pdf:data,page},undefined,task.signal);data=rendered.image;
  }
  task.step('Decoding the image…');
  const decoded=new Image();decoded.src=data;
  try{await decoded.decode();}catch{throw new Error('The file is not a readable image. The current image was kept.');}
  if(!decoded.naturalWidth||!decoded.naturalHeight||decoded.naturalWidth*decoded.naturalHeight>16000000)throw new Error('Images must contain at most 16 million pixels.');
  if(stale())return;
  if((puzzle.image||puzzle.cells.some(c=>c.black||c.number||c.letter||c.guess))&&!await confirmAction('Import this screenshot as a fresh grid? Save first to keep the current puzzle.')){task.finish();return;}
  if(task.cancelled||token!==imageToken)return;
  const next=fresh(puzzle.rows,puzzle.cols,puzzle.language);Object.assign(next,{name:puzzle.name,rules:puzzle.rules,useDictionary:puzzle.useDictionary,image:data,imageBounds:{x:0,y:0,width:1,height:1}});
  setPuzzle(next);importedPuzzle=puzzle;const recognitionVersion=revision;
  task.step('Detecting grid dimensions, blocked cells and numbers locally…');
  try{
   const result=await api('/api/ocr',{image:data,autoDetect:true},undefined,task.signal);
   if(task.cancelled)return;
   if(token!==imageToken||puzzle!==importedPuzzle||revision!==recognitionVersion){task.finish();return notify('The workspace changed during recognition. The latest edits were kept; recognize again when ready.');}
   puzzle.rows=result.rows;puzzle.cols=result.cols;puzzle.cells=result.cells.map(c=>({...c,prefilled:!!c.letter}));puzzle.imageBounds=result.bounds||result.imageBounds||puzzle.imageBounds;
   invalidate();syncControls();render();task.finish();notify(['Image imported. Review recognized cells before solving.',...(result.diagnostics||[])].join(' '));
  }catch(error){if(!task.cancelled&&puzzle===importedPuzzle){task.finish();notify('Image kept. Automatic recognition failed: '+error.message+' For a photo taken at an angle or of a curved page, use Straighten photo. Otherwise set rows, columns and image bounds, then apply dimensions and recognize again.',true);}}
 }catch(error){if(!task.cancelled)throw error;}
 finally{
  task.finish();
  if(task.cancelled)notify(importedPuzzle&&puzzle===importedPuzzle?'Recognition cancelled. The image was kept on an empty grid; set rows, columns and image bounds, then recognize when ready.':'Import cancelled. The current puzzle was not changed.');
 }
});
$('image').onchange=importImageFile;
// The bundled sample page goes through the same import and recognition as a chosen file.
async function importSamplePage(){
 const response=await fetch('/samples/showcase-en.png');if(!response.ok)throw new Error('The sample page could not be loaded.');
 const file=new File([await response.blob()],'showcase-en.png',{type:'image/png'});
 await importImageFile({target:{files:[file],value:''}});
 if(!puzzle.image)return false;
 const sample=Samples.samplePuzzle();Object.assign(puzzle,{name:sample.name+' (from an image)',language:sample.language,useDictionary:false,searchMode:'deep',sample:sample.sample});
 syncControls();render();return true;
}
$('sample-image').onclick=protect(async()=>{
 if((puzzle.image||puzzle.cells.some(c=>c.number||c.letter||c.guess||c.black))&&!await confirmAction('Replace this workspace with the sample page? Save first to keep current work.'))return;
 setPuzzle(fresh(13,13,'en'));
 if(await importSamplePage())notify('Sample page imported: recognition read the grid from the image. Review it, then click Solve. Use dictionary is off and search time is Deep.');
});
$('apply-image-dimensions').onclick=async()=>{const rows=Number($('rows').value),cols=Number($('cols').value);if(!Number.isInteger(rows)||!Number.isInteger(cols)||rows<1||rows>40||cols<1||cols>40)return notify('Use whole-number dimensions between 1 and 40.',true);if(puzzle.cells.some(c=>c.number||c.letter||c.guess||c.black)&&!await confirmAction('Apply these dimensions and clear grid entries? The image and alignment will be kept.'))return;puzzle.rows=rows;puzzle.cols=cols;puzzle.cells=fresh(rows,cols).cells;selected=0;numericEntry=null;invalidate();render();};

for(const key of ['x','y','width','height'])$('bound-'+key).oninput=()=>{alignmentDirty=true;solveJob.cancel();revision++;$('alignment-status').textContent='Alignment changes are not applied yet.';};
$('apply-alignment').onclick=()=>{
 const values={};for(const key of ['x','y','width','height'])values[key]=$('bound-'+key).value;
 try{const bounds=PuzzleState.imageBoundsFromPercent(values);puzzle.imageBounds=bounds;alignmentDirty=false;solveJob.cancel();revision++;renderGrid();$('alignment-status').textContent='Alignment applied.';}
 catch(error){$('alignment-status').textContent=error.message;}
};
$('opacity').oninput=()=>document.documentElement.style.setProperty('--overlay',$('opacity').value/100);$('remove-image').onclick=()=>{delete puzzle.image;delete puzzle.imageBounds;delete puzzle.straightenedPhoto;solveJob.cancel();revision++;render();};$('ocr').onclick=protect(async()=>{if(alignmentDirty)throw new Error('Apply the alignment changes before recognizing the grid.');if(!ocrAvailable)throw new Error('Local OCR is unavailable. You can still enter cells manually over the image.');if(puzzle.cells.some(c=>c.number||c.letter||c.guess||c.black)&&!await confirmAction('Recognition replaces the current grid entries. Continue?'))return;const version=revision,task=startBusyTask('Recognizing the grid','Cancel recognition');task.step('Detecting blocked cells and reading numbers locally…');try{const result=await api('/api/ocr',{image:puzzle.image,rows:puzzle.rows,cols:puzzle.cols,bounds:puzzle.imageBounds,photo:!!puzzle.straightenedPhoto},undefined,task.signal);if(task.cancelled)return;task.finish();if(version!==revision)return notify('The puzzle changed during recognition. Run recognition again.');puzzle.cells=result.cells.map(c=>({...c,prefilled:!!c.letter}));invalidate();render();notify(['Recognition complete. Review all cells before solving.',...result.diagnostics].join(' '));}catch(error){if(!task.cancelled)throw error;}finally{task.finish();if(task.cancelled)notify('Recognition cancelled. The grid was not changed.');}});
let dictionaryPages=PuzzleState.dictionaryPages(),dictionaryPage=0,dictionaryBusy=false;
function renderDictionaryPage(){
 $('dictionary-words').value=dictionaryPages.page(dictionaryPage);
 $('dictionary-page-status').textContent=`Page ${dictionaryPage+1} of ${dictionaryPages.count}`;
 $('dictionary-previous').disabled=dictionaryBusy||dictionaryPage===0;
 $('dictionary-next').disabled=dictionaryBusy||dictionaryPage===dictionaryPages.count-1;
}
function loadDictionaryText(text){dictionaryPages=PuzzleState.dictionaryPages(text);dictionaryPage=0;renderDictionaryPage();}
$('dictionary-previous').onclick=()=>{dictionaryPage--;renderDictionaryPage();};
$('dictionary-next').onclick=()=>{dictionaryPage++;renderDictionaryPage();};
const dictionaryEditor=PuzzleState.dictionaryEditor(api,data=>{
 dictionaryLanguage=data.language;
 $('dictionary-title').textContent=PuzzleState.languagePresentation({language:dictionaryLanguage}).name+' dictionary';
 $('dictionary-source').textContent=`${data.source} · ${data.words.length} entries. Bundled demonstration lists are not comprehensive.`;
 loadDictionaryText(data.words.join('\n'));bulkLoaded=true;bulkDirty=false;if(!$('dictionary-dialog').open)$('dictionary-dialog').showModal();
},result=>{
 $('dictionary-dialog').close();
 notify(`Saved ${result.count} ${PuzzleState.languagePresentation({language:result.language}).name} dictionary entries.`+(result.importing?` Skipped ${result.skipped} invalid lines; removed ${result.duplicates} duplicates.`:''));
},result=>{wordChecks.clear(result.language);if(puzzle.language===result.language){invalidate();render();}},busy=>{
 for(const id of ['dictionary','save-dictionary','dictionary-file'])$(id).disabled=busy;
 $('dictionary-words').readOnly=busy;dictionaryBusy=busy;renderDictionaryPage();
});
$('dictionary-dialog').addEventListener('close',()=>{dictionaryEditor.cancel();dictionarySearchToken++;});
// Search-driven editing: the server filters and pages, so even an 870k-word
// list never has to load into the browser. Bulk text loads only on demand.
let dictionaryOffset=0,dictionarySearchToken=0,bulkLoaded=false,bulkDirty=false,lastDictionarySearch=null;
async function searchDictionary(offset=0){const token=++dictionarySearchToken,language=dictionaryLanguage;const query=$('dictionary-query').value.trim(),status=$('dictionary-filter').value;
 $('dictionary-search-status').textContent='Searching…';
 try{const result=await api(`/api/dictionaries/${language}/search?q=${encodeURIComponent(query)}&status=${status}&offset=${offset}`);if(token!==dictionarySearchToken)return;lastDictionarySearch=result;dictionaryOffset=result.offset;renderDictionaryResults(result);}
 catch(error){if(token===dictionarySearchToken)$('dictionary-search-status').textContent='Search failed: '+error.message;}}
function renderDictionaryResults(result){const output=$('dictionary-results');output.replaceChildren();
 $('dictionary-source').textContent=`${result.custom?modeView.customDictionary:'Bundled demonstration vocabulary (not comprehensive)'} · ${result.count.toLocaleString('en')} entries, ${result.disabledCount.toLocaleString('en')} disabled.`;
 $('dictionary-search-status').textContent=PuzzleState.dictionarySearchSummary(result);
 for(const entry of result.words){const row=document.createElement('div');row.className='dictionary-row'+(entry.enabled?'':' disabled');
  const toggle=document.createElement('label');toggle.className='check';const box=document.createElement('input');box.type='checkbox';box.checked=entry.enabled;box.setAttribute('aria-label',(entry.enabled?'Disable ':'Enable ')+entry.word);box.title=entry.enabled?'Enabled: used for solving. Untick to disable.':'Disabled: kept but not used. Tick to enable.';
  box.onchange=protect(()=>editDictionary(box.checked?{enable:[entry.word]}:{disable:[entry.word]},`${box.checked?'Enabled':'Disabled'} ${entry.word}.`));
  const word=document.createElement('span');word.textContent=entry.word;toggle.append(box,word);
  const remove=document.createElement('button');remove.type='button';remove.className='icon-button';remove.textContent='Delete';remove.setAttribute('aria-label','Delete '+entry.word);
  remove.onclick=protect(async()=>{if(await confirmAction(`Delete ${entry.word} from the ${PuzzleState.languagePresentation({language:dictionaryLanguage}).name} dictionary? To keep it but stop using it, untick it instead.`,'Delete word?'))await editDictionary({remove:[entry.word]},`Deleted ${entry.word}.`);});
  row.append(toggle,remove);output.append(row);}
 $('dictionary-results-previous').disabled=result.offset===0;$('dictionary-results-next').disabled=result.offset+result.words.length>=result.total;
 $('dictionary-results-page').textContent=result.total?`Page ${Math.floor(result.offset/result.limit)+1} of ${Math.ceil(result.total/result.limit)}`:'';}
async function editDictionary(edits,message){const language=dictionaryLanguage;
 if(bulkDirty&&!await confirmAction('The bulk editor has unsaved changes. Discard them and apply this change?','Discard bulk edits?')){if(lastDictionarySearch)renderDictionaryResults(lastDictionarySearch);return;}
 const result=await api(`/api/dictionaries/${language}/entries`,edits);
 notify(message+(result.skipped?` ${result.skipped} already in that state.`:''));
 wordChecks.clear(language);if(puzzle.language===language){invalidate();render();}
 if(bulkLoaded){bulkLoaded=false;bulkDirty=false;if($('dictionary-bulk').open)await dictionaryEditor.open(language);}
 await searchDictionary(dictionaryOffset);}
$('dictionary').onclick=protect(async()=>{dictionaryEditor.cancel();dictionaryLanguage=puzzle.language;bulkLoaded=false;bulkDirty=false;$('dictionary-bulk').open=false;
 $('dictionary-title').textContent=PuzzleState.languagePresentation({language:dictionaryLanguage}).name+' dictionary';$('dictionary-source').textContent='';$('dictionary-results').replaceChildren();$('dictionary-query').value='';$('dictionary-filter').value='all';lastDictionarySearch=null;
 $('dictionary-dialog').showModal();await searchDictionary(0);});
$('dictionary-bulk').addEventListener('toggle',protect(async()=>{if($('dictionary-bulk').open&&!bulkLoaded)await dictionaryEditor.open(dictionaryLanguage);}));
$('dictionary-search').onclick=()=>searchDictionary(0);
$('dictionary-query').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();searchDictionary(0);}};
// Emptying the box (typing or the clear button) shows the unfiltered list again.
$('dictionary-query').oninput=()=>{if(!$('dictionary-query').value.trim()&&lastDictionarySearch?.query)searchDictionary(0);};
$('dictionary-filter').onchange=()=>searchDictionary(0);
$('dictionary-results-previous').onclick=()=>searchDictionary(Math.max(0,dictionaryOffset-(lastDictionarySearch?.limit||100)));
$('dictionary-results-next').onclick=()=>searchDictionary(dictionaryOffset+(lastDictionarySearch?.limit||100));
$('dictionary-add').onclick=protect(async()=>{const words=PuzzleState.dictionaryInputWords($('dictionary-add-words').value);if(!words.length)return notify('Type one or more words to add.');
 await editDictionary({add:words},`Added ${words.length===1?words[0]:words.length+' words'}.`);$('dictionary-add-words').value='';});
$('dictionary-add-words').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();$('dictionary-add').click();}};
$('dictionary-words').oninput=()=>{dictionaryPages.update(dictionaryPage,$('dictionary-words').value);dictionaryEditor.manualEdit();bulkDirty=true;};
$('dictionary-file').onchange=protect(async event=>{
 const file=event.target.files[0];event.target.value='';if(!file)return;
 if(file.size>modeView.maxImportBytes)throw new Error(`Word list is too large (maximum ${modeView.maxImportBytes/1024/1024} MB).`);
 const contents=await dictionaryEditor.readFile(()=>file.text());
 if(contents!==null&&$('dictionary-dialog').open)loadDictionaryText(contents);
});
$('save-dictionary').onclick=protect(()=>dictionaryEditor.save(dictionaryPages.text()));
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());
$('demo').onclick=async()=>{if((puzzle.image||puzzle.cells.some(c=>c.number||c.letter||c.guess||c.black))&&!await confirmAction('Replace this workspace with the example? Save first to keep current work.'))return;const demo=fresh(3,3);demo.name='First steps · word square';const letters='CATARETEN',mapping={C:'1',A:'2',T:'3',R:'4',E:'5',N:'6'};demo.cells=demo.cells.map((c,i)=>({...c,number:mapping[letters[i]],letter:i===0?'C':'',openBeforeAcross:false,openAfterAcross:false,openBeforeDown:false,openAfterDown:false}));setPuzzle(demo);notify('Example loaded: a small word square. Click Solve, then review and accept suggestions.');};
$('showcase').onclick=async()=>{if((puzzle.image||puzzle.cells.some(c=>c.number||c.letter||c.guess||c.black))&&!await confirmAction('Replace this workspace with the showcase puzzle? Save first to keep current work.'))return;const sample=Samples.samplePuzzle(),showcase={...fresh(sample.rows,sample.cols,sample.language),...sample};setPuzzle(showcase);notify('Showcase loaded: a full-size English codeword with no letters given. Use dictionary is off and search time is Deep. Click Solve and watch the grid settle; the search takes up to a minute.');};
// Guided demo: import the sample page, solve, replay, compare with the answer.
function demoCaption(text){$('demo-caption').textContent=text||'';$('demo-caption').hidden=!text;}
function waitUntil(test,run,timeout=120000){
 const started=Date.now();
 return new Promise(resolve=>{const tick=()=>{if(run!==demoRun)return resolve(false);if(test())return resolve(true);if(Date.now()-started>timeout)return resolve(false);setTimeout(tick,150);};tick();});
}
$('watch-demo').onclick=protect(async()=>{
 if((puzzle.image||puzzle.cells.some(c=>c.number||c.letter||c.guess||c.black))&&!await confirmAction('Replace this workspace with the guided demo? Save first to keep current work.'))return;
 const run=++demoRun;demoActive=true;
 try{
  setPuzzle(fresh(13,13,'en'));
  let fromImage=false;
  if(ocrAvailable){demoCaption('Step 1 of 4 · Importing a printed page and reading its grid, black cells and numbers from the image…');fromImage=await importSamplePage();}
  if(run!==demoRun)return;
  const sample=Samples.samplePuzzle(),recognised=Samples.compareWithSample(puzzle,puzzle.cells.map(()=>''));
  if(!fromImage||!recognised){setPuzzle({...fresh(sample.rows,sample.cols,sample.language),...sample});}
  puzzle.searchMode='quick';syncControls();render();
  const numbered=puzzle.cells.filter(c=>!c.black&&c.number).length;
  demoCaption(fromImage&&recognised?`Step 2 of 4 · Recognised a ${puzzle.rows} × ${puzzle.cols} grid with ${numbered} numbered cells and no letters given. Solving without a dictionary; the grid shows the best guess as it improves…`
   :`Step 2 of 4 · ${fromImage?'Recognition did not match the sample exactly, so the demo uses the typed-in grid.':'Image recognition is not available here, so the demo starts from the typed-in grid.'} Solving without a dictionary…`);
  $('solve').click();
  if(!await waitUntil(()=>!$('cancel-solve').hidden,run,10000))return;
  if(!await waitUntil(()=>$('cancel-solve').hidden,run))return;
  if(!replay){demoCaption('The search finished without a replay. See the result below.');return;}
  demoCaption(`Step 3 of 4 · Replaying the ${replay.length} improvements the search found. Coral letters have a close rival, light coral a moderate lead.`);
  $('replay-play').click();
  if(!await waitUntil(()=>!replayTimer&&replayIndex===null,run,180000))return;
  const check=Samples.compareWithSample(puzzle,puzzle.suggestions?.solutions?.[0]?.letters);
  demoCaption(check?`Step 4 of 4 · The top answer matches the known answer in ${check.correct} of ${check.total} cells. Shaded cells show where to check first; nothing is confirmed until you accept it.`
   :'Step 4 of 4 · Done. Shaded cells show where to check first; nothing is confirmed until you accept it.');
 }finally{if(run===demoRun)demoActive=false;}
});
function straightenSize(){const image=$('puzzle-image');return [image.naturalWidth||1,image.naturalHeight||1];}
function renderStraighten(){
 if(!puzzle.image)straightenHandles=null;
 const active=!!straightenHandles,was=$('board-stage').classList.contains('straightening');$('board-stage').classList.toggle('straightening',active);if(was!==active)updateView();$('straighten-overlay').hidden=!active;$('straighten-panel').hidden=!active;$('straighten-photo').hidden=active;
 $('straighten-apply').disabled=$('straighten-cancel').disabled=$('straighten-detect').disabled=straightenBusy;
 if(!active)return;
 const [width,height]=straightenSize(),paths=Straighten.edgePaths(straightenHandles,width,height);
 $('straighten-outline').setAttribute('d',Straighten.outlinePath(straightenHandles,width,height));
 for(const edge of Straighten.EDGE_NAMES)$('straighten-hit-'+edge).setAttribute('d',paths[edge]);
 // Edge point buttons are rebuilt only when points are added or removed, never during a drag.
 const layout=Straighten.EDGE_NAMES.map(edge=>straightenHandles[edge].length).join();
 if($('straighten-overlay').dataset.layout!==layout){
  $('straighten-overlay').dataset.layout=layout;$('straighten-overlay').querySelectorAll('.straighten-handle.middle').forEach(handle=>handle.remove());
  for(const edge of Straighten.EDGE_NAMES)straightenHandles[edge].forEach((_,index)=>straightenHandle('handle-'+edge+'-'+index,`${edge} edge point ${index+1} handle (Delete removes it)`,true,
   ()=>straightenHandles[edge][index],(handles,x,y)=>Straighten.moveEdgePoint(handles,edge,index,x,y),()=>Straighten.removeEdgePoint(straightenHandles,edge,index)));
 }
 for(const name of Straighten.CORNERS)placeStraightenHandle($('handle-'+name),straightenHandles[name]);
 for(const edge of Straighten.EDGE_NAMES)straightenHandles[edge].forEach((point,index)=>placeStraightenHandle($('handle-'+edge+'-'+index),point));
}
function placeStraightenHandle(handle,point){handle.style.left=point.x*100+'%';handle.style.top=point.y*100+'%';}
function straightenHandle(id,label,middle,point,move,remove){
 const handle=document.createElement('button');
 handle.type='button';handle.id=id;handle.className='straighten-handle'+(middle?' middle':'');handle.setAttribute('aria-label',label);
 const moveTo=event=>{const box=$('straighten-overlay').getBoundingClientRect();straightenHandles=move(straightenHandles,(event.clientX-box.left)/box.width,(event.clientY-box.top)/box.height);renderStraighten();};
 const removeHandle=()=>{if(!remove||straightenBusy)return;straightenHandles=remove();renderStraighten();};
 handle.onpointerdown=event=>{if(straightenBusy)return;event.preventDefault();handle.setPointerCapture(event.pointerId);handle.onpointermove=moveTo;};
 handle.onpointerup=handle.onpointercancel=()=>{handle.onpointermove=null;};
 handle.ondblclick=removeHandle;
 handle.onkeydown=event=>{
  if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();removeHandle();return;}
  const step=event.shiftKey?.01:.002,d={ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]}[event.key];if(!d||straightenBusy)return;event.preventDefault();
  const p=point();straightenHandles=move(straightenHandles,p.x+d[0],p.y+d[1]);renderStraighten();};
 $('straighten-overlay').append(handle);
 return handle;
}
for(const name of Straighten.CORNERS)straightenHandle('handle-'+name,name.replace(/([A-Z])/,' $1').toLowerCase()+' corner handle',false,()=>straightenHandles[name],(handles,x,y)=>Straighten.moveCorner(handles,name,x,y));
// Clicking the outline adds a bend point there, so a strongly curved edge can be followed closely.
for(const edge of Straighten.EDGE_NAMES)$('straighten-hit-'+edge).onclick=event=>{
 if(!straightenHandles||straightenBusy)return;
 const box=$('straighten-overlay').getBoundingClientRect(),[width,height]=straightenSize();
 const added=Straighten.addEdgePoint(straightenHandles,edge,(event.clientX-box.left)/box.width,(event.clientY-box.top)/box.height,width,height);
 if(added.error)return notify(added.error);
 straightenHandles=added.handles;renderStraighten();$('handle-'+edge+'-'+added.index).focus();
};
// Puzzles have a printed border, so the handles start on it when it can be found.
async function detectBorder(){
 const target=puzzle,image=puzzle.image;straightenBusy=true;renderStraighten();notify('Looking for the grid border…');
 try{
  const {handles}=await api('/api/straighten/detect',{image});
  if(puzzle!==target||puzzle.image!==image||!straightenHandles)return;
  if(handles){straightenHandles=handles;notify('Found the grid border. Check that the outline follows it, drag any handle that is off, then Apply.');}
  else notify('Could not find the grid border. Drag the corner handles onto the outer corners of the grid.',true);
 }catch(error){notify('Could not look for the grid border: '+error.message+' Drag the corner handles onto the outer corners of the grid.',true);}
 finally{straightenBusy=false;renderStraighten();}
}
$('straighten-photo').onclick=()=>{if(!puzzle.image||!editMode)return;straightenHandles=Straighten.defaultHandles();fitMode='puzzle';updateView();renderStraighten();$('board-stage').scrollIntoView({block:'nearest'});detectBorder();};
$('straighten-detect').onclick=()=>{if(straightenHandles&&!straightenBusy)detectBorder();};
$('straighten-cancel').onclick=()=>{straightenHandles=null;renderStraighten();};
$('straighten-apply').onclick=protect(async()=>{
 if(!straightenHandles||straightenBusy)return;
 if(puzzle.cells.some(c=>c.number||c.letter||c.guess||c.black)&&!await confirmAction('Straightening replaces the image and reads the grid again. Current grid entries are replaced. Continue?'))return;
 const target=puzzle,version=revision,handles=straightenHandles,task=startBusyTask('Straightening the photo','Cancel');straightenBusy=true;renderStraighten();
 task.step('Straightening the photo and evening out its cells locally…');
 let straightened=false;
 try{
  const flat=await api('/api/straighten',{image:puzzle.image,handles},undefined,task.signal);
  if(task.cancelled)return;
  if(puzzle!==target||revision!==version){task.finish();return notify('The puzzle changed while straightening. Try again.');}
  straightenHandles=null;solveJob.cancel();
  Object.assign(puzzle,{image:flat.image,straightenedPhoto:true,imageBounds:flat.bounds||{x:0,y:0,width:1,height:1}});
  if(flat.rows){puzzle.rows=flat.rows;puzzle.cols=flat.cols;}
  puzzle.cells=fresh(puzzle.rows,puzzle.cols).cells;selected=0;numericEntry=null;invalidate();syncControls();render();
  straightened=true;const recognitionVersion=revision;
  task.step('Reading the grid from the straightened photo…');
  try{
   const result=await api('/api/ocr',flat.rows?{image:flat.image,rows:flat.rows,cols:flat.cols,bounds:flat.bounds,photo:true}:{image:flat.image,autoDetect:true,photo:true},undefined,task.signal);
   if(task.cancelled)return;task.finish();
   if(puzzle!==target||revision!==recognitionVersion)return notify('The puzzle changed during recognition. Read the grid from the image again when ready.');
   puzzle.rows=result.rows;puzzle.cols=result.cols;puzzle.imageBounds=result.bounds||puzzle.imageBounds;puzzle.cells=result.cells.map(c=>({...c,prefilled:!!c.letter}));
   invalidate();syncControls();render();notify(['Photo straightened. Review recognized cells before solving.',...(result.diagnostics||[])].join(' '));
  }catch(error){if(!task.cancelled){task.finish();notify('Photo straightened, but the grid could not be read: '+error.message+' Set rows and columns, apply them to the image, then read the grid again.',true);}}
 }catch(error){if(!task.cancelled)throw error;}
 finally{
  task.finish();straightenBusy=false;renderStraighten();
  if(task.cancelled)notify(straightened?'Photo straightened; reading the grid was cancelled. Set rows and columns, apply them to the image, then read the grid again.':'Straightening cancelled. The photo and grid were not changed.');
 }
});
// Autosave: one recovery copy of the workspace, so a reload or closed tab
// never loses work. The local app keeps it on the server; hosted mode keeps
// it in this browser (IndexedDB). Explicit Save/Export still name and keep puzzles.
const browserAutosave={
 open(){return new Promise((resolve,reject)=>{const request=indexedDB.open('codeword-workbench',1);request.onupgradeneeded=()=>request.result.createObjectStore('autosave');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error||new Error('Browser storage is unavailable.'));});},
 async run(mode,action){const db=await this.open();try{return await new Promise((resolve,reject)=>{const tx=db.transaction('autosave',mode),request=action(tx.objectStore('autosave'));tx.oncomplete=()=>resolve(request.result);tx.onerror=tx.onabort=()=>reject(tx.error||new Error('Browser storage failed.'));});}finally{db.close();}},
 get(){return this.run('readonly',store=>store.get('workspace'));},
 put(value){return this.run('readwrite',store=>store.put(value,'workspace'));}
};
async function readAutosave(){return modeView.autosave==='server'?(await api('/api/autosave')).autosave:(await browserAutosave.get())||null;}
async function writeAutosave(value,unsaved){if(modeView.autosave==='server')return api('/api/autosave',{puzzle:value,unsaved},'PUT');await browserAutosave.put({puzzle:JSON.parse(JSON.stringify(value)),unsaved,savedAt:new Date().toISOString()});}
let savedFingerprint='',autosavedFingerprint=null,autosaveBusy=false,autosaveError='';
function workspaceFingerprint(){return JSON.stringify(puzzle,(key,value)=>key==='image'&&typeof value==='string'?value.length+':'+value.slice(-64):value);}
function hasUnsavedChanges(){return workspaceFingerprint()!==savedFingerprint;}
async function autosaveNow(){
 if(autosavedFingerprint===null||autosaveBusy)return;
 const fingerprint=workspaceFingerprint();if(fingerprint===autosavedFingerprint)return;
 autosaveBusy=true;
 try{await writeAutosave(puzzle,fingerprint!==savedFingerprint);autosavedFingerprint=fingerprint;autosaveError='';}
 catch(error){if(error.message!==autosaveError){autosaveError=error.message;notify('Automatic backup failed: '+error.message+' Save the puzzle to keep your work.',true);}}
 finally{autosaveBusy=false;}
}
async function restoreAutosave(){
 const version=revision,initial=puzzle;
 try{
  const autosave=await readAutosave();
  if(autosave&&puzzle===initial&&version===revision){
   const restored=await restorePuzzle(autosave.puzzle);
   if(puzzle===initial&&version===revision){setPuzzle(restored);if(autosave.unsaved)savedFingerprint='';notify(autosave.unsaved?'Restored your workspace with its unsaved changes. '+(modeView.serverStorage?'Save it to keep it as a named puzzle.':'Use Export JSON to keep a copy.'):'Restored your last workspace.');return true;}
  }
 }catch(error){notify('Could not restore the automatic backup: '+error.message,true);}
 finally{autosavedFingerprint=workspaceFingerprint();setInterval(autosaveNow,1500);}
}
window.addEventListener('beforeunload',event=>{if(hasUnsavedChanges()){event.preventDefault();event.returnValue='';}});
function loadHealth(){if(healthLoaded)return;healthLoaded=true;api('/api/health').then(data=>{ocrAvailable=data.ocrAvailable;$('ocr-status').textContent=ocrAvailable?'Local OCR available. Recognition can make mistakes.':'OCR is unavailable. Manual image transcription is supported.';}).catch(error=>{healthLoaded=false;notify('Could not reach the server: '+error.message,true);});}
async function start(){
 try{applySession(await api('/api/session'));}catch(error){notify('Could not reach the server: '+error.message,true);}
 // Restoring rechecks words against the dictionary, which needs access first.
 if(modeView.mode==='signed-out')await new Promise(resolve=>{afterSignIn=resolve;});
 const restored=await restoreAutosave();
 if(modeView.mode==='guest'&&!restored)notify('Guest mode: your work stays in this browser and is not saved on the server. Use Export JSON to keep a copy'+(session.userLogin?', or switch to User mode.':'.'));
}
setPuzzle(fresh());start();
