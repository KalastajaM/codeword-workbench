'use strict';
const assert = require('node:assert/strict');
const {canonicalPuzzle, slots, candidateLetters, matchesSlot} = require('../static/state.js');
const test = require('node:test');
test('Normalize and restore candidates without corrupting fixed cells or fragments', () => {
const puzzle = canonicalPuzzle({rows:1, cols:2, language:'fi', cells:[{letter:' a\u0308 ',number:'1'},{letter:'',number:'2'}]});
assert.equal(puzzle.cells[0].letter, 'Ä', 'Known letters normalize NFC, whitespace and case');
assert.deepEqual(candidateLetters(puzzle,{letters:['ä','n']}), ['Ä','N']);
assert.equal(candidateLetters(puzzle,{letters:['a','n']}), null, 'Restoration must preserve fixed letters');
assert.equal(candidateLetters(puzzle,{letters:['ä','NO']}), null, 'Every cell holds one letter');
assert.equal(candidateLetters(puzzle,{letters:['ä']}), null, 'Candidate dimensions must match');
assert.equal(candidateLetters(puzzle,{letters:['ä',3]}), null, 'Malformed candidate letters rejected');
assert.equal(slots(puzzle).length, 1);
assert.equal(matchesSlot('AT',{before:false,after:true},'ATE'), true);
assert.equal(matchesSlot('AT',{before:true,after:false},'ATE'), false);
assert.equal(matchesSlot('AT',{before:true,after:true},'CATS'), true);
assert.equal(matchesSlot('AT',{before:false,after:false},'CATS'), false);
const blackPuzzle=canonicalPuzzle({rows:1,cols:3,language:'en',cells:[{letter:'A'},{black:true,letter:'X',number:'9'},{letter:'B'}]});
assert.equal(blackPuzzle.cells[1].letter,'');
assert.equal(blackPuzzle.cells[1].number,'');
assert.equal(slots(blackPuzzle).length,0,'Black cells split slots');
assert.equal(candidateLetters(blackPuzzle,{letters:['A','X','B']}),null,'Black cells cannot gain letters');
});
test('New cells have no open boundaries and numeric entry replaces, appends and resets', () => {
 const {blankCell,numberEntry}=require('../static/state.js');
 assert.deepEqual(blankCell(),{black:false,number:'',letter:'',openBeforeAcross:false,openAfterAcross:false,openBeforeDown:false,openAfterDown:false});
 let entry=numberEntry(null,4,'2',1000);
 assert.equal(entry.digits,'2');
 entry=numberEntry(entry,4,'9',1200);assert.equal(entry.digits,'29');
 assert.equal(numberEntry(entry,4,'0',1250).digits,'29','Numbers cannot exceed two digits');
 entry=numberEntry(entry,4,'Backspace',1400);assert.equal(entry.digits,'2');
 assert.equal(numberEntry(entry,5,'1',1450).digits,'1','Changing cell starts a new number');
 assert.equal(numberEntry(entry,4,'1',2500).digits,'1','Pause starts replacement');
 assert.equal(numberEntry(entry,4,'Backspace',2500),null,'Backspace outside numeric entry clears a letter instead');
 assert.equal(numberEntry(null,4,'0',1000),null,'Numbers cannot start with zero');
});
test('Image clue and answer shading survive canonical save/open state',()=>{
 const puzzle=canonicalPuzzle({rows:1,cols:2,cells:[{black:true,clue:true,number:'3',letter:'Z'},{highlight:true,number:'4',letter:''}]});
 assert.equal(puzzle.cells[0].clue,true);assert.equal(puzzle.cells[0].black,true);assert.equal(puzzle.cells[0].letter,'');assert.equal(puzzle.cells[0].number,'');assert.equal(puzzle.cells[1].highlight,true);
});
test('Image alignment accepts a complete draft without changing applied bounds on invalid steps',()=>{
 const {imageBoundsFromPercent}=require('../static/state.js');
 let applied={x:0,y:0,width:1,height:1};
 const draft={x:'10',y:'0',width:'100',height:'100'};
 assert.throws(()=>{applied=imageBoundsFromPercent(draft);},/100%/);
 assert.deepEqual(applied,{x:0,y:0,width:1,height:1});
 assert.equal(draft.x,'10','Invalid application keeps typed values for correction');
 draft.width='80';draft.y='15';draft.height='70';
 applied=imageBoundsFromPercent(draft);
 assert.deepEqual(applied,{x:.1,y:.15,width:.8,height:.7});
 assert.throws(()=>imageBoundsFromPercent({...draft,x:''}),/all four/);
 assert.throws(()=>imageBoundsFromPercent({...draft,width:'0'}),/greater than zero/);
 assert.throws(()=>imageBoundsFromPercent({...draft,x:'-1'}),/zero or greater/);
 assert.throws(()=>imageBoundsFromPercent({...draft,y:'35'}),/100%/);
});
test('Fit view constrains both dimensions without modifying image alignment',()=>{
 const {fitScale}=require('../static/state.js');
 assert.equal(fitScale(1000,1500,600,600),.4);
 assert.equal(fitScale(1500,500,600,600),.4);
 assert.equal(fitScale(300,300,600,600),2);
});
test('Mapping deductions take precedence over alternatives and saved guesses',()=>{
 const {suggestedLetter}=require('../static/state.js');
 const puzzle={cells:[{letter:'A'},{letter:''},{black:true}],suggestions:{solutions:[],forcedLetters:['A','B','C']}};
 assert.equal(suggestedLetter(puzzle,1),'B');assert.equal(suggestedLetter(puzzle,2),'');
 puzzle.suggestions.solutions=[{letters:['A','D','']}];
 assert.equal(suggestedLetter(puzzle,1),'B');
 assert.equal(puzzle.cells[1].letter,'','Rendering does not silently confirm deductions');
 delete puzzle.suggestions;assert.equal(suggestedLetter(puzzle,1),'');
});
test('Saved mapping deductions can be recomputed from confirmed cells without trusting imported suggestions',()=>{
 const {mappingDeductions}=require('../static/state.js');
 const puzzle={rules:{maxLettersPerNumber:1},cells:[{number:'1',letter:'A'},{number:'1',letter:''},{number:'2',letter:''},{black:true,number:'1',letter:''}],suggestions:{forcedLetters:['Z','Z','Z','Z']}};
 assert.deepEqual(mappingDeductions(puzzle),['A','A','','']);
 puzzle.rules.maxLettersPerNumber=4;assert.deepEqual(mappingDeductions(puzzle),['A','','','']);
});
test('Solve feedback distinguishes conflicts, missing dictionary and exhausted search budget',()=>{
 const {solveSummary}=require('../static/state.js');
 assert.match(solveSummary('conflict',0,0),/Conflicting constraints/);
 assert.match(solveSummary('empty_dictionary',0,4),/dictionary is empty/);
 assert.match(solveSummary('empty_dictionary',0,4),/4 mapping deductions remain provisional/);
 assert.match(solveSummary('budget_exhausted',0,0),/time or work limit/);
 assert.match(solveSummary('budget_exhausted',2,1),/2 full suggestions/);
 assert.match(solveSummary('no_solution',0,0),/No full suggestion found within this search/);
});
test('Drawn grid fit accounts for every scaled cell, gap and border',()=>{
 const {fitScale}=require('../static/state.js');
 const cols=40,rows=30,width=cols*46+(cols-1)+4,height=rows*46+(rows-1)+4;
 const scale=fitScale(width,height,400,300);
 assert.ok((cols*46+(cols-1)+4)*scale<=400);
 assert.ok((rows*46+(rows-1)+4)*scale<=300);
});
test('Unconfirm a manual letter preserves a normalized provisional guess across save/open',()=>{
 const {unconfirmCells,suggestedLetter,confirmCells}=require('../static/state.js');
 const puzzle=canonicalPuzzle({rows:1,cols:1,language:'fi',cells:[{letter:'ä',number:'1'}]});
 assert.equal(unconfirmCells(puzzle,[0]),true);
 assert.equal(puzzle.cells[0].letter,'');assert.equal(puzzle.cells[0].guess,'Ä');assert.equal(suggestedLetter(puzzle,0),'Ä');
 const reopened=canonicalPuzzle(JSON.parse(JSON.stringify(puzzle)));
 assert.equal(reopened.cells[0].guess,'Ä');assert.equal(reopened.cells[0].letter,'');
 assert.ok(confirmCells(reopened,[0]));assert.equal(reopened.cells[0].letter,'Ä');assert.equal(reopened.cells[0].guess,'');
});
test('Unconfirm number group removes fixed mapping but preserves each provisional letter including variants',()=>{
 const {unconfirmCells,numberCells,suggestedLetter,refreshDeductions}=require('../static/state.js');
 const puzzle=canonicalPuzzle({rows:1,cols:4,cells:[{number:'1',letter:'A'},{number:'1',letter:'A'},{number:'1',letter:''},{number:'2',letter:'B'}]});
 refreshDeductions(puzzle);assert.equal(suggestedLetter(puzzle,2),'A');
 unconfirmCells(puzzle,[0]);assert.equal(suggestedLetter(puzzle,0),'A','Other confirmed occurrence still forces A');
 unconfirmCells(puzzle,numberCells(puzzle,0));assert.equal(suggestedLetter(puzzle,2),'','Revoked deduction cannot remain fixed or stale');
 assert.equal(puzzle.cells[0].guess,'A');assert.equal(puzzle.cells[1].guess,'A');assert.equal(puzzle.cells[3].letter,'B');
 const variant=canonicalPuzzle({rows:1,cols:3,rules:{maxLettersPerNumber:4},cells:[{number:'1',letter:'A'},{number:'1',letter:'B'},{number:'1'}]});
 unconfirmCells(variant,numberCells(variant,0));assert.deepEqual(variant.cells.map(c=>c.letter),['','','']);
 assert.equal(suggestedLetter(variant,0),'A');assert.equal(suggestedLetter(variant,1),'B');assert.equal(suggestedLetter(variant,2),'');
});
test('Undo confirmation restores filtered alternatives and guesses but preserves unrelated metadata',()=>{
 const {confirmCells,undoConfirmation,acceptanceHistory}=require('../static/state.js');
 const puzzle=canonicalPuzzle({name:'Before',rows:1,cols:2,cells:[{guess:'A'},{guess:'B'}],suggestions:{solutions:[{letters:['A','B']},{letters:['C','D']}],stats:{exhaustive:true}}});
 const history=acceptanceHistory();history.push(confirmCells(puzzle,[0,1],0));
 assert.deepEqual(puzzle.cells.map(c=>c.letter),['A','B']);assert.equal(puzzle.suggestions.solutions.length,1);
 puzzle.name='Renamed';undoConfirmation(puzzle,history.pop());
 assert.equal(puzzle.name,'Renamed');assert.deepEqual(puzzle.cells.map(c=>c.letter),['','']);assert.deepEqual(puzzle.cells.map(c=>c.guess),['A','B']);assert.equal(puzzle.suggestions.solutions.length,2);
 history.push(confirmCells(puzzle,[0]));history.clear();puzzle.cells[0].letter='X';
 assert.equal(undoConfirmation(puzzle,history.pop()),false);assert.equal(puzzle.cells[0].letter,'X','Cleared history never reverts a later edit');
});
test('Unconfirm retains compatible alternatives without claiming an exhaustive search',()=>{
 const {unconfirmCells}=require('../static/state.js');
 const puzzle=canonicalPuzzle({rows:1,cols:2,cells:[{letter:'A'},{letter:'B'}],suggestions:{solutions:[{letters:['A','B']}],forcedLetters:['A','B'],stats:{exhaustive:true}}});
 unconfirmCells(puzzle,[0,1]);assert.equal(puzzle.suggestions.solutions.length,1);assert.equal(puzzle.suggestions.stats.exhaustive,false);assert.deepEqual(puzzle.suggestions.forcedLetters,['','']);
});
test('Fit width and Fit height constrain only the chosen dimension',()=>{
 const {fitScale}=require('../static/state.js');
 assert.equal(fitScale(1000,2000,500,600,'width'),.5);
 assert.equal(fitScale(1000,2000,500,600,'height'),.3);
 assert.equal(fitScale(2000,1000,500,600,'height'),.6);
 assert.equal(fitScale(2000,1000,500,600,'puzzle'),.25);
});
test('Word candidate table uses solver slot order, coordinates and displayed patterns',()=>{
 const {wordChoices}=require('../static/state.js');
 const puzzle=canonicalPuzzle({rows:2,cols:3,cells:[{letter:'A'},{black:true},{guess:'C'},{letter:'D',openBeforeAcross:true},{guess:'E'},{letter:'F'}]});
 const words=wordChoices(puzzle);
 assert.deepEqual(words.map(w=>({id:w.slotId,cells:w.cells,direction:w.direction,row:w.row,col:w.col,pattern:w.pattern})),[
  {id:0,cells:[3,4,5],direction:'Across',row:2,col:1,pattern:'…DEF'},
  {id:1,cells:[0,3],direction:'Down',row:1,col:1,pattern:'AD'},
  {id:2,cells:[2,5],direction:'Down',row:1,col:3,pattern:'CF'}
 ]);
});
test('Word table distinguishes vertical one-column slots and limits selection to eight existing words',()=>{
 const {wordChoices,candidateSelection}=require('../static/state.js');
 const narrow=canonicalPuzzle({rows:3,cols:1,cells:[{},{},{}]});
 assert.equal(wordChoices(narrow)[0].direction,'Down');
 const puzzle=canonicalPuzzle({rows:5,cols:5,cells:Array.from({length:25},()=>({}))});
 const choices=wordChoices(puzzle),keys=new Set(choices.map(w=>w.key));keys.add('Across:invalid');
 assert.equal(candidateSelection(choices,keys).length,8);
 assert.deepEqual(candidateSelection(choices,new Set([choices[7].key,choices[2].key])),[2,7]);
});
test('Selected-word search uses displayed letters without confirming or constraining unrelated guesses',()=>{
 const {wordChoices,candidateSearchPuzzle}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:7,cells:[{letter:'A'},{},{guess:'I'},{black:true},{guess:'Z'},{letter:'E'},{}],suggestions:{forcedLetters:['A','Ä','','','','E',''],solutions:[{letters:['A','X','','','Q','E','R']},{letters:['A','Y','Ö','','S','E','T']}]}});
 const before=JSON.stringify(p);
 assert.equal(wordChoices(p,1)[0].pattern,'AÄÖ');
 assert.equal(wordChoices(p,1)[0].provisionalCount,2);
 const request=candidateSearchPuzzle(p,[0],1);
 assert.deepEqual(request.cells.map(c=>c.letter),['A','Ä','Ö','','','E','']);
 assert.equal(JSON.stringify(p),before);
 assert.equal(p.cells[1].letter,'');
 assert.equal(candidateSearchPuzzle(p,[0],0).cells[2].letter,'I');
});

test('Solve preferences have backward-compatible defaults and survive save/open',()=>{
 const p=canonicalPuzzle({rows:1,cols:1,cells:[{}]});
 assert.equal(p.searchMode,'quick');assert.equal(p.allowUnknownWords,true);assert.equal(p.useMorphology,true);
 const changed=canonicalPuzzle({...p,searchMode:'deep',allowUnknownWords:true,useMorphology:false});
 assert.equal(changed.searchMode,'deep');assert.equal(changed.allowUnknownWords,true);assert.equal(changed.useMorphology,false);
});
test('Restored evidence trusts only current dictionary matches, preserving other hypotheses as unverified',()=>{
 const {restoredWords,wordEvidenceLabel}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:3,cells:[{},{},{}]});
 const words=restoredWords(p,['C','A','T'],['CAT']);
 assert.equal(words[0].source,'dictionary');assert.equal(words[0].verified,true);
 const unknown=restoredWords(p,['C','A','T'],[])[0];
 assert.equal(unknown.verified,false);assert.equal(wordEvidenceLabel(unknown),'Unverified');
 assert.equal(wordEvidenceLabel({source:'morphology',verified:true}),'Morphology match');
 p.cells[0].openBeforeAcross=true;
 assert.equal(restoredWords(p,['C','A','T'],['BOBCAT'])[0].source,'fragment');
});
test('Cancelling before job creation returns cancels the eventual backend job without showing its result',async()=>{
 const {solveRunner}=require('../static/state.js');let release;const calls=[],updates=[];
 const runner=solveRunner({request:async(path,body,method)=>{calls.push([path,method]);if(method==='POST')return new Promise(r=>release=r);return {status:'cancelled'};},onUpdate:value=>updates.push(value)});
 const pending=runner.start({});runner.cancel();release({id:'old',status:'running'});await pending;
 assert.deepEqual(calls,[['/api/solve-jobs','POST'],['/api/solve-jobs/old','DELETE']]);assert.deepEqual(updates,[]);
});
test('Replacing a running solve ignores its late poll and leaves the newer solve active',async()=>{
 const {solveRunner}=require('../static/state.js');let releasePoll;let posts=0;const updates=[],deleted=[];
 const runner=solveRunner({delay:async()=>{},request:async(path,body,method)=>{if(method==='POST')return {id:String(++posts),status:posts===1?'running':'completed',...(posts===1?{}:{result:{status:'new'}})};if(method==='DELETE'){deleted.push(path);return {status:'cancelled'};}return new Promise(r=>releasePoll=r);},onUpdate:value=>updates.push(value)});
 const old=runner.start({});await new Promise(setImmediate);await runner.start({});releasePoll({status:'completed',result:{status:'old'}});await old;
 assert.deepEqual(updates.filter(x=>x.result).map(x=>x.result.status),['new']);assert.deepEqual(deleted,['/api/solve-jobs/1']);
});
test('Poll failures stop the backend job and clear busy state',async()=>{
 const {solveRunner}=require('../static/state.js');const errors=[],busy=[],deleted=[];
 const runner=solveRunner({delay:async()=>{},request:async(path,body,method)=>{if(method==='POST')return {id:'job',status:'running'};if(method==='DELETE'){deleted.push(path);return {};}throw Error('Offline');},onError:error=>errors.push(error.message),onBusy:value=>busy.push(value)});
 await runner.start({});assert.deepEqual(errors,['Offline']);assert.deepEqual(busy,[true,false]);assert.deepEqual(deleted,['/api/solve-jobs/job']);
});
test('Partial solver letters remain provisional and yield to a complete alternative',()=>{
 const {suggestedLetter}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:2,cells:[{},{}],suggestions:{partialLetters:['A',''],solutions:[]}});
 assert.equal(suggestedLetter(p,0),'A');assert.equal(p.cells[0].letter,'');
 p.suggestions.solutions=[{letters:['B','C']}];assert.equal(suggestedLetter(p,0),'B');
});
test('Confirming a guess outside a partial hypothesis clears globally stale partial letters',()=>{
 const {confirmCells,suggestedLetter,undoConfirmation}=require('../static/state.js');
 for(const rules of [{uniqueLetters:true},{uniqueLetters:false,maxLettersPerNumber:1},{uniqueLetters:false,forbiddenPatterns:['AA']}]){
  const p=canonicalPuzzle({rows:1,cols:2,rules,cells:[{number:'1'},{number:rules.maxLettersPerNumber?'1':'2',guess:rules.maxLettersPerNumber?'B':'A'}],suggestions:{partialLetters:['A',''],solutions:[]}});
  const snapshot=confirmCells(p,[1]);
  assert.equal(p.suggestions.partialLetters,undefined);
  if(rules.uniqueLetters===true)assert.equal(suggestedLetter(p,0),'');
  undoConfirmation(p,snapshot);assert.deepEqual(p.suggestions.partialLetters,['A','']);
 }
});
test('Confirming a letter already supported by the partial hypothesis retains its remaining letters',()=>{
 const {confirmCells}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:2,cells:[{number:'1'},{number:'2'}],suggestions:{partialLetters:['A','B'],solutions:[]}});
 confirmCells(p,[1]);assert.deepEqual(p.suggestions.partialLetters,['A','B']);
});
test('Inspector labels the displayed source when a partial suggestion overrides a pencil mark',()=>{
 const {suggestionLabel}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:1,cells:[{guess:'B'}],suggestions:{partialLetters:['A'],solutions:[]}});
 assert.equal(suggestionLabel(p,0),'Partial suggestion');
 p.suggestions.solutions=[{letters:['C']}];assert.equal(suggestionLabel(p,0),'Suggested');
 p.suggestions.forcedLetters=['D'];assert.equal(suggestionLabel(p,0),'Mapping deduction');
 delete p.suggestions;assert.equal(suggestionLabel(p,0),'Unconfirmed letter');
});

test('Mapping status changes confirm, release and remove a pair without reviving deductions',()=>{
 const {changeMappingLetter,mappingLetterInfo,refreshDeductions,suggestedLetter,undoConfirmation}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:4,cells:[{number:'1',letter:'A'},{number:'1'},{number:'1'},{number:'2',letter:'B'}]});
 refreshDeductions(p);const before=JSON.parse(JSON.stringify(p));
 assert.deepEqual(mappingLetterInfo(p,'1','A'),{indices:[0,1,2],status:'confirmed'});
 const snapshot=changeMappingLetter(p,'1','A','confirmed');
 assert.deepEqual(p.cells.map(c=>c.letter),['A','A','A','B']);
 changeMappingLetter(p,'1','A','suggested');
 assert.deepEqual(p.cells.map(c=>c.letter),['','','','B']);
 assert.deepEqual(p.cells.slice(0,3).map(c=>c.guess),['A','A','A']);
 assert.equal(mappingLetterInfo(p,'1','A').status,'suggested');
 changeMappingLetter(p,'1','A','remove');
 assert.deepEqual(p.cells.slice(0,3).map((c,i)=>suggestedLetter(p,i)),['','','']);
 assert.equal(mappingLetterInfo(p,'1','A').status,'empty');
 undoConfirmation(p,snapshot);assert.deepEqual(p,before);
});
test('Mapping action keeps one confirmed anchor and automatic deductions',()=>{
 const {changeMappingLetter,suggestedLetter}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:3,cells:[{number:'1',guess:'A'},{number:'1'},{number:'1'}]});
 changeMappingLetter(p,'1','A','mapping');
 assert.deepEqual(p.cells.map(c=>c.letter),['A','','']);
 assert.deepEqual(p.cells.map((c,i)=>c.letter||suggestedLetter(p,i)),['A','A','A']);
 assert.deepEqual(p.cells.map(c=>c.guess),['','','']);
});
test('Pair edits isolate variant letters and leave black and confirmed numberless cells unchanged',()=>{
 const {changeMappingLetter}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:5,rules:{maxLettersPerNumber:2},cells:[{number:'1',letter:'A'},{number:'1',letter:'B'},{number:'1',guess:'B'},{black:true},{letter:'C'}]});
 const unrelated=JSON.parse(JSON.stringify(p.cells.slice(1)));
 changeMappingLetter(p,'1','A','suggested');assert.equal(p.cells[0].guess,'A');
 assert.deepEqual(p.cells.slice(1),unrelated);
 changeMappingLetter(p,'1','A','remove');assert.equal(p.cells[0].guess,'');assert.deepEqual(p.cells.slice(1),unrelated);
});
test('Mapping edits use the displayed alternative and undo restores all alternatives and hypotheses',()=>{
 const {changeMappingLetter,undoConfirmation}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:3,cells:[{number:'1'},{number:'2',guess:'X'},{}],suggestions:{solutions:[{letters:['A','B','C']},{letters:['D','E','F']}],partialLetters:['G','H','I']}});
 const before=JSON.parse(JSON.stringify(p));const snapshot=changeMappingLetter(p,'1','D','suggested',1);
 assert.deepEqual(p.cells.map(c=>c.guess),['D','E','F']);assert.equal(p.suggestions,undefined);
 assert.equal(snapshot.solutionIndex,1);undoConfirmation(p,snapshot);assert.deepEqual(p,before);
});
test('Invalid mapping actions and nonexistent pairs fail before changing state',()=>{
 const {changeMappingLetter}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:2,rules:{maxLettersPerNumber:2},cells:[{number:'1',letter:'A'},{number:'1',letter:'B'}]});
 for(const [number,letter,action]of [['1','A','unknown'],['1','C','confirmed'],['2','A','remove'],['1','A','mapping']]){
  const before=JSON.stringify(p);assert.throws(()=>changeMappingLetter(p,number,letter,action));assert.equal(JSON.stringify(p),before);
 }
});
test('Reset progress preserves puzzle structure, image, identity and settings',()=>{
 const {resetProgress}=require('../static/state.js');
 const p=canonicalPuzzle({id:'saved',name:'Example',rows:1,cols:3,image:'data:image/png;base64,test',imageBounds:{x:.1,y:.2,width:.5,height:.5},language:'fi',useMorphology:false,searchMode:'deep',allowUnknownWords:true,rules:{maxLettersPerNumber:2},cells:[{number:'2',letter:'Ä',highlight:true},{number:'3',guess:'Ö',openBeforeAcross:true},{black:true,clue:true}],suggestions:{forcedLetters:['Ä','Ö',''],solutions:[{letters:['Ä','Ö','']}]}});
 const expected=JSON.parse(JSON.stringify(p));delete expected.suggestions;expected.cells.forEach(c=>{c.letter='';c.guess='';});
 resetProgress(p);assert.deepEqual(p,expected);
});

test('Confirm and mapping never overwrite a different confirmed letter in a conflicted standard group',()=>{
 const {changeMappingLetter,mappingLetterInfo}=require('../static/state.js');
 for(const action of ['confirmed','mapping']){
  const p=canonicalPuzzle({rows:1,cols:3,cells:[{number:'1',guess:'A'},{number:'1',letter:'B'},{number:'1'}]});
  changeMappingLetter(p,'1','A',action);assert.equal(p.cells[1].letter,'B');
 }
 const deduction=canonicalPuzzle({rows:1,cols:1,cells:[{number:'1'}],suggestions:{forcedLetters:['A']}});
 assert.equal(mappingLetterInfo(deduction,'1','A').status,'mapping');
});

test('Extended search persists through a canonical JSON round trip',()=>{
 const p=canonicalPuzzle({rows:1,cols:1,cells:[{}],searchMode:'extended'});
 assert.equal(canonicalPuzzle(JSON.parse(JSON.stringify(p))).searchMode,'extended');
});
test('Stop summaries distinguish exact limits and explain pruning without claiming impossibility',()=>{
 const {solveSummary}=require('../static/state.js');
 for(const [reason,text]of [['time_limit',/time limit/],['node_limit',/node limit/],['solution_limit',/solution limit/],['search_exhausted',/explored/],['cancelled',/cancelled/],['invalid_constraints',/Conflicting constraints/],['no_candidates',/candidate/],['empty_dictionary',/dictionary is empty/]]){
  assert.match(solveSummary('solutions_found',2,0,{stopReason:reason}),text);
 }
 const pruned=solveSummary('solutions_found',2,0,{stopReason:'search_exhausted',limitsReached:['candidate_limit','memory_limit']});
 assert.match(pruned,/Candidate lists were limited/);assert.match(pruned,/memory limit/);assert.match(pruned,/not exhaustive/);
});
test('User cancellation before POST returns still receives the best result and sends DELETE once',async()=>{
 const {solveRunner}=require('../static/state.js');let release;const calls=[],updates=[],busy=[];
 const runner=solveRunner({delay:async()=>{},request:async(path,body,method)=>{calls.push(method||'GET');if(method==='POST')return new Promise(r=>release=r);if(method==='DELETE')return {status:'running'};return {status:'cancelled',result:{solutions:[{letters:['A']}]}};},onUpdate:value=>updates.push(value),onBusy:value=>busy.push(value)});
 const pending=runner.start({});runner.requestCancel();runner.requestCancel();release({id:'early',status:'running'});await pending;
 assert.deepEqual(calls,['POST','DELETE','GET']);assert.equal(updates.at(-1).result.solutions[0].letters[0],'A');assert.deepEqual(busy,[true,false]);
});
test('Editing after user cancellation discards the late best result',async()=>{
 const {solveRunner}=require('../static/state.js');let releasePoll;const updates=[],deleted=[];
 const runner=solveRunner({delay:async()=>{},request:async(path,body,method)=>{if(method==='POST')return {id:'old',status:'running'};if(method==='DELETE'){deleted.push(path);return {status:'running'};}return new Promise(r=>releasePoll=r);},onUpdate:value=>updates.push(value)});
 const pending=runner.start({});await new Promise(setImmediate);runner.requestCancel();runner.cancel();releasePoll({status:'cancelled',result:{solutions:[{letters:['A']}]}});await pending;
 assert.equal(updates.some(value=>value.result),false);assert.deepEqual(deleted,['/api/solve-jobs/old']);
});
test('A cancelled result is useful only when it contributes provisional progress',()=>{
 const {hasSolveProgress}=require('../static/state.js');const p=canonicalPuzzle({rows:1,cols:2,cells:[{letter:'A'},{}]});
 assert.equal(hasSolveProgress(p,{solutions:[],forcedLetters:['A',''],partialLetters:['A','']}),false);
 assert.equal(hasSolveProgress(p,{partialLetters:['A','B']}),true);
 assert.equal(hasSolveProgress(p,{forcedLetters:['A','B']}),true);
 assert.equal(hasSolveProgress(p,{solutions:[{letters:['A','B']}]}),true);
});
test('A failed user cancellation permits retry while polling stays active',async()=>{
 const {solveRunner}=require('../static/state.js');let releasePoll,attempts=0;const errors=[],updates=[],stopping=[];
 const runner=solveRunner({delay:async()=>{},request:async(path,body,method)=>{if(method==='POST')return {id:'retry',status:'running'};if(method==='DELETE'){if(++attempts===1)throw Error('Connection interrupted');return {status:'running'};}return new Promise(r=>releasePoll=r);},onUpdate:value=>updates.push(value),onCancelError:error=>errors.push(error.message),onStopping:value=>stopping.push(value)});
 const pending=runner.start({});await new Promise(setImmediate);runner.requestCancel();await new Promise(setImmediate);runner.requestCancel();releasePoll({status:'cancelled',result:{solutions:[],partialLetters:['A']}});await pending;
 assert.equal(attempts,2);assert.deepEqual(errors,['Connection interrupted']);assert.deepEqual(stopping,[true,false,true]);assert.equal(updates.at(-1).status,'cancelled');
});
test('Replacing a user-cancelled job ignores its late result without cancelling the replacement',async()=>{
 const {solveRunner}=require('../static/state.js');let releasePoll,posts=0;const updates=[],deleted=[];
 const runner=solveRunner({delay:async()=>{},request:async(path,body,method)=>{if(method==='POST'){posts++;return posts===1?{id:'old',status:'running'}:{id:'new',status:'completed',result:{marker:'new'}};}if(method==='DELETE'){deleted.push(path);return {status:'running'};}return new Promise(r=>releasePoll=r);},onUpdate:value=>updates.push(value)});
 const old=runner.start({});await new Promise(setImmediate);runner.requestCancel();await runner.start({});releasePoll({status:'cancelled',result:{marker:'old'}});await old;
 assert.deepEqual(updates.filter(value=>value.result).map(value=>value.result.marker),['new']);assert.deepEqual(deleted,['/api/solve-jobs/old']);
});
test('Cancelled search retains the more complete provisional result instead of losing progress',()=>{
 const {cancelledResult}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:4,cells:[{letter:'A'},{},{},{}],suggestions:{solutions:[],partialLetters:['A','B','C',''],forcedLetters:['A','B','','']}});
 const previous=p.suggestions;
 assert.equal(cancelledResult(p,{solutions:[],forcedLetters:['A','B','','']}),previous);
 assert.equal(cancelledResult(p,{solutions:[],partialLetters:['A','','','D']}),previous);
 const improved={solutions:[],partialLetters:['A','B','C','D']};assert.equal(cancelledResult(p,improved),improved);
 const full={solutions:[{letters:['A','B','C','D']}]};assert.equal(cancelledResult(p,full),full);
 p.suggestions=full;assert.equal(cancelledResult(p,improved),full);
 const otherFull={solutions:[{letters:['A','E','F','G']}]};assert.equal(cancelledResult(p,otherFull),otherFull);
});

test('Manual letter entry preserves partial progress as pencil marks and keeps fixed puzzle data',()=>{
 const {editConfirmedLetter,suggestedLetter}=require('../static/state.js');
 const p=canonicalPuzzle({id:'saved',name:'Krypto',rows:1,cols:4,image:'image',cells:[{number:'1',letter:'A',highlight:true},{number:'2',openAfterAcross:true},{number:'3'},{black:true,clue:true}],suggestions:{partialLetters:['A','B','',''],solutions:[],stats:{exhaustive:false}}});
 const fixed=JSON.parse(JSON.stringify(p.cells[0])),black=JSON.parse(JSON.stringify(p.cells[3]));
 editConfirmedLetter(p,2,'c');
 assert.deepEqual(p.cells.map(c=>c.letter),['A','','C','']);assert.equal(p.cells[1].guess,'B');assert.equal(suggestedLetter(p,1),'B');
 assert.equal(p.suggestions?.partialLetters,undefined);assert.equal(p.suggestions?.solutions?.length||0,0);
 assert.deepEqual(p.cells[0],fixed);assert.deepEqual(p.cells[3],black);assert.equal(p.cells[1].openAfterAcross,true);assert.equal(p.id,'saved');assert.equal(p.image,'image');
});
test('Manual edits preserve the displayed full alternative rather than the first alternative',()=>{
 const {editConfirmedLetter}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:3,cells:[{},{},{}],suggestions:{solutions:[{letters:['A','B','C']},{letters:['D','E','F']}],partialLetters:['G','H','I']}});
 editConfirmedLetter(p,1,'X',1);assert.deepEqual(p.cells.map(c=>c.guess),['D','','F']);assert.equal(p.cells[1].letter,'X');assert.equal(p.suggestions,undefined);
});
test('Manual letter replaces contrary provisional mappings and clears uniqueness conflicts without overwriting fixed cells',()=>{
 const {editConfirmedLetter,suggestedLetter}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:5,cells:[{number:'1'},{number:'1'},{number:'2'},{letter:'Z'},{number:'3'}],suggestions:{partialLetters:['A','A','C','Z','D'],solutions:[]}});
 editConfirmedLetter(p,0,'C');assert.equal(p.cells[0].letter,'C');assert.equal(p.cells[1].guess,'');assert.equal(suggestedLetter(p,1),'C');assert.equal(p.cells[2].guess,'');assert.equal(p.cells[3].letter,'Z');assert.equal(p.cells[4].guess,'D');
 const conflict=canonicalPuzzle({rows:1,cols:2,cells:[{number:'1',letter:'A'},{number:'1'}]});
 editConfirmedLetter(conflict,1,'B');assert.deepEqual(conflict.cells.map(c=>c.letter),['A','B']);
});
test('Manual variant edits clear over-capacity provisional extras while preserving supported and unrelated letters',()=>{
 const {editConfirmedLetter}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:5,rules:{maxLettersPerNumber:2},cells:[{number:'1',letter:'A'},{number:'1'},{number:'1'},{number:'1'},{number:'2'}],suggestions:{partialLetters:['A','','C','A','D'],solutions:[]}});
 editConfirmedLetter(p,1,'B');assert.deepEqual(p.cells.map(c=>c.guess),['','','','A','D']);
 const unsettled=canonicalPuzzle({rows:1,cols:3,rules:{maxLettersPerNumber:2},cells:[{number:'1'},{number:'1'},{number:'1'}],suggestions:{partialLetters:['','A','C'],solutions:[]}});
 editConfirmedLetter(unsettled,0,'B');assert.deepEqual(unsettled.cells.map(c=>c.guess),['','','']);
});
test('Clearing a manual letter clears only that cell while preserving other displayed suggestions',()=>{
 const {editConfirmedLetter}=require('../static/state.js');
 const p=canonicalPuzzle({rows:1,cols:3,cells:[{letter:'A'},{},{}],suggestions:{partialLetters:['A','B','C'],solutions:[]}});
 editConfirmedLetter(p,0,'');assert.deepEqual(p.cells.map(c=>c.letter),['','','']);assert.deepEqual(p.cells.map(c=>c.guess),['','B','C']);
 editConfirmedLetter(p,1,'');assert.deepEqual(p.cells.map(c=>c.guess),['','','C']);
});


test('Reset suggestions retains confirmed mappings but removes solver guesses and stale deductions',()=>{
 const {resetSuggestions}=require('../static/state.js');
 const p={rows:1,cols:3,image:'image',rules:{maxLettersPerNumber:1,uniqueLetters:true},cells:[{number:'1',letter:'A',guess:'B'},{number:'1',letter:'',guess:'B'},{number:'2',letter:'',guess:'C'}],suggestions:{solutions:[{letters:['A','A','C']}],partialLetters:['A','A','C'],forcedLetters:['A','B','C']}};
 resetSuggestions(p);
 assert.deepEqual(p.cells.map(c=>c.letter),['A','','']);
 assert.deepEqual(p.cells.map(c=>c.guess),['','','']);
 assert.deepEqual(p.suggestions.forcedLetters,['A','A','']);
 assert.deepEqual(p.suggestions.solutions,[]);
 assert.equal(p.suggestions.partialLetters,undefined);
 assert.equal(p.image,'image');
});


test('Missing-word option defaults on while preserving explicit saved choices',()=>{
 const {canonicalPuzzle}=require('../static/state.js');
 assert.equal(canonicalPuzzle({cells:[]}).allowUnknownWords,true);
 assert.equal(canonicalPuzzle({cells:[],allowUnknownWords:false}).allowUnknownWords,false);
 assert.equal(canonicalPuzzle({cells:[],allowUnknownWords:true}).allowUnknownWords,true);
});


test('Prefilled provenance survives save/open without locking player answers',()=>{
 const p=canonicalPuzzle({cells:[{letter:'A'},{letter:'B',prefilled:false},{letter:'C',prefilled:true},{}]});
 assert.deepEqual(p.cells.map(c=>c.prefilled),[true,false,true,false]);
 assert.deepEqual(canonicalPuzzle(JSON.parse(JSON.stringify(p))).cells.map(c=>c.prefilled),[true,false,true,false]);
});

test('Conflicting letter ownership moves all previous occurrences without deleting unrelated progress',()=>{
 const {letterOwners,moveLetterAssignment}=require('../static/state.js');
 const p=canonicalPuzzle({language:'en',cells:[{number:'1',letter:'A'},{number:'1'},{number:'2'},{number:'3',guess:'B'}],suggestions:{forcedLetters:['A','A','',''],solutions:[]}});
 assert.deepEqual(letterOwners(p,2,'A'),['1']);
 assert.deepEqual(letterOwners(p,1,'A'),[]);
 moveLetterAssignment(p,2,'A');
 assert.deepEqual(p.cells.map(c=>c.letter),['','','A','']);
 assert.equal(p.cells[0].prefilled,false);
 assert.equal(p.cells[1].guess,'');assert.equal(p.cells[3].guess,'B');
 assert.deepEqual(letterOwners(p,0,'A'),['2']);
 p.rules.uniqueLetters=false;assert.deepEqual(letterOwners(p,0,'A'),[]);
});

test('Cell word selection defaults across, toggles, and skips one-letter directions',()=>{
 const {cellWord}=require('../static/state.js');
 const p=canonicalPuzzle({rows:3,cols:3,cells:Array.from({length:9},()=>({}))});
 assert.equal(cellWord(p,4).direction,'Across');
 assert.equal(cellWord(p,4,'Across',true).direction,'Down');
 assert.equal(cellWord(p,4,'Down',true).direction,'Across');
 p.cells[3].black=true;p.cells[5].black=true;
 assert.equal(cellWord(p,4).direction,'Down');
 assert.equal(cellWord(p,4,'Down',true).direction,'Down');
 p.cells[1].black=true;p.cells[7].black=true;
 assert.equal(cellWord(p,4),null);
 assert.equal(cellWord(p,3),null);
});

test('Language presentation keeps Finnish morphology out of English and Dutch',()=>{
 const {languagePresentation}=require('../static/state.js');
 for(const [language,name] of [['en','English'],['nl','Dutch']]){
  const info=languagePresentation({language,useDictionary:true,useMorphology:true});
  assert.equal(info.name,name);assert.equal(info.showMorphology,false);
  assert.doesNotMatch(info.candidateExplanation,/Finnish|morphology/i);
 }
 assert.equal(languagePresentation({language:'fi',useDictionary:true}).showMorphology,true);
 const dutch=canonicalPuzzle({rows:1,cols:2,language:'nl',cells:[{letter:'i'},{letter:'j'}]});
 assert.equal(dutch.language,'nl');assert.deepEqual(candidateLetters(dutch,{letters:['I','J']}),['I','J']);
 assert.equal(candidateLetters(dutch,{letters:['IJ','A']}),null);
});

test('Dictionary editor imports raw text and ignores stale language responses',async()=>{
 const {dictionaryEditor}=require('../static/state.js');
 const pending=[],loaded=[],saved=[];
 const editor=dictionaryEditor((path,body,method)=>new Promise(resolve=>pending.push({path,body,method,resolve})),data=>loaded.push(data),data=>saved.push(data));
 const english=editor.open('en');const dutch=editor.open('nl');
 pending[1].resolve({language:'nl',words:['HUIS'],source:'custom'});await dutch;
 pending[0].resolve({language:'en',words:['HOUSE'],source:'custom'});await english;
 assert.equal(loaded.length,1);assert.equal(loaded[0].language,'nl');
 const importing=editor.save('huis\nbad-word\nhuis',true);
 assert.equal(pending[2].path,'/api/dictionaries/nl/import');assert.deepEqual(pending[2].body,{text:'huis\nbad-word\nhuis'});
 editor.cancel();pending[2].resolve({language:'nl',count:1,skipped:1,duplicates:1,total:3});await importing;
 assert.equal(saved.length,0,'Closed or switched editors ignore stale results');
});

test('Manual empty dictionaries clear via PUT while empty file imports retain import validation',async()=>{
 const {dictionaryEditor}=require('../static/state.js');const calls=[];
 const editor=dictionaryEditor(async(path,body,method)=>{calls.push({path,body,method});return {language:'en',words:[],count:0};},()=>{},()=>{});
 await editor.open('en');await editor.save('');assert.equal(calls[1].method,'PUT');assert.deepEqual(calls[1].body,{words:[]});
 await editor.readFile(()=>Promise.resolve(''));await editor.save('');assert.equal(calls[2].path,'/api/dictionaries/en/import');
 editor.manualEdit();await editor.save('');assert.equal(calls[3].method,'PUT');
 await editor.save('DOG');assert.equal(calls[4].path,'/api/dictionaries/en/import');
});

test('Dictionary reopens wait for saves and file reads block saving or stale editor replacement',async()=>{
 const {dictionaryEditor}=require('../static/state.js');const pending=[],loaded=[];
 const editor=dictionaryEditor((path,body,method)=>new Promise(resolve=>pending.push({path,body,method,resolve})),data=>loaded.push(data),()=>{});
 const opening=editor.open('en');pending[0].resolve({language:'en',words:['OLD']});await opening;
 const saving=editor.save('NEW');editor.cancel();const reopening=editor.open('en');
 assert.equal(pending.length,2,'No stale GET while save is pending');
 pending[1].resolve({language:'en',count:1});await saving;await Promise.resolve();
 assert.equal(pending.length,3);pending[2].resolve({language:'en',words:['NEW']});await reopening;
 let finishRead;const reading=editor.readFile(()=>new Promise(resolve=>{finishRead=resolve;}));
 await assert.rejects(editor.save('NEW'),/reading/i);
 editor.cancel();finishRead('STALE');assert.equal(await reading,null);
 assert.equal(loaded.at(-1).words[0],'NEW');
});

test('Paged dictionaries preserve unseen words and edits across pages',()=>{
 const {dictionaryPages}=require('../static/state.js');
 const pages=dictionaryPages('ONE\nTWO\nTHREE\nFOUR\nFIVE',2);
 assert.equal(pages.count,3);assert.equal(pages.page(0),'ONE\nTWO');
 pages.update(0,'NEW\nTWO');pages.update(1,'THREE\nEDITED\nADDED');
 assert.equal(pages.page(2),'FIVE');assert.equal(pages.text(),'NEW\nTWO\nTHREE\nEDITED\nADDED\nFIVE');
 const large=dictionaryPages(Array.from({length:466550},(_,i)=>'WORD'+i).join('\n'));
 assert.equal(large.count,467);assert.equal(large.page(0).split('\n').length,1000);
 assert.equal(large.page(466).split('\n').length,550);
});

test('plausibility labels describe letter patterns without verifying words', () => {
 const {plausibilityLabel,plausibilityDetail,candidateDisplay}=require('../static/state.js');
 assert.equal(plausibilityLabel({label:'typical'}),'Typical pattern');
 assert.equal(plausibilityLabel(undefined),'');
 assert.equal(plausibilityLabel({label:'unassessed'}),'');
 assert.match(plausibilityDetail({label:'implausible',reasons:['no vowel']}),/Implausible pattern: no vowel\. A letter-pattern check, not a dictionary check\./);
 assert.equal(candidateDisplay('HOUSE',{label:'typical'}),'HOUSE');
 assert.equal(candidateDisplay('XQZT',{label:'implausible'}),'XQZT (implausible)');
 assert.equal(candidateDisplay('HOUSE',undefined),'HOUSE');
});

test('Finnish and Swedish allow Å, Ä and Ö; English and Dutch do not', () => {
 const {nordicLetters,languagePresentation}=require('../static/state.js');
 assert.equal(nordicLetters('fi'),true);assert.equal(nordicLetters('sv'),true);
 assert.equal(nordicLetters('en'),false);assert.equal(nordicLetters('nl'),false);
 const swedish=languagePresentation({language:'sv',useDictionary:true});
 assert.equal(swedish.name,'Swedish');assert.equal(swedish.showMorphology,false);
});

test('lookup helpers describe dictionary status and pattern scores', () => {
 const {lookupPattern,candidateEvidenceText,wordLookupText,patternScoreText}=require('../static/state.js');
 const puzzle={cells:[{number:'12',letter:''},{number:'',letter:'A'},{number:'07',letter:''},{number:'',letter:''}]};
 assert.equal(lookupPattern(puzzle,[1,0,0,2,3]),'A 12 12 7 ?');
 assert.equal(patternScoreText({label:'typical',bitsPerLetter:1.234}),'Typical pattern (score 1.23)');
 assert.equal(patternScoreText(undefined),'No letter-pattern score for this language');
 assert.equal(candidateEvidenceText({source:'dictionary',inDictionary:true},{label:'typical',bitsPerLetter:2,reasons:[]},'en'),'In your word list · Typical pattern (score 2.00)');
 assert.match(candidateEvidenceText({source:'generated'},{label:'unusual',bitsPerLetter:0.1,reasons:['no vowel']},'en'),/^Not in the dictionary: pattern guess · Unusual pattern \(score 0\.10\) · no vowel$/);
 assert.match(candidateEvidenceText({source:'morphology'},{label:'typical',bitsPerLetter:2,reasons:[]},'fi'),/Finnish form index, not in your word list/);
 assert.match(wordLookupText({inDictionary:false,inMorphology:false,plausibility:{label:'implausible',bitsPerLetter:-3,reasons:[]}}),/^Not in your word list · Implausible pattern/);
});

test('selected words are checked only when every cell has a letter', () => {
 const {completeWordText,selectedWordCheckText}=require('../static/state.js');
 const puzzle={cells:[{letter:'K'},{letter:''},{letter:'T'}],suggestions:{solutions:[{letters:['K','A','T']}]}};
 const word={cells:[0,1,2],provisionalCount:1,before:false,after:false};
 assert.deepEqual(completeWordText(puzzle,word,0),{text:'KAT',provisional:true,partial:false});
 assert.equal(completeWordText({cells:[{letter:'K'},{letter:''},{letter:'T'}]},word,0),null);
 assert.equal(completeWordText(puzzle,null,0),null);
 assert.equal(completeWordText(puzzle,{...word,after:true},0).partial,true);
 const result={word:'KAT',inDictionary:true,inMorphology:false,plausibility:{label:'typical',bitsPerLetter:1.5,reasons:[]}};
 assert.equal(selectedWordCheckText(result,{provisional:true}),'KAT: In your word list · Typical pattern (score 1.50) · includes provisional letters');
 assert.equal(selectedWordCheckText(result,{provisional:false}),'KAT: In your word list · Typical pattern (score 1.50)');
});

test('dictionary editor parses added words and summarises searches', () => {
 const {dictionaryInputWords,dictionarySearchSummary}=require('../static/state.js');
 assert.deepEqual(dictionaryInputWords(' katt, hund\nbåt;  '),['KATT','HUND','BÅT']);
 assert.deepEqual(dictionaryInputWords(''),[]);
 assert.equal(dictionarySearchSummary({total:0,query:'K?T',status:'all',offset:0,words:[]}),'No words match K?T.');
 assert.equal(dictionarySearchSummary({total:0,query:'',status:'disabled',offset:0,words:[]}),'No disabled words.');
 assert.equal(dictionarySearchSummary({total:1234,query:'K*',status:'all',offset:100,words:new Array(100)}),'1,234 words match K* · showing 101–200');
});

test('dictionary search summary uses singular for one match', () => {
 const {dictionarySearchSummary}=require('../static/state.js');
 assert.equal(dictionarySearchSummary({total:1,query:'K?TT*',status:'disabled',offset:0,words:[{}]}),'1 disabled word matches K?TT* · showing 1–1');
});
test('Workspace mode view keeps guests off server storage and explains their limits', () => {
 const {workspaceModeView} = require('../static/state.js');
 const local = workspaceModeView({mode:'local'});
 assert.equal(local.serverStorage, true); assert.equal(local.autosave, 'server'); assert.equal(local.modeButton, null); assert.equal(local.dictionaryNote, '');
 const limits = {words:200000, importMegabytes:4, idleHours:2};
 const guest = workspaceModeView({mode:'guest', userLogin:true, guestLimits:limits});
 assert.equal(guest.serverStorage, false); assert.equal(guest.autosave, 'browser'); assert.equal(guest.modeButton, 'User mode');
 assert.equal(guest.maxImportBytes, 4*1024*1024); assert.match(guest.dictionaryNote, /200,000 words and 4 MB/); assert.match(guest.dictionaryNote, /2 hours/);
 assert.equal(workspaceModeView({mode:'guest', userLogin:false, guestLimits:limits}).modeButton, null, 'No password configured: no user mode');
 const user = workspaceModeView({mode:'user', userLogin:true});
 assert.equal(user.serverStorage, true); assert.equal(user.autosave, 'browser', 'Shared servers keep recovery copies per browser');
 assert.equal(user.modeButton, 'Leave user mode'); assert.equal(user.maxImportBytes, 16*1024*1024);
 const signedOut = workspaceModeView({mode:'signed-out', userLogin:true});
 assert.equal(signedOut.serverStorage, false); assert.equal(signedOut.modeButton, null);
 assert.equal(workspaceModeView({mode:'bogus'}).mode, 'local');
});
test('Blocks and picture areas keep no number review mark when a puzzle is loaded', () => {
const puzzle = canonicalPuzzle({rows:1, cols:2, language:'en', cells:[
 {black:true, clue:true, number:'', numberReview:'check'}, {number:'', numberReview:'missing'}]});
assert.equal('numberReview' in puzzle.cells[0], false);
assert.equal(puzzle.cells[1].numberReview, 'missing');
});
test('Correcting a number moves the cell to the new number in confirmed letters and kept suggestions', () => {
 const {renumberCell, refreshDeductions, suggestedLetter, suggestionLabel} = require('../static/state.js');
 // C A T with numbers 1 2 3; the last cell is corrected from 3 to 1.
 const make = () => { const p = canonicalPuzzle({rows:1, cols:4, language:'en', cells:[{number:'1'},{number:'2'},{number:'3'},{number:'4'}]});
  p.suggestions = {status:'completed', solutions:[{letters:['C','A','T','S'], score:1, words:[]}, {letters:['B','A','T','S'], score:2, words:[]}], stats:{}, diagnostics:[]};
  return p; };
 let p = make();
 assert.equal(renumberCell(p, 2, '1'), true);
 refreshDeductions(p, true);
 assert.deepEqual(p.suggestions.solutions.map(s => s.letters), [['C','A','C','S'], ['B','A','B','S']], 'Each suggestion uses its own letter for the new number');
 assert.equal(p.cells[2].number, '1');
 assert.equal(renumberCell(p, 2, '1'), false, 'Same number: no change');
 // A number used nowhere else leaves the cell empty in every suggestion.
 p = make(); renumberCell(p, 2, '9'); refreshDeductions(p, true);
 assert.deepEqual(p.suggestions.solutions[0].letters, ['C','A','','S']);
 // A confirmed answer letter belonged to the old number: cleared, and the new number's
 // confirmed letter shows as a mapping deduction, not a confirmed letter.
 p = make(); p.cells[0].letter = 'C'; p.cells[2].letter = 'T'; p.cells[2].guess = '';
 renumberCell(p, 2, '1'); refreshDeductions(p, true);
 assert.equal(p.cells[2].letter, ''); assert.equal(suggestedLetter(p, 2), 'C'); assert.equal(suggestionLabel(p, 2), 'Mapping deduction');
 assert.equal(p.suggestions.solutions.length, 1, 'Suggestions that contradict confirmed letters are dropped');
 // A letter entered in Edit mode also follows the number, so one letter never sits on two
 // numbers: S stays with 4 elsewhere and the corrected cell takes number 1's C.
 p = make(); p.cells.push({...p.cells[3]}); p.rows = 1; p.cols = 5; p.cells[4] = {...p.cells[4], number:'4', letter:'S', prefilled:true};
 p.cells[0].letter = 'C'; p.cells[3].letter = 'S'; p.cells[3].prefilled = true;
 assert.equal(renumberCell(p, 3, '1'), true); refreshDeductions(p, true);
 assert.equal(p.cells[3].letter, ''); assert.equal(p.cells[3].prefilled, false);
 assert.equal(suggestedLetter(p, 3), 'C'); assert.equal(p.cells[4].letter, 'S');
 // Partial results follow the same rule; a cleared number takes no letter.
 p = make(); p.suggestions = {partialLetters:['C','A','T',''], solutions:[], stats:{}, diagnostics:[]};
 renumberCell(p, 2, '1'); assert.deepEqual(p.suggestions.partialLetters, ['C','A','C','']);
 renumberCell(p, 2, ''); assert.deepEqual(p.suggestions.partialLetters, ['C','A','','']);
 // With several letters per number, a number does not determine the letter.
 p = make(); p.rules.maxLettersPerNumber = 2; renumberCell(p, 2, '1');
 assert.equal(p.suggestions.solutions[0].letters[2], '');
});
test('Saved-puzzle list offers only languages present, with counts, and filters by language', () => {
 const {savedPuzzleView} = require('../static/state.js');
 const items = [{id:'a', language:'fi'}, {id:'b', language:'en'}, {id:'c', language:'fi'}, {id:'d'}];
 const all = savedPuzzleView(items);
 assert.deepEqual(all.languages.map(l => [l.code, l.name, l.count]), [['en','English',1], ['fi','Finnish',2], ['','Unknown',1]]);
 assert.equal(all.selected, ''); assert.equal(all.items.length, 4);
 assert.deepEqual(savedPuzzleView(items, 'fi').items.map(i => i.id), ['a','c'], 'Filter keeps the server order');
 assert.equal(savedPuzzleView(items, 'sv').selected, '', 'A language no longer present falls back to all');
 assert.equal(savedPuzzleView(items, 'sv').items.length, 4);
});

test('Solve progress names preparation and says the search time starts after it', () => {
 const {solveProgressText} = require('../static/state.js');
 assert.equal(solveProgressText({stage:'indexing_dictionary',elapsedSeconds:1.26}), 'Preparing: indexing dictionary · 1.3 seconds · search time starts after this');
 assert.equal(solveProgressText({stage:'adapting_letter_model'}), 'Preparing: adapting letter model · 0.0 seconds · search time starts after this');
 assert.equal(solveProgressText(null), 'Preparing: loading puzzle and dictionary · 0.0 seconds · search time starts after this');
 assert.equal(solveProgressText({stage:'missing_word_search',nodes:1200,elapsedSeconds:2,solutionsFound:1}), `missing word search · ${(1200).toLocaleString()} search nodes · 2.0 seconds · 1 suggestions found`);
 assert.equal(solveProgressText({stage:'missing_word_search'},true), 'Stopping search · 0.0 seconds');
});
