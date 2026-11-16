(function () {
    'use strict';
    const root = document.querySelector('[data-patient-preview]');
    if (!root) return;
    const form = root.querySelector('[data-preview-form]');
    const messages = root.querySelector('[data-preview-messages]');
    let previewId = null;
    let busy = false;
    root.querySelector('[data-preview-reset]').addEventListener('click', () => {
        if (busy) return;
        previewId = null; messages.replaceChildren();
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (busy) return;
        const input = form.elements.message;
        const message = input.value.trim();
        if (!message) return;
        busy = true;
        const button = form.querySelector('button'); button.disabled = true;
        try {
            const response = await secureFetch(root.dataset.url, {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({preview_id:previewId, message, level:root.querySelector('[data-preview-level]').value}),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Aperçu indisponible.');
            previewId = data.preview_id;
            const paragraph = document.createElement('p');
            paragraph.textContent = `Vous : ${message}\nPatient : ${data.response.content}`;
            messages.append(paragraph); input.value = '';
        } catch (error) {
            const paragraph = document.createElement('p'); paragraph.textContent = error.message;
            messages.append(paragraph);
        } finally { busy = false; button.disabled = false; }
    });
})();
