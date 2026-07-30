(function () {
    'use strict';
    const root = document.querySelector('[data-kine-chat]');
    if (!root) return;
    const messages = root.querySelector('[data-chat-messages]');
    const statusNode = root.querySelector('[data-session-status]');
    const chatForm = root.querySelector('[data-chat-form]');
    const testForm = root.querySelector('[data-test-form]');
    const vitalsBody = root.querySelector('[data-vitals-body]');

    function renderVitalMeasurements(items) {
        if (!vitalsBody) return;
        vitalsBody.replaceChildren();
        (items || []).forEach((item) => {
            const row = document.createElement('tr');
            [item.name, item.moment_label, `${item.value}${item.unit ? ` ${item.unit}` : ''}`].forEach((value) => {
                const cell = document.createElement('td'); cell.textContent = value || ''; row.append(cell);
            });
            vitalsBody.append(row);
        });
        root.querySelector('[data-vitals-empty]')?.classList.toggle('hidden', Boolean(items?.length));
        root.querySelector('[data-vitals-table-wrap]')?.classList.toggle('hidden', !items?.length);
    }

    function appendMessage(role, content, type) {
        const article = document.createElement('article');
        article.className = `kine-message kine-message--${role}`;
        const title = document.createElement('strong'); title.textContent = role === 'student' ? (root.dataset.studentName || 'Étudiant') : (type === 'incident' ? 'Incident patient' : 'Patient');
        const paragraph = document.createElement('p'); paragraph.textContent = content;
        article.append(title, paragraph); messages.append(article); messages.scrollTop = messages.scrollHeight;
    }
    async function post(url, body) {
        const response = await fetch(url, {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Request failed');
        return data;
    }
    function setInputs(disabled) { root.querySelectorAll('[data-chat-form] input,[data-chat-form] button,[data-test-form] input,[data-test-form] button').forEach(node => node.disabled = disabled); }
    function appendList(parent, title, items) {
        if (!(items || []).length) return;
        const heading=document.createElement('p'); const strong=document.createElement('strong'); strong.textContent=title; heading.append(strong); parent.append(heading);
        const list=document.createElement('ul'); items.forEach(item=>{const li=document.createElement('li');li.textContent=item;list.append(li);}); parent.append(list);
    }
    function appendEvidence(parent, evidence) {
        if (!(evidence || []).length) return;
        const heading=document.createElement('p'); const strong=document.createElement('strong'); strong.textContent='Phrases exactes utilisées comme preuves :'; heading.append(strong); parent.append(heading);
        evidence.forEach(item=>{
            const quote=document.createElement('blockquote'); quote.append(document.createTextNode(`« ${item.quote || ''} »`));
            const footer=document.createElement('footer'); const phase=item.phase?`Phase ${item.phase}`:'Phase non enregistrée';
            let timestamp=''; if(item.timestamp){const date=new Date(item.timestamp);timestamp=Number.isNaN(date.getTime())?item.timestamp:date.toLocaleString('fr-FR');}
            footer.textContent=`${phase}${timestamp?` · ${timestamp}`:''}`; quote.append(footer); parent.append(quote);
        });
    }
    function renderEvaluation(content, evaluation) {
        content.replaceChildren();
        if (evaluation.student) {
            const identity=document.createElement('p'); const label=document.createElement('strong');
            label.textContent='Étudiant : ';
            const details=[
                evaluation.student.name,
                evaluation.student.student_code ? `Code Apogée ${evaluation.student.student_code}` : '',
                evaluation.student.level,
                evaluation.student.group_name ? `Groupe ${evaluation.student.group_name}` : '',
                evaluation.student.class_name ? `Classe ${evaluation.student.class_name}` : ''
            ].filter(Boolean).join(' · ');
            identity.append(label,document.createTextNode(details)); content.append(identity);
        }
        const score=document.createElement('p'); const strong=document.createElement('strong');
        const number=value=>String(value??0).replace('.',',');
        strong.textContent=`${number(evaluation.points_earned)}/${number(evaluation.points_total??20)} — ${evaluation.passed?'Réussi':'Non réussi'}`; score.append(strong); content.append(score);
        if (evaluation.eliminatory_error_triggered) {
            const warning=document.createElement('div'); warning.className='kine-evaluation-errors';
            const title=document.createElement('strong'); title.textContent=`Erreur${(evaluation.eliminatory_errors||[]).length>1?'s':''} éliminatoire${(evaluation.eliminatory_errors||[]).length>1?'s':''} — score plafonné à ${evaluation.elimination_cap??8}/20`; warning.append(title);
            (evaluation.eliminatory_errors||[]).forEach(item=>{const article=document.createElement('article');const heading=document.createElement('h4');heading.textContent=item.description||item.id||'Erreur éliminatoire';const reason=document.createElement('p');reason.textContent=item.justification||'Erreur établie par une preuve explicite.';article.append(heading,reason);appendEvidence(article,Array.isArray(item.evidence)?item.evidence:[]);warning.append(article);}); content.append(warning);
        }
        const sections=document.createElement('div'); sections.className='kine-evaluation-sections';
        (evaluation.section_scores||[]).forEach(item=>{
            const article=document.createElement('article'); article.className='kine-evaluation-section';
            const header=document.createElement('header'); const title=document.createElement('h3'); title.textContent=item.title||item.criterion||'Section';
            const points=document.createElement('strong'); points.textContent=`${item.points_earned}/${item.points_possible} point${item.points_possible>1?'s':''}`; header.append(title,points);
            article.append(header);
            const criterionLabel=document.createElement('p');const criterionStrong=document.createElement('strong');criterionStrong.textContent='Critère évalué : ';criterionLabel.append(criterionStrong,document.createTextNode(item.criterion||''));article.append(criterionLabel);
            (item.criteria||[]).forEach(criterion=>{
                const block=document.createElement('section');block.className='kine-evaluation-criterion';
                const heading=document.createElement('h4');heading.textContent=criterion.criterion||'Critère';
                const status=document.createElement('p');status.textContent=`${criterion.status_label||'Non réalisé'} — ${number(criterion.points_earned)}/${number(criterion.points_possible)} point${criterion.points_possible===1?'':'s'}`;
                block.append(heading,status);
                appendList(block,'Éléments attendus :',criterion.expected_elements);
                appendList(block,'Éléments détectés et comptabilisés :',criterion.detected_elements);
                appendEvidence(block,criterion.evidence);
                appendList(block,'Partiellement réalisé :',criterion.partial_elements);
                appendList(block,'Absent ou restant à réaliser :',criterion.missing_elements);
                const justification=document.createElement('p');const strong=document.createElement('strong');strong.textContent='Justification : ';justification.append(strong,document.createTextNode(criterion.justification||'Aucune justification disponible.'));block.append(justification);article.append(block);
            });
            const justification=document.createElement('p'); justification.textContent=`Justification de la section : ${item.justification||'Aucune justification disponible.'}`; article.append(justification); sections.append(article);
        });
        if (sections.children.length) content.append(sections);
        if (evaluation.feedback) { const feedback=document.createElement('p'); feedback.className='kine-evaluation-feedback'; feedback.textContent=evaluation.feedback; content.append(feedback); }
    }
    chatForm?.addEventListener('submit', async event => {
        event.preventDefault(); const input = chatForm.elements.message; const value = input.value.trim(); if (!value) return;
        appendMessage('student', value); input.value=''; setInputs(true);
        try { const data=await post(root.dataset.messageUrl,{message:value}); appendMessage('patient',data.response.content,data.response.type); renderVitalMeasurements(data.vital_measurements); window.dispatchEvent(new CustomEvent('kine:progress',{detail:data.progress})); }
        catch(error){ appendMessage('patient',error.message,'error'); } finally { if(root.dataset.status==='in_progress') setInputs(false); }
    });
    testForm?.addEventListener('submit', async event => {
        event.preventDefault(); const input=testForm.elements.test; const value=input.value.trim(); if(!value)return;
        appendMessage('student',`Je vais réaliser le test ${value}.`); input.value=''; setInputs(true);
        try { const data=await post(root.dataset.testUrl,{test:value}); appendMessage('patient',data.response.content,data.response.type); renderVitalMeasurements(data.vital_measurements); window.dispatchEvent(new CustomEvent('kine:progress',{detail:data.progress})); }
        catch(error){ appendMessage('patient',error.message,'error'); } finally { if(root.dataset.status==='in_progress') setInputs(false); }
    });
    root.querySelector('[data-pause-toggle]')?.addEventListener('click', async event => {
        try {
            const paused=root.dataset.status==='paused'; const data=await post(paused?root.dataset.resumeUrl:root.dataset.pauseUrl,{});
            root.dataset.status=data.status; statusNode.textContent=data.status==='paused'?'En pause':'En cours'; event.currentTarget.textContent=data.status==='paused'?'Reprendre':'Pause'; setInputs(data.status!=='in_progress');
        } catch(error){ window.alert(error.message); }
    });
    async function completeSimulation(automatic=false) {
        if(!automatic && !window.confirm('Terminer la simulation et lancer l’évaluation ?'))return;
        if(root.dataset.completionPending==='true') return;
        root.dataset.completionPending='true';
        try {
            const data=await post(root.dataset.completeUrl,{}); root.dataset.status=data.status; statusNode.textContent=data.status==='completed'?'Terminée':data.status; setInputs(true);
            const evaluation=data.evaluation; const panel=root.querySelector('[data-evaluation-panel]'); panel.classList.remove('hidden');
            const content=panel.querySelector('[data-evaluation-content]'); renderEvaluation(content,evaluation);
            if(data.progress) window.dispatchEvent(new CustomEvent('kine:progress',{detail:data.progress}));
        } catch(error){ if(!automatic) window.alert(error.message); }
        finally { root.dataset.completionPending='false'; }
    }
    root.querySelector('[data-complete]')?.addEventListener('click', () => completeSimulation(false));
    const clock=root.querySelector('[data-exam-clock] strong');
    if(clock && root.dataset.deadline){
        const deadline=new Date(root.dataset.deadline).getTime();
        let expirationTriggered=false;
        const tick=()=>{const seconds=Math.max(0,Math.floor((deadline-Date.now())/1000));clock.textContent=`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;if(seconds===0&&!expirationTriggered){expirationTriggered=true;setInputs(true);statusNode.textContent='Clôture automatique…';completeSimulation(true);}};
        tick(); setInterval(tick,1000);
    }
})();
