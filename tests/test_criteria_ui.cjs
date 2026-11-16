const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');

class Element {
    constructor(tag) { this.tagName=tag;this.children=[];this.listeners={};this.dataset={};this.value='';this.checked=false;this.textContent=''; }
    append(...nodes) { for(const n of nodes){this.children.push(n);n.parent=this;} }
    replaceChildren(...nodes) {this.children=[];this.append(...nodes);}
    remove() {this.parent.children=this.parent.children.filter(n=>n!==this);this.removed=true;}
    get isConnected() {return !this.removed && (!this.parent || this.parent.isConnected);}
    addEventListener(type,callback) {(this.listeners[type]??=[]).push(callback);}
    fire(type) {(this.listeners[type]||[]).forEach(f=>f({target:this}));}
    querySelector(selector) {if(selector==='[data-criteria-value]')return null;return this.pages?.[selector]||null;}
}
function descendants(root) {return root.children.flatMap(n=>[n,...descendants(n)]);}
function field(root,label) {return descendants(root).find(n=>n.tagName==='label'&&n.textContent===label).children[0];}
function setup(rows) {
    const form=new Element('form');form.pages={};
    for(let i=1;i<=8;i++){const page=new Element('section');form.append(page);form.pages[`[data-case-page="${i}"]`]=page;}
    const initial={textContent:JSON.stringify(rows)};
    const document={querySelector:s=>s==='[data-criteria-form]'?form:s==='[data-criteria-initial]'?initial:null,createElement:t=>new Element(t)};
    vm.runInNewContext(fs.readFileSync('static/js/kine-criteria.js','utf8'),{document,crypto,queueMicrotask:f=>f()});
    const read=()=>{form.fire('submit');return JSON.parse(form.children.find(n=>n.name==='criteria_json').value);};
    return {form,read};
}

test('Criteria editor preserves fractional weights, alternatives, types and explicit approvals across steps',()=>{
    const original={id:'gather',step:'history',title:'Question',expected:'Attendu',alternatives:['Autre formulation'],type:'information_gathering',weight:'1/2',active:true,teacher_approved:true,importance:'complementary',applicability:{kind:'always'},safety:{consequence:'critical',on_status:['incorrect']}};
    const {form,read}=setup([original]);
    const card=descendants(form).find(n=>n.tagName==='fieldset');
    assert.equal(read()[0].weight,'1/2');
    field(card,'Alternatives et formulations équivalentes (une par ligne)').value='Alternative A\nAlternative B';
    field(card,'Nature').value='justification';
    field(card,'Conséquence déclenchée si : Dangereuse').checked=true;
    const row=read()[0];
    assert.deepEqual(row.alternatives,['Alternative A','Alternative B']);
    assert.equal(row.type,'justification');assert.equal(row.step,'history');
    assert.deepEqual(row.safety.on_status,['incorrect','dangerous']);assert.equal(row.teacher_approved,true);
    descendants(card).find(n=>n.tagName==='button'&&n.textContent==='Retirer').fire('click');
    assert.deepEqual(read(),[]);
});

test('New custom criteria stay inactive and unapproved until teacher chooses both',()=>{
    const {form,read}=setup([]);
    descendants(form.pages['[data-case-page="6"]']).find(n=>n.tagName==='button').fire('click');
    const card=descendants(form).find(n=>n.tagName==='fieldset');
    field(card,'Intitulé').value='Décision fictive';field(card,'Réponse, question ou action attendue').value='Action validée';
    assert.equal(read()[0].active,false);assert.equal(read()[0].teacher_approved,false);
    field(card,'Activer').checked=true;field(card,'J’ai validé ce critère et ses règles').checked=true;
    assert.equal(read()[0].step,'prescription');assert.equal(read()[0].teacher_approved,true);
});
