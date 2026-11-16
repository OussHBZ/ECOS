const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

class Element {
    constructor(tag='div') { this.tag=tag; this.children=[]; this.events={}; this.value=''; this.textContent=''; }
    append(...children) { this.children.push(...children); }
    replaceChildren() { this.children=[]; }
    addEventListener(name, callback) { (this.events[name] ||= []).push(callback); }
    fire(name) { for (const cb of this.events[name] || []) cb({preventDefault(){}}); }
    all() { return [this,...this.children.flatMap(c=>c.all())]; }
}
function editor(program={}) {
    const root = new Element(); const form = new Element('form');
    form.elements={program_json:{value:''}};
    form.querySelector=()=>root;
    let counter=0;
    const data = {
        '[data-rehabilitation-editor]':form,
        '[data-program-data]':{textContent:JSON.stringify(program)},
        '[data-program-categories]':{textContent:JSON.stringify({aerobic:'Aérobie'})},
        '[data-program-suggestions]':{textContent:JSON.stringify({objectives:[],modalities:{aerobic:['Vélo']},surveillance:{aerobic:['Borg','Fatigue']}})},
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/js/kine-rehabilitation.js'),'utf8'), {
        document:{querySelector:s=>data[s],createElement:tag=>new Element(tag)},
        crypto:{randomUUID:()=>`id-${++counter}`},
    });
    return {root,form,button(text) {return root.all().find(e=>e.tag==='button' && e.textContent===text);},
        field(label) {return root.all().find(e=>e.tag==='label' && e.textContent===label)?.children[0];},
        save() {form.fire('submit');return JSON.parse(form.elements.program_json.value);}};
}

test('exercise suggestions require explicit approval and never activate criteria',()=>{
    const ui=editor(); ui.button('+ Ajouter : Exercices').fire('click');
    assert.equal(ui.save().surveillance.length,0);
    ui.field('Modalité retenue / précision personnalisée').value='<script>not HTML</script>';
    ui.field('Modalité retenue / précision personnalisée').fire('input');
    ui.button('Proposer les critères de surveillance à vérifier').fire('click');
    assert.equal(ui.save().surveillance.length,2);
    assert.ok(ui.save().surveillance.every(s=>s.active===false && s.teacher_approved===false));
    ui.button('Proposer les critères de surveillance à vérifier').fire('click');
    assert.equal(ui.save().surveillance.length,2);
    assert.equal(ui.save().exercises[0].modality,'<script>not HTML</script>');
});

test('duration and intensity expose their applicable fields and retain entered values',()=>{
    const ui=editor();ui.button('+ Ajouter : Exercices').fire('click');
    let field=ui.field('Durée');field.value='conditional';field.fire('input');field.fire('change');
    assert.ok(ui.field('Condition d’application'));
    field=ui.field('Condition d’application');field.value='Condition validée';field.fire('input');
    ui.button('+ Ajouter : Intensité prescrite').fire('click');
    field=ui.field('Méthode');field.value='borg';field.fire('input');field.fire('change');
    assert.ok(ui.field('Échelle utilisée'));
    assert.equal(ui.save().exercises[0].fitt.duration.condition,'Condition validée');
    field=ui.field('Durée');field.value='not_applicable';field.fire('input');field.fire('change');
    assert.equal(ui.save().exercises[0].fitt.duration.quantity,undefined);
});
