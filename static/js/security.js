// CSRF token is session-bound and rendered by the server. URLs keep their prefix.
async function secureFetch(url, options = {}) {
    if (new URL(url, window.location.href).origin !== window.location.origin) {
        throw new Error('Requête vers une origine externe refusée.');
    }
    const method = (options.method || 'GET').toUpperCase();
    const headers = new Headers(options.headers || {});
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
        const token = document.querySelector('meta[name="csrf-token"]')?.content;
        if (token) headers.set('X-CSRF-Token', token);
    }
    return fetch(url, {...options, headers, credentials: options.credentials || 'same-origin'});
}

async function changeAccountStatus(kind, id, action) {
    // getBasePath is supplied by auth-utils.js on the administration page.
    const response = await secureFetch(getBasePath() + `/admin/accounts/${kind}/${id}/status`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action})
    });
    const result = await response.json();
    if (!response.ok) { window.alert(result.error || 'Action impossible.'); return; }
    if (kind === 'teacher') loadAdminTeachers();
    else loadAdminStudents();
}

// Shared native dialog shell; fields and submit handlers remain owned by each form.
function createAccountDialog(heading) {
    const dialog = document.createElement('dialog'); dialog.className = 'app-dialog';
    const header = document.createElement('div'); header.className = 'app-dialog-header';
    const title = document.createElement('h2'); title.textContent = heading;
    const close = document.createElement('button'); close.type = 'button'; close.className = 'app-dialog-close';
    close.dataset.dialogClose = ''; close.textContent = 'Fermer';
    close.addEventListener('click', () => dialog.close());
    header.append(title, close);
    const form = document.createElement('form'); form.className = 'app-dialog-form';
    const body = document.createElement('div'); body.className = 'app-dialog-body';
    const actions = document.createElement('div'); actions.className = 'app-dialog-actions';
    form.append(body, actions); dialog.append(header, form);
    dialog.setAttribute('aria-label', heading);
    return {dialog, form, body, actions};
}

async function editTeacherScope(id) {
    const endpoint = getBasePath() + `/admin/teachers/${id}/kine-scope`;
    const response = await secureFetch(endpoint);
    const scope = await response.json();
    if (!response.ok) { window.alert(scope.error || 'Suivi indisponible.'); return; }
    const {dialog, form, body: content, actions} = createAccountDialog('Étudiants suivis — attributions explicites');
    const fields = [];
    for (const [labelText, items, key, selected] of [
        ['Étudiants', scope.students.map(s => [s.id, `${s.name} (${s.student_code})`]), 'student_ids', scope.student_ids],
        ['Groupes (membres actuels)', scope.groups.map(g => [g, g]), 'group_names', scope.group_names]
    ]) {
        const fieldset = document.createElement('fieldset');
        fieldset.className = 'app-scope-options';
        const legend = document.createElement('legend'); legend.textContent = labelText; fieldset.append(legend);
        for (const [value, text] of items) {
            const label = document.createElement('label');
            const input = document.createElement('input'); input.type = 'checkbox'; input.checked = selected.includes(value);
            fields.push({input, key, value}); label.append(input, document.createTextNode(text)); fieldset.append(label);
        }
        content.append(fieldset);
    }
    const error = document.createElement('p'); error.setAttribute('role', 'alert'); content.append(error);
    const save = document.createElement('button'); save.type = 'submit'; save.textContent = 'Enregistrer';
    const cancel = document.createElement('button'); cancel.type = 'button'; cancel.textContent = 'Annuler';
    save.className = 'btn btn-primary'; cancel.className = 'btn btn-secondary'; cancel.dataset.dialogClose = '';
    cancel.addEventListener('click', () => dialog.close()); actions.append(save, cancel);
    form.addEventListener('submit', async event => {
        event.preventDefault(); save.disabled = true;
        try {
            const data = {student_ids: [], group_names: []};
            fields.filter(f => f.input.checked).forEach(f => data[f.key].push(f.value));
            const result = await secureFetch(endpoint, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
            const body = await result.json();
            if (!result.ok) throw new Error(body.error || 'Attribution impossible.');
            dialog.close();
        } catch (reason) { error.textContent = reason.message; }
        finally { save.disabled = false; }
    });
    document.body.append(dialog);
    dialog.addEventListener('close', () => dialog.remove()); dialog.showModal();
}

async function editAccountProfile(kind, id) {
    const endpoint = getBasePath() + `/admin/accounts/${kind}/${id}`;
    const response = await secureFetch(endpoint);
    const account = await response.json();
    if (!response.ok) { window.alert(account.error || 'Profil indisponible.'); return; }
    const {dialog, form, body: content, actions} = createAccountDialog('Modifier le profil');
    const grid = document.createElement('div'); grid.className = 'app-form-grid'; content.append(grid);
    const labels = {name: 'Nom complet', student_code: 'Numéro d’Apogée', group_name: 'Groupe', class_name: 'Classe', email: 'Email'};
    const fields = kind === 'student' ? ['name', 'student_code', 'group_name', 'class_name'] : ['name', 'email'];
    for (const field of fields) {
        const label = document.createElement('label'); label.textContent = labels[field];
        const input = document.createElement('input'); input.name = field; input.value = account[field] || '';
        input.required = ['name', 'student_code', 'email'].includes(field);
        if (field === 'email') input.type = 'email';
        label.append(input); grid.append(label);
    }
    const error = document.createElement('p'); error.setAttribute('role', 'alert'); content.append(error);
    const save = document.createElement('button'); save.type = 'submit'; save.className = 'btn btn-primary'; save.textContent = 'Enregistrer';
    const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'btn btn-secondary'; cancel.textContent = 'Annuler';
    cancel.dataset.dialogClose = '';
    cancel.addEventListener('click', () => dialog.close()); actions.append(save, cancel);
    form.addEventListener('submit', async event => {
        event.preventDefault(); save.disabled = true;
        try {
            const result = await secureFetch(endpoint, {method: 'PATCH', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(Object.fromEntries(new FormData(form)))});
            const body = await result.json();
            if (!result.ok) throw new Error(body.error || 'Modification impossible.');
            dialog.close();
            if (kind === 'teacher') loadAdminTeachers(); else loadAdminStudents();
        } catch (reason) { error.textContent = reason.message; }
        finally { save.disabled = false; }
    });
    document.body.append(dialog);
    dialog.addEventListener('close', () => dialog.remove()); dialog.showModal();
}
