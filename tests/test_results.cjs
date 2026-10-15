'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),S=require('../static/state.js');
const word=(text,source,label,score,verified=['dictionary','morphology'].includes(source))=>({text,source,verified,plausibility:{label,bitsPerLetter:score}});
test('Result filters use full-word evidence without claiming unchecked words are absent from dictionary',()=>{
 const words=[word('DICT','dictionary','typical',-2),word('MORPH','morphology','typical',-2),word('FRAGMENT','fragment','typical',-2),word('GUESS','unverified','typical',-2),word('UNTRUSTED','dictionary','typical',-2,false)];
 assert.deepEqual(S.solvedWordsView(words,'no-dictionary','grid').map(w=>w.text),['MORPH','FRAGMENT','GUESS','UNTRUSTED']);
 assert.deepEqual(S.solvedWordsView(words,'unverified','grid').map(w=>w.text),['FRAGMENT','GUESS','UNTRUSTED']);
 assert.deepEqual(S.solvedWordsView(words,'dictionary','grid').map(w=>w.text),['DICT']);
 assert.deepEqual(S.solvedWordsView([], 'all'),[]);
});
test('Uncertain-first orders evidence tiers, unassessed first, then labels and lower finite scores with stable ties',()=>{
 const words=[word('DICT','dictionary','implausible',-20),word('TYPICAL','unverified','typical',-2),word('UNUSUAL','unverified','unusual',-7),word('BAD1','unverified','implausible',-10),word('BAD2','unverified','implausible',-10),word('WORSE','unverified','implausible',-15),word('MISSING','unverified','unassessed',null),word('MORPH','morphology','unassessed',null),word('FRAGMENT','fragment','typical',-3)];const snapshot=structuredClone(words);
 assert.deepEqual(S.solvedWordsView(words).map(w=>w.text),['MISSING','WORSE','BAD1','BAD2','UNUSUAL','TYPICAL','MORPH','FRAGMENT','DICT']);assert.deepEqual(words,snapshot);
 assert.deepEqual(S.solvedWordsView(words,'all','grid'),words);assert.equal(S.solvedWordsView(words,'all','alphabetical')[0].text,'BAD1');
});
test('Missing and nonfinite pattern scores are never printed as numeric confidence',()=>{
 for(const score of [null,undefined,NaN,Infinity,-Infinity,'-4'])assert.equal(S.solvedWordPatternScore(word('X','unverified','unassessed',score)),'Pattern score unavailable');
 assert.equal(S.solvedWordPatternScore(word('X','unverified','typical',-4.126)),'Pattern score -4.13');assert.equal(S.solvedWordPatternScore(word('X','unverified','typical',0)),'Pattern score 0.00');
});
const puzzle=()=>S.canonicalPuzzle({rows:2,cols:2,language:'en',cells:[{letter:'A',prefilled:false},{guess:'B'},{guess:'C'},{guess:'D'}]});
test('Result selection matches exact slot cells and direction, without mutating puzzle',()=>{
 const p=puzzle(),before=structuredClone(p);assert.deepEqual(S.solvedWordSelection(p,{cells:[0,2]}),{cells:[0,2],index:0,direction:'Down'});assert.deepEqual(S.solvedWordSelection(p,{cells:[0,1]}),{cells:[0,1],index:0,direction:'Across'});
 for(const cells of [[0],[0,3],[2,0],[0,1,2],[]])assert.equal(S.solvedWordSelection(p,{cells}),null);assert.deepEqual(p,before);
});
test('Result actions hide unavailable controls and explain mixed rows, including locked prefills',()=>{
 const p=puzzle(),w={cells:[0,1]};assert.deepEqual(S.solvedWordActions(p,w),{confirm:true,unconfirm:true,confirmLabel:'Confirm',unconfirmLabel:'Unconfirm'});
 p.cells[0].letter='';p.cells[0].guess='A';assert.equal(S.solvedWordActions(p,w).unconfirm,false);assert.equal(S.solvedWordActions(p,w).confirmLabel,'Confirm');
 p.cells[0].letter='A';p.cells[1].letter='B';assert.equal(S.solvedWordActions(p,w).confirm,false);assert.equal(S.solvedWordActions(p,w).unconfirmLabel,'Unconfirm');
 p.cells[0].prefilled=true;p.cells[1].prefilled=true;assert.equal(S.solvedWordActions(p,w,0,false).unconfirm,false);p.cells[1].letter='';p.cells[1].prefilled=false;assert.equal(S.solvedWordActions(p,w,0,false).confirmLabel,'Confirm');assert.equal(S.solvedWordActions(p,w,0,false).unconfirm,false);
});
test('Actual result-word click selects Down, scrolls and focuses without confirming or changing suggestions',()=>{
 const fs=require('node:fs'),vm=require('node:vm'),source=fs.readFileSync(require.resolve('../static/app.js'),'utf8'),p=puzzle();p.suggestions={solutions:[{letters:['A','B','C','D']}]};const before=JSON.stringify(p);let scrolled=false,focused=false,renders=0;
 const context={PuzzleState:S,puzzle:p,selected:3,wordDirection:'Across',lastClickedCell:null,numericEntry:{},render(){renders++;},$:()=>({children:[{scrollIntoView(){scrolled=true;},focus(){focused=true;}}]})};
 vm.runInNewContext(source.slice(source.indexOf('function jumpToSolvedWord('),source.indexOf("$('solved-word-filter').onchange")),context);context.jumpToSolvedWord({cells:[0,2]});assert.equal(context.selected,0);assert.equal(context.wordDirection,'Down');assert.equal(context.numericEntry,null);assert.equal(renders,1);assert.ok(scrolled&&focused);assert.equal(JSON.stringify(p),before);
});
test('Displayed words exist without a complete alternative: partial, deductions, notes and confirmed grids',()=>{
 const p=puzzle();delete p.cells[1].guess;delete p.cells[2].guess;delete p.cells[3].guess;
 assert.deepEqual(S.displayedPuzzleWords(p).map(w=>w.text),['A·','··','A·','··']);
 p.suggestions={partialLetters:['','B','C','']};assert.deepEqual(S.displayedPuzzleWords(p).map(w=>w.text),['AB','C·','AC','B·']);
 p.suggestions={forcedLetters:['','B','','D']};assert.deepEqual(S.displayedPuzzleWords(p).map(w=>w.text),['AB','·D','A·','BD']);
 delete p.suggestions;p.cells.forEach((c,i)=>c.letter='ABCD'[i]);assert.deepEqual(S.displayedPuzzleWords(p).map(w=>w.text),['AB','CD','AC','BD']);assert.ok(S.displayedPuzzleWords(p).every(w=>!w.verified&&!w.plausibility));
});
test('Displayed words reuse evidence only for matching complete text and exact slot cells',()=>{
 const p=puzzle();p.suggestions={solutions:[{letters:['A','B','C','D'],words:[{cells:[0,1],text:'AB',source:'dictionary',verified:true,plausibility:{label:'typical',bitsPerLetter:-3},analyses:[{lemma:'ab'}]},{cells:[0,2],text:'XX',source:'dictionary',verified:true,plausibility:{bitsPerLetter:-1}},{cells:[1,3],text:'BD',source:'morphology',verified:true}]}]};
 const words=S.displayedPuzzleWords(p);assert.equal(words[0].source,'dictionary');assert.equal(words[0].plausibility.bitsPerLetter,-3);assert.equal(words[2].verified,false);assert.equal(words[2].plausibility,undefined);assert.equal(words[3].source,'morphology');
 p.cells[1].letter='Z';const changed=S.displayedPuzzleWords(p);assert.equal(changed[0].text,'AZ');assert.equal(changed[0].source,'unverified');assert.equal(changed[0].analyses,undefined);assert.equal(changed[0].plausibility,undefined);
});
function resultUI(p){
 const vm=require('node:vm'),fs=require('node:fs'),source=fs.readFileSync(require.resolve('../static/app.js'),'utf8');
 class Element{constructor(){this.children=[];this.textContent='';this.dataset={};}replaceChildren(){this.children=[];}append(...children){this.children.push(...children);}setAttribute(){}}
 const nodes={},$=id=>nodes[id]??=new Element();const context={puzzle:p,PuzzleState:S,$,wordChecks:{ensure:(_p,w)=>({status:w.unknownCount?'incomplete':w.before||w.after?'fragment':'queued'})},acceptanceHistory:{length:0},solution:()=>p.suggestions?.solutions?.[0],solutionIndex:0,editMode:false,solvedWordFilter:'all',solvedWordSort:'grid',document:{createElement:()=>new Element()},suggestion:i=>S.suggestedLetter(p,i),accept(){},unconfirm(){},jumpToSolvedWord(){}};
 vm.runInNewContext(source.slice(source.indexOf('function renderResults(){'),source.indexOf('function jumpToSolvedWord(')),context);return {$,context};
}
test('Result UI renders grid words without fabricating a complete alternative or full-confirm action',()=>{
 const p=puzzle();p.suggestions={partialLetters:['','B','C',''],status:'partial',solutions:[]};const {$,context}=resultUI(p);context.renderResults();
 assert.equal($('result-content').hidden,false);assert.equal($('word-results').children.length,4);assert.equal($('result-alternatives').hidden,true);assert.equal($('alternatives').children.length,0);
});
test('Manual and fully confirmed grids have word rows; real isolated-cell alternatives keep their toolbar',()=>{
 for(const p of [puzzle(),S.canonicalPuzzle({rows:1,cols:2,cells:[{letter:'A'},{letter:'B'}]})]){const {$,context}=resultUI(p);context.renderResults();assert.equal($('result-content').hidden,false);assert.ok($('word-results').children.length);assert.equal($('result-alternatives').hidden,true);assert.equal($('accept-all').disabled,true);}
 const p=S.canonicalPuzzle({rows:1,cols:1,cells:[{guess:'A'}]});p.suggestions={solutions:[{letters:['A'],words:[],score:1}],stats:{},status:'found'};const {$,context}=resultUI(p);context.renderResults();assert.equal($('result-content').hidden,false);assert.equal($('result-alternatives').hidden,false);assert.equal($('accept-all').disabled,false);assert.equal($('alternatives').children.length,1);assert.match($('solved-word-count').textContent,/No Across or Down/);
 delete p.suggestions;context.renderResults();assert.match($('result-empty').textContent,/No Across or Down/);
});
test('Incomplete word evidence is unavailable and confirmation only accepts displayed known cells',()=>{
 const p=S.canonicalPuzzle({rows:1,cols:3,cells:[{},{},{}]});p.suggestions={partialLetters:['A','','C'],solutions:[]};const words=S.displayedPuzzleWords(p);assert.equal(words[0].text,'A·C');assert.equal(words[0].unknownCount,1);assert.equal(words[0].verified,false);
 S.confirmCells(p,words[0].cells);assert.deepEqual(p.cells.map(c=>c.letter),['A','','C']);
 p.suggestions={solutions:[{letters:['A','','C'],words:[{cells:[0,1,2],text:'A·C',source:'dictionary',verified:true,plausibility:{bitsPerLetter:-1}}]}]};assert.equal(S.displayedPuzzleWords(p)[0].plausibility,undefined);
});
test('Real rows and selected-word panel share independent lookup, ignore delayed edits and clear after dictionary change',async()=>{
 const fs=require('node:fs'),vm=require('node:vm'),source=fs.readFileSync(require.resolve('../static/app.js'),'utf8');const p=S.canonicalPuzzle({rows:1,cols:3,language:'en',useDictionary:false,cells:[{letter:'C'},{letter:'A'},{letter:'T'}]});const {$,context}=resultUI(p);
 let timer;const pending=[];context.wordChecks=S.wordAssessmentQueue((_path,payload)=>new Promise(resolve=>pending.push({payload,resolve})),()=>{context.renderResults();context.renderCurrentWordCheck({cells:[0,1,2]});},{schedule(fn){timer=fn;return 1;},unschedule(){timer=null;}});
 vm.runInNewContext(source.slice(source.indexOf('function renderCurrentWordCheck('),source.indexOf('// Each word: dictionary status')),context);
 context.renderResults();context.renderCurrentWordCheck({cells:[0,1,2]});timer();await new Promise(r=>setImmediate(r));assert.equal(pending.length,1);assert.equal(pending[0].payload.query,'CAT');assert.equal(pending[0].payload.puzzle.useDictionary,true);
 p.cells[2].letter='';context.renderResults();context.renderCurrentWordCheck({cells:[0,1,2]});pending[0].resolve({kind:'word',word:'CAT',inDictionary:true,plausibility:{label:'typical',bitsPerLetter:-2}});await new Promise(r=>setImmediate(r));
 assert.match($('word-results').children[0].children[1].children[0].textContent,/Incomplete word/);assert.match($('candidate-current-check').textContent,/Incomplete word/);
 p.cells[2].letter='T';context.renderResults();assert.match($('word-results').children[0].children[1].children[0].textContent,/Dictionary match/);
 context.wordChecks.clear();context.renderResults();assert.match($('word-results').children[0].children[1].children[0].textContent,/Checking dictionary/);timer();await new Promise(r=>setImmediate(r));pending[1].resolve({kind:'word',word:'CAT',inDictionary:false,disabled:true,plausibility:{label:'typical',bitsPerLetter:-2}});await new Promise(r=>setImmediate(r));assert.match($('word-results').children[0].children[1].children[0].textContent,/Disabled in dictionary/);
});
