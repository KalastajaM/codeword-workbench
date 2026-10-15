'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),S=require('../static/state.js');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const puzzle=(language='en')=>({language,useDictionary:false,useMorphology:true,rules:{maxLettersPerNumber:1,uniqueLetters:true,forbiddenPatterns:[],discouragedPatterns:[]}});
function harness(){let next=0;const scheduled=new Map(),calls=[],changed=[];const queue=S.wordAssessmentQueue((path,payload)=>new Promise((resolve,reject)=>calls.push({path,payload,resolve,reject})),key=>changed.push(key),{schedule(fn){scheduled.set(++next,fn);return next;},unschedule(id){scheduled.delete(id);}});return {queue,calls,changed,flush(){const jobs=[...scheduled.values()];scheduled.clear();jobs.forEach(fn=>fn());}};}
const answer=(word,extras={})=>({kind:'word',word,inDictionary:true,plausibility:{label:'typical',bitsPerLetter:-3},...extras});
test('Closed complete words queue automatically regardless solver mode; incomplete/fragments never request',async()=>{
 const h=harness(),p=puzzle();assert.equal(h.queue.ensure(p,{text:'C·T',unknownCount:1}).status,'incomplete');assert.equal(h.queue.ensure(p,{text:'CAT',after:true}).status,'fragment');
 const record=h.queue.ensure(p,{text:'CAT'});assert.equal(h.queue.ensure(p,{text:'CAT'}),record);assert.equal(h.calls.length,0);p.language='fi';p.rules.uniqueLetters=false;
 h.flush();await tick();assert.equal(h.calls.length,1);assert.equal(h.calls[0].payload.puzzle.useDictionary,true);assert.equal(h.calls[0].payload.puzzle.language,'en');assert.equal(h.calls[0].payload.puzzle.rules.uniqueLetters,true);
 h.calls[0].resolve(answer('CAT'));await tick();assert.equal(record.status,'ready');assert.equal(h.queue.ensure(puzzle(),{text:'CAT'}),record);
});
test('Assessment requests are deduplicated and run at most two concurrently',async()=>{
 const h=harness();for(const text of ['CAT','DOG','BAT','RAT'])h.queue.ensure(puzzle(),{text});h.flush();await tick();assert.equal(h.calls.length,2);
 h.calls[0].resolve(answer('CAT'));await tick();assert.equal(h.calls.length,3);h.calls[1].resolve(answer('DOG'));await tick();assert.equal(h.calls.length,4);
 h.calls[2].resolve(answer('BAT'));h.calls[3].resolve(answer('RAT'));await tick();assert.equal(h.changed.length,4);
});
test('Dictionary-generation invalidation prevents an old in-flight result repopulating cache',async()=>{
 const h=harness(),p=puzzle();h.queue.ensure(p,{text:'CAT'});h.flush();await tick();h.queue.clear();const fresh=h.queue.ensure(p,{text:'CAT'});h.flush();await tick();assert.equal(h.calls.length,2);
 h.calls[0].resolve(answer('CAT'));await tick();assert.equal(fresh.status,'loading');assert.equal(h.changed.length,0);
 h.calls[1].resolve(answer('CAT',{inDictionary:false,disabled:true}));await tick();assert.equal(fresh.result.inDictionary,false);assert.equal(h.changed.length,1);assert.match(S.assessedWordLabel(S.assessedWord({text:'CAT'},fresh)),/Disabled in dictionary/);
});
test('Language and morphology keys isolate delayed results, errors wait for explicit retry',async()=>{
 const h=harness(),en=h.queue.ensure(puzzle('en'),{text:'CAT'}),fi=h.queue.ensure(puzzle('fi'),{text:'CAT'});assert.notEqual(en,fi);assert.notEqual(fi,h.queue.ensure({...puzzle('fi'),useMorphology:false},{text:'CAT'}));
 h.flush();await tick();h.calls[0].reject(new Error('offline'));await tick();assert.equal(en.status,'error');assert.equal(h.queue.ensure(puzzle('en'),{text:'CAT'}),en);assert.equal(h.calls.length,3);
 h.calls[1].resolve(answer('CAT'));h.calls[2].resolve(answer('CAT'));await tick();h.queue.retryErrors();h.flush();await tick();assert.equal(h.calls.length,4);h.calls[3].resolve(answer('CAT'));await tick();assert.equal(en.status,'ready');
});
test('Loading, error and incomplete assessments remove old evidence; ready answers provide current analyses',()=>{
 const word={text:'CAT',source:'dictionary',verified:true,plausibility:{label:'typical',bitsPerLetter:-2},analyses:[{lemma:'old'}]};
 for(const status of ['queued','loading','error','incomplete']){const result=S.assessedWord(word,{status,error:'offline'});assert.equal(result.verified,false);assert.equal(result.plausibility,undefined);assert.equal(result.analyses,undefined);assert.equal(S.solvedWordPatternScore(result),'');}
 assert.equal(S.assessedWordLabel(S.assessedWord(word,{status:'incomplete'})),'Incomplete word');
 const result=S.assessedWord(word,{status:'ready',result:answer('CAT',{inDictionary:false,inMorphology:true,analyses:[{lemma:'new'}]})});assert.equal(result.source,'morphology');assert.equal(result.analyses[0].lemma,'new');assert.match(S.assessedWordLabel(result),/Not in dictionary/);
});
test('Selected-word and row descriptions agree that a dictionary entry is disabled',()=>{
 const result=answer('CAT',{inDictionary:false,disabled:true});assert.match(S.wordLookupText(result),/^Disabled in dictionary/);assert.match(S.selectedWordCheckText(result,{provisional:false}),/Disabled in dictionary/);assert.equal(S.assessedWordLabel(S.assessedWord({text:'CAT'},{status:'ready',result})),'Disabled in dictionary');
});
test('Cache holds every possible current-grid word without repeated lookup churn above 1000 entries',async()=>{
 let timer,calls=0;const queue=S.wordAssessmentQueue(async(_path,payload)=>{calls++;return answer(payload.query);},()=>{},{schedule(fn){timer=fn;return 1;},unschedule(){}});
 const texts=Array.from({length:1600},(_,i)=>[Math.floor(i/676),Math.floor(i/26)%26,i%26].map(n=>String.fromCharCode(65+n)).join(''));
 for(const text of texts)queue.ensure(puzzle(),{text});timer();await tick();assert.equal(calls,1600);assert.equal(queue.size,1600);
 for(const text of texts)assert.equal(queue.ensure(puzzle(),{text}).status,'ready');await tick();assert.equal(calls,1600);
});
test('Saving an old language invalidates only its checks, leaving the current language loading and cache intact',async()=>{
 const h=harness(),en=h.queue.ensure(puzzle('en'),{text:'CAT'}),nl=h.queue.ensure(puzzle('nl'),{text:'KAT'});h.flush();await tick();assert.equal(h.calls.length,2);
 h.queue.clear('en');assert.equal(h.queue.ensure(puzzle('nl'),{text:'KAT'}),nl);h.calls[0].resolve(answer('CAT'));h.calls[1].resolve(answer('KAT'));await tick();assert.equal(nl.status,'ready');assert.equal(h.changed.length,1);assert.match(h.changed[0],/^nl\|/);assert.notEqual(h.queue.ensure(puzzle('en'),{text:'CAT'}),en);
});
