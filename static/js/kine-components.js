(function () {
    'use strict';

    function trackerPhases(root) {
        return Array.from(root.querySelectorAll('[data-phase]')).map(step => ({
            number: Number(step.dataset.phase),
            label: step.dataset.phaseLabel || '',
            guidance: step.dataset.phaseGuidance || '',
            step,
        }));
    }

    function updateTracker(root, progress) {
        const phases = trackerPhases(root);
        if (!phases.length) return;
        const state = typeof progress === 'object' && progress !== null ? progress : {};
        const phase = state.current_phase ?? progress;
        const current = Math.max(1, Math.min(phases.length, Number(phase) || 1));
        const currentPhase = phases[current - 1];
        root.dataset.currentPhase = String(current);
        const percentage = Number(state.progress_percentage ?? Math.round(current / phases.length * 100));
        const bar = root.querySelector('[data-tracker-bar]');
        const progressbar = root.querySelector('[role="progressbar"]');
        if (bar) bar.style.width = `${percentage}%`;
        if (progressbar) progressbar.setAttribute('aria-valuenow', String(percentage));
        const percentageNode = root.querySelector('[data-tracker-percentage]');
        const label = root.querySelector('[data-tracker-phase-label]');
        if (percentageNode) percentageNode.textContent = String(percentage);
        if (label) label.textContent = currentPhase.label;
        const guidance = root.querySelector('[data-tracker-guidance]');
        if (guidance) guidance.textContent = currentPhase.guidance;
        const phaseCounter = root.querySelector('.kine-tracker__summary strong');
        if (phaseCounter) phaseCounter.textContent = `Phase ${current}/${phases.length}`;
        const requirements = root.querySelector('[data-tracker-requirements]');
        if (requirements && state.requirements_message) requirements.textContent = state.requirements_message;
        phases.forEach(({number, step}) => {
            step.classList.toggle('is-current', number === current);
            step.classList.remove('is-complete');
            step.classList.toggle('is-remaining', number !== current);
            const button = step.querySelector('button');
            if (button) {
                const serverPhase = (state.phases || []).find(item => Number(item.number) === number);
                if (serverPhase) {
                    button.disabled = Boolean(serverPhase.locked);
                    button.title = serverPhase.lock_reason || '';
                }
                if (number === current) button.setAttribute('aria-current', 'step');
                else button.removeAttribute('aria-current');
            }
        });
    }

    async function requestPhase(root, phase) {
        const current = Number(root.dataset.currentPhase || 1);
        const url = root.dataset.progressUrl;
        if (url) {
            const response = await secureFetch(url, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                credentials: 'same-origin', body: JSON.stringify({phase})
            });
            const data = await response.json().catch(() => ({}));
            const errorNode = root.querySelector('[data-tracker-error]');
            if (!response.ok) {
                const message = data.error || 'La phase demandée reste verrouillée.';
                if (errorNode) {
                    errorNode.textContent = message;
                    errorNode.classList.remove('hidden');
                }
                throw new Error(message);
            }
            if (errorNode) {
                errorNode.textContent = '';
                errorNode.classList.add('hidden');
            }
            updateTracker(root, data);
            root.dispatchEvent(new CustomEvent('kine:phasechange', {bubbles: true, detail: data}));
            return;
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
            document.querySelectorAll('[data-kine-tracker]').forEach((root) => updateTracker(root, event.detail));
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
        const structured = data.structured_content || {};
        const social = structured.social_context || {};
        const anamnese = structured.anamnese || {};
        const diagnostic = structured.diagnostic_context || {};
        const reasoning = structured.reasoning || {};
        const rehab = structured.rehabilitation_prescription || {};
        const structuredPrescriptions = structured.prescriptions || {};
        const medicalPrescription = structuredPrescriptions.medical || {};
        const physiotherapyPrescription = structuredPrescriptions.physiotherapy || {};
        const etp = structured.etp || {};
        let filled = 0;
        const mappings = {
            case_number: data.case_number, title: data.title,
            folder_id: data.folder_id, level: data.level,
            mode_availability: data.mode_availability, emotional_state: data.emotional_state,
            difficulty: data.difficulty, subpathology: data.subpathology,
            rehabilitation_phase: data.rehabilitation_phase,
            planned_sessions: data.planned_sessions, pedagogical_summary: data.pedagogical_summary,
            identity_name: identity.name, identity_first_name: identity.first_name,
            identity_last_name: identity.last_name,
            identity_age: identity.age, identity_gender: identity.gender,
            family_situation: identity.family_situation, occupation: identity.occupation,
            height_cm: identity.height_cm, weight_kg: identity.weight_kg, bmi: identity.bmi,
            housing: identity.housing, physical_activity: identity.physical_activity,
            physical_activity_other: identity.physical_activity_other,
            tobacco: identity.tobacco, tobacco_details: identity.tobacco_details,
            alcohol: identity.alcohol, alcohol_details: identity.alcohol_details,
            diet: identity.diet,
            social_environment: social.environment,
            social_barriers_other: social.social_barriers_other,
            professional_situation: social.professional_situation,
            family_support: social.family_support, daily_autonomy: social.daily_autonomy,
            social_objectives: social.social_objectives,
            medical_diagnosis: context.main_diagnosis,
            diagnosis: data.diagnosis || reasoning.expected_physiotherapy_diagnosis,
            illness_history: context.illness_history || context.admission_reason,
            disease_onset: anamnese.onset, initial_reason: anamnese.initial_reason,
            initial_symptoms_other: anamnese.initial_symptoms_other,
            disease_evolution: anamnese.evolution, current_situation: anamnese.current_situation,
            clinical_phase: context.clinical_phase || diagnostic.clinical_phase,
            diagnosis_date: context.diagnosis_date || diagnostic.diagnosis_date,
            clinical_state: context.clinical_state || diagnostic.clinical_state,
            history_cardiovascular: history.cardiovascular,
            history_medical: [...asList(history.medical), ...asList(data.comorbidities)],
            history_surgical: history.surgical, history_personal: history.personal,
            history_allergies: history.allergies,
            risk_factors: [...asList(history.risk_factors), ...asList(history.lifestyle)],
            medical_prescription: prescriptions.medical,
            physiotherapy_prescription: prescriptions.physiotherapy,
            pedagogical_objectives: data.pedagogical_objectives || data.directives,
            directives: data.directives,
            clinical_synthesis: reasoning.clinical_synthesis,
            rehabilitation_notes: rehab.notes,
            medical_prescription_diagnosis: medicalPrescription.diagnosis,
            medical_prescription_indication: medicalPrescription.indication,
            medical_prescription_objectives: medicalPrescription.objectives,
            medical_prescription_precautions: medicalPrescription.precautions,
            medical_prescription_contraindications: medicalPrescription.contraindications,
            physiotherapy_prescription_objectives: physiotherapyPrescription.objectives,
            physiotherapy_care_type: physiotherapyPrescription.care_type,
            physiotherapy_frequency: physiotherapyPrescription.frequency,
            physiotherapy_session_duration: physiotherapyPrescription.session_duration,
            physiotherapy_precautions: physiotherapyPrescription.precautions,
            physiotherapy_contraindications: physiotherapyPrescription.contraindications,
        };
        Object.entries(mappings).forEach(([name, value]) => { filled += setField(form, name, value); });
        [['social_barriers', social.social_barriers], ['initial_symptoms', anamnese.initial_symptoms],
         ['important_events', anamnese.important_events], ['care_already_received', anamnese.care_already_received],
         ['associated_diagnoses', context.associated_diagnoses || diagnostic.associated_diagnoses]].forEach(([name, values]) => {
            const field = form.elements[name];
            if (!field || !Array.isArray(values)) return;
            Array.from(field.options || []).forEach(option => { option.selected = values.includes(option.value); });
        });

        filled += fillRepeater('procedures', data.procedures || []);
        filled += fillRepeater('medications', data.medications || [], {precautions: 'physiotherapy_precautions'});
        filled += fillRepeater('incidents', data.incidents || []);
        filled += fillRepeater('evaluation_checklist', data.evaluation_checklist || []);
        filled += fillRepeater('reasoning_hypotheses', reasoning.hypotheses || []);
        filled += fillRepeater('safety_points', reasoning.safety_points || []);
        filled += fillRepeater('therapeutic_objectives', structured.objectives || []);
        filled += fillRepeater('rehabilitation_modalities', rehab.modalities || []);
        filled += fillRepeater('etp_items', etp.items || []);

        const profile = structured.patient_personality || {};
        Object.entries(profile).forEach(([key, value]) => {
            if (key !== 'transitions') filled += setField(form, `personality_${key}`, String(value));
        });
        filled += fillRepeater('personality_transitions', (profile.transitions || []).map(row => ({...row, terms:row.terms.join('|')})));
        const effortTests = data.effort_tests || data.tests?.effort_tests || [];
        filled += fillRepeater('effort_tests', effortTests);
        filled += fillRepeater('effort_measurements', effortTests.flatMap(test => (test.measurements || []).map(row => ({...row, test_id:test.id, patient_knows:String(row.patient_knows === true)}))));
        const tests = [];
        Object.entries(data.tests || {}).filter(([category]) => category !== 'effort_tests').forEach(([category, entries]) => {
            (Array.isArray(entries) ? entries : []).forEach(entry => tests.push({
                ...(typeof entry === 'object' ? entry : {name: entry}), category,
            }));
        });
        filled += fillRepeater('tests', tests);

        const vitals = [];
        const referenceVitals = data.reference_vitals || {};
        if (referenceVitals.blood_pressure_systolic_mmhg || referenceVitals.blood_pressure_diastolic_mmhg) {
            vitals.push({
                name: 'Pression artérielle',
                value: referenceVitals.blood_pressure_systolic_mmhg,
                secondary_value: referenceVitals.blood_pressure_diastolic_mmhg,
                unit: 'mmHg', status: 'value',
            });
        }
        Object.entries(referenceVitals).forEach(([name, raw]) => {
            if (name === 'blood_pressure_systolic_mmhg' || name === 'blood_pressure_diastolic_mmhg') return;
            if (raw === null || raw === undefined || raw === '') return;
            const item = typeof raw === 'object' ? raw : {value: raw};
            vitals.push({
                name,
                value: item.value ?? item.systolic ?? item.blood_pressure_systolic_mmhg ?? raw,
                secondary_value: item.secondary_value ?? item.diastolic ?? item.blood_pressure_diastolic_mmhg,
                unit: item.unit || '', status: item.status || 'value',
                condition: item.condition || '',
            });
        });
        filled += fillRepeater('parameters', vitals);

        const assessment = data.physiotherapy_assessment || {};
        Object.entries(assessment).forEach(([domain, entries]) => {
            if (domain !== 'exertion_kinetics') {
                filled += fillRepeater(`assessment_${domain}`, entries || []);
            }
        });
        let vitalParameters = data.vital_parameters || [];
        if (!vitalParameters.length && Array.isArray(assessment.exertion_kinetics)) {
            const grouped = new Map();
            assessment.exertion_kinetics.forEach((item) => {
                const name = item.measure || item.name || '';
                if (!name) return;
                const key = `${name.toLowerCase()}|${(item.unit || '').toLowerCase()}`;
                const row = grouped.get(key) || {name, unit: item.unit || ''};
                const moment = /avant|initial|repos/i.test(item.time || '') ? 'before'
                    : (/après|apres|récup|recup|post/i.test(item.time || '') ? 'after' : 'during');
                row[moment] = item.value;
                grouped.set(key, row);
            });
            vitalParameters = Array.from(grouped.values());
        }
        filled += fillRepeater('vital_parameters', vitalParameters.map((item) => ({
            ...item,
            before: item.values?.before ?? item.before,
            during: item.values?.during ?? item.during,
            after: item.values?.after ?? item.after,
        })));
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
            if (!container.children.length && !container.dataset.optionalRepeater) addRepeaterRow(container.dataset.repeater);
        });
    }

    function initVitalParameterValidation() {
        const form = document.querySelector('[data-kine-case-form]');
        if (!form) return;
        form.addEventListener('submit', (event) => {
            form.querySelectorAll('.kine-vital-parameter-row').forEach((row) => {
                const name = row.querySelector('[data-vital-parameter-name]');
                const values = ['before', 'during', 'after'].map((moment) =>
                    row.querySelector(`[name$="[${moment}]"]`)?.value.trim()
                );
                name.required = values.some(Boolean);
                name.setCustomValidity(name.required && !name.value.trim()
                    ? 'Le nom du paramètre est obligatoire.'
                    : '');
            });
            if (!form.checkValidity()) {
                event.preventDefault();
                form.reportValidity();
            }
        });
    }

    function initConfirmations() {
        document.addEventListener('submit', (event) => {
            const message = event.target.dataset.confirm;
            if (message && !window.confirm(message)) event.preventDefault();
        });
    }

    function initCaseSave() {
        const form = document.querySelector('[data-kine-case-form]');
        const status = form?.querySelector('[data-case-save-status]');
        if (!status) return;
        let saving = false;
        form.addEventListener('submit', async (event) => {
            if (event.defaultPrevented) return;
            event.preventDefault();
            if (saving || !form.reportValidity()) return;
            saving = true;
            const body = new FormData(form);
            const buttons = form.querySelectorAll('button[type="submit"]');
            buttons.forEach(button => button.disabled = true);
            status.classList.remove('hidden');
            status.textContent = 'Enregistrement en cours…';
            try {
                const response = await secureFetch(form.action, {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'Accept': 'application/json'}, body,
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.error || `Impossible d’enregistrer le cas (${response.status}).`);
                if (!data.redirect_url) throw new Error('La session a expiré ou la réponse est invalide. Reconnectez-vous dans un autre onglet puis réessayez.');
                window.location.assign(data.redirect_url);
            } catch (error) {
                status.textContent = `${error.message} Vos saisies sont conservées dans ce formulaire.`;
                status.focus();
                status.scrollIntoView({behavior: 'auto', block: 'center'});
            } finally {
                saving = false;
                buttons.forEach(button => button.disabled = false);
            }
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
                const response = await secureFetch(form.dataset.extractionUrl, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Accept': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body
                });
                const contentType = response.headers.get('content-type') || '';
                let payload = {};
                if (contentType.includes('application/json')) {
                    payload = await response.json();
                } else {
                    // Reverse proxies and authentication redirects commonly
                    // return an HTML page. Never feed that page to JSON.parse.
                    const responseText = await response.text();
                    const title = responseText.match(/<title[^>]*>([^<]+)<\/title>/i)?.[1]?.trim();
                    if (response.redirected || response.url.includes('/login')) {
                        throw new Error('Votre session a expiré. Reconnectez-vous puis relancez l’extraction.');
                    }
                    const proxyErrors = {
                        413: 'Le document dépasse la taille maximale autorisée (25 Mo).',
                        502: 'Le service d’extraction est momentanément indisponible.',
                        504: 'L’extraction a dépassé le délai du serveur. Réessayez ou utilisez un document plus court.'
                    };
                    throw new Error(proxyErrors[response.status] ||
                        `Le serveur a retourné une réponse non JSON (${response.status}${title ? ` – ${title}` : ''}).`);
                }
                if (!response.ok) {
                    if (payload.auth_required && payload.redirect) window.location.assign(payload.redirect);
                    throw new Error(payload.error || `Extraction impossible (${response.status})`);
                }
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

    function initAuthoringWizard() {
        const form = document.querySelector('[data-kine-case-form]');
        if (!form) return;
        const pages = Array.from(form.querySelectorAll('[data-case-page]'));
        if (!pages.length) return;
        let labels = [];
        try { labels = JSON.parse(form.dataset.pageLabels || '[]'); } catch (_) { labels = []; }
        const progress = document.querySelector('[data-authoring-progress]');
        const pageInput = form.querySelector('[data-wizard-page-input]');
        const completedRoot = form.querySelector('[data-completed-pages]');
        let current = Math.max(1, Math.min(8, Number(form.dataset.wizardPage || pageInput?.value || 1)));
        const completed = new Set();

        function renderCompletedInputs() {
            if (!completedRoot) return;
            completedRoot.innerHTML = '';
            Array.from(completed).sort((a, b) => a - b).forEach((page) => {
                const input = document.createElement('input');
                input.type = 'hidden'; input.name = 'wizard_completed_pages'; input.value = String(page);
                completedRoot.appendChild(input);
            });
        }
        function show(page, focus = false) {
            current = Math.max(1, Math.min(8, Number(page) || 1));
            pages.forEach(node => node.classList.toggle('hidden', Number(node.dataset.casePage) !== current));
            if (pageInput) pageInput.value = String(current);
            progress?.querySelectorAll('[data-authoring-step]').forEach((node) => {
                const number = Number(node.dataset.authoringStep);
                node.classList.toggle('is-current', number === current);
                node.classList.toggle('is-complete', completed.has(number));
                const stepButton = node.querySelector('button');
                if (number === current) stepButton?.setAttribute('aria-current', 'step');
                else stepButton?.removeAttribute('aria-current');
            });
            const bar = progress?.querySelector('.kine-authoring-progress__bar span');
            if (bar) bar.style.width = `${current / 8 * 100}%`;
            const label = progress?.querySelector('[data-current-page-label]');
            if (label) label.textContent = labels[current - 1] || `Page ${current}`;
            const text = progress?.querySelector('[data-progress-text]');
            if (text) text.textContent = `Page ${current} sur 8`;
            const previous = form.querySelector('[data-previous-page]');
            const next = form.querySelector('[data-next-page]');
            if (previous) previous.disabled = current === 1;
            if (next) { next.disabled = current === 8; next.textContent = current === 7 ? 'Vérifier le cas' : 'Continuer'; }
            renderCompletedInputs();
            if (focus) {
                const heading = pages.find(node => Number(node.dataset.casePage) === current)?.querySelector('h2');
                heading?.setAttribute('tabindex', '-1');
                heading?.focus?.();
            }
        }
        document.addEventListener('click', (event) => {
            const target = event.target.closest('[data-go-page],[data-previous-page],[data-next-page]');
            if (!target || (!target.closest('[data-kine-case-form]') && !target.closest('[data-authoring-progress]'))) return;
            if (target.matches('[data-next-page]')) { completed.add(current); show(current + 1, true); }
            else if (target.matches('[data-previous-page]')) show(current - 1, true);
            else show(Number(target.dataset.goPage), true);
        });
        form.addEventListener('submit', () => { completed.add(current); renderCompletedInputs(); });
        show(current);
    }

    function initStructuredFieldStates() {
        const form = document.querySelector('[data-kine-case-form]');
        if (!form) return;
        function update(select) {
            const row = select.closest('.kine-repeater-row');
            if (!row) return;
            const active = select.value === 'value';
            row.querySelectorAll('[name$="[value]"],[name$="[secondary_value]"],[name$="[unit]"]').forEach((field) => {
                if (!active) field.value = '';
                field.disabled = !active;
            });
        }
        form.addEventListener('change', (event) => {
            if (event.target.matches('[data-information-state]')) update(event.target);
        });
        form.querySelectorAll('[data-information-state]').forEach(update);
    }

    function initBmiCalculation() {
        const form = document.querySelector('[data-kine-case-form]');
        if (!form) return;
        const elements = form.elements || {};
        const height = elements.height_cm;
        const weight = elements.weight_kg;
        const bmi = elements.bmi;
        if (!height || !weight || !bmi) return;
        const calculate = () => {
            const metres = Number(height.value) / 100;
            const kilograms = Number(weight.value);
            bmi.value = metres > 0 && kilograms > 0 ? (kilograms / (metres * metres)).toFixed(2) : '';
        };
        height.addEventListener('input', calculate); weight.addEventListener('input', calculate);
        if (!bmi.value) calculate();
    }

    function initCasePublication() {
        const form = document.querySelector('[data-kine-case-form]');
        const button = form?.querySelector('[data-publish-case]');
        const status = form?.querySelector('[data-case-save-status]');
        if (!form || !button || !form.dataset.publishUrl) return;
        button.addEventListener('click', async () => {
            button.disabled = true;
            if (status) { status.classList.remove('hidden'); status.textContent = 'Publication en cours…'; }
            try {
                const response = await secureFetch(form.dataset.publishUrl, {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
                    body: '{}',
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error((data.validation_issues || [data.error]).filter(Boolean).join(' '));
                if (status) status.textContent = `Version ${data.number} publiée.`;
            } catch (error) {
                if (status) status.textContent = error.message || 'Publication impossible.';
                button.disabled = false;
            }
        });
    }

    function initEffortTables() {
        const target = document.querySelector('[data-effort-author-tables]');
        const form = document.querySelector('[data-kine-case-form]');
        if (!target || !form) return;
        function rows(name) {
            return Array.from(form.querySelectorAll(`[data-repeater="${name}"] .kine-repeater-row`)).map(row => {
                const value = {};
                row.querySelectorAll('input,select,textarea').forEach(field => {
                    const key = field.name.match(/\[([^\]]+)\]$/)?.[1];
                    if (key) value[key] = field.value;
                });
                return value;
            });
        }
        function render() {
            target.replaceChildren();
            const measurements = rows('effort_measurements');
            rows('effort_tests').filter(test => test.id).forEach(test => {
                const heading = document.createElement('h3'); heading.textContent = test.name || test.id;
                const table = document.createElement('table');
                const selected = measurements.filter(row => row.test_id === test.id);
                const moments = [...new Set(selected.map(row => `${row.moment} ${row.moment_detail || ''}`))];
                const tr = document.createElement('tr');
                ['Paramètre', ...moments].forEach(label => {const th=document.createElement('th'); th.textContent=label; tr.append(th);});
                const head=document.createElement('thead'); head.append(tr); table.append(head);
                const body=document.createElement('tbody');
                [...new Set(selected.map(row => row.name))].forEach(name => {
                    const tr=document.createElement('tr'); const th=document.createElement('th'); th.textContent=name; tr.append(th);
                    moments.forEach(moment => {
                        const td=document.createElement('td');
                        td.textContent=selected.filter(row => row.name===name && `${row.moment} ${row.moment_detail || ''}`===moment)
                            .map(row => `${row.status==='value' ? (row.value || 'Non renseigné') : row.status} ${row.unit || ''} · ${row.actor}`).join(' ; ');
                        tr.append(td);
                    }); body.append(tr);
                }); table.append(body); target.append(heading,table);
            });
        }
        form.addEventListener('input', render);
        form.addEventListener('change', render);
        form.addEventListener('click', event => {
            if (event.target.closest('[data-remove-row]') || event.target.closest('[data-add-repeater]')) queueMicrotask(render);
        });
        render();
    }

    document.addEventListener('DOMContentLoaded', () => {
        initTrackers(); initRepeaters(); initVitalParameterValidation(); initConfirmations(); initDocumentExtraction(); initDashboardCharts();
        initExistingCaseForm(); initLocalDateTimes(); initCaseSave(); initAuthoringWizard();
        initStructuredFieldStates(); initBmiCalculation(); initCasePublication(); initEffortTables();
    });
})();
