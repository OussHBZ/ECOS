(function () {
    'use strict';
    const root = document.querySelector('[data-effort-panel]');
    if (!root) return;
    const selector = root.querySelector('[name="measurement"]');
    const status = root.querySelector('[data-effort-status]');
    const body = root.querySelector('[data-effort-results]');
    const choices = new Map();
    const tables = new Map();
    function append(row) {
        const testId = row.test_id;
        if (!tables.has(testId)) {
            const heading=document.createElement('h3'); heading.textContent=row.test_name || testId;
            const table=document.createElement('table'); const head=document.createElement('thead'); const tr=document.createElement('tr');
            ['Paramètre','Moment','Responsable','Valeur recueillie','Source'].forEach(label=>{const th=document.createElement('th'); th.textContent=label; tr.append(th);});
            head.append(tr); table.append(head); const tbody=document.createElement('tbody'); table.append(tbody);
            body.append(heading,table); tables.set(testId,tbody);
        }
        const tr = document.createElement('tr');
        [row.name, `${row.moment} ${row.moment_detail || ''}`, row.actor,
            row.status === 'value' ? `${row.value ?? ''} ${row.unit || ''}` : row.status, row.source].forEach(value => {
            const td = document.createElement('td'); td.textContent = value || ''; tr.append(td);
        });
        tables.get(testId).append(tr);
    }
    async function call(url, value) {
        if (value) value.request_id = await window.kardioxDelivery.key(url, JSON.stringify(value));
        const response = await secureFetch(url, value ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(value)} : {});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Mesure indisponible.');
        if (value) window.kardioxDelivery.clear(url);
        return data;
    }
    call(root.dataset.url).then(data => {
        data.tests.forEach(test => test.measurements.filter(row => row.actor === 'student').forEach(row => {
            const key = `${test.id}/${row.id}`;
            choices.set(key, {test_id:test.id, measurement_id:row.id});
            const option = document.createElement('option'); option.value = key;
            option.textContent = `${test.name} · ${row.name} · ${row.moment} ${row.moment_detail || ''}`;
            selector.append(option);
        }));
        data.measurements.forEach(append);
    }).catch(error => { status.textContent = error.message; });
    let busy = false;
    root.querySelector('form').addEventListener('submit', async event => {
        event.preventDefault();
        if (busy || !choices.has(selector.value)) return;
        busy = true;
        try {
            const payload = {...choices.get(selector.value)};
            const observed = root.querySelector('[name="observed_value"]').value.trim();
            if (event.submitter?.dataset.report !== undefined) {
                if (!observed) throw new Error('Renseignez la valeur relevée.');
                payload.observed_value = observed;
            }
            const data = await call(root.dataset.url, payload);
            append(data.measurement); status.textContent = 'Mesure enregistrée.';
            const frame = document.querySelector('[data-record-frame]');
            if (frame) frame.src = frame.src;
        } catch (error) { status.textContent = error.message; }
        finally { busy = false; }
    });
    root.querySelector('[data-effort-event-form]').addEventListener('submit', async event => {
        event.preventDefault();
        if (busy) return;
        busy = true;
        try {
            const form = event.currentTarget;
            const data = await call(root.dataset.eventUrl, {test_id:form.elements.test_id.value, event:form.elements.event.value});
            data.measurements.forEach(append);
            status.textContent = data.measurements.length ? 'Événement enregistré.' : 'Aucune nouvelle mesure prévue pour cet événement.';
            const frame = document.querySelector('[data-record-frame]'); if (frame) frame.src = frame.src;
        } catch (error) { status.textContent = error.message; }
        finally { busy = false; }
    });
})();
