(function () {
    'use strict';
    const form = document.querySelector('[data-kine-exam-form]');
    form?.addEventListener('submit', async (event) => {
        event.preventDefault();
        const status = form.querySelector('[data-exam-status]');
        const button = form.querySelector('button[type="submit"]');
        const body = new FormData(form);
        // datetime-local has no timezone. Send the browser offset so the
        // server stores an exact UTC opening/closing instant.
        body.set('timezone_offset_minutes', String(new Date().getTimezoneOffset()));
        button.disabled = true; status.textContent = 'Création de l’examen en cours…';
        try {
            const response = await fetch(form.dataset.endpoint, {method:'POST', credentials:'same-origin', body, headers:{'Accept':'application/json'}});
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || 'Impossible de créer cet examen.');
            status.textContent = 'Examen créé avec succès. Actualisation…';
            window.location.reload();
        } catch (error) {
            status.textContent = error.message; button.disabled = false;
        }
    });
    document.addEventListener('click', async (event) => {
        const button = event.target.closest('[data-exam-delete]');
        if (!button || !window.confirm('Supprimer cet examen programmé ?')) return;
        button.disabled = true;
        try {
            const response = await fetch(button.dataset.examDelete, {method:'DELETE', credentials:'same-origin', headers:{'Accept':'application/json'}});
            if (!response.ok) throw new Error('Suppression impossible.');
            button.closest('tr')?.remove();
        } catch (error) { window.alert(error.message); button.disabled = false; }
    });
})();
