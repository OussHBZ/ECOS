(function () {
    'use strict';
    const form = document.querySelector('[data-kine-exam-form]');
    const studentSelector = form?.querySelector('[data-student-selector]');
    const studentSearch = studentSelector?.querySelector('[data-student-search]');
    const studentOptions = [...(studentSelector?.querySelectorAll('[data-student-option]') || [])];
    const searchEmpty = studentSelector?.querySelector('[data-student-search-empty]');
    const selectionSummary = studentSelector?.querySelector('[data-student-selection-summary]');
    const normalizeSearch = (value) => String(value || '').normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('fr').trim();
    const updateStudentSummary = () => {
        const count = studentOptions.filter(option => option.querySelector('input')?.checked).length;
        if (selectionSummary) {
            selectionSummary.textContent = `${count} étudiant${count > 1 ? 's' : ''} sélectionné${count > 1 ? 's' : ''}`;
        }
    };
    const filterStudents = () => {
        const term = normalizeSearch(studentSearch?.value);
        let visibleCount = 0;
        studentOptions.forEach(option => {
            const visible = !term || normalizeSearch(option.dataset.search).includes(term);
            option.hidden = !visible;
            if (visible) visibleCount += 1;
        });
        if (searchEmpty) searchEmpty.hidden = visibleCount !== 0;
        // Les cases ne sont jamais recréées : une sélection reste cochée
        // lorsqu'un autre filtre est saisi.
        updateStudentSummary();
    };
    studentSearch?.addEventListener('input', filterStudents);
    studentSelector?.addEventListener('change', updateStudentSummary);
    updateStudentSummary();
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
