(() => {
    'use strict';
    const steps = ['clinical_record','history','assessment','reasoning','objectives','prescription','etp','final'];
    const form = document.querySelector('[data-criteria-form]') || document.querySelector('[data-kine-case-form]');
    if (!form) return;
    const data = document.querySelector('[data-initial-case-data]');
    const initial = document.querySelector('[data-criteria-initial]');
    const rows = initial ? JSON.parse(initial.textContent) : (data ? JSON.parse(data.textContent).structured_content?.evaluation_criteria || [] : []);
    let hidden = form.querySelector('[data-criteria-value]');
    if (!hidden) {hidden=document.createElement('input');hidden.type='hidden';hidden.name='criteria_json';form.append(hidden);}
    const editors=[];
    function field(parent,label,value,type='text',options=null) {
        const wrap=document.createElement('label'); wrap.textContent=label;
        const input=document.createElement(options?'select':type==='textarea'?'textarea':'input');
        if(options) Object.entries(options).forEach(([value,text])=>{const o=document.createElement('option');o.value=value;o.textContent=text;input.append(o);});
        else if(type!=='textarea') input.type=type;
        if(type==='checkbox') input.checked=!!value; else input.value=value??'';
        wrap.append(input); parent.append(wrap); return input;
    }
    function add(parent,step,row={}) {
        const card=document.createElement('fieldset');card.className='kine-card';
        const id=row.id||`criterion-${crypto.randomUUID()}`;
        const title=field(card,'Intitulé',row.title);
        const nature=field(card,'Nature',row.type||'information_gathering','text', {information_gathering:'Recueil d’informations',interpretation:'Interprétation',decision:'Décision',justification:'Justification'});
        const expected=field(card,'Réponse, question ou action attendue',row.expected,'textarea');
        const alternatives=field(card,'Alternatives et formulations équivalentes (une par ligne)',(row.alternatives||[]).join('\n'),'textarea');
        const importance=field(card,'Importance',row.importance||'important','text',{essential:'Essentiel (3)',important:'Important (2)',complementary:'Complémentaire (1)',not_evaluated:'Non évalué (0)'});
        const weight=field(card,'Poids',row.weight??2);weight.inputMode='decimal';
        importance.addEventListener('change',()=>weight.value={essential:3,important:2,complementary:1,not_evaluated:0}[importance.value]);
        const applicability=field(card,'Applicabilité',row.applicability?.kind||'always','text',{always:'Toujours attendue',not_applicable:'Non applicable',event:'Si l’événement scénarisé survient'});
        const eventId=field(card,'Identifiant de l’événement (si conditionnel)',row.applicability?.event_id);
        const consequence=field(card,'Conséquence de sécurité',row.safety?.consequence||'none','text',{none:'Aucune',critical:'Critique non éliminatoire',eliminatory:'Éliminatoire',review:'À confirmer par l’enseignant'});
        const triggers=Object.entries({correct:'Correcte',acceptable:'Acceptable',partial:'Partiellement correcte',incorrect:'Incorrecte ou omission attendue',dangerous:'Dangereuse'}).map(([key,label])=>[key,field(card,'Conséquence déclenchée si : '+label,(row.safety?.on_status||[]).includes(key),'checkbox')]);
        const active=field(card,'Activer',row.active,'checkbox');
        const approved=field(card,'J’ai validé ce critère et ses règles',row.teacher_approved,'checkbox');
        const remove=document.createElement('button');remove.type='button';remove.textContent='Retirer';remove.addEventListener('click',()=>card.remove());card.append(remove);parent.append(card);
        editors.push(()=>!card.isConnected?null:{id,step,title:title.value,type:nature.value,expected:expected.value,alternatives:alternatives.value.split('\n').map(s=>s.trim()).filter(Boolean),importance:importance.value,weight:weight.value,active:active.checked,teacher_approved:approved.checked,applicability:{kind:applicability.value,event_id:eventId.value},safety:{consequence:consequence.value,on_status:triggers.filter(([,input])=>input.checked).map(([key])=>key)}});
    }
    const suggestions=document.querySelector('[data-criteria-suggestions]');
    const proposed=suggestions?JSON.parse(suggestions.textContent):[];
    const panels={};
    function offer(r){const panel=panels[r.step];if(!panel||rows.some(row=>row.id===r.id))return;const b=document.createElement('button');b.type='button';b.textContent=`Proposer : ${r.title}`;b.addEventListener('click',()=>{add(panel,r.step,r);b.remove();});panel.append(b);}
    steps.forEach((step,index)=>{
        const page=form.querySelector(`[data-criterion-step="${step}"]`)||form.querySelector(`[data-case-page="${index+1}"]`);if(!page)return;
        const panel=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Évaluation de cette étape';panel.append(summary);page.append(panel);panels[step]=panel;
        rows.filter(r=>r.step===step).forEach(r=>add(panel,step,r));
        const button=document.createElement('button');button.type='button';button.textContent='+ Critère personnalisé';button.addEventListener('click',()=>add(panel,step));panel.append(button);
        proposed.filter(r=>r.step===step).forEach(offer);
    });
    if(form.dataset.criteriaUrl)fetch(form.dataset.criteriaUrl,{headers:{Accept:'application/json'}}).then(r=>r.ok?r.json():{}).then(data=>(data.suggestions||[]).forEach(offer)).catch(()=>{});
    const finalPage=form.querySelector('[data-case-page="8"]');
    const recap=document.createElement('section');
    if(finalPage)finalPage.append(recap);
    function sync(){
        const values=editors.map(read=>read()).filter(Boolean);hidden.value=JSON.stringify(values);
        recap.replaceChildren();const title=document.createElement('h3');title.textContent='Synthèse des critères sélectionnés';recap.append(title);
        values.forEach(row=>{const line=document.createElement('p');line.textContent=`${row.title} (${row.step}) : ${row.expected}. Alternatives : ${row.alternatives.join(' ; ')}. Poids : ${row.weight}. Sécurité : ${row.safety.consequence}. ${row.active&&row.teacher_approved?'Validé et actif':'Inactif ou à valider'}`;recap.append(line);});
    }
    form.addEventListener('input',sync);form.addEventListener('change',sync);form.addEventListener('click',()=>queueMicrotask(sync));form.addEventListener('submit',sync);sync();
})();
