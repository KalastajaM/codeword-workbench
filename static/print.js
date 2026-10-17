/* Printable codeword sheets as SVG, shared by the browser and Node checks.
   The puzzle sheet shows numbers and given letters only; the solution sheet
   adds the answer of a generated puzzle. */
(function(root){
'use strict';
const CELL=40,MARGIN=24,TITLE=44,GAP=24;
const escape=text=>String(text).replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'})[ch]);
function alphabetFor(language){return 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'+(language==='fi'||language==='sv'?'ÅÄÖ':'');}
// Given letters by number: prefilled letters, which every cell of that number shares.
function givenLetters(puzzle){
 const given=new Map();
 for(const cell of puzzle.cells){
  if(cell.black||!cell.number||!cell.letter||cell.prefilled===false)continue;
  given.set(cell.number,given.has(cell.number)&&given.get(cell.number)!==cell.letter?null:cell.letter);
 }
 for(const [number,letter]of given)if(!letter)given.delete(number);
 return given;
}
function numberAnchor(position,x,y){
 const right=position.endsWith('right'),bottom=position.startsWith('bottom');
 return {x:right?x+CELL-3:x+3,y:bottom?y+CELL-4:y+11,anchor:right?'end':'start'};
}
// options: solution (letters per cell, or null) and key (number key and alphabet strip).
// grade, when given, is printed as the difficulty beside the title.
function sheetSvg(puzzle,{solution=null,key=true,grade=null}={}){
 const width=puzzle.cols*CELL,height=puzzle.rows*CELL,given=givenLetters(puzzle);
 const position=puzzle.numberPosition||'top-left';
 const parts=[];
 const title=(puzzle.name||'Codeword')+(solution?' · solution':'');
 parts.push(`<text x="${MARGIN}" y="${MARGIN+18}" font-size="20" font-weight="700">${escape(title)}</text>`);
 const level={easy:'Easy',medium:'Medium',hard:'Hard'}[grade];
 if(level)parts.push(`<text x="${MARGIN+width}" y="${MARGIN+18}" font-size="13" text-anchor="end" fill="#555">Difficulty: ${level}</text>`);
 const top=MARGIN+TITLE;
 puzzle.cells.forEach((cell,i)=>{
  const x=MARGIN+(i%puzzle.cols)*CELL,y=top+Math.floor(i/puzzle.cols)*CELL;
  if(cell.black){parts.push(`<rect x="${x}" y="${y}" width="${CELL}" height="${CELL}" fill="${cell.clue?'#c8c8c8':'#111'}"/>`);return;}
  if(cell.highlight)parts.push(`<rect x="${x}" y="${y}" width="${CELL}" height="${CELL}" fill="#e3e3e3"/>`);
  if(cell.number){const a=numberAnchor(position,x,y);parts.push(`<text x="${a.x}" y="${a.y}" font-size="10" text-anchor="${a.anchor}">${escape(cell.number)}</text>`);}
  const own=cell.prefilled!==false?cell.letter||'':'',letter=solution?solution[i]:own||given.get(cell.number)||'';
  if(letter){const isGiven=own===letter||given.get(cell.number)===letter;parts.push(`<text x="${x+CELL/2}" y="${y+CELL/2+9}" font-size="24" text-anchor="middle" font-weight="${isGiven?700:400}">${escape(letter)}</text>`);}
 });
 // Grid lines on top of the cells, so black cells keep sharp edges.
 for(let r=0;r<=puzzle.rows;r++)parts.push(`<line x1="${MARGIN}" y1="${top+r*CELL}" x2="${MARGIN+width}" y2="${top+r*CELL}" stroke="#111" stroke-width="1"/>`);
 for(let c=0;c<=puzzle.cols;c++)parts.push(`<line x1="${MARGIN+c*CELL}" y1="${top}" x2="${MARGIN+c*CELL}" y2="${top+height}" stroke="#111" stroke-width="1"/>`);
 parts.push(`<rect x="${MARGIN}" y="${top}" width="${width}" height="${height}" fill="none" stroke="#111" stroke-width="2.5"/>`);
 let bottom=top+height;
 const numbers=[...new Set(puzzle.cells.filter(c=>!c.black&&c.number).map(c=>c.number))].sort((a,b)=>Number(a)-Number(b));
 if(key&&numbers.length){
  // Two rows for a classic 26-number key; more rows when boxes would get too small.
  const box=Math.max(24,Math.min(CELL,width/Math.ceil(numbers.length/2))),perRow=Math.max(1,Math.floor(width/box));
  const solved=new Map();if(solution)puzzle.cells.forEach((c,i)=>{if(!c.black&&c.number)solved.set(c.number,solution[i]);});
  bottom+=GAP;
  numbers.forEach((number,k)=>{
   const x=MARGIN+(k%perRow)*box,y=bottom+Math.floor(k/perRow)*box,letter=solution?solved.get(number):given.get(number);
   parts.push(`<rect x="${x}" y="${y}" width="${box}" height="${box}" fill="none" stroke="#111" stroke-width="1"/>`);
   parts.push(`<text x="${x+3}" y="${y+10}" font-size="9">${escape(number)}</text>`);
   if(letter)parts.push(`<text x="${x+box/2}" y="${y+box/2+7}" font-size="${Math.round(box*.5)}" text-anchor="middle" font-weight="${given.get(number)===letter?700:400}">${escape(letter)}</text>`);
  });
  bottom+=Math.ceil(numbers.length/perRow)*box;
  if(!solution){
   // Letters to cross off; the given ones are already used.
   const used=new Set(given.values()),letters=[...alphabetFor(puzzle.language)],step=width/letters.length;
   bottom+=GAP;
   letters.forEach((letter,k)=>{
    const x=MARGIN+k*step+step/2;
    parts.push(`<text x="${x}" y="${bottom+12}" font-size="${Math.min(16,step*.8).toFixed(1)}" text-anchor="middle" fill="${used.has(letter)?'#aaa':'#111'}"${used.has(letter)?' text-decoration="line-through"':''}>${escape(letter)}</text>`);
   });
   bottom+=16;
  }
 }
 const totalWidth=width+2*MARGIN,totalHeight=bottom+MARGIN;
 return `<svg xmlns="http://www.w3.org/2000/svg" width="${totalWidth}" height="${totalHeight}" viewBox="0 0 ${totalWidth} ${totalHeight}" font-family="Helvetica, Arial, sans-serif" fill="#111">`+
  `<rect width="100%" height="100%" fill="#fff"/>${parts.join('')}</svg>`;
}
const PrintSheet={sheetSvg,givenLetters};
root.PrintSheet=PrintSheet;
if(typeof module!=='undefined')module.exports=PrintSheet;
})(typeof globalThis!=='undefined'?globalThis:this);
