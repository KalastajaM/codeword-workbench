'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const S=require('../static/state.js');
const make=(cells,rules={})=>S.canonicalPuzzle({language:'en',rows:1,cols:cells.length,cells,rules:{maxLettersPerNumber:1,uniqueLetters:true,...rules}});
test('Assignment plans fill every occurrence without changing live puzzle before approval; undo restores provenance',()=>{
 const p=make([{number:'1'},{number:'1'},{number:'2',guess:'B'}]),before=JSON.stringify(p);
 const plan=S.numberAssignmentPlan(p,'1','a',0,true);assert.equal(JSON.stringify(p),before);
 assert.deepEqual(plan.trial.cells.map(c=>c.letter),['A','A','']);assert.equal(plan.trial.cells[2].guess,'B');assert.ok(plan.trial.cells[0].prefilled);
 S.undoConfirmation(plan.trial,plan.snapshot);assert.deepEqual(plan.trial.cells.map(c=>[c.letter,c.prefilled]),p.cells.map(c=>[c.letter,c.prefilled]));
});
test('Replacement reports known/provisional conflicts and moves letter ownership, retaining unrelated progress',()=>{
 const p=make([{number:'1',letter:'B'},{number:'1',guess:'C'},{number:'2',letter:'A'},{number:'2',guess:'A'},{number:'3',guess:'D'}]);
 const plan=S.numberAssignmentPlan(p,'1','A',0,true);
 assert.deepEqual(plan.previous,['B','C']);assert.deepEqual(plan.owners,['2']);assert.deepEqual(plan.trial.cells.map(c=>c.letter),['A','A','','','']);assert.equal(plan.trial.cells[3].guess,'');assert.equal(plan.trial.cells[4].guess,'D');
});
test('Ownership may be shared when uniqueness is off and variants explicitly replace the whole target group',()=>{
 const p=make([{number:'1',letter:'B',prefilled:false},{number:'1',letter:'C',prefilled:false},{number:'2',letter:'A',prefilled:false}],{maxLettersPerNumber:2,uniqueLetters:false});
 const plan=S.numberAssignmentPlan(p,'1','A',0,false);assert.deepEqual(plan.owners,[]);assert.deepEqual(plan.trial.cells.map(c=>c.letter),['A','A','A']);assert.equal(plan.trial.cells[0].prefilled,false);
});
test('Puzzle mode protects locked target and owner letters while retaining unchanged prefilled provenance',()=>{
 assert.throws(()=>S.numberAssignmentPlan(make([{number:'1',letter:'B',prefilled:true}]),'1','A',0,false),/prefilled/);
 assert.throws(()=>S.numberAssignmentPlan(make([{number:'1'},{number:'2',letter:'A',prefilled:true}]),'1','A',0,false),/prefilled/);
 const plan=S.numberAssignmentPlan(make([{number:'1',letter:'A',prefilled:true},{number:'1'}]),'1','A',0,false);assert.equal(plan.trial.cells[0].prefilled,true);assert.equal(plan.trial.cells[1].prefilled,false);
});
test('Assignment uses the displayed alternative and preserves its unrelated provisional letters',()=>{
 const p=make([{number:'1'},{number:'1'},{number:'2'},{number:'3'}]);p.suggestions={solutions:[{letters:['C','C','D','E']},{letters:['B','B','A','F']}]};
 const plan=S.numberAssignmentPlan(p,'1','A',1,false);assert.deepEqual(plan.previous,['B']);assert.deepEqual(plan.owners,['2']);assert.equal(plan.trial.cells[2].guess,'');assert.equal(plan.trial.cells[3].guess,'F');
});
// Execute the real lookup event handlers with a small DOM stub and deferred API.
function lookupUI(){
 const vm=require('node:vm'),fs=require('node:fs');const nodes={};const $=id=>nodes[id]??=( {value:'',disabled:false,textContent:'',children:[],replaceChildren(){this.children=[];},append(x){this.children.push(x);},focus(){},click(){return this.onclick();}} );
 const pending=[];const context={$,...{puzzle:{},revision:0},PuzzleState:S,document:{createElement(){return {append(){},textContent:''};}},api:()=>new Promise(resolve=>pending.push(resolve)),protect:fn=>fn,notify(){},currentSelectedWord:()=>null,appendWordEvidence(){}};
 const code=fs.readFileSync(require.resolve('../static/app.js'),'utf8');vm.runInNewContext(code.slice(code.indexOf('let lookupRequest='),code.indexOf("$('use-morphology').onchange")),context);
 return {$,pending,context};
}
test('Lookup Clear releases pending UI immediately and stale completion cannot affect a replacement request',async()=>{
 const {$,pending}=lookupUI();$('lookup-query').value='CAT';const first=$('lookup-run').onclick();assert.equal($('lookup-run').disabled,true);
 $('lookup-clear').onclick();assert.equal($('lookup-query').value,'');assert.equal($('lookup-status').textContent,'');assert.equal($('lookup-run').disabled,false);
 $('lookup-query').value='DOG';const second=$('lookup-run').onclick();pending[0]({kind:'word',word:'CAT'});await first;assert.equal($('lookup-run').disabled,true);assert.equal($('lookup-status').textContent,'Looking up…');
 pending[1]({kind:'word',word:'DOG'});await second;assert.equal($('lookup-run').disabled,false);assert.equal($('lookup-status').textContent,'Word checked.');
});
test('Invalidating lookup releases disabled button and ignores old results',async()=>{
 const {$,pending,context}=lookupUI();$('lookup-query').value='CAT';const first=$('lookup-run').onclick();context.clearLookup();assert.equal($('lookup-run').disabled,false);
 pending[0]({kind:'word',word:'CAT'});await first;assert.equal($('lookup-status').textContent,'');assert.equal($('lookup-results').children.length,0);
});
test('Solve and Cancel share the solver busy state',()=>{
 const vm=require('node:vm'),fs=require('node:fs'),source=fs.readFileSync(require.resolve('../static/app.js'),'utf8');
 const nodes={},$=id=>nodes[id]??={disabled:false,hidden:true,textContent:'',click(){if(!this.disabled)this.onclick?.();}};let calls=0;$('solve').onclick=()=>calls++;
 const busyCode=source.match(/onBusy:busy=>(.*),\n onStopping:/)[1];const notices=[],context={$,stopSearchPrompt:false,noticeIsProgress:false,notify:message=>{notices.push(message);context.noticeIsProgress=false;}};const busy=vm.runInNewContext('(busy=>'+busyCode+')',context);busy(true);
 assert.equal($('solve').disabled,true);assert.equal($('solve').textContent,'Solving…');assert.equal($('cancel-solve').hidden,false);$('solve').click();assert.equal(calls,0);
 busy(false);assert.equal($('solve').textContent,'Solve puzzle →');assert.equal($('cancel-solve').hidden,true);$('solve').click();assert.equal(calls,1);
 assert.deepEqual(notices,[],'a search that ended with its own message adds none');
 busy(true);context.noticeIsProgress=true;busy(false);
 assert.deepEqual(notices,['Search stopped before it finished. Its unfinished results were discarded.'],'progress left in the top message is replaced when a search is abandoned');
});
test('Removing a pair preserves numbers, other variant letters and unrelated hypotheses; undo restores prefills',()=>{
 const p=make([{number:'1',letter:'A',prefilled:true},{number:'1',guess:'A'},{number:'1',letter:'B',prefilled:false},{number:'2',guess:'C'}],{maxLettersPerNumber:2});const before=JSON.stringify(p);
 const plan=S.numberRemovalPlan(p,'1','A',0,true);assert.equal(JSON.stringify(p),before);
 assert.deepEqual(plan.trial.cells.map(c=>c.letter),['','','B','']);assert.deepEqual(plan.trial.cells.map(c=>c.number),['1','1','1','2']);assert.equal(plan.trial.cells[1].guess,'');assert.equal(plan.trial.cells[3].guess,'C');assert.equal(plan.trial.cells[0].prefilled,false);
 S.undoConfirmation(plan.trial,plan.snapshot);assert.equal(plan.trial.cells[0].prefilled,true);assert.equal(plan.trial.cells[0].letter,'A');
});
test('Pair removal protects prefills and removes selected-alternative matches while preserving other displayed letters',()=>{
 assert.throws(()=>S.numberRemovalPlan(make([{number:'1',letter:'A',prefilled:true}]),'1','A',0,false),/prefilled/);
 const p=make([{number:'1'},{number:'1'},{number:'2'}]);p.suggestions={solutions:[{letters:['B','B','C']},{letters:['A','A','D']}]};
 const plan=S.numberRemovalPlan(p,'1','A',1,false);assert.equal(plan.trial.cells[0].guess,'');assert.equal(plan.trial.cells[1].guess,'');assert.equal(plan.trial.cells[2].guess,'D');
});
test('Reverse drag cancellation and stale confirmation never commit a removal',async()=>{
 const vm=require('node:vm'),fs=require('node:fs'),source=fs.readFileSync(require.resolve('../static/app.js'),'utf8');const code=source.slice(source.indexOf('async function removeNumberAssignment('),source.indexOf("$('assign-number-dialog').addEventListener"));
 const p=make([{number:'1',letter:'A',prefilled:false}]),before=JSON.stringify(p);let resolve,current=true;
 const context={puzzle:p,PuzzleState:S,solutionIndex:0,editMode:false,assignmentCurrent:()=>current,confirmAction:()=>new Promise(r=>resolve=r)};vm.runInNewContext(code,context);
 const cancelled=context.removeNumberAssignment({number:'1',letter:'A'});resolve(false);assert.equal(await cancelled,false);assert.equal(JSON.stringify(p),before);
 const stale=context.removeNumberAssignment({number:'1',letter:'A'});current=false;resolve(true);await assert.rejects(stale,/puzzle changed/);assert.equal(JSON.stringify(p),before);
});
function dragUI(){
 const vm=require('node:vm'),fs=require('node:fs'),source=fs.readFileSync(require.resolve('../static/app.js'),'utf8');
 class Node{constructor(){this.children=[];this.classList={add(){},remove(){}};this.attrs={};this.dataset={};this.textContent='';}append(...items){for(const x of items){this.children.push(x);if(typeof x==='object')x.parentElement=this;}}replaceChildren(){this.children=[];}setAttribute(k,v){this.attrs[k]=v;}focus(){}querySelectorAll(){return this.children.flatMap(c=>typeof c==='object'?[c,...c.querySelectorAll()]:[]);}contains(x){return x===this||this.children.some(c=>typeof c==='object'&&c.contains(x));}}
 const nodes={},$=id=>nodes[id]??=new Node();$('unmatched-letters').parentElement=new Node();let accept=true,validations=0;
 const context={$,puzzle:make([{number:'1'},{number:'1'},{number:'2',guess:'B'}]),revision:0,editMode:false,solutionIndex:0,PuzzleState:S,document:{createElement:()=>new Node(),querySelectorAll:()=>[]},protect:fn=>fn,api:async()=>{validations++;return {valid:true};},confirmAction:async()=>accept,solveJob:{cancel(){}},clearCandidateResults(){},clearLookup(){},acceptanceHistory:S.acceptanceHistory(),numericEntry:null,validate(){},render(){context.renderMapping();}};
 context.suggestion=i=>S.suggestedLetter(context.puzzle,i,context.solutionIndex);
 const render=source.slice(source.indexOf('function renderMapping(){'),source.indexOf('function openNumberAssignment('));
 const actions=source.slice(source.indexOf('async function applyNumberAssignment('),source.indexOf("$('assign-number-dialog').addEventListener"));
 const cycles=source.slice(source.indexOf('async function cycleMappingLetter('),source.indexOf("$('reset-suggestions').onclick"));vm.runInNewContext(render+actions+cycles,context);context.renderMapping();
 const event=()=>({preventDefault(){this.prevented=true;},stopPropagation(){},dataTransfer:{setData(){}}});
 return {context,$,event,setAccept(value){accept=value;},get validations(){return validations;}};
}
test('Drag event handlers assign unmatched letters and reverse drop requires confirmation',async()=>{
 const ui=dragUI(),{$,context,event}=ui;const a=$('unmatched-letters').children.find(n=>n.textContent==='A');assert.equal(a.draggable,true);
 a.ondragstart(event());let tile=$('mapping').children[0];const over=event();tile.ondragover(over);assert.equal(over.prevented,true);await tile.ondrop(event());assert.equal(ui.validations,1);assert.deepEqual(context.puzzle.cells.map(c=>c.letter),['A','A','']);
 let assigned=$('mapping').children[0].children[0];assert.equal(assigned.draggable,true);assigned.ondragstart(event());const zone=$('unmatched-letters').parentElement,reverseOver=event();zone.ondragover(reverseOver);assert.equal(reverseOver.prevented,true);
 ui.setAccept(false);await zone.ondrop(event());assert.equal(context.puzzle.cells[0].letter,'A');
 assigned.ondragstart(event());ui.setAccept(true);await zone.ondrop(event());assert.deepEqual(context.puzzle.cells.map(c=>c.letter),['','','']);assert.equal(context.puzzle.cells[2].guess,'B');assert.equal(context.acceptanceHistory.length,2);
});
test('Drop handlers ignore external drags and stale same-workspace drags',async()=>{
 const {$,context,event}=dragUI();let tile=$('mapping').children[0];let over=event();tile.ondragover(over);assert.equal(over.prevented,undefined);await tile.ondrop(event());assert.equal(context.puzzle.cells[0].letter,'');
 $('unmatched-letters').children.find(n=>n.textContent==='A').ondragstart(event());context.revision++;over=event();tile.ondragover(over);assert.equal(over.prevented,undefined);await tile.ondrop(event());assert.equal(context.puzzle.cells[0].letter,'');
});
test('Accessible status Remove unlocks cleared cells and Undo restores their prefilled provenance',()=>{
 const p=make([{number:'1',letter:'A',prefilled:true},{number:'1',guess:'A'},{number:'2',letter:'B',prefilled:true}]);
 const snapshot=S.changeMappingLetter(p,'1','A','remove');assert.equal(p.cells[0].letter,'');assert.equal(p.cells[0].prefilled,false);assert.equal(p.cells[1].guess,'');assert.equal(p.cells[2].prefilled,true);
 S.undoConfirmation(p,snapshot);assert.equal(p.cells[0].letter,'A');assert.equal(p.cells[0].prefilled,true);assert.equal(p.cells[1].guess,'A');assert.equal(p.cells[2].letter,'B');
});
test('Single-letter primary tile supports reverse drag and suppresses the follow-up click',async()=>{
 const {$,context,event}=dragUI();let opens=0;context.openNumberAssignment=()=>opens++;
 const tile=$('mapping').children[1].children[0];assert.equal(tile.draggable,true);tile.ondragstart(event());tile.onclick();assert.equal(opens,0);
 const zone=$('unmatched-letters').parentElement;await zone.ondrop(event());tile.ondragend();tile.onclick();assert.equal(opens,0);assert.equal(context.puzzle.cells[2].guess,'');
});
test('Direct mapping cycle survives singleton/repeated reload and supports Undo at every step',()=>{
 for(const count of [1,3]){
  let p=make(Array.from({length:count},()=>({number:'1',letter:'A',prefilled:false})));
  for(const expected of ['suggested','mapping','confirmed']){
   const previous=S.mappingLetterInfo(p,'1','A').status;
   const plan=S.mappingCyclePlan(p,'1','A',0,false);assert.equal(plan.action,expected);assert.equal(S.mappingLetterInfo(p,'1','A').status,previous);
   p=plan.trial;assert.equal(S.mappingLetterInfo(p,'1','A').status,expected);
   const restored=S.canonicalPuzzle(JSON.parse(JSON.stringify(p)));S.refreshDeductions(restored);assert.equal(S.mappingLetterInfo(restored,'1','A').status,expected);
   const undone=structuredClone(p);S.undoConfirmation(undone,plan.snapshot);assert.equal(S.mappingLetterInfo(undone,'1','A').status,previous);
  }
 }
});
test('Variants skip mapping; prefills require Edit mode and releasing them clears locks',()=>{
 let p=make([{number:'1',letter:'A',prefilled:true},{number:'1',letter:'B',prefilled:false}],{maxLettersPerNumber:2});
 assert.throws(()=>S.mappingCyclePlan(p,'1','A',0,false),/prefilled/);
 p=S.mappingCyclePlan(p,'1','A',0,true).trial;assert.equal(p.cells[0].prefilled,false);assert.equal(S.mappingLetterInfo(p,'1','A').status,'suggested');assert.equal(p.cells[1].letter,'B');
 p=S.mappingCyclePlan(p,'1','A',0,false).trial;assert.equal(S.mappingLetterInfo(p,'1','A').status,'confirmed');assert.equal(p.cells[1].letter,'B');
});
test('Explicit confirmation, manual editing and full reset clear mapping provenance',()=>{
 const initial=()=>S.mappingCyclePlan(make([{number:'1',guess:'A'},{number:'1',guess:'A'}]),'1','A',0,false).trial;
 let p=initial();S.confirmCells(p,[1]);assert.ok(p.cells.every(c=>!c.mappingAnchor));assert.equal(S.mappingLetterInfo(p,'1','A').status,'confirmed');
 p=initial();S.editConfirmedLetter(p,0,'A');assert.ok(p.cells.every(c=>!c.mappingAnchor));
 p=initial();S.resetSuggestions(p);assert.equal(S.mappingLetterInfo(p,'1','A').status,'mapping');assert.equal(p.cells[0].mappingAnchor,true);assert.equal(p.cells[0].letter,'A');assert.equal(p.cells[1].guess,'');assert.equal(S.suggestedLetter(p,1),'A');
 p=initial();S.resetProgress(p);assert.ok(p.cells.every(c=>!c.mappingAnchor));
});
test('Moving between numbers clears the source even with uniqueness off and retains other variant pairs',()=>{
 const p=make([{number:'1',letter:'A',prefilled:false},{number:'1',letter:'B',prefilled:false},{number:'2',guess:'C'},{number:'2'},{number:'3',guess:'D'}],{uniqueLetters:false,maxLettersPerNumber:2});const before=JSON.stringify(p);
 const plan=S.numberMovePlan(p,'1','2','A',0,false);assert.equal(JSON.stringify(p),before);assert.deepEqual(plan.previous,['C']);assert.deepEqual(plan.trial.cells.map(c=>c.letter),['','B','A','A','']);assert.equal(plan.trial.cells[4].guess,'D');
 S.undoConfirmation(plan.trial,plan.snapshot);assert.deepEqual(plan.trial.cells.map(c=>[c.letter,c.guess]),p.cells.map(c=>[c.letter,c.guess]));assert.equal(S.numberMovePlan(p,'1','1','A',0,false),null);
 assert.throws(()=>S.numberMovePlan(make([{number:'1',letter:'A',prefilled:true},{number:'2'}]),'1','2','A',0,false),/prefilled/);
 assert.throws(()=>S.numberMovePlan(make([{number:'1',letter:'A',prefilled:false},{number:'2',letter:'B',prefilled:true}]),'1','2','A',0,false),/prefilled/);
});
test('Actual assigned buttons cycle without dialogs and assigned drops confirm before moving',async()=>{
 const {$,context,event,setAccept}=dragUI();context.puzzle=make([{number:'1',letter:'A',prefilled:false},{number:'1',letter:'A',prefilled:false},{number:'2',guess:'B'}],{uniqueLetters:false});context.renderMapping();
 for(const expected of ['suggested','mapping','confirmed']){await $('mapping').children[0].children[0].onclick();assert.equal(S.mappingLetterInfo(context.puzzle,'1','A').status,expected);}
 let source=$('mapping').children[0].children[0],target=$('mapping').children[1];source.ondragstart(event());setAccept(false);await target.ondrop(event());assert.equal(context.puzzle.cells[0].letter,'A');assert.equal(context.puzzle.cells[2].guess,'B');
 source.ondragstart(event());setAccept(true);await target.ondrop(event());assert.equal(context.puzzle.cells[0].letter,'');assert.equal(context.puzzle.cells[1].letter,'');assert.equal(context.puzzle.cells[2].letter,'A');
});
test('Late validation cannot apply stale cycle or reassignment results',async()=>{
 const {context}=dragUI();context.puzzle=make([{number:'1',letter:'A',prefilled:false},{number:'2'}]);context.renderMapping();
 let resolve;context.api=()=>new Promise(r=>resolve=r);const before=JSON.stringify(context.puzzle);
 const cycle=context.cycleMappingLetter({...context.assignmentContext(),number:'1',letter:'A'});context.solutionIndex++;resolve({valid:true});assert.equal(await cycle,false);assert.equal(JSON.stringify(context.puzzle),before);
 context.solutionIndex=0;const move=context.moveNumberAssignment({...context.assignmentContext(),number:'1',letter:'A'},'2');await Promise.resolve();context.revision++;resolve({valid:true});assert.equal(await move,false);assert.equal(JSON.stringify(context.puzzle),before);
});
test('Assignment status chooses pencil marks or one mapped anchor without creating prefilled clues',()=>{
 for(const status of ['confirmed','suggested','mapping']){
  const p=make([{number:'1'},{number:'1'},{number:'2',guess:'B'}]);const plan=S.numberAssignmentPlan(p,'1','A',0,true,status);
  assert.equal(S.mappingLetterInfo(plan.trial,'1','A').status,status);assert.equal(plan.trial.cells[2].guess,'B');
  if(status==='suggested'){assert.deepEqual(plan.trial.cells.slice(0,2).map(c=>c.letter),['','']);assert.deepEqual(plan.trial.cells.slice(0,2).map(c=>c.guess),['A','A']);}
  if(status==='mapping'){assert.equal(plan.trial.cells.filter(c=>c.letter==='A').length,1);assert.equal(plan.trial.cells.filter(c=>c.mappingAnchor).length,1);assert.equal(S.suggestedLetter(plan.trial,1),'A');}
  if(status!=='confirmed')assert.ok(plan.trial.cells.every(c=>!c.prefilled));
  S.undoConfirmation(plan.trial,plan.snapshot);assert.deepEqual(plan.trial.cells,p.cells);
 }
});
test('Assignment status keeps ownership warnings and protects locked same-letter clues from release',()=>{
 const p=make([{number:'1',guess:'B'},{number:'2',letter:'A',prefilled:false}]);const plan=S.numberAssignmentPlan(p,'1','A',0,false,'suggested');assert.deepEqual(plan.previous,['B']);assert.deepEqual(plan.owners,['2']);assert.equal(plan.trial.cells[1].letter,'');assert.equal(plan.trial.cells[0].guess,'A');
 for(const status of ['suggested','mapping'])assert.throws(()=>S.numberAssignmentPlan(make([{number:'1',letter:'A',prefilled:true}]),'1','A',0,false,status),/prefilled/);
 assert.throws(()=>S.numberAssignmentPlan(make([{number:'1'}],{maxLettersPerNumber:2}),'1','A',0,true,'mapping'),/one letter per number/);
});
test('Delete and Backspace on assigned mapping buttons prevent default and honor removal confirmation',async()=>{
 for(const key of ['Delete','Backspace']){
  const ui=dragUI(),{$,context}=ui;let stopped=false,prevented=false;ui.setAccept(false);
  const button=$('mapping').children[1].children[0];await button.onkeydown({key,preventDefault(){prevented=true;},stopPropagation(){stopped=true;}});
  assert.equal(prevented,true);assert.equal(stopped,true);assert.equal(context.puzzle.cells[2].guess,'B');
  ui.setAccept(true);await button.onkeydown({key,preventDefault(){},stopPropagation(){}});assert.equal(context.puzzle.cells[2].guess,'');
 }
});
test('App assignment applies selected status and stale approval cannot commit it',async()=>{
 const ui=dragUI(),{context}=ui;await context.applyNumberAssignment({...context.assignmentContext(),number:'1'},'A','suggested');assert.equal(S.mappingLetterInfo(context.puzzle,'1','A').status,'suggested');assert.ok(context.puzzle.cells.every(c=>!c.prefilled));
 let resolve;context.confirmAction=()=>new Promise(r=>resolve=r);const before=JSON.stringify(context.puzzle);
 const pending=context.applyNumberAssignment({...context.assignmentContext(),number:'1'},'B','mapping');context.revision++;resolve(true);await assert.rejects(pending,/puzzle changed/);assert.equal(JSON.stringify(context.puzzle),before);
});
test('Capacity UI rejects out-of-range edits without changing rules or legacy values; hidden uniqueness persists',()=>{
 const fs=require('node:fs'),vm=require('node:vm'),source=fs.readFileSync(require.resolve('../static/app.js'),'utf8');
 const nodes={capacity:{value:'1'},forbidden:{value:''},discouraged:{value:''}};let changes=0,notices=0;const context={$:id=>{assert.notEqual(id,'unique');return nodes[id];},puzzle:{cells:[{mappingAnchor:true}],rules:{maxLettersPerNumber:1,uniqueLetters:false}},normalize:s=>s.toUpperCase(),notify(){notices++;},invalidate(){changes++;},render(){}};
 vm.runInNewContext(source.slice(source.indexOf('function updateRules('),source.indexOf("$('edit-tool').onclick")),context);
 for(const value of ['0','10','1.5','']){nodes.capacity.value=value;nodes.capacity.onchange({target:nodes.capacity});assert.equal(context.puzzle.rules.maxLettersPerNumber,1);assert.equal(nodes.capacity.value,1);assert.equal(context.puzzle.cells[0].mappingAnchor,true);}
 assert.equal(changes,0);assert.equal(notices,4);nodes.capacity.value='9';nodes.capacity.onchange({target:nodes.capacity});assert.equal(context.puzzle.rules.maxLettersPerNumber,9);assert.equal(context.puzzle.rules.uniqueLetters,false);
 context.puzzle.rules.maxLettersPerNumber=29;nodes.capacity.value='29';nodes.forbidden.value='aa';nodes.forbidden.onchange({target:nodes.forbidden});assert.equal(context.puzzle.rules.maxLettersPerNumber,29);assert.equal(context.puzzle.rules.uniqueLetters,false);assert.equal(context.puzzle.rules.forbiddenPatterns[0],'AA');
});
