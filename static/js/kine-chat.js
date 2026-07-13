(function () {
    'use strict';
    const root = document.querySelector('[data-kine-chat]');
    if (!root) return;
    const messages = root.querySelector('[data-chat-messages]');
    const statusNode = root.querySelector('[data-session-status]');
    const chatForm = root.querySelector('[data-chat-form]');
    const testForm = root.querySelector('[data-test-form]');

    function appendMessage(role, content, type) {
        const article = document.createElement('article');
        article.className = `kine-message kine-message--${role}`;
        const title = document.createElement('strong'); title.textContent = role === 'student' ? 'Étudiant' : (type === 'incident' ? 'Incident patient' : 'Patient');
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
    function renderEvaluation(content, evaluation) {
        content.replaceChildren();
        const score=document.createElement('p'); const strong=document.createElement('strong');
        strong.textContent=`${evaluation.points_earned}/20 — ${evaluation.passed?'Réussi':'Non réussi'}`; score.append(strong); content.append(score);
        if (evaluation.eliminatory_error_triggered) {
            const warning=document.createElement('div'); warning.className='kine-evaluation-errors';
            const title=document.createElement('strong'); title.textContent=`Erreur${(evaluation.eliminatory_errors||[]).length>1?'s':''} éliminatoire${(evaluation.eliminatory_errors||[]).length>1?'s':''}`; warning.append(title);
            const list=document.createElement('ul'); (evaluation.eliminatory_errors||[]).forEach(item=>{const li=document.createElement('li');li.textContent=item.description||item.justification||'Erreur éliminatoire détectée';list.append(li);}); warning.append(list); content.append(warning);
        }
        const sections=document.createElement('div'); sections.className='kine-evaluation-sections';
        (evaluation.section_scores||[]).forEach(item=>{
            const article=document.createElement('article'); article.className='kine-evaluation-section';
            const header=document.createElement('header'); const title=document.createElement('h3'); title.textContent=item.title||item.criterion||'Section';
            const points=document.createElement('strong'); points.textContent=`${item.points_earned}/${item.points_possible} point${item.points_possible>1?'s':''}`; header.append(title,points);
            const justification=document.createElement('p'); justification.textContent=item.justification||'Aucune justification disponible.'; article.append(header,justification); sections.append(article);
        });
        if (sections.children.length) content.append(sections);
        if (evaluation.feedback) { const feedback=document.createElement('p'); feedback.className='kine-evaluation-feedback'; feedback.textContent=evaluation.feedback; content.append(feedback); }
    }
    chatForm?.addEventListener('submit', async event => {
        event.preventDefault(); const input = chatForm.elements.message; const value = input.value.trim(); if (!value) return;
        appendMessage('student', value); input.value=''; setInputs(true);
        try { const data=await post(root.dataset.messageUrl,{message:value}); appendMessage('patient',data.response.content,data.response.type); }
        catch(error){ appendMessage('patient',error.message,'error'); } finally { if(root.dataset.status==='in_progress') setInputs(false); }
    });
    testForm?.addEventListener('submit', async event => {
        event.preventDefault(); const input=testForm.elements.test; const value=input.value.trim(); if(!value)return;
        appendMessage('student',`Je vais réaliser le test ${value}.`); input.value=''; setInputs(true);
        try { const data=await post(root.dataset.testUrl,{test:value}); appendMessage('patient',data.response.content,data.response.type); }
        catch(error){ appendMessage('patient',error.message,'error'); } finally { if(root.dataset.status==='in_progress') setInputs(false); }
    });
    root.querySelector('[data-pause-toggle]')?.addEventListener('click', async event => {
        try {
            const paused=root.dataset.status==='paused'; const data=await post(paused?root.dataset.resumeUrl:root.dataset.pauseUrl,{});
            root.dataset.status=data.status; statusNode.textContent=data.status; event.currentTarget.textContent=data.status==='paused'?'Reprendre':'Pause'; setInputs(data.status!=='in_progress');
        } catch(error){ window.alert(error.message); }
    });
    async function completeSimulation(automatic=false) {
        if(!automatic && !window.confirm('Terminer la simulation et lancer l’évaluation ?'))return;
        if(root.dataset.completionPending==='true') return;
        root.dataset.completionPending='true';
        try {
            const data=await post(root.dataset.completeUrl,{}); root.dataset.status=data.status; statusNode.textContent=data.status; setInputs(true);
            const evaluation=data.evaluation; const panel=root.querySelector('[data-evaluation-panel]'); panel.classList.remove('hidden');
            const content=panel.querySelector('[data-evaluation-content]'); renderEvaluation(content,evaluation);
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
