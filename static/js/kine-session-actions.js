(() => {
    'use strict';
    const root = document.querySelector('[data-session-actions]');
    if (!root) return;
    const form = root.querySelector('form');
    const result = root.querySelector('[data-session-action-result]');
    form.addEventListener('submit', async event => {
        event.preventDefault(); const button = form.querySelector('button'); button.disabled = true;
        try {
            const body={action:form.elements.action.value,exercise_name:form.elements.exercise_name.value};
            body.request_id=await window.kardioxDelivery.key(root.dataset.sessionActions,JSON.stringify(body));
            const response = await secureFetch(root.dataset.sessionActions, {method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify(body)});
            const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Action non enregistrée.');
            window.kardioxDelivery.clear(root.dataset.sessionActions);
            result.textContent = (data.events || []).map(e => e.reaction + (e.measurements.length ? '\n' + e.measurements.map(m=>`${m.name} : ${m.value} ${m.unit || ''}`).join('\n') : '')).join('\n') || 'Action enregistrée. Aucune nouvelle réaction du patient.';
            form.elements.action.value = '';
        } catch (error) { result.textContent = error.message; }
        finally { button.disabled = false; }
    });
})();
