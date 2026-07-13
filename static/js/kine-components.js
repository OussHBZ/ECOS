(function () {
    'use strict';

    const PHASES = [
        {label:'Accueil et présentation', guidance:'Accueillir le patient, se présenter et établir une relation thérapeutique.'},
        {label:'Anamnèse', guidance:'Explorer le motif, l’histoire, les traitements, les symptômes, les habitudes, les limitations et les objectifs du patient.'},
        {label:'Antécédents et risques', guidance:'Analyser les antécédents, les comorbidités et les facteurs de risque sans demander le diagnostic au patient.'},
        {label:'Bilan kinésithérapique', guidance:'Choisir et annoncer les tests pertinents : EVA, Borg, TUG, 6MWT, Sit To Stand, FC, SpO₂, PA, auscultation…'},
        {label:'Raisonnement clinique', guidance:'Présenter votre analyse et votre raisonnement clinique sans attendre que le patient donne le diagnostic.'},
        {label:'Objectifs thérapeutiques', guidance:'Définir des objectifs adaptés et formulés selon la méthode SMART.'},
        {label:'Programme de rééducation', guidance:'Construire le programme FITT : exercices, intensité, fréquence, progression, surveillance et séance type.'},
        {label:'Incidents cliniques', guidance:'Identifier et gérer uniquement les incidents prévus dans le dossier clinique.'},
        {label:'Éducation thérapeutique', guidance:'Informer, conseiller et vérifier la compréhension du patient.'},
        {label:'Fin de prise en charge', guidance:'Conclure la séance, sécuriser le patient et résumer la suite de la prise en charge.'},
        {label:'Évaluation et feedback', guidance:'Terminer la simulation pour obtenir l’évaluation et le feedback.'}
    ];

    function updateTracker(root, phase) {
        const current = Math.max(1, Math.min(PHASES.length, Number(phase) || 1));
        root.dataset.currentPhase = String(current);
        const percentage = Math.round(current / PHASES.length * 100);
        const bar = root.querySelector('[data-tracker-bar]');
        const progressbar = root.querySelector('[role="progressbar"]');
        if (bar) bar.style.width = `${percentage}%`;
        if (progressbar) progressbar.setAttribute('aria-valuenow', String(percentage));
        const percentageNode = root.querySelector('[data-tracker-percentage]');
        const label = root.querySelector('[data-tracker-phase-label]');
        if (percentageNode) percentageNode.textContent = String(percentage);
        if (label) label.textContent = PHASES[current - 1].label;
        const guidance = root.querySelector('[data-tracker-guidance]');
        if (guidance) guidance.textContent = PHASES[current - 1].guidance;
        const phaseCounter = root.querySelector('.kine-tracker__summary strong');
        if (phaseCounter) phaseCounter.textContent = `Phase ${current}/${PHASES.length}`;
        root.querySelectorAll('[data-phase]').forEach((step) => {
            const number = Number(step.dataset.phase);
            step.classList.toggle('is-current', number === current);
            step.classList.toggle('is-complete', number < current);
            step.classList.toggle('is-remaining', number > current);
            const button = step.querySelector('button');
            if (button) {
                const locked = root.dataset.mode === 'exam' && (number < current || number > current + 1);
                button.disabled = locked;
                if (number === current) button.setAttribute('aria-current', 'step');
                else button.removeAttribute('aria-current');
            }
        });
    }

    async function requestPhase(root, phase) {
        const current = Number(root.dataset.currentPhase || 1);
        if (root.dataset.mode === 'exam' && phase < current) return;
        const url = root.dataset.progressUrl;
        if (url) {
            const response = await fetch(url, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                credentials: 'same-origin', body: JSON.stringify({phase})
            });
            if (!response.ok) throw new Error('Échec de la mise à jour de la progression');
            const data = await response.json();
            phase = data.current_phase || phase;
        }
        updateTracker(root, phase);
        root.dispatchEvent(new CustomEvent('kine:phasechange', {bubbles: true, detail: {phase}}));
    }

    function initTrackers() {
        document.querySelectorAll('[data-kine-tracker]').forEach((root) => {
            updateTracker(root, root.dataset.currentPhase);
            root.addEventListener('click', (event) => {
                const button = event.target.closest('[data-phase-button]');
                if (!button || button.disabled) return;
                requestPhase(root, Number(button.dataset.phaseButton)).catch(console.error);
            });
        });
        window.addEventListener('kine:progress', (event) => {
            document.querySelectorAll('[data-kine-tracker]').forEach((root) => updateTracker(root, event.detail.current_phase));
        });
    }

    function repeaterTemplate(name) {
        return document.querySelector(`[data-repeater-template="${name}"]`) ||
            (name.startsWith('assessment_') ? document.querySelector('[data-repeater-template="assessment"]') : null);
    }

    function addRepeaterRow(name) {
        const container = document.querySelector(`[data-repeater="${name}"]`);
        const template = repeaterTemplate(name);
        if (!container || !template) return null;
        const index = Number(container.dataset.nextIndex || 0);
        container.dataset.nextIndex = String(index + 1);
        const html = template.innerHTML.replaceAll('__INDEX__', String(index)).replaceAll('__NAME__', name);
        container.insertAdjacentHTML('beforeend', html);
        return container.lastElementChild;
    }

    function textValue(value) {
        if (value === undefined || value === null) return '';
        if (Array.isArray(value)) return value.map(textValue).filter(Boolean).join('\n');
        if (typeof value === 'object') {
            return value.description || value.name || value.value || JSON.stringify(value, null, 2);
        }
        return String(value);
    }

    function setField(form, name, value) {
        const field = form.elements[name];
        const normalized = textValue(value);
        if (!field || !normalized) return 0;
        field.value = normalized;
        field.dispatchEvent(new Event('input', {bubbles: true}));
        field.dispatchEvent(new Event('change', {bubbles: true}));
        return 1;
    }

    function asList(value) {
        if (value === undefined || value === null || value === '') return [];
        return Array.isArray(value) ? value : [value];
    }

    function fillRepeater(name, items, aliases = {}) {
        const container = document.querySelector(`[data-repeater="${name}"]`);
        if (!container || !Array.isArray(items) || !items.length) return 0;
        container.innerHTML = '';
        container.dataset.nextIndex = '0';
        let filled = 0;
        items.filter(item => item && (typeof item !== 'object' || Object.values(item).some(value => textValue(value)))).forEach((item) => {
            const normalized = typeof item === 'object' ? item : {description: item};
            const row = addRepeaterRow(name);
            if (!row) return;
            row.querySelectorAll('input, textarea, select').forEach((field) => {
                const match = field.name.match(/\[([^\]]+)\]$/);
                if (!match) return;
                const key = match[1];
                const sourceKey = aliases[key] || key;
                const value = normalized[sourceKey] ?? normalized[key];
                if (textValue(value)) {
                    field.value = textValue(value);
                    filled += 1;
                }
            });
        });
        return filled;
    }

    function populateExtractedCase(form, data) {
        const identity = data.patient_info || {};
        const context = data.medical_context || {};
        const history = data.history || {};
        const prescriptions = data.prescriptions || {};
        let filled = 0;
        const mappings = {
            case_number: data.case_number, title: data.title || data.diagnosis,
            folder_id: data.folder_id, level: data.level,
            mode_availability: data.mode_availability, emotional_state: data.emotional_state,
            identity_name: identity.name, identity_age: identity.age, identity_gender: identity.gender,
            family_situation: identity.family_situation, occupation: identity.occupation,
            height_cm: identity.height_cm, weight_kg: identity.weight_kg, bmi: identity.bmi,
            diagnosis: context.main_diagnosis || data.diagnosis,
            illness_history: context.illness_history || context.admission_reason,
            history_cardiovascular: history.cardiovascular,
            history_medical: [...asList(history.medical), ...asList(data.comorbidities)],
            history_surgical: history.surgical, history_allergies: history.allergies,
            risk_factors: [...asList(history.risk_factors), ...asList(history.lifestyle)],
            medical_prescription: prescriptions.medical,
            physiotherapy_prescription: prescriptions.physiotherapy,
            pedagogical_objectives: data.pedagogical_objectives || data.directives,
        };
        Object.entries(mappings).forEach(([name, value]) => { filled += setField(form, name, value); });

        filled += fillRepeater('procedures', data.procedures || []);
        filled += fillRepeater('medications', data.medications || [], {precautions: 'physiotherapy_precautions'});
        filled += fillRepeater('incidents', data.incidents || []);

        const tests = [];
        Object.entries(data.tests || {}).forEach(([category, entries]) => {
            (Array.isArray(entries) ? entries : []).forEach(entry => tests.push({
                ...(typeof entry === 'object' ? entry : {name: entry}), category,
            }));
        });
        filled += fillRepeater('tests', tests);

        const vitals = [];
        Object.entries(data.reference_vitals || {}).forEach(([name, raw]) => {
            if (raw === null || raw === undefined || raw === '') return;
            const item = typeof raw === 'object' ? raw : {value: raw};
            vitals.push({name, value: item.value ?? raw, unit: item.unit || ''});
        });
        filled += fillRepeater('parameters', vitals);

        const assessment = data.physiotherapy_assessment || {};
        Object.entries(assessment).forEach(([domain, entries]) => {
            filled += domain === 'exertion_kinetics'
                ? fillRepeater('kinetics', entries || [])
                : fillRepeater(`assessment_${domain}`, entries || []);
        });
        return filled;
    }

    function initExistingCaseForm() {
        const form = document.querySelector('[data-kine-case-form]');
        const source = document.querySelector('[data-initial-case-data]');
        if (!form || !source) return;
        try {
            const data = JSON.parse(source.textContent || '{}');
            form.querySelector('[data-extracted-case-data]').value = JSON.stringify(data);
            populateExtractedCase(form, data);
        } catch (error) {
            console.error('Impossible de charger les données enregistrées du cas.', error);
        }
    }

    function initRepeaters() {
        document.addEventListener('click', (event) => {
            const add = event.target.closest('[data-add-repeater]');
            if (add) addRepeaterRow(add.dataset.addRepeater);
            const remove = event.target.closest('[data-remove-row]');
            if (remove) remove.closest('.kine-repeater-row')?.remove();
        });
        document.querySelectorAll('[data-repeater]').forEach((container) => {
            if (!container.children.length) addRepeaterRow(container.dataset.repeater);
        });
    }

    function initConfirmations() {
        document.addEventListener('submit', (event) => {
            const message = event.target.dataset.confirm;
            if (message && !window.confirm(message)) event.preventDefault();
        });
    }

    function initDocumentExtraction() {
        const form = document.querySelector('[data-kine-case-form]');
        const button = form?.querySelector('[data-extract-document]');
        if (!form || !button || !form.dataset.extractionUrl) return;
        button.addEventListener('click', async () => {
            const file = form.elements.source_document?.files?.[0];
            const status = form.querySelector('[data-extraction-status]');
            if (!file) { status.textContent = 'Sélectionnez un document.'; return; }
            button.disabled = true; status.textContent = 'Extraction en cours…';
            const body = new FormData(); body.append('source_document', file); body.append('case_number', form.elements.case_number?.value || 'kine-preview');
            try {
                const response = await fetch(form.dataset.extractionUrl, {method:'POST', credentials:'same-origin', body});
                const payload = await response.json(); if (!response.ok) throw new Error(payload.error || 'Extraction impossible');
                const data = payload.extracted_data || {}; form.querySelector('[data-extracted-case-data]').value = JSON.stringify(data);
                const filled = populateExtractedCase(form, data);
                status.textContent = filled
                    ? `Extraction terminée : ${filled} champ${filled > 1 ? 's' : ''} prérempli${filled > 1 ? 's' : ''}. Vérifiez les données avant l’enregistrement.`
                    : 'Extraction terminée, mais aucune donnée reconnue ne correspond aux champs du formulaire. Vérifiez le contenu du document.';
            } catch(error) { status.textContent = error.message; } finally { button.disabled = false; }
        });
    }

    function initDashboardCharts() {
        document.querySelectorAll('[data-chart]').forEach(container => {
            let series=[]; try { series=JSON.parse(container.dataset.series||'[]'); } catch(error) { return; }
            container.innerHTML='';
            if(!series.length){container.textContent='Aucune donnée disponible.';return;}
            const max=Math.max(...series.map(item=>Number(item.value)||0),1);
            series.slice(-20).forEach(item=>{
                const row=document.createElement('div'); row.className='kine-chart-row';
                const label=document.createElement('span'); label.textContent=item.label;
                const bar=document.createElement('i'); bar.style.width=`${Math.max(2,(Number(item.value)||0)/max*100)}%`;
                const value=document.createElement('strong'); value.textContent=item.value;
                row.append(label,bar,value); container.append(row);
            });
        });
    }

    function initLocalDateTimes() {
        const formatter = new Intl.DateTimeFormat('fr-FR', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
        document.querySelectorAll('[data-kine-local-time]').forEach((node) => {
            const value = new Date(node.getAttribute('datetime'));
            if (!Number.isNaN(value.getTime())) node.textContent = formatter.format(value);
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        initTrackers(); initRepeaters(); initConfirmations(); initDocumentExtraction(); initDashboardCharts();
        initExistingCaseForm(); initLocalDateTimes();
    });
})();
