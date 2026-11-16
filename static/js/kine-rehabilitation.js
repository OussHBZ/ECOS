/* Teacher-authored data only: no clinical defaults, thresholds or equivalences. */
(() => {
    'use strict';
    const form = document.querySelector('[data-rehabilitation-editor]');
    if (!form) return;
    const program = JSON.parse(document.querySelector('[data-program-data]').textContent);
    const categories = JSON.parse(document.querySelector('[data-program-categories]').textContent);
    const suggestions = JSON.parse(document.querySelector('[data-program-suggestions]').textContent);
    const root = form.querySelector('[data-program-fields]');
    const id = () => `r_${crypto.randomUUID().replaceAll('-', '').slice(0, 20)}`;
    const node = (tag, text, parent) => { const n = document.createElement(tag); if (text) n.textContent = text; if (parent) parent.append(n); return n; };
    const button = (parent, text, callback) => { const b = node('button', text, parent); b.type = 'button'; b.className = 'btn btn-secondary'; b.addEventListener('click', callback); return b; };
    function field(parent, obj, key, label, choices = null, type = 'text') {
        const l = node('label', label, parent);
        const input = node(choices ? 'select' : type === 'textarea' ? 'textarea' : 'input', null, l);
        if (choices) Object.entries(choices).forEach(([v, text]) => { const o = node('option', text, input); o.value = v; });
        else if (type !== 'textarea') {input.type = type; if(type === 'number') input.step = 'any';}
        if (type === 'checkbox') input.checked = obj[key] === true;
        else input.value = obj[key] ?? '';
        input.addEventListener('input', () => {
            if (type === 'checkbox') obj[key] = input.checked;
            else if (type === 'number') { if (input.value === '') delete obj[key]; else obj[key] = Number(input.value); }
            else obj[key] = input.value;
        });
        return input;
    }
    function quantity(parent, obj, key, label) {
        const group = node('fieldset', null, parent); node('legend', label, group);
        obj[key] ||= {kind: 'exact', unit: ''}; const q = obj[key];
        field(group, q, 'kind', 'Valeur', {exact:'Précise', range:'Plage acceptable', choices:'Plusieurs valeurs acceptables', qualitative:'Qualitative'})
            .addEventListener('change', () => { const next = {kind:q.kind, unit:q.unit || ''}; obj[key] = next; render(); });
        if (q.kind === 'range') { field(group,q,'min','Minimum',null,'number'); field(group,q,'max','Maximum',null,'number'); }
        else if (q.kind === 'choices') {
            const tmp = {values:(q.values || []).join(', ')};
            field(group,tmp,'values','Valeurs séparées par des virgules').addEventListener('input', () => { q.values = tmp.values.split(',').filter(s => s.trim()).map(Number); });
        } else field(group,q,'value',q.kind === 'qualitative' ? 'Description' : 'Valeur',null,q.kind === 'qualitative' ? 'text' : 'number');
        if (q.kind !== 'qualitative') field(group,q,'unit','Unité');
    }
    function list(parent, obj, key, label, make, edit) {
        obj[key] ||= []; const section = node('section', null, parent); section.className = 'kine-card'; node('h3',label,section);
        obj[key].forEach((item, index) => {
            const card = node('fieldset',null,section); node('legend',`${label} ${index+1}`,card);
            edit(card,item); button(card,'Retirer',() => { obj[key].splice(index,1); render(); });
        });
        button(section,`+ Ajouter : ${label}`,() => {obj[key].push(make()); render();});
    }
    function fitt(parent, f) {
        field(parent,f,'type','Mode de réalisation',{continuous:'Continu',intermittent:'Intermittent',resistance:'Renforcement',circuit:'Circuit',functional:'Fonctionnel',other:'Autre',...(f.type?{[f.type]:f.type}:{})}).addEventListener('change',render);
        quantity(parent,f,'frequency','Fréquence');
        list(parent,f,'intensity','Intensité prescrite',() => ({id:id(),method:'other',role:'reference',target:{kind:'qualitative',value:''}}),(p,i) => {
            field(p,i,'method','Méthode',{other:'Autre / qualitative',target_hr:'FC cible',heart_rate_reserve:'FC de réserve',percent_hrmax:'% FC maximale',rpe:'RPE',borg:'Borg',dyspnea:'Dyspnée',symptoms:'Symptômes',power:'Puissance',speed:'Vitesse',load:'Charge / résistance',percent_capacity:'% capacité fonctionnelle'}).addEventListener('change',render);
            field(p,i,'role','Statut',{reference:'Prescription de référence',acceptable:'Alternative acceptable'});
            quantity(p,i,'target','Valeur ou plage attendue');
            if (['rpe','borg','dyspnea'].includes(i.method)) field(p,i,'scale','Échelle utilisée');
            if (['heart_rate_reserve','percent_hrmax','percent_capacity'].includes(i.method)) field(p,i,'reference','Référentiel utilisé');
            field(p,i,'notes','Précision complémentaire');
        });
        ['duration','volume'].forEach(key => {
            f[key] ||= {applicability:'not_applicable'}; const spec = f[key]; const g=node('fieldset',null,parent);
            field(g,spec,'applicability',key === 'duration' ? 'Durée' : 'Volume',{not_applicable:'Non applicable',required:'Requis',conditional:'Conditionnel'}).addEventListener('change',() => {if(spec.applicability === 'not_applicable') delete spec.quantity; render();});
            if (spec.applicability === 'conditional') field(g,spec,'condition','Condition d’application');
            if (spec.applicability !== 'not_applicable') quantity(g,spec,'quantity','Valeur');
        });
        const t=f.duration?.quantity, freq=f.frequency;
        if(f.duration?.applicability === 'required' && t?.kind === 'exact' && t.unit === 'min/session' && freq?.kind === 'exact' && freq.unit === 'sessions/week') {
            node('p',`Volume hebdomadaire calculé : ${t.value * freq.value} min/semaine. Vérifiez sa cohérence avec le volume retenu.`,parent);
        }
        list(parent,f,'components','Composants (intervalles, séries, circuit)',() => ({id:id(),label:''}),(p,c) => {
            field(p,c,'label','Composant');
            const labels={duration:'Durée',repetitions:'Répétitions / intervalles',sets:'Séries',recovery:'Récupération',distance:'Distance',load:'Charge',stations:'Stations',circuits:'Circuits',steps:'Nombre de pas'};
            const suggested = f.type === 'resistance' ? ['sets','repetitions','load','recovery'] : f.type === 'intermittent' ? ['duration','repetitions','recovery'] : f.type === 'circuit' ? ['stations','circuits','duration','recovery'] : ['duration','distance'];
            [...new Set([...suggested,...Object.keys(c).filter(k=>labels[k]),...Object.keys(labels)])].forEach(key => {
                if (c[key]) {quantity(p,c,key,labels[key]); button(p,`Retirer ${labels[key]}`,()=>{delete c[key]; render();});}
                else button(p,`+ ${labels[key]}`,()=>{c[key]={kind:'exact',unit:''};render();});
            });
            list(p,c,'custom_parameters','Paramètres complémentaires',()=>({id:id(),label:''}),(p,v)=>{field(p,v,'label','Paramètre');quantity(p,v,'quantity','Valeur');});
        });
        list(parent,f,'progression','Progression',() => ({id:id(),condition:'',change:''}),(p,r)=>{field(p,r,'condition','Conditions à réunir');field(p,r,'change','Changement prévu');});
    }
    function render() {
        root.replaceChildren();
        list(root,program,'objectives','Objectifs SMART',() => ({id:id()}),(p,o) => {
            field(p,o,'theme','Objectif proposé ou personnalisé',{'':'Personnalisé',...Object.fromEntries(suggestions.objectives.map(s=>[s,s]))});
            field(p,o,'importance','Importance',{'':'Non définie',primary:'Principal',secondary:'Secondaire',complementary:'Complémentaire'});
            Object.entries({specific:'Spécifique',measurable:'Mesurable',achievable:'Atteignable',relevant:'Pertinent',time_bound:'Échéance'}).forEach(([k,l])=>field(p,o,k,l));
        });
        list(root,program,'categories','Catégories propres au cas',()=>({id:id(),label:''}),(p,c)=>field(p,c,'label','Intitulé'));
        const all = {...categories,...Object.fromEntries((program.categories || []).map(c=>[c.id,c.label]))};
        list(root,program,'exercises','Exercices',()=>({id:id(),category:'aerobic',modality:'',fitt:{type:''}}),(p,e)=>{
            field(p,e,'category','Catégorie',all).addEventListener('change',render);
            const choice = field(p,e,'modality','Modalité proposée ou personnalisée',{'':'Personnalisée',...Object.fromEntries((suggestions.modalities[e.category]||[]).map(s=>[s,s])),...(e.modality ? {[e.modality]:e.modality} : {})});
            field(p,e,'modality','Modalité retenue / précision personnalisée');
            choice.addEventListener('change',render);
            button(p,'Proposer les critères de surveillance à vérifier',()=>{
                program.surveillance ||= [];
                (suggestions.surveillance[e.category]||[]).forEach(description=>{
                    if(!program.surveillance.some(r=>r.exercise_id===e.id && r.description===description)) program.surveillance.push({id:id(),exercise_id:e.id,description,active:false,teacher_approved:false});
                });render();
            });
            fitt(p,e.fitt);
            list(p,e,'acceptable_alternatives','Alternatives acceptables',()=>({type:''}),(p,a)=>{field(p,a,'justification','Justification / contexte');fitt(p,a);});
        });
        ['surveillance','adaptation_rules','stop_conditions'].forEach((key,index)=>{
            const titles=['Surveillance — validation explicite','Règles d’adaptation','Conditions d’arrêt'];
            list(root,program,key,titles[index],()=>({id:id(),active:false,teacher_approved:false}),(p,r)=>{
                field(p,r,'description','Paramètre / critère');
                field(p,r,'exercise_id','Exercice concerné',{'':'Tous / non spécifique',...Object.fromEntries((program.exercises||[]).map(e=>[e.id,e.modality||e.id]))});
                field(p,r,'importance','Niveau de surveillance',{'':'Non défini',essential:'Essentiel',monitor:'À surveiller',unused:'Non utilisé'});
                if(index) {field(p,r,'condition','Condition');field(p,r,'action','Conduite attendue');}
                field(p,r,'teacher_approved','J’ai vérifié et validé ce critère',null,'checkbox');field(p,r,'active','Activer ce critère',null,'checkbox');
            });
        });
        program.session ||= {};const session=node('section',null,root);node('h2','Évolution de séance',session);
        field(session,program.session,'enabled','Activer ce scénario',null,'checkbox');
        field(session,program.session,'undefined_response','Réaction prévue pour une situation non définie');
        list(session,program.session,'events','Événements du scénario',()=>({id:id(),kind:'evolution',trigger:{},reaction:'',teacher_approved:false}),(p,e)=>{
            field(p,e,'kind','Type',{evolution:'Évolution de séance',incident:'Incident facultatif (Master)'});
            field(p,e.trigger,'phase','Étape (numéro, facultatif)',null,'number');
            field(p,e.trigger,'action_contains','Action / mots déclencheurs');
            field(p,e.trigger,'exercise_id','Exercice',{'':'Non spécifique',...Object.fromEntries((program.exercises||[]).map(x=>[x.id,x.modality||x.id]))});
            field(p,e.trigger,'elapsed_seconds_min','Après une durée écoulée (secondes)',null,'number');
            field(p,e,'reaction','Réaction exacte du patient',null,'textarea');
            field(p,e,'teacher_approved','J’ai validé cet événement',null,'checkbox');
            list(p,e,'measurements','Mesures après événement',()=>({id:id(),name:'',value:'',unit:'',delivery:'on_request'}),(p,m)=>{
                field(p,m,'name','Paramètre');field(p,m,'value','Valeur scénarisée');field(p,m,'unit','Unité');field(p,m,'delivery','Communication',{on_request:'Sur demande de mesure',automatic:'Automatique'});
            });
        });
    }
    render();
    form.addEventListener('submit',()=>{form.elements.program_json.value=JSON.stringify(program);});
})();
