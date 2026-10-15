'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {installHelp} = require('../static/help.js');
class Element {
 constructor() { this.events = {}; this.attributes = {}; this.dataset = {}; this.style = {}; this.children = []; this.classList={contains:()=>true}; }
 addEventListener(type, fn) { (this.events[type] ||= []).push(fn); }
 emit(type, extra = {}) { const event = {target:this, preventDefault(){this.prevented=true;},stopPropagation(){this.stopped=true;},...extra}; for(const fn of this.events[type]||[]) fn(event); return event; }
 setAttribute(key, value) { this.attributes[key] = value; }
 append(node) { this.children.push(node); }
 contains(node) { return this === node || this.children.some(child=>child.contains(node)); }
 getBoundingClientRect() { return {left:900, top:300, bottom:326, width:this.dataset.help?26:300, height:this.dataset.help?26:100}; }
}
function setup(action=false) {
 const doc = new Element(), win = new Element(), buttons = [new Element(),new Element()];
 buttons.forEach((button,i)=>button.dataset.help='Help '+i); doc.body=new Element();doc.activeElement=null;
 if(action)buttons[0].classList={contains:()=>false};
 doc.querySelectorAll=()=>buttons;doc.createElement=()=>new Element();win.innerWidth=1000;win.innerHeight=600;
 let timer=0;const pending=new Map();win.setTimeout=fn=>{pending.set(++timer,fn);return timer;};win.clearTimeout=id=>pending.delete(id);
 installHelp(doc,win);
 return {doc,win,buttons,panels:doc.body.children,flush(){for(const fn of pending.values())fn();pending.clear();}};
}
test('Help is accessible and keyboard focus opens only its associated explanation',()=>{
 const {doc,buttons,panels}=setup();
 assert.equal(panels[0].attributes.role,'tooltip');assert.equal(buttons[0].attributes['aria-describedby'],panels[0].id);
 doc.activeElement=buttons[0];buttons[0].emit('focus');assert.equal(panels[0].hidden,false);assert.equal(buttons[0].attributes['aria-expanded'],'true');
 doc.activeElement=buttons[1];buttons[1].emit('focus');assert.equal(panels[0].hidden,true);assert.equal(panels[1].hidden,false);
 const escape=doc.emit('keydown',{key:'Escape'});assert.equal(panels[1].hidden,true);assert.equal(escape.prevented,true);assert.equal(doc.activeElement,buttons[1]);
});
test('Action tooltips open on focus and hover without consuming clicks or changing action semantics',()=>{
 const {buttons,panels}=setup(true);
 buttons[0].emit('focus');assert.equal(panels[0].hidden,false);
 const click=buttons[0].emit('click');assert.equal(click.prevented,undefined);assert.equal(click.stopped,undefined);
 assert.equal(panels[0].hidden,true);assert.equal(buttons[0].attributes['aria-expanded'],undefined);
 buttons[0].emit('pointerenter',{pointerType:'mouse'});assert.equal(panels[0].hidden,false);
});
test('Tap pins help without triggering a control; second tap and outside pointer dismiss it',()=>{
 const {doc,buttons,panels,flush}=setup();
 buttons[0].emit('pointerenter',{pointerType:'touch'});assert.equal(panels[0].hidden,true);
 const click=buttons[0].emit('click');assert.equal(click.prevented,true);assert.equal(click.stopped,true);assert.equal(panels[0].hidden,false);
 buttons[0].emit('pointerleave');flush();assert.equal(panels[0].hidden,false);
 buttons[0].emit('click');assert.equal(panels[0].hidden,true);
 buttons[0].emit('click');doc.emit('pointerdown',{target:panels[0]});assert.equal(panels[0].hidden,false);
 doc.emit('pointerdown',{target:new Element()});assert.equal(panels[0].hidden,true);
});
test('Hover help remains reachable over the popup and closes after leaving both',()=>{
 const {buttons,panels,flush}=setup();buttons[0].emit('pointerenter',{pointerType:'mouse'});assert.equal(panels[0].hidden,false);
 buttons[0].emit('pointerleave');panels[0].emit('pointerenter');flush();assert.equal(panels[0].hidden,false);
 panels[0].emit('pointerleave');flush();assert.equal(panels[0].hidden,true);
});
test('Popup stays within viewport and dismisses on focus departure, resize and scrolling',()=>{
 const {doc,win,buttons,panels}=setup();buttons[0].emit('focus');assert.equal(panels[0].style.left,'692px');
 buttons[0].emit('blur',{relatedTarget:new Element()});assert.equal(panels[0].hidden,true);
 buttons[0].emit('click');win.emit('resize');assert.equal(panels[0].hidden,true);
 buttons[0].emit('click');doc.emit('scroll');assert.equal(panels[0].hidden,true);
});
test('Popup clears the scrollbar and remains open when its own content scrolls',()=>{
 const {doc,buttons,panels}=setup();doc.documentElement={clientWidth:985,clientHeight:600};
 buttons[0].emit('click');assert.equal(panels[0].style.left,'677px');
 doc.emit('scroll',{target:panels[0]});assert.equal(panels[0].hidden,false);
 doc.emit('scroll',{target:doc});assert.equal(panels[0].hidden,true);
 doc.activeElement=buttons[0];buttons[0].emit('focus');
 doc.emit('scroll',{target:doc});assert.equal(panels[0].hidden,false);
});
