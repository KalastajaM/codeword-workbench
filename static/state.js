/* Pure puzzle state helpers, shared by browser interactions and Node checks. */
(function(root){
'use strict';
const normalize=value=>value.normalize('NFC').trim().toUpperCase();
function canonicalPuzzle(value){return {...value,name:value.name||'Untitled puzzle',numberPosition:['top-left','top-right','bottom-left','bottom-right'].includes(value.numberPosition)?value.numberPosition:'top-left',useDictionary:value.useDictionary!==false,useMorphology:value.useMorphology!==false,searchMode:['deep','extended'].includes(value.searchMode)?value.searchMode:'quick',allowUnknownWords:value.allowUnknownWords!==false,eliminations:canonicalEliminations(value.eliminations),rejectedWords:Array.isArray(value.rejectedWords)?value.rejectedWords.filter(entry=>entry&&Number.isInteger(entry.start)&&['Across','Down'].includes(entry.direction)&&typeof entry.word==='string').map(entry=>({start:entry.start,direction:entry.direction,word:normalize(entry.word)})):[],rules:{maxLettersPerNumber:1,uniqueLetters:true,forbiddenPatterns:[],discouragedPatterns:[],...value.rules},cells:value.cells.map(({numberReview,...c})=>({black:false,number:'',...c,...(c.black||!numberReview?{}:{numberReview}),number:c.black?'':(c.number||''),letter:c.black?'':normalize(c.letter||''),prefilled:!c.black&&!!c.letter&&c.prefilled!==false,guess:c.black?'':normalize(c.guess||''),mappingAnchor:!c.black&&!!c.number&&!!c.letter&&c.mappingAnchor===true&&(value.rules?.maxLettersPerNumber??1)===1}))};}
function slots(puzzle){const result=[];for(const direction of ['Across','Down']){const across=direction==='Across',lines=across?puzzle.rows:puzzle.cols,length=across?puzzle.cols:puzzle.rows;for(let line=0;line<lines;line++){let cells=[];for(let offset=0;offset<=length;offset++){const i=across?line*puzzle.cols+offset:offset*puzzle.cols+line;if(offset<length&&!puzzle.cells[i].black){cells.push(i);continue;}if(cells.length>=2)result.push({cells,direction,before:!!puzzle.cells[cells[0]]['openBefore'+direction],after:!!puzzle.cells[cells[cells.length-1]]['openAfter'+direction]});cells=[];}}}return result;}
function candidateLetters(puzzle,candidate){if(!candidate||!Array.isArray(candidate.letters)||candidate.letters.length!==puzzle.cells.length||candidate.letters.some(l=>typeof l!=='string'))return null;const alphabet=nordicLetters(puzzle.language)?/^[A-ZÅÄÖ]$/:/^[A-Z]$/,letters=candidate.letters.map(normalize);if(puzzle.cells.some((c,i)=>c.black?letters[i]!=='':!alphabet.test(letters[i])||(c.letter&&c.letter!==letters[i])))return null;return letters;}
function matchesSlot(text,slot,word){if(!slot.before&&!slot.after)return text===word;if(slot.before&&slot.after)return word.includes(text);return slot.before?word.endsWith(text):word.startsWith(text);}
function blankCell(){return {black:false,number:'',letter:'',openBeforeAcross:false,openAfterAcross:false,openBeforeDown:false,openAfterDown:false};}
function numberEntry(previous, cell, key, now){
 const continuing=previous&&previous.cell===cell&&now-previous.at<900;
 const digits=continuing?previous.digits:'';
 if(key==='Backspace')return continuing?{cell,at:now,digits:digits.slice(0,-1)}:null;
 if(!/^[0-9]$/.test(key))return null;
 const next=digits+key;
 if(!/^[1-9][0-9]?$/.test(next))return continuing?previous:null;
 return {cell,at:now,digits:next};
}
function imageBoundsFromPercent(values){
 const bounds={};
 for(const key of ['x','y','width','height']){
  if(values[key]===undefined||values[key]===null||String(values[key]).trim()==='')throw new Error('Fill in all four alignment values.');
  bounds[key]=Number(values[key])/100;
 }
 if(!Object.values(bounds).every(Number.isFinite)||bounds.x<0||bounds.y<0||bounds.width<=0||bounds.height<=0)throw new Error('Left and top must be zero or greater; width and height must be greater than zero.');
 if(bounds.x+bounds.width>1.000001||bounds.y+bounds.height>1.000001)throw new Error('Left + width and top + height must each fit within 100%. Adjust the values, then apply again.');
 return bounds;
}
function fitScale(width,height,availableWidth,availableHeight,mode='puzzle'){return mode==='width'?availableWidth/width:mode==='height'?availableHeight/height:Math.min(availableWidth/width,availableHeight/height);}
function suggestedLetter(puzzle,index,solutionIndex=0){
 const cell=puzzle.cells[index];if(!cell||cell.black)return '';
 return puzzle.suggestions?.forcedLetters?.[index]||puzzle.suggestions?.solutions?.[solutionIndex]?.letters?.[index]||puzzle.suggestions?.partialLetters?.[index]||cell.guess||'';
}
// How clearly each open cell's letter leads its number's best rival in the
// selected dictionary-free alternative: 'close' (check first), 'moderate' or
// 'clear'. A clear lead is not proof the letter is right.
// liveMargins shades a running search's preview instead of a finished alternative.
function letterCertainty(puzzle,solutionIndex=0,liveMargins){
 const margins=liveMargins||puzzle.suggestions?.solutions?.[solutionIndex]?.numberMargins,stats=liveMargins?{}:puzzle.suggestions?.stats||{};
 const close=stats.closeMargin??5,clear=stats.clearMargin??15;
 return puzzle.cells.map(cell=>{
  if(!margins||cell.black||cell.letter||!cell.number)return null;
  const number=String(Number(cell.number)),info=margins[number];
  if(!info)return null;
  return {number,alternative:info.alternative,margin:info.margin,level:info.margin<close?'close':info.margin<clear?'moderate':'clear'};
 });
}
function suggestionLabel(puzzle,index,solutionIndex=0){
 if(puzzle.suggestions?.forcedLetters?.[index])return 'Mapping deduction';
 if(puzzle.suggestions?.solutions?.[solutionIndex]?.letters?.[index])return 'Suggested';
 if(puzzle.suggestions?.partialLetters?.[index])return 'Partial suggestion';
 return puzzle.cells[index]?.guess?'Unconfirmed letter':'Suggested';
}
function mappingDeductions(puzzle){
 const known=new Map();for(const cell of puzzle.cells){if(!cell.black&&cell.number&&cell.letter){if(!known.has(cell.number))known.set(cell.number,new Set());known.get(cell.number).add(cell.letter);}}
 const owners=new Map();let conflict=false;for(const [number,letters]of known){if(letters.size>puzzle.rules.maxLettersPerNumber)conflict=true;for(const letter of letters){if(puzzle.rules.uniqueLetters&&owners.has(letter)&&owners.get(letter)!==number)conflict=true;owners.set(letter,number);}}
 const propagate=!conflict&&puzzle.rules.maxLettersPerNumber===1;
 return puzzle.cells.map(cell=>{if(cell.black)return '';if(cell.letter)return cell.letter;const letters=known.get(cell.number);return propagate&&letters?.size===1?[...letters][0]:'';});
}
function solveStopExplanation(status,stats={}){
 const reason=stats.stopReason||({conflict:'invalid_constraints',empty_dictionary:'empty_dictionary',cancelled:'cancelled'}[status]);
 const messages={time_limit:'Search stopped at its time limit.',node_limit:'Search stopped at its search-node limit.',solution_limit:'Search stopped at its solution limit; more alternatives may exist.',search_exhausted:'All retained search branches were explored.',cancelled:'Search cancelled by you.',invalid_constraints:'Conflicting constraints prevent a consistent result. Review the diagnostics and correct the grid.',no_candidates:'No compatible candidates were available within this search.',empty_dictionary:'The selected dictionary is empty. Import words or turn off Use dictionary.'};
 let message=messages[reason]||(status==='budget_exhausted'?'Search stopped at its time or work limit.':'Search finished.');
 const limits=new Set(stats.limitsReached||[]);
 if(limits.has('candidate_limit'))message+=' Candidate lists were limited.';
 if(limits.has('morphology_query_limit'))message+=' Finnish morphology queries were limited.';
 if(limits.has('memory_limit'))message+=' The memory limit pruned search branches.';
 if(limits.size)message+=' Results are not exhaustive.';
 return message;
}
function solveSummary(status,count,forced,stats={}){
 const deductions=forced?` ${forced} mapping deduction${forced===1?'':'s'} remain provisional.`:'';
 const reason=stats.stopReason;
 const explanation=solveStopExplanation(status,stats);
 if(status==='conflict'||status==='empty_dictionary'||reason==='invalid_constraints'||reason==='empty_dictionary')return explanation+deductions;
 const results=count?`${count} full suggestion${count===1?'':'s'} available; review provisional letters before accepting.`:'No full suggestion found within this search. Review the diagnostics below.';
 return explanation+' '+results+deductions;
}
function hasSolveProgress(puzzle,result){
 if(result?.solutions?.length)return true;
 return puzzle.cells.some((cell,i)=>!cell.black&&!cell.letter&&(result?.partialLetters?.[i]||result?.forcedLetters?.[i]));
}
function cancelledResult(puzzle,result){
 const previous=puzzle.suggestions;
 if(result?.solutions?.length)return result;
 if(previous?.solutions?.length)return previous;
 const coverage=value=>puzzle.cells.filter((cell,i)=>!cell.black&&!cell.letter&&(value?.partialLetters?.[i]||value?.forcedLetters?.[i])).length;
 const incoming=coverage(result);
 return incoming>0&&incoming>=coverage(previous)?result:previous;
}
function refreshDeductions(puzzle,retainAlternatives=true){
 const previous=retainAlternatives?puzzle.suggestions:null;
 // A new confirmed letter outside the hypothesis can invalidate distant mappings
 // or complete a forbidden word. Retain only hypotheses covering every fixed letter.
 if(previous?.partialLetters&&puzzle.cells.some((c,i)=>c.letter&&c.letter!==previous.partialLetters[i]))delete previous.partialLetters;
 const forcedLetters=mappingDeductions(puzzle);
 const solutions=(previous?.solutions||[]).filter(s=>puzzle.cells.every((c,i)=>c.black?!s.letters[i]:!c.letter||s.letters[i]===c.letter));
 if(previous||forcedLetters.some((l,i)=>l&&!puzzle.cells[i].letter))puzzle.suggestions={...previous,status:previous?.status||'mapping_deductions',solutions,forcedLetters,stats:{...previous?.stats,exhaustive:false},diagnostics:previous?.diagnostics||[]};
 else delete puzzle.suggestions;
}
// Correcting a cell's number moves the cell to the new number's letter, so
// one letter never ends up on two numbers. The cell's own letter belonged
// to the old number and is cleared, also when it was entered in Edit mode.
// Confirmed letters of the new number then show as a mapping deduction,
// never as a confirmed letter. Each kept suggestion gives the cell the
// letter it has for the new number elsewhere in the grid, or none.
// Returns false when nothing changed.
function renumberCell(puzzle,index,number){
 const cell=puzzle.cells[index];if(!cell||cell.black||cell.number===number)return false;
 cell.number=number;cell.mappingAnchor=false;delete cell.numberReview;
 cell.letter='';cell.guess='';cell.prefilled=false;
 const letterFor=letters=>{
  if(!number||puzzle.rules.maxLettersPerNumber!==1)return '';
  const other=puzzle.cells.findIndex((c,i)=>i!==index&&!c.black&&c.number===number&&(c.letter||letters?.[i]));
  return other<0?'':puzzle.cells[other].letter||letters[other];
 };
 const suggestions=puzzle.suggestions;
 if(suggestions){
  suggestions.solutions=(suggestions.solutions||[]).map(solution=>{const letters=[...solution.letters];letters[index]=letterFor(solution.letters);return {...solution,letters};});
  if(suggestions.partialLetters){const letters=[...suggestions.partialLetters];letters[index]=letterFor(suggestions.partialLetters);suggestions.partialLetters=letters;}
 }
 return true;
}
function clearMappingProvenance(puzzle,number){for(const cell of puzzle.cells)if(cell.number===number)cell.mappingAnchor=false;}
function confirmCells(puzzle,indices,solutionIndex=0){
 const pending=[...new Set(indices)].filter(i=>puzzle.cells[i]&&!puzzle.cells[i].black&&!puzzle.cells[i].letter&&suggestedLetter(puzzle,i,solutionIndex));
 if(!pending.length)return null;
 const snapshot={cells:puzzle.cells.map((cell,index)=>({index,letter:cell.letter,guess:cell.guess||'',prefilled:!!cell.prefilled,mappingAnchor:!!cell.mappingAnchor})),suggestions:puzzle.suggestions?JSON.parse(JSON.stringify(puzzle.suggestions)):null,solutionIndex};
 const letters=pending.map(i=>suggestedLetter(puzzle,i,solutionIndex));
 pending.forEach((i,j)=>{puzzle.cells[i].letter=letters[j];puzzle.cells[i].guess='';clearMappingProvenance(puzzle,puzzle.cells[i].number);});
 refreshDeductions(puzzle);return snapshot;
}
function unconfirmCells(puzzle,indices){
 let changed=false;
 for(const i of new Set(indices)){const cell=puzzle.cells[i];if(cell&&!cell.black&&cell.letter){cell.guess=cell.letter;cell.letter='';cell.mappingAnchor=false;cell.prefilled=false;changed=true;}}
 if(changed){refreshDeductions(puzzle);if(puzzle.suggestions){puzzle.suggestions.status='edited_suggestions';puzzle.suggestions.diagnostics=['Confirmed letters were released. Retained alternatives are not exhaustive; solve again to explore more.'];}}return changed;
}
function numberCells(puzzle,index){const number=puzzle.cells[index]?.number;return number?puzzle.cells.map((c,i)=>!c.black&&c.number===number?i:-1).filter(i=>i>=0):[];}
function mappingLetterInfo(puzzle,number,letter,solutionIndex=0){
 const indices=puzzle.cells.map((cell,index)=>!cell.black&&cell.number&&String(cell.number)===String(number)&&(cell.letter||suggestedLetter(puzzle,index,solutionIndex))===letter?index:-1).filter(index=>index>=0);
 const status=!indices.length?'empty':indices.some(index=>puzzle.cells[index].letter===letter&&!puzzle.cells[index].mappingAnchor)?'confirmed':indices.some(index=>puzzle.cells[index].mappingAnchor||puzzle.suggestions?.forcedLetters?.[index]===letter)?'mapping':'suggested';
 return {indices,status};
}
function changeMappingLetter(puzzle,number,letter,action,solutionIndex=0){
 if(!['confirmed','suggested','mapping','remove'].includes(action))throw new Error('Choose confirmed, suggested, mapping or remove.');
 const alphabet=nordicLetters(puzzle.language)?/^[A-ZÅÄÖ]$/:/^[A-Z]$/;
 if(typeof letter!=='string'||!alphabet.test(letter))throw new Error('Choose one mapped letter.');
 const info=mappingLetterInfo(puzzle,number,letter,solutionIndex);
 if(!info.indices.length)throw new Error('This number and letter no longer have a displayed match.');
 const standard=puzzle.rules.maxLettersPerNumber===1;
 if(action==='mapping'&&!standard)throw new Error('Mapping deductions require one letter per number. Use confirmed or suggested for this variant.');
 const snapshot={cells:puzzle.cells.map((cell,index)=>({index,letter:cell.letter,guess:cell.guess||'',prefilled:!!cell.prefilled,mappingAnchor:!!cell.mappingAnchor})),suggestions:puzzle.suggestions?JSON.parse(JSON.stringify(puzzle.suggestions)):null,solutionIndex};
 const targets=new Set(info.indices);
 if(standard&&(action==='confirmed'||action==='mapping'))puzzle.cells.forEach((cell,index)=>{if(!cell.black&&String(cell.number)===String(number)&&!cell.letter)targets.add(index);});
 // Alternatives were generated under the old constraints. Preserve the displayed
 // hypotheses as pencil marks, then remove their obsolete evidence and rankings.
 puzzle.cells.forEach((cell,index)=>{if(!cell.black&&!cell.letter)cell.guess=suggestedLetter(puzzle,index,solutionIndex);});
 delete puzzle.suggestions;
 const anchor=info.indices.find(index=>puzzle.cells[index].letter===letter)??info.indices[0];
 for(const index of targets){
  const cell=puzzle.cells[index];cell.mappingAnchor=action==='mapping'&&index===anchor;
  if(action==='confirmed'||(action==='mapping'&&index===anchor)){cell.letter=letter;cell.guess='';}
  else {cell.letter='';cell.guess=action==='suggested'?letter:'';cell.prefilled=false;}
 }
 refreshDeductions(puzzle,false);
 return snapshot;
}
// Manual correction retains the displayed hypothesis as pencil marks, not solver evidence.
function editConfirmedLetter(puzzle,index,value,solutionIndex=0){
 const target=puzzle.cells[index];if(!target||target.black)return;
 const letter=normalize(value),alphabet=nordicLetters(puzzle.language)?/^[A-ZÅÄÖ]?$/:/^[A-Z]?$/;
 if(!alphabet.test(letter))throw new Error('Enter exactly one letter from the selected language alphabet.');
 puzzle.cells.forEach((cell,i)=>{if(!cell.black&&!cell.letter)cell.guess=suggestedLetter(puzzle,i,solutionIndex);});
 delete puzzle.suggestions;target.letter=letter;target.guess='';clearMappingProvenance(puzzle,target.number);
 const known=new Map(),owners=new Map();
 for(const cell of puzzle.cells){if(cell.black||!cell.number||!cell.letter)continue;
  if(!known.has(cell.number))known.set(cell.number,new Set());known.get(cell.number).add(cell.letter);
  if(!owners.has(cell.letter))owners.set(cell.letter,new Set());owners.get(cell.letter).add(cell.number);
 }
 // A newly confirmed owner takes precedence over a different number's pencil mark.
 for(const cell of puzzle.cells){if(cell.black||cell.letter||!cell.number||!cell.guess)continue;
  if(puzzle.rules.uniqueLetters&&[...(owners.get(cell.guess)||[])].some(number=>number!==cell.number))cell.guess='';
 }
 const proposed=new Map();
 for(const cell of puzzle.cells){if(cell.black||cell.letter||!cell.number||!cell.guess)continue;
  if(!proposed.has(cell.number))proposed.set(cell.number,new Set(known.get(cell.number)||[]));proposed.get(cell.number).add(cell.guess);
 }
 // When several old provisional letters compete for newly reduced capacity,
 // discard the unsupported extras instead of selecting an arbitrary survivor.
 for(const cell of puzzle.cells){if(cell.black||cell.letter||!cell.number||!cell.guess)continue;
  const fixed=known.get(cell.number)||new Set(),capacity=puzzle.rules.maxLettersPerNumber;
  if(fixed.size>capacity||(proposed.get(cell.number)?.size>capacity&&!fixed.has(cell.guess)))cell.guess='';
 }
 refreshDeductions(puzzle,false);
}
function letterOwners(puzzle,index,letter,solutionIndex=0){
 const number=puzzle.cells[index]?.number;
 if(!letter||!number||!puzzle.rules.uniqueLetters)return [];
 return [...new Set(puzzle.cells.filter((cell,i)=>!cell.black&&cell.number&&cell.number!==number&&(cell.letter||suggestedLetter(puzzle,i,solutionIndex))===letter).map(cell=>cell.number))];
}
function moveLetterAssignment(puzzle,index,letter,solutionIndex=0){
 const owners=new Set(letterOwners(puzzle,index,letter,solutionIndex));
 // Keep unrelated displayed progress as pencil marks before dropping stale alternatives.
 puzzle.cells.forEach((cell,i)=>{if(!cell.black&&!cell.letter)cell.guess=suggestedLetter(puzzle,i,solutionIndex);});
 for(const cell of puzzle.cells){if(owners.has(cell.number)){
  if(cell.letter===letter){cell.letter='';cell.prefilled=false;cell.mappingAnchor=false;}
  if(cell.guess===letter)cell.guess='';
 }}
 delete puzzle.suggestions;
 editConfirmedLetter(puzzle,index,letter,solutionIndex);
}
// Plan a whole-number assignment without mutating the live puzzle before approval.
function numberAssignmentPlan(puzzle,number,value,solutionIndex=0,editing=true,status='confirmed'){
 if(!['confirmed','suggested','mapping'].includes(status))throw new Error('Choose Confirmed, Suggested or Mapped.');
 if(status==='mapping'&&puzzle.rules.maxLettersPerNumber!==1)throw new Error('Mapped status requires one letter per number.');
 const letter=normalize(value),alphabet=nordicLetters(puzzle.language)?/^[A-ZÅÄÖ]$/:/^[A-Z]$/;
 if(!alphabet.test(letter))throw new Error('Enter exactly one letter from the selected language alphabet.');
 const targets=puzzle.cells.map((cell,i)=>!cell.black&&cell.number&&String(cell.number)===String(number)?i:-1).filter(i=>i>=0);
 if(!targets.length)throw new Error('This number is no longer in the puzzle.');
 const previous=[...new Set(targets.map(i=>puzzle.cells[i].letter||suggestedLetter(puzzle,i,solutionIndex)).filter(l=>l&&l!==letter))];
 const owners=letterOwners(puzzle,targets[0],letter,solutionIndex);
 const trial=JSON.parse(JSON.stringify(puzzle));
 const snapshot={cells:puzzle.cells.map((cell,index)=>({index,letter:cell.letter,guess:cell.guess||'',prefilled:!!cell.prefilled,mappingAnchor:!!cell.mappingAnchor})),suggestions:puzzle.suggestions?JSON.parse(JSON.stringify(puzzle.suggestions)):null,solutionIndex};
 trial.cells.forEach((cell,i)=>{if(!cell.black&&!cell.letter)cell.guess=suggestedLetter(puzzle,i,solutionIndex);});
 delete trial.suggestions;
 for(const cell of trial.cells){if(!cell.black&&owners.includes(cell.number)){
  if(cell.letter===letter){cell.letter='';cell.prefilled=false;cell.mappingAnchor=false;}
  if(cell.guess===letter)cell.guess='';
 }}
 for(const i of targets){const cell=trial.cells[i];cell.prefilled=editing||(!!cell.prefilled&&cell.letter===letter);cell.letter=letter;cell.guess='';cell.mappingAnchor=false;}
 if(!editing&&puzzle.cells.some((cell,i)=>cell.prefilled&&cell.letter!==trial.cells[i].letter))throw new Error('This would change a prefilled letter. Switch to Edit mode to change it.');
 editConfirmedLetter(trial,targets[0],letter,0);
 if(status!=='confirmed'){changeMappingLetter(trial,number,letter,status,0);for(const i of targets)trial.cells[i].prefilled=false;}
 if(!editing&&puzzle.cells.some((cell,i)=>cell.prefilled&&(cell.letter!==trial.cells[i].letter||!!cell.mappingAnchor!==!!trial.cells[i].mappingAnchor)))throw new Error('This would change a prefilled letter. Switch to Edit mode to change it.');
 return {trial,snapshot,letter,number:String(number),previous,owners,count:targets.length,status};
}
function numberRemovalPlan(puzzle,number,letter,solutionIndex=0,editing=true){
 const info=mappingLetterInfo(puzzle,number,letter,solutionIndex);
 if(!info.indices.length)throw new Error('This number and letter no longer have a displayed match.');
 if(!editing&&info.indices.some(i=>puzzle.cells[i].prefilled&&puzzle.cells[i].letter===letter))throw new Error('This is a prefilled letter. Switch to Edit mode to remove it.');
 const trial=JSON.parse(JSON.stringify(puzzle));
 const snapshot=changeMappingLetter(trial,number,letter,'remove',solutionIndex);
 snapshot.cells.forEach(before=>{before.prefilled=!!puzzle.cells[before.index].prefilled;});
 for(const i of info.indices)trial.cells[i].prefilled=false;
 return {trial,snapshot,letter,number:String(number),count:info.indices.length};
}
function mappingCyclePlan(puzzle,number,letter,solutionIndex=0,editing=true){
 const current=mappingLetterInfo(puzzle,number,letter,solutionIndex).status;
 if(current==='empty')throw new Error('This letter no longer belongs to this number.');
 const action=current==='confirmed'?'suggested':current==='suggested'&&puzzle.rules.maxLettersPerNumber===1?'mapping':'confirmed';
 const trial=JSON.parse(JSON.stringify(puzzle));
 const snapshot=changeMappingLetter(trial,number,letter,action,solutionIndex);
 if(!editing&&puzzle.cells.some((cell,i)=>cell.prefilled&&(cell.letter!==trial.cells[i].letter||!!cell.mappingAnchor!==!!trial.cells[i].mappingAnchor)))throw new Error('This is a prefilled letter. Switch to Edit mode to change its status.');
 if(action==='confirmed')for(const cell of trial.cells)if(!cell.black&&cell.number===String(number)&&cell.letter===letter)cell.prefilled=editing||cell.prefilled;
 if(action==='mapping')for(const cell of trial.cells)if(cell.number===String(number)&&cell.mappingAnchor)cell.prefilled=false;
 return {trial,snapshot,action,letter,number:String(number)};
}
function numberMovePlan(puzzle,sourceNumber,targetNumber,letter,solutionIndex=0,editing=true){
 if(String(sourceNumber)===String(targetNumber))return null;
 const removal=numberRemovalPlan(puzzle,sourceNumber,letter,solutionIndex,editing);
 const assignment=numberAssignmentPlan(removal.trial,targetNumber,letter,0,editing);
 return {...assignment,snapshot:removal.snapshot,sourceNumber:String(sourceNumber)};
}
function resetSuggestions(puzzle){
 for(const cell of puzzle.cells)cell.guess='';
 delete puzzle.suggestions;
 refreshDeductions(puzzle,false);
}
function resetProgress(puzzle){
 for(const cell of puzzle.cells){cell.letter='';cell.guess='';cell.mappingAnchor=false;}
 puzzle.eliminations={};puzzle.rejectedWords=[];
 delete puzzle.suggestions;
}
function undoConfirmation(puzzle,snapshot){
 if(!snapshot)return false;
 for(const before of snapshot.cells){puzzle.cells[before.index].letter=before.letter;puzzle.cells[before.index].guess=before.guess;if(Object.hasOwn(before,'prefilled'))puzzle.cells[before.index].prefilled=before.prefilled;if(Object.hasOwn(before,'mappingAnchor'))puzzle.cells[before.index].mappingAnchor=before.mappingAnchor;}
 if(snapshot.suggestions)puzzle.suggestions=JSON.parse(JSON.stringify(snapshot.suggestions));else delete puzzle.suggestions;
 return true;
}
function acceptanceHistory(limit=20){const entries=[];return {get length(){return entries.length;},push(snapshot){if(snapshot){entries.push(snapshot);if(entries.length>limit)entries.shift();}},pop(){return entries.pop();},clear(){entries.length=0;}};}
function cellWord(puzzle,index,direction='Across',toggle=false,solutionIndex=0){
 const choices=wordChoices(puzzle,solutionIndex).filter(word=>word.cells.includes(index));
 const preferred=toggle?(direction==='Across'?'Down':'Across'):direction;
 return choices.find(word=>word.direction===preferred)||choices[0]||null;
}
function wordChoices(puzzle,solutionIndex=0){return slots(puzzle).map((slot,slotId)=>({...slot,slotId,key:slot.direction+':'+slot.cells.join(','),row:Math.floor(slot.cells[0]/puzzle.cols)+1,col:slot.cells[0]%puzzle.cols+1,provisionalCount:slot.cells.filter(i=>!puzzle.cells[i].letter&&suggestedLetter(puzzle,i,solutionIndex)).length,pattern:(slot.before?'…':'')+slot.cells.map(i=>puzzle.cells[i].letter||suggestedLetter(puzzle,i,solutionIndex)||'·').join('')+(slot.after?'…':'')}));}
// Search-only snapshot: selected hypotheses constrain this request, never the editor.
function candidateSearchPuzzle(puzzle,slotIds,solutionIndex=0){
 const selected=new Set(slots(puzzle).filter((slot,i)=>slotIds.includes(i)).flatMap(slot=>slot.cells));
 return {...puzzle,cells:puzzle.cells.map((cell,i)=>({...cell,letter:cell.black?'':cell.letter||(selected.has(i)?suggestedLetter(puzzle,i,solutionIndex):'')}))};
}
function candidateSelection(choices,keys){return choices.filter(word=>keys.has(word.key)).map(word=>word.slotId).slice(0,8);}
// Imported evidence is not trusted: only rechecked dictionary entries regain a source label.
function restoredWords(puzzle,letters,dictionary){return slots(puzzle).map(slot=>{
 const text=slot.cells.map(i=>letters[i]).join(''),match=puzzle.useDictionary&&dictionary.some(entry=>matchesSlot(text,slot,entry));
 const source=match?(slot.before||slot.after?'fragment':'dictionary'):'unverified';
 return {cells:slot.cells,text,source,verified:source==='dictionary'};
});}
// Letter-pattern assessments are heuristics; they never verify a word.
function plausibilityLabel(assessment){const labels={typical:'Typical pattern',unusual:'Unusual pattern',implausible:'Implausible pattern'};return labels[assessment?.label]||'';}
function plausibilityDetail(assessment){const label=plausibilityLabel(assessment);if(!label)return '';const reasons=assessment.reasons?.length?': '+assessment.reasons.join('; '):'';return `${label}${reasons}. A letter-pattern check, not a dictionary check.`;}
function candidateDisplay(text,assessment){return assessment&&assessment.label!=='typical'&&plausibilityLabel(assessment)?`${text} (${assessment.label})`:text;}
function patternScoreText(assessment){const label=plausibilityLabel(assessment);if(!label)return 'No letter-pattern score for this language';return typeof assessment.bitsPerLetter==='number'?`${label} (score ${assessment.bitsPerLetter.toFixed(2)})`:label;}
// One line per candidate: where it came from, then its letter-pattern score.
function candidateEvidenceText(evidence,assessment,language){const sources={dictionary:'In your word list',fragment:'Part of a listed word (open word end)',morphology:language==='fi'?'In the Finnish form index, not in your word list':'In the form index, not in your word list',generated:'Not in the dictionary: pattern guess'};const origin=sources[evidence?.source]||'Dictionary status unknown';const reasons=assessment?.reasons?.length?' · '+assessment.reasons.join('; '):'';return `${origin} · ${patternScoreText(assessment)}${reasons}`;}
function wordLookupText(result){const where=result.disabled?'Disabled in dictionary':result.inDictionary?'In your word list':result.inMorphology?'In the Finnish form index, not in your word list':'Not in your word list';const reasons=result.plausibility?.reasons?.length?' · '+result.plausibility.reasons.join('; '):'';return `${where} · ${patternScoreText(result.plausibility)}${reasons}`;}
// A selected word with every cell filled (confirmed or displayed suggestion).
function completeWordText(puzzle,word,solutionIndex=0){if(!word)return null;const letters=word.cells.map(i=>puzzle.cells[i].letter||suggestedLetter(puzzle,i,solutionIndex)||'');if(letters.some(letter=>!letter))return null;return {text:letters.join(''),provisional:word.provisionalCount>0,partial:!!(word.before||word.after)};}
function selectedWordCheckText(result,full){return `${result.word}: ${wordLookupText(result)}`+(full?.provisional?' · includes provisional letters':'');}
// Words typed into the add box: spaces, commas or new lines separate them.
function dictionaryInputWords(text){return String(text||'').split(/[\s,;]+/).map(normalize).filter(Boolean);}
function dictionarySearchSummary(result){if(!result.total)return result.query?`No ${result.status==='all'?'':result.status+' '}words match ${result.query}.`:`No ${result.status==='all'?'':result.status+' '}words.`;const last=Math.min(result.offset+result.words.length,result.total);return `${result.total.toLocaleString('en')} ${result.status==='all'?'':result.status+' '}${result.total===1?'word':'words'}${result.query?(result.total===1?' matches ':' match ')+result.query:''} · showing ${(result.offset+1).toLocaleString('en')}–${last.toLocaleString('en')}`;}
// Confirmed letters stay letters, numbered cells become numbers, others ?.
function lookupPattern(puzzle,cells){return cells.map(i=>{const cell=puzzle.cells[i];if(cell.letter)return cell.letter;if(cell.number)return String(Number(cell.number));return '?';}).join(' ');}
function wordAssessmentQueue(request,onChange=()=>{},options={}){
 const schedule=options.schedule||((fn,ms)=>setTimeout(fn,ms)),unschedule=options.unschedule||(timer=>clearTimeout(timer));
 const limit=options.concurrency||2,records=new Map();let generation=0,active=0,timer=null,queue=[];
 const keyFor=(puzzle,text)=>[puzzle.language,puzzle.useMorphology!==false,text].join('|');
 function pump(){
  if(timer!==null)unschedule(timer);timer=null;
  while(active<limit&&queue.length){
   const record=queue.shift();if(record.generation!==generation||records.get(record.key)!==record)continue;
   active++;record.status='loading';
   Promise.resolve().then(()=>request('/api/lookup',record.payload)).then(result=>{
    if(record.generation!==generation||records.get(record.key)!==record)return;
    if(result.kind!=='word'||result.word!==record.payload.query)throw new Error('The word check returned an unexpected result.');
    record.status='ready';record.result=result;onChange(record.key);
   }).catch(error=>{
    if(record.generation!==generation||records.get(record.key)!==record)return;
    record.status='error';record.error=error.message||String(error);onChange(record.key);
   }).finally(()=>{active--;pump();});
  }
 }
 function enqueue(record){record.status='queued';queue.push(record);if(timer===null)timer=schedule(pump,180);}
 return {
  ensure(puzzle,word){
   if(word.unknownCount||!word.text||word.text.includes('·'))return {status:'incomplete'};
   if(word.before||word.after)return {status:'fragment'};
   const key=keyFor(puzzle,word.text);if(records.has(key)){const found=records.get(key);records.delete(key);records.set(key,found);return found;}
   // Bound settled cache entries without evicting in-flight requests.
   if(records.size>=5000)for(const [oldKey,old]of records){if(['ready','error'].includes(old.status)){records.delete(oldKey);if(records.size<4000)break;}}
   const record={key,generation,status:'queued',payload:{puzzle:{name:'Word check',language:puzzle.language,rows:1,cols:word.text.length,cells:[...word.text].map(letter=>({black:false,number:'',letter})),rules:JSON.parse(JSON.stringify(puzzle.rules)),useDictionary:true,useMorphology:puzzle.useMorphology!==false},query:word.text}};
   records.set(key,record);enqueue(record);return record;
  },
  clear(language){if(language){for(const [key,record]of records)if(record.payload.puzzle.language===language)records.delete(key);queue=queue.filter(record=>record.payload.puzzle.language!==language);if(!queue.length&&timer!==null){unschedule(timer);timer=null;}}else{generation++;records.clear();queue=[];if(timer!==null)unschedule(timer);timer=null;}},
  retryErrors(){for(const record of records.values())if(record.status==='error'){delete record.error;enqueue(record);}},
  get size(){return records.size;}
 };
}
function assessedWord(word,assessment){
 const status=assessment.status;
 if(status==='fragment')return {...word,source:word.source==='fragment'?'fragment':'unverified',verified:false,plausibility:word.source==='fragment'?word.plausibility:undefined,assessmentStatus:status};
 const base={...word,source:'unverified',verified:false,plausibility:undefined,analyses:undefined,evidence:undefined,details:undefined,assessmentStatus:status};
 if(status!=='ready')return {...base,assessmentError:assessment.error};
 const result=assessment.result;
 return {...base,source:result.inDictionary?'dictionary':result.inMorphology?'morphology':'unverified',verified:!!(result.inDictionary||result.inMorphology),plausibility:result.plausibility,analyses:result.analyses||[],dictionaryChecked:true,inDictionary:!!result.inDictionary,disabledInDictionary:!!result.disabled};
}
function assessedWordLabel(word){
 if(word.assessmentStatus==='incomplete')return 'Incomplete word';
 if(word.assessmentStatus==='fragment')return word.source==='fragment'?'Dictionary fragment (open word)':'Open word fragment';
 if(['queued','loading'].includes(word.assessmentStatus))return 'Checking dictionary and pattern…';
 if(word.assessmentStatus==='error')return 'Word check failed: '+word.assessmentError;
 if(word.dictionaryChecked&&word.disabledInDictionary)return word.source==='morphology'?'Disabled in dictionary · Morphology match':'Disabled in dictionary';
 if(word.dictionaryChecked)return word.inDictionary?'Dictionary match':word.source==='morphology'?'Morphology match · Not in dictionary':'Not in dictionary';
 return ({dictionary:'Dictionary match',morphology:'Morphology match',fragment:'Dictionary fragment',unverified:'Unverified'})[solvedWordEvidence(word)];
}
function displayedPuzzleWords(puzzle,solutionIndex=0){
 const evidence=puzzle.suggestions?.solutions?.[solutionIndex]?.words||[];
 return slots(puzzle).map(slot=>{
  const letters=slot.cells.map(i=>puzzle.cells[i].letter||suggestedLetter(puzzle,i,solutionIndex)||'');
  const text=letters.map(letter=>letter||'·').join('');
  const match=letters.every(Boolean)?evidence.find(word=>word.text===text&&Array.isArray(word.cells)&&word.cells.length===slot.cells.length&&word.cells.every((index,i)=>index===slot.cells[i])):null;
  return {...(match||{source:'unverified',verified:false}),cells:[...slot.cells],direction:slot.direction,before:slot.before,after:slot.after,text,unknownCount:letters.filter(letter=>!letter).length};
 });
}
function solvedWordEvidence(word){
 if(word.source==='dictionary'&&word.verified===true)return 'dictionary';
 if(word.source==='morphology'&&word.verified===true)return 'morphology';
 if(word.source==='fragment')return 'fragment';
 return 'unverified';
}
function solvedWordsView(words,filter='all',sort='uncertain',language='en'){
 const evidenceRank={unverified:0,morphology:1,fragment:1,dictionary:2};
 const patternRank={unassessed:0,implausible:1,unusual:2,typical:3};
 const label=word=>Object.hasOwn(patternRank,word.plausibility?.label)?word.plausibility.label:'unassessed';
 const score=word=>Number.isFinite(word.plausibility?.bitsPerLetter)?word.plausibility.bitsPerLetter:null;
 const rows=(words||[]).map((word,index)=>({word,index,evidence:solvedWordEvidence(word)})).filter(row=>filter==='no-dictionary'?row.evidence!=='dictionary':filter==='unverified'?!['dictionary','morphology'].includes(row.evidence):filter==='dictionary'?row.evidence==='dictionary':true);
 if(sort==='alphabetical')rows.sort((a,b)=>String(a.word.text||'').localeCompare(String(b.word.text||''),['en','fi','nl','sv'].includes(language)?language:'en')||a.index-b.index);
 else if(sort!=='grid')rows.sort((a,b)=>{
  const tier=evidenceRank[a.evidence]-evidenceRank[b.evidence]||patternRank[label(a.word)]-patternRank[label(b.word)];if(tier)return tier;
  const av=score(a.word),bv=score(b.word);return (av===null&&bv!==null?-1:bv===null&&av!==null?1:av!==null&&bv!==null?av-bv:0)||a.index-b.index;
 });
 return rows.map(row=>row.word);
}
function solvedWordSelection(puzzle,word){
 if(!Array.isArray(word?.cells)||word.cells.length<2)return null;
 const slot=slots(puzzle).find(slot=>slot.cells.length===word.cells.length&&slot.cells.every((index,i)=>index===word.cells[i]));
 return slot?{cells:[...slot.cells],index:slot.cells[0],direction:slot.direction}:null;
}
function solvedWordActions(puzzle,word,solutionIndex=0,editing=true){const confirm=word.cells.some(i=>!puzzle.cells[i].letter&&suggestedLetter(puzzle,i,solutionIndex)),unconfirm=word.cells.some(i=>!!puzzle.cells[i].letter&&(editing||!puzzle.cells[i].prefilled));return {confirm,unconfirm,confirmLabel:'Confirm',unconfirmLabel:'Unconfirm'};}
function solvedWordPatternScore(word){if(['incomplete','queued','loading','error'].includes(word.assessmentStatus))return '';const score=word.plausibility?.bitsPerLetter;return Number.isFinite(score)?`Pattern score ${score.toFixed(2)}`:'Pattern score unavailable';}
function wordEvidenceLabel(word){if(word.source==='fragment')return 'Dictionary fragment';if(word.source==='morphology')return 'Morphology match';if(word.source==='dictionary'&&word.verified)return 'Dictionary match';return 'Unverified';}
// Each request has its own identity. Cancellation also handles an outstanding POST.
function solveRunner({request,path='/api/solve-jobs',onUpdate=()=>{},onError=()=>{},onBusy=()=>{},onCancelError=()=>{},onStopping=()=>{},delay=()=>new Promise(resolve=>setTimeout(resolve,500))}){
 let active=null;
 async function stop(job){if(!job.id||job.cancelSent)return;job.cancelSent=true;try{await request(path+'/'+encodeURIComponent(job.id),undefined,'DELETE');}catch(error){if(active===job){job.cancelSent=false;job.cancelRequested=false;onStopping(false);}onCancelError(error);}}
 function cancel(){if(!active)return;const job=active;active=null;job.cancelled=true;onBusy(false);void stop(job);}
 function requestCancel(){if(!active||active.cancelRequested)return;active.cancelRequested=true;onStopping(true);void stop(active);}
 async function start(snapshot){
  cancel();const job={id:null,cancelled:false,cancelSent:false,cancelRequested:false};active=job;onBusy(true);
  try{
   let state=await request(path,snapshot,'POST');job.id=state.id;
   if(active!==job){await stop(job);return;}
   if(job.cancelRequested)await stop(job);
   while(active===job){
    onUpdate(state,job.cancelRequested);
    if(state.status!=='running'&&state.status!=='queued')break;
    await delay();if(active!==job)return;
    state=await request(path+'/'+encodeURIComponent(job.id));
   }
  }catch(error){if(active===job){await stop(job);if(active===job)onError(error);}}
  finally{if(active===job){active=null;onBusy(false);}}
 }
 return {start,cancel,requestCancel,get running(){return !!active;}};
}
// While a search runs, any change to the puzzle cancels it, so such an input
// asks first. kind: button (including checkboxes and file inputs), select,
// text, number, range, drag or other.
// Inputs on safe controls (viewing, zooming, help, lookups) and moving around
// the grid never ask; typing into the grid does.
function searchInterruption({type,key='',kind,safe=false,grid=false,modifier=false}){
 if(safe)return false;
 if(grid)return type==='keydown'&&!modifier&&(key.length===1||key==='Backspace'||key==='Delete');
 if(type==='dragstart')return true;
 if(type==='click')return kind==='button';
 if(type==='mousedown')return kind==='select'||kind==='number';
 if(type==='beforeinput')return kind==='text'||kind==='number';
 if(type==='keydown')return kind==='select'&&!['Tab','Escape','Shift','Control','Alt','Meta'].includes(key)||kind==='number'&&(key==='ArrowUp'||key==='ArrowDown');
 return false;
}
// A generated puzzle keeps its answer, letters per cell, for checking and
// printing only. It applies while the black cells and numbers are unchanged.
function generatedAnswer(puzzle){
 const generated=puzzle?.generated;
 if(!generated||!Array.isArray(generated.answer)||!Array.isArray(generated.numbers)||generated.answer.length!==puzzle.cells.length||generated.numbers.length!==puzzle.cells.length)return null;
 const matches=puzzle.cells.every((cell,i)=>cell.black?!generated.answer[i]:!!generated.answer[i]&&String(cell.number||'')===generated.numbers[i]);
 return matches?generated.answer:null;
}
// Confirmed letters against the answer. Suggestions are not counted.
function answerCheck(puzzle){
 const answer=generatedAnswer(puzzle);if(!answer)return null;
 const wrong=[];let right=0,empty=0,total=0;
 puzzle.cells.forEach((cell,i)=>{if(cell.black)return;total++;if(!cell.letter)empty++;else if(cell.letter===answer[i])right++;else wrong.push(i);});
 return {right,wrong,empty,total,solved:right===total};
}
function answerCheckText(check){
 if(check.solved)return `Solved: all ${check.total} letters match the answer.`;
 const entered=check.total-check.empty,wrong=check.wrong.length;
 if(!entered)return `No letters yet; ${check.total} cells to fill.`;
 return `${entered} of ${check.total} cells filled: ${check.right} right, ${wrong} wrong${wrong?' (outlined in red)':''}. ${check.empty} cell${check.empty===1?'':'s'} still empty.`;
}
// Words of the drawn grid as the generator counts them: runs of two or more
// letter cells. loose counts letter cells that are in no word.
function layoutSummary(puzzle){
 const runs=slots(puzzle),lengths=runs.map(s=>s.cells.length),covered=new Set(runs.flatMap(s=>s.cells));
 return {words:runs.length,shortest:lengths.length?Math.min(...lengths):0,longest:lengths.length?Math.max(...lengths):0,
  loose:puzzle.cells.filter((c,i)=>!c.black&&!covered.has(i)).length};
}
// Shown in the grid summary line, for example "71 words of 4–10 letters".
function layoutSummaryText(summary){
 if(!summary.words)return 'no words yet';
 const lengths=summary.shortest===summary.longest?`${summary.shortest} letters`:`${summary.shortest}–${summary.longest} letters`;
 return `${summary.words} word${summary.words===1?'':'s'} of ${lengths}`+(summary.loose?` · ${summary.loose} cell${summary.loose===1?'':'s'} in no word`:'');
}
// Whether the grid already matches a word layout target.
function meetsLayout(summary,target){return !summary.loose&&summary.words===target.words&&summary.shortest>=target.shortest&&summary.longest<=target.longest;}
const LEVEL_NAMES={easy:'Easy',medium:'Medium',hard:'Hard'};
const LEVEL_MEANING={easy:'it can be solved word by word',medium:'in places it needs letters that every fitting word agrees on',hard:'deduction alone does not solve it everywhere'};
function generatedSummary(result){
 const {words,distinctLetters,extraGivens=0,included=0}=result.stats,givens=result.givens||[];
 const filled=`Generated ${words} words using ${distinctLetters} letters, ${givens.length} given (${givens.join(', ')||'none'}).`+(included?` ${included===1?'The word you listed is':included===2?'Both words you listed are':`All ${included} words you listed are`} included.`:'');
 const graded=['easy','medium'].includes(result.difficulty);
 const asked=result.stats.starters,why=graded?'to reach the difficulty':'to rule out other answers';
 const extra=extraGivens?` ${extraGivens} ${extraGivens===1?'letter was':'letters were'} added ${why}`+(asked!==undefined?` (you asked for ${asked} starter letter${asked===1?'':'s'}).`:'.'):'';
 const askedLevel=result.difficulty&&result.difficulty!=='any'?result.difficulty:null;
 const level=result.grade?` Difficulty: ${LEVEL_NAMES[result.grade]}; ${LEVEL_MEANING[result.grade]}.`+(askedLevel&&askedLevel!==result.grade?` You asked for ${LEVEL_NAMES[askedLevel]}; this was the closest after trying other starter letters.`:''):askedLevel?' The difficulty could not be checked in time.':'';
 if(result.uniqueness==='unique')return `${filled}${extra} Only one answer fits with the current dictionary.${level}`;
 if(result.uniqueness==='unconfirmed')return `${filled}${extra} A single answer is not confirmed: the check stopped at its time limit.${level}`;
 return `${filled} Not checked for other answers.${level}`;
}
// Finnish and Swedish add Å, Ä and Ö to A–Z.
function nordicLetters(language){return language==='fi'||language==='sv';}
function languagePresentation(puzzle){
 const showMorphology=puzzle.language==='fi';
 return {name:({en:'English',fi:'Finnish',nl:'Dutch',sv:'Swedish'})[puzzle.language]||puzzle.language,showMorphology,
 candidateExplanation:!puzzle.useDictionary?'These are language-pattern guesses and can include invented words.':showMorphology&&puzzle.useMorphology!==false?'Candidates come from the current word list and, when enabled and available, the local Finnish form index. Source information is shown below. Neither list membership nor generated morphology establishes the intended answer.':'Candidates come from the current word list. Source information is shown below. List membership does not establish the intended answer.'};
}
function dictionaryPages(text='',size=1000){
 const lines=text.split(/\r?\n/),pages=[];
 for(let i=0;i<lines.length;i+=size)pages.push(lines.slice(i,i+size).join('\n'));
 return {get count(){return pages.length;},page(index){return pages[index];},update(index,value){pages[index]=value;},text(){return pages.join('\n');}};
}
function dictionaryEditor(request,onLoaded,onSaved,onCommitted=()=>{},onBusy=()=>{}){
 let token=0,language=null,saving=null,reading=false,imported=false;
 const busy=()=>onBusy(!!saving||reading);
 return {
  cancel(){token++;language=null;imported=false;},
  manualEdit(){imported=false;},
  async open(nextLanguage){
   const current=++token;language=nextLanguage;imported=false;
   if(saving){try{await saving;}catch{}}
   if(current!==token)return;
   const data=await request('/api/dictionaries/'+nextLanguage);if(current===token)onLoaded(data);
  },
  async readFile(read){
   if(reading||saving)throw new Error('Wait for the current dictionary operation to finish.');
   const current=token;reading=true;busy();
   try{const text=await read();if(current!==token)return null;imported=true;return text;}
   finally{reading=false;busy();}
  },
  async save(text,fromFile=imported){
   if(reading)throw new Error('Wait until the dictionary file has finished reading.');
   if(saving)throw new Error('Wait until the dictionary has finished saving.');
   if(!language)throw new Error('Open a language dictionary first.');
   const current=token,target=language,importing=fromFile||!!text.trim();
   saving=request('/api/dictionaries/'+target+(importing?'/import':''),importing?{text}:{words:[]},importing?'POST':'PUT');busy();
   try{const result=await saving;
    onCommitted({...result,language:target,importing});
    if(current===token)onSaved({...result,language:target,importing});
   }finally{saving=null;busy();}
  }
 };
}
// Ruled-out letters (number cannot be letter) and rejected words for one
// slot are user decisions for this puzzle. The solver treats both as hard rules.
function canonicalEliminations(value){const result={};if(!value||typeof value!=='object'||Array.isArray(value))return result;for(const [number,letters] of Object.entries(value)){if(!/^\d+$/.test(number)||!Array.isArray(letters))continue;const key=String(Number(number)),set=new Set([...(result[key]||[]),...letters.filter(l=>typeof l==='string').map(normalize)]);if(set.size)result[key]=[...set].sort();}return result;}
function ruledOutLetters(puzzle,number){return number?puzzle.eliminations?.[String(Number(number))]||[]:[];}
function setRuledOut(puzzle,number,letters,ruledOut=true){const key=String(Number(number)),current=new Set(ruledOutLetters(puzzle,key)),before=current.size;for(const letter of letters)ruledOut?current.add(normalize(letter)):current.delete(normalize(letter));if(current.size===before&&letters.every(l=>current.has(normalize(l))===ruledOut))return false;puzzle.eliminations={...puzzle.eliminations};if(current.size)puzzle.eliminations[key]=[...current].sort();else delete puzzle.eliminations[key];return true;}
// Letters per number as the grid shows them: confirmed, and confirmed or
// displayed (suggestion, mapping deduction or pencil mark).
function numberLetterSets(puzzle,solutionIndex=0){const sets=new Map();puzzle.cells.forEach((c,i)=>{if(c.black||!c.number)return;const key=String(Number(c.number));if(!sets.has(key))sets.set(key,{confirmed:new Set(),shown:new Set()});const entry=sets.get(key),shown=c.letter||suggestedLetter(puzzle,i,solutionIndex);if(c.letter)entry.confirmed.add(c.letter);if(shown)entry.shown.add(shown);});return sets;}
// Ruled-out letters worth showing: only numbers in the grid without a
// displayed letter. For a confirmed number, a ruled-out confirmed letter
// (a conflict) stays visible. Hidden entries stay stored and apply again
// once the number is open.
function visibleRuledOut(puzzle,solutionIndex=0){const sets=numberLetterSets(puzzle,solutionIndex);return Object.entries(puzzle.eliminations||{}).filter(([number])=>sets.has(number)).map(([number,letters])=>{const {confirmed,shown}=sets.get(number);return {number,confirmed:confirmed.size>0,letters:confirmed.size?letters.filter(letter=>confirmed.has(letter)):shown.size?[]:letters};}).filter(entry=>entry.letters.length).sort((a,b)=>Number(a.number)-Number(b.number));}
function numberIsOpen(puzzle,number,solutionIndex=0){const entry=numberLetterSets(puzzle,solutionIndex).get(String(Number(number)));return !!entry&&!entry.shown.size;}
function slotIdentity(slot){return {start:slot.cells[0],direction:slot.direction};}
function rejectedWordsFor(puzzle,slot){if(!slot)return [];const {start,direction}=slotIdentity(slot);return (puzzle.rejectedWords||[]).filter(entry=>entry.start===start&&entry.direction===direction).map(entry=>entry.word);}
function setWordRejected(puzzle,slot,word,rejected=true){const {start,direction}=slotIdentity(slot),text=normalize(word),has=rejectedWordsFor(puzzle,slot).includes(text);if(has===rejected)return false;puzzle.rejectedWords=rejected?[...(puzzle.rejectedWords||[]),{start,direction,word:text}]:(puzzle.rejectedWords||[]).filter(entry=>!(entry.start===start&&entry.direction===direction&&entry.word===text));return true;}
// Groups the server's suggestions by number. Leaves out numbers that show a
// letter, letters already ruled out, and (with unique letters) letters the
// grid shows on another number.
function eliminationSuggestionGroups(puzzle,suggestions,solutionIndex=0){const sets=numberLetterSets(puzzle,solutionIndex),taken=new Set(),groups=new Map();if(puzzle.rules?.uniqueLetters!==false)for(const {shown} of sets.values())for(const letter of shown)taken.add(letter);for(const s of Array.isArray(suggestions)?suggestions:[]){const number=String(Number(s.number));if(!sets.has(number)||sets.get(number).shown.size||taken.has(s.letter)||ruledOutLetters(puzzle,number).includes(s.letter))continue;if(!groups.has(number))groups.set(number,[]);groups.get(number).push({letter:s.letter,run:s.run});}return [...groups].sort((a,b)=>Number(a[0])-Number(b[0])).map(([number,letters])=>({number,letters}));}
// What the header, storage buttons and dictionary dialog show for the
// server's access level: local, guest, user, or signed-out (hosted without
// guest access). Hosted recovery copies stay in the browser, so people
// sharing a server never overwrite each other's workspace.
function workspaceModeView(info){
 const mode=['local','guest','user','signed-out'].includes(info?.mode)?info.mode:'local',limits=info?.guestLimits||{};
 const guest=mode==='guest',user=mode==='user',words=limits.words||200000,megabytes=limits.importMegabytes||4,hours=limits.idleHours||2;
 return {mode,
  label:mode==='local'?'Local workspace':user?'User mode · saved on the server':guest?'Guest mode · not saved on the server':'Sign-in required',
  serverStorage:mode==='local'||user,autosave:mode==='local'?'server':'browser',
  modeButton:user?'Leave user mode':guest&&info.userLogin?'User mode':null,
  savedWhere:user?'on the server':'locally',
  customDictionary:guest?'Temporary guest dictionary':user?'Shared dictionary':'Custom local dictionary',
  maxImportBytes:guest?megabytes*1024*1024:16*1024*1024,
  dictionaryNote:guest?`Guest mode: dictionary changes apply only to this browser session and are removed after ${hours} hours without use. Up to ${words.toLocaleString('en')} words and ${megabytes} MB.`:''};
}
// Saved-puzzle list: language filter options (only languages present, with
// counts) and the rows for the chosen language. An unknown choice shows all.
function savedPuzzleView(items,language=''){
 const counts=new Map();for(const item of items)counts.set(item.language||'',(counts.get(item.language||'')||0)+1);
 const languages=[...counts].map(([code,count])=>({code,count,name:code?languagePresentation({language:code}).name:'Unknown'})).sort((a,b)=>a.name.localeCompare(b.name));
 const selected=counts.has(language)?language:'';
 return {languages,selected,items:selected?items.filter(item=>(item.language||'')===selected):items};
}
// Preparation stages run before the search budget starts.
const PREPARATION_STAGES=new Set(['preparing','adapting_letter_model','indexing_dictionary']);
function solveProgressText(progress,stopping){
 const p=progress||{},stage=String(p.stage||'preparing'),seconds=`${Number(p.elapsedSeconds||0).toFixed(1)} seconds`;
 if(stopping)return `Stopping search · ${seconds}`;
 if(PREPARATION_STAGES.has(stage))return `Preparing: ${stage==='preparing'?'loading puzzle and dictionary':stage.replaceAll('_',' ')} · ${seconds} · search time starts after this`;
 return `${stage.replaceAll('_',' ')} · ${Number(p.nodes||0).toLocaleString()} search nodes · ${seconds} · ${Number(p.solutionsFound||0)} suggestions found`;
}
// numberPosition is where the puzzle prints its numbers. Over an image the
// app's numbers go in the opposite corner so they do not cover the print.
function displayNumberPosition(puzzle){const position=['top-left','top-right','bottom-left','bottom-right'].includes(puzzle.numberPosition)?puzzle.numberPosition:'top-left';if(!puzzle.image)return position;const [vertical,horizontal]=position.split('-');return `${vertical==='top'?'bottom':'top'}-${horizontal==='left'?'right':'left'}`;}
const helpers={displayNumberPosition,layoutSummary,layoutSummaryText,meetsLayout,generatedSummary,generatedAnswer,answerCheck,answerCheckText,letterCertainty,savedPuzzleView,renumberCell,workspaceModeView,visibleRuledOut,numberIsOpen,canonicalEliminations,ruledOutLetters,setRuledOut,slotIdentity,rejectedWordsFor,setWordRejected,eliminationSuggestionGroups,wordAssessmentQueue,assessedWord,assessedWordLabel,displayedPuzzleWords,solvedWordActions,solvedWordEvidence,solvedWordsView,solvedWordSelection,solvedWordPatternScore,mappingCyclePlan,numberMovePlan,clearMappingProvenance,numberRemovalPlan,numberAssignmentPlan,dictionaryInputWords,dictionarySearchSummary,nordicLetters,completeWordText,selectedWordCheckText,patternScoreText,candidateEvidenceText,wordLookupText,lookupPattern,dictionaryPages,languagePresentation,dictionaryEditor,cellWord,letterOwners,moveLetterAssignment,resetSuggestions,editConfirmedLetter,cancelledResult,searchInterruption,solveProgressText,solveStopExplanation,hasSolveProgress,mappingLetterInfo,changeMappingLetter,resetProgress,suggestionLabel,restoredWords,wordEvidenceLabel,plausibilityLabel,plausibilityDetail,candidateDisplay,solveRunner,canonicalPuzzle,slots,candidateLetters,matchesSlot,blankCell,numberEntry,imageBoundsFromPercent,fitScale,suggestedLetter,mappingDeductions,solveSummary,refreshDeductions,confirmCells,unconfirmCells,numberCells,undoConfirmation,acceptanceHistory,wordChoices,candidateSelection,candidateSearchPuzzle};if(typeof module!=='undefined'&&module.exports)module.exports=helpers;else root.PuzzleState=helpers;
})(typeof globalThis!=='undefined'?globalThis:this);
