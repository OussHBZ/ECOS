(function () {
    'use strict';
    const uploadForm = document.querySelector('[data-case-import-upload]');
    uploadForm?.addEventListener('submit', async (event) => {
        event.preventDefault();
        const status = uploadForm.querySelector('[data-import-upload-status]');
        const button = uploadForm.querySelector('button[type="submit"]');
        button.disabled = true;
        status.textContent = 'Création de la file de brouillons…';
        try {
            const response = await fetch(uploadForm.action || window.location.href, {
                method: 'POST', credentials: 'same-origin',
                headers: {'Accept': 'application/json'},
                body: new FormData(uploadForm)
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || 'Import impossible.');
            status.textContent = 'Lot créé. Ouverture de la file…';
            window.location.assign(data.detail_url);
        } catch (error) {
            status.textContent = error.message;
            button.disabled = false;
        }
    });

    const batch = document.querySelector('[data-import-batch]');
    if (!batch) return;
    let running = false;
    const render = (data) => {
        batch.dataset.batchStatus = data.status;
        batch.querySelector('[data-batch-status]').textContent = data.status_label;
        batch.querySelector('[data-progress-bar]').style.width = `${data.progress_percentage}%`;
        batch.querySelector('[data-progress-label]').textContent =
            `${data.processed_files}/${data.total_files} documents traités — ${data.progress_percentage} %`;
        [['successful', data.successful_files], ['incomplete', data.incomplete_files],
            ['error', data.error_files], ['duplicate', data.duplicate_files]]
            .forEach(([key, value]) => {
                const node = batch.querySelector(`[data-count="${key}"]`);
                if (node) node.textContent = value;
            });
        const retry = batch.querySelector('[data-retry-errors]');
        if (retry) retry.hidden = !data.error_files;
    };
    const processNext = async () => {
        if (running || batch.dataset.batchStatus === 'completed') return;
        running = true;
        try {
            const response = await fetch(batch.dataset.processUrl, {
                method: 'POST', credentials: 'same-origin',
                headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
                body: JSON.stringify({limit: 3})
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Traitement interrompu.');
            render(data);
            if (data.status === 'completed') {
                window.location.reload();
                return;
            }
        } catch (error) {
            batch.querySelector('[data-batch-status]').textContent =
                `Traitement suspendu : ${error.message}`;
        } finally {
            running = false;
        }
        window.setTimeout(processNext, 500);
    };
    batch.querySelector('[data-retry-errors]')?.addEventListener('click', async () => {
        const response = await fetch(batch.dataset.retryUrl, {
            method: 'POST', credentials: 'same-origin',
            headers: {'Accept': 'application/json'}
        });
        const data = await response.json();
        if (!response.ok) {
            window.alert(data.error || 'La reprise a échoué.');
            return;
        }
        render(data);
        processNext();
    });
    if (batch.dataset.batchStatus !== 'completed') processNext();
})();
