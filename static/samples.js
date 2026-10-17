/* Bundled sample puzzles. The showcase grid is original: built by
   scripts/build_sample_puzzle.py from common English words, then numbered
   with a fixed key. Its answer is kept so the app can report how many cells
   a search got right; the answer never fills the grid by itself. */
(function(root){
'use strict';
const SHOWCASE={
 id:'showcase-en',
 name:'Showcase · full-size codeword, no dictionary',
 language:'en',
 answer:['LUCY#STOPPING','E#O###H#I#S#E','ACRE#DOWNTOWN','N#E#D#U#E#L#E','###LODGE#HAIR','S#I#I#H#K#T#A','TUNING#INTENT',
  'R#T#G#C#O#D#E','EVEN#MATCH###','N#R#B#N#K#C#F','GUIDANCE#TAIL','T#O#L#E###L#E','HORRIBLE#FLUX'],
 key:{A:6,B:19,C:22,D:16,E:8,F:15,G:23,H:21,I:7,K:20,L:14,M:17,N:9,O:1,P:10,R:12,S:4,T:18,U:3,V:2,W:13,X:5,Y:11}
};
function sampleCells(sample){
 return sample.answer.join('').split('').map(ch=>({black:ch==='#',number:ch==='#'?'':String(sample.key[ch]),letter:'',
  openBeforeAcross:false,openAfterAcross:false,openBeforeDown:false,openAfterDown:false}));
}
function samplePuzzle(sample=SHOWCASE){
 return {name:sample.name,rows:sample.answer.length,cols:sample.answer[0].length,language:sample.language,
  useDictionary:false,searchMode:'deep',sample:sample.id,cells:sampleCells(sample)};
}
// Cells a suggestion gets right, or null when the grid no longer matches the sample.
function compareWithSample(puzzle,letters){
 const sample=[SHOWCASE].find(s=>s.id===puzzle?.sample);
 if(!sample||!Array.isArray(letters))return null;
 const expected=sampleCells(sample),answer=sample.answer.join('');
 if(puzzle.rows!==sample.answer.length||puzzle.cols!==sample.answer[0].length||puzzle.cells.length!==expected.length)return null;
 if(puzzle.cells.some((c,i)=>!!c.black!==expected[i].black||String(c.number||'')!==expected[i].number))return null;
 let correct=0,total=0;
 puzzle.cells.forEach((c,i)=>{if(c.black)return;total++;if((c.letter||letters[i])===answer[i])correct++;});
 return {correct,total};
}
const Samples={SHOWCASE,samplePuzzle,compareWithSample};
root.Samples=Samples;
if(typeof module!=='undefined')module.exports=Samples;
})(typeof globalThis!=='undefined'?globalThis:this);
