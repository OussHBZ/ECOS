# TECHNICAL SPECIFICATION — ECOS Physiotherapy (Kinésithérapie) Extension

## 0. Context

**Existing project:** ECOS — OSCE Consultation Simulator
**Repository:** https://github.com/OussHBZ/ECOS
**Branch to create:** `kinesitherapy`

ECOS is a Flask platform that simulates OSCE consultations with virtual patients driven by an LLM (Llama-4-Scout-17B via the Groq API/LangChain), with automatic clinical case extraction from documents, automated LLM-based evaluation, and PDF report generation.

**Current stack:**
- Backend: Flask (Python)
- AI: LangChain + Groq API, model `meta-llama/llama-4-scout-17b-16e-instruct` (fallback `llama3-8b-8192`)
- Database: SQLAlchemy + SQLite
- Document extraction: PyPDF2, python-docx, docx2txt
- PDF: ReportLab
- Frontend: vanilla JavaScript + CSS, Jinja2 templates (Flask)

**Current root files:**
```
app.py                        # main routes / Flask entry point
auth.py                       # authentication, roles
document_processor.py         # PDF/Word extraction -> structured case
enhanced_evaluation_agent.py  # LLM evaluation engine (categorized)
evaluation_agent.py           # LLM evaluation engine (legacy/fallback)
evaluation_config.py          # evaluation grid/criteria definitions
init_db.py                    # database initialization
models.py                     # SQLAlchemy models
response_template.json        # structured response template
simple_pdf_generator.py       # PDF report generation
blueprints/                   # Flask routes organized by module
static/                       # JS/CSS
templates/                    # Jinja2 views
```

**Goal of this extension:** build a "physiotherapy" (kinésithérapie) variant of the platform (cardio-vascular pathologies first), reusing the existing architecture, without breaking the generic OSCE version (`main`).

---

## 1. Main functional objective

A chatbot must embody a **patient with a cardio-vascular condition**. The physiotherapy student must carry out the entire consultation (interview, assessment, clinical reasoning, session prescription, incident management, therapeutic education) by conversing with this virtual patient.

Non-negotiable rules for the AI patient:
- Never plays the role of the teacher during the simulation.
- Only responds as a real patient, strictly based on the information in the structured clinical record — **never invents information**.
- Never spontaneously reveals information that was not asked for.
- Only becomes the evaluator at the very end of the simulation.

---

## 2. Roles and account management

Three account types (partially exists already in `auth.py` / `models.py` — to be extended):

### A. Administrator
- Full CRUD on teacher and student accounts (create/edit/suspend/delete)
- Password resets
- Role/permission assignment
- Platform-wide statistics
- Management of all clinical cases and exams
- Global oversight

### B. Teacher
- CRUD clinical cases (create, edit at any time, delete/archive)
- Select cases to include in an exam
- Define which students/groups have access to an exam
- Schedule exam opening/closing dates
- Set a maximum duration (timer) per exam
- Review student conversations and automated evaluations
- Download PDFs of selected conversations
- Add supplementary evaluation / personalized comments

### C. Student
- Access to available training cases
- Unlimited simulations, unlimited repetition of the same case
- Free progression in training mode (no time limit)
- Full simulation history (case, date, full conversation, score, report, successes/errors/omissions, recommendations, progress over time)

**Mandatory addition:** classify students by **training level**:
- `Licence` (Bachelor's)
- `Master`

The teacher assigns/changes this level at any time. This level determines: which cases are accessible, the level of detail shown in the medication record, and which evaluation grid is applied.

---

## 3. The two simulation modes

### Training Mode (Practice)
- Free access to authorized cases
- Unlimited attempts, no time limit
- Ability to pause and resume a simulation
- Detailed evaluation at the end of each session
- Full history retained
- Progression tracker is **unlocked** (backward navigation allowed)

### Exam Mode
- Created only by a teacher, who defines: cases used, list of authorized students, start/end date-time, maximum duration (timer), specific instructions
- Timer continuously displayed
- Access restricted to the selected cases only
- Answers saved automatically
- Automatic closure when time expires
- Progression tracker is **locked** (no backward navigation)

---

## 4. Initial patient record (to be shown before the chat)

As soon as a case is opened, the student must see a **structured medical record** (a static page, NOT a chatbot response) before starting the conversation. Content (fields conditional on the scenario):

1. **Patient identity**: name/initials, age, sex, family situation, occupation, (height/weight/BMI if relevant)
2. **Medical context**: main diagnosis, associated diagnoses, reason for hospitalization/admission, date of the cardiovascular event/procedure
3. **Medical history**: cardiovascular (MI, heart failure, rhythm disorders, valve disease, arterial disease...), medical (diabetes, hypertension, dyslipidemia, renal failure, COPD, stroke...), surgical, allergies
4. **Comorbidities**
5. **Procedure(s) performed**: type, date, postoperative complications (repeatable — several procedures possible)
6. **Key medical results**: cardiac (LVEF, ECG, echo, Holter, stress test), vascular (Doppler ultrasound, ABI, angio-CT), biological (CBC, CRP, troponin, BNP/NT-proBNP, glucose, HbA1c, lipid panel, creatinine, electrolytes, blood gas), imaging
7. **Drug treatment**: presented as a prescription (therapeutic class + INN). **Licence level**: + drug effect and physio-relevant precautions. **Master level**: therapeutic class only.
8. **Physiotherapy medical prescription**: medical diagnosis, indication, objectives, precautions, contraindications — presented as an actual prescription
9. **Reference clinical parameters**: height, weight, BMI, resting HR, BP, SpO2, RR
10. **Available medical documents**: list of attached document types (prescription, physio referral, discharge letter, hospitalization/operative report, ECG, echo, lab results, imaging, other)

---

## 5. Consultation flow (phases)

The patient chatbot must only respond to what is asked, never spontaneously. The student progresses through these phases:

| Phase | Content |
|---|---|
| 1. Welcome | Introduction, therapeutic relationship, communication |
| 2. History-taking (Anamnesis) | Chief complaint, history of the illness, past history, treatments, risk factors, lifestyle habits, pain, dyspnea, fatigue, limitations, physical activity, patient's goals |
| 3. Clinical analysis | Student's reflection — **the chatbot never gives the diagnosis** |
| 4. Physiotherapy assessment | The chatbot only describes what the patient feels; the student chooses the tests (VAS, Borg, TUG, 6MWT, Sit-to-Stand, HR, SpO2, BP, auscultation...); **when the student announces a test, the chatbot returns exactly the value predefined in the case** |
| 5. Reasoning | The student proposes their clinical reasoning |
| 6. Rehabilitation program | Based on SMART objectives and the FITT model (Frequency, Intensity, Time, Type): exercises, intensity, frequency, progression, monitoring, therapeutic education — a sample session |
| 7. Incident management | Unexpected events triggered **only if predefined in the case** (chest pain, dyspnea, dizziness, feeling unwell...); the chatbot adapts its behavior based on the student's reaction |
| 8. Therapeutic education | Personalized advice |
| 9. End of care | |
| 10. Evaluation and feedback | The chatbot becomes the evaluator, only at this stage |

### Progression tracker (mandatory, always visible)
- Shows the current phase, completed steps, and remaining steps
- Overall progress bar/percentage
- **Training mode**: free navigation between phases (backward navigation allowed)
- **Exam mode**: completed steps are locked

### Timeline
- Automatic, timestamped logging of every student action (e.g. `08:31 Hello`, `08:34 Chief complaint`...), viewable after the simulation.

---

## 6. AI patient behavior (levels of intelligence)

1. **Realism**: natural responses, human-like expressions, patient sometimes worried/stressed/forgetful depending on the scenario — never robotic.
2. **Conversational memory**: remembers everything, avoids contradictions.
3. **Adaptation**: if the student rephrases a question, the response differs in wording but conveys the same information.
4. **Emotional management**: reassured / scared / angry / tired / cooperative / anxious, depending on the case scenario.

---

## 7. Pedagogical content organization

- Two student levels: **Licence** and **Master** (assignment editable by the teacher).
- Clinical cases are grouped into **pathology folders**. Each folder can contain an unlimited number of cases. The teacher can create/edit/delete/archive a folder, and move a case from one folder to another.
- Initial pathology folders to provide (but **the list must remain freely editable** — not hardcoded):
  - Ischemic heart disease
  - Non-ischemic heart disease
  - Congenital heart disease
  - Cardiac surgery
  - Heart transplant
  - Hypertension (HTN)
  - Hemodynamic regulation
  - Peripheral arterial disease of the lower limbs (PAD)
  - Special arterial diseases
  - Vascular compression syndromes
  - Venous diseases
  - Mild venous and lymphatic diseases
- Each case can be associated with the Licence level, Master level, or both; and with Training mode, Exam mode, or both.
- Any change to a case is **automatically taken into account** in the next simulations, without rebuilding the virtual patient.

---

## 8. Clinical case creation form

Expected fields in the teacher's form (full structure):

1. General information
2. Patient identity
3. Social context
4. History of the illness
5. Diagnosis
6. Past history (cardiovascular / medical / surgical / allergies — separate text fields)
7. Risk factors (text)
8. Procedure(s) — repeatable, **"+ Add a procedure"** button
9. Medications — repeatable, **"+ Add a medication"** button
10. Medical prescription (large text field)
11. Physiotherapy prescription (large text field)
12. Additional tests — text + numeric value, **"+ Add a test"** button
13. Initial parameters — text + numeric value, **"+ Add a parameter"** button
14. Physiotherapy assessment, with repeatable subsections each with its own add button:
    - General condition (long text)
    - Pain
    - Dyspnea
    - Respiratory assessment
    - Muscular assessment
    - Joint assessment
    - Neurological assessment
    - Balance
    - Gait
    - Scar (long text)
    - Exertion parameters
15. Exertion kinetics — text + numeric value, repeatable
16. Incidents — unlimited number, **"+ Add an incident"** button (trigger condition + expected patient reaction)

---

## 9. Evaluation grids (CRITICAL LOGIC)

Two distinct grids are needed, automatically selected based on the student's level, with an **eliminatory-error rule** that caps the score.

### 9.1 LICENCE GRID — "Clinical Fundamentals" (/20)
Pass threshold: **12/20** (with no eliminatory error)

**Eliminatory errors** (a single one is enough → score capped at **8/20**):
- Starting the session without checking initial vitals (BP, HR, SpO2)
- Failing to respect an absolute contraindication
- Ignoring a stopping criterion for the session
- Prescribing a dangerous exercise or inappropriate intensity
- Absence of clinical monitoring during exertion

**Score breakdown by section:**

| Section | Criterion evaluated | Pts | AI success indicators |
|---|---|---|---|
| I. Medical record analysis | Use of the initial medical record | 2 | Diagnosis identified, procedure understood, treatment accounted for, tests interpreted, risk factors/contraindications identified |
| II. History-taking | Quality of the clinical interview | 3 | Symptoms, pain, dyspnea, fatigue, functional limitations, physical activity, occupation, family situation, housing, goals, fears, motivation, relevant questions, active listening |
| III. Physiotherapy assessment | Performing the clinical assessment | 4 | Vitals (BP, HR, SpO2, RR, weight, BMI, NYHA, Borg), pain, dyspnea, fatigue, inspection, edema, scar, muscular/joint assessment, balance, gait, independence |
| IV. Clinical reasoning | Analysis and decision-making | 3 | Coherent physiotherapy diagnosis, priorities, limiting factors, precautions, appropriate SMART goals |
| V. Session prescription | Building the session | 3 | Warm-up, exercises, cool-down, monitoring, therapeutic education, coherent FITT, appropriate stopping/progression criteria |
| VI. Therapeutic communication | Therapeutic relationship | 2 | Empathy, active listening, rephrasing, plain language, trust |
| VII. Therapeutic education | Advice given to the patient | 3 | Condition, treatments, warning signs, self-monitoring, physical activity, personalized home-return advice |

### 9.2 MASTER GRID — "Clinical Expertise & Crisis Management" (/20)
Pass threshold: **14/20** (with no eliminatory error)

**Eliminatory errors** (all of the Licence ones, PLUS):
- Serious incident not recognized or ignored
- Poor conduct when facing an emergency
- Resuming the session after a major incident without medical advice
- Prescription that directly endangers the patient

**Score breakdown by section:**

| Section | Criterion evaluated | Pts | AI success indicators |
|---|---|---|---|
| I. Expert medical record analysis | Advanced record use | 2 | Critical analysis of tests, drug interactions, comorbidities, pathophysiology, prognostic factors, problem prioritization |
| II. Expert history-taking | In-depth clinical interview | 2 | Red flags, limiting factors, psychosocial context, patient understanding, relevant follow-up questions |
| III. Expert physiotherapy assessment | Complete clinical assessment | 3 | Vitals, orthostatism, functional tests, muscular/respiratory/cardiovascular assessment, balance, gait, scar and functional evaluation |
| IV. Advanced clinical reasoning | Complex analysis | 3 | Physiotherapy diagnosis, problem hierarchy, comorbidity interactions, care adaptation, clinical projection |
| V. Advanced prescription (FITT) | Program construction | 3 | Individualized prescription, progression, scientific justification, symptom-based adaptation, progression/stopping criteria |
| VI. Dynamic session management | Real-time adaptation | 2 | Continuous adjustment based on HR/BP/SpO2/Borg/pain/dyspnea/fatigue/behavior |
| VII. Incident management | Emergency situations | 3 | Early detection, sign interpretation, session stop, securing the patient, positioning, decision to resume/stop/call for medical help |
| VIII. Advanced therapeutic education | Patient empowerment | 2 | Personalized explanation, Teach-Back, self-management plan, secondary prevention, resuming activities, phase III transition criteria |

---

## 10. Student history / portfolio

For each simulation, retain: the scenario completed, the full conversation, the score, the complete evaluation report, pedagogical feedback, date and duration. Viewable at any time + PDF download.

## 11. Teacher dashboard

Must display, **for each student**:
- First/last name, class/group, pathology folder
- Total cases completed per folder, number completed / in progress, number of attempts per case
- Total time spent on the platform, average time per simulation
- Last login, overall progress (%)

**Simulation history** (per student): case name, mode (training/exam), date/time, total duration, time spent per step (history-taking, assessment, reasoning, rehabilitation, incidents...), score, status (completed/interrupted/in progress).

**Simulation detail (on click)**: full conversation, all questions/answers, tests/assessments requested and results provided, clinical decisions, incidents encountered, student's reactions, proposed physiotherapy diagnosis, rehabilitation program developed.

**Performance analytics**: score evolution over time, evolution of time needed per simulation, progress by competency, comparison between students, overall class-level statistics.

**Teacher tools**: filters (student/group/class/case/period), student search, personalized comments after a simulation, ability to complement/edit the automated evaluation, PDF download, Excel/CSV export, separate views for exam vs. training simulations.

## 12. Cross-cutting pedagogical requirements

- Clear distinction between training activities and certifying evaluations.
- Clinical cases remain evolving: any teacher update is taken into account immediately for future simulations, without rebuilding the chatbot.
- Scalable architecture: the AI engine must be independent from the database; clinical cases must be extendable without touching the code; future extension to other specialties (neurology, respiratory, orthopedics, pediatrics, geriatrics, intensive care, internal medicine) **without rebuilding the application**.

---

## 13. TECHNICAL MODIFICATION PLAN (to be executed on the `kinesitherapy` branch)

### 13.1 Git

```bash
git clone https://github.com/OussHBZ/ECOS
cd ECOS
git checkout -b kinesitherapy
```
All modifications below are made on this branch. `main` remains the generic OSCE version.

### 13.2 `models.py` — new models / fields

- **`Student`** (existing, to extend): add `level` (enum: `licence` / `master`), editable by the teacher.
- **`PathologyFolder`** (new): `id`, `name`, `specialty` (="kine"), `is_archived`, `created_by`, timestamps.
- **`ClinicalCase`** (existing, to extend): add `folder_id` (FK), `level` (enum: `licence` / `master` / `both`), `mode_availability` (enum: `training` / `exam` / `both`), `pedagogical_objectives` (text), `emotional_state` (enum or free text: reassured/scared/angry/tired/cooperative/anxious).
- **`PatientRecord`** (new, 1-1 with `ClinicalCase`): all fields of the initial medical record (section 4) — identity, medical context, history (by category), comorbidities, tests (by category), reference parameters, prescriptions (medical + physio), available documents (list of types).
- **`Intervention`** (new, N-1 with `PatientRecord`): type, date, possible complications — repeatable.
- **`Medication`** (new, N-1 with `PatientRecord`): therapeutic class, INN, effect/precautions (shown only if level = Licence).
- **`Incident`** (new, N-1 with `ClinicalCase`): trigger description, trigger condition (e.g. phase >= assessment, or a specific action), scripted patient reaction, severity (minor/major — used for the Master grid).
- **`EvaluationGrid`** (new, or extend `evaluation_config.py` in the DB): `level` (licence/master), `sections` (JSON or linked table: section, criterion, points, AI indicators), `elimination_rules` (list of rules), `validation_threshold`, `elimination_cap` (=8).
- **`SimulationSession`** (existing, to extend): `mode` (training/exam), `status` (completed/interrupted/in_progress), `current_phase`, `phase_timings` (JSON), `timeline` (JSON, list of `{timestamp, action}` objects), `eliminatory_error_triggered` (bool + which one).
- **`Exam`** (existing under some other form in the blueprints, or new): cases used, authorized students/groups, start/end date-time, max duration, instructions.

Migration: Alembic script or manual SQLite migration (adapt `init_db.py`) to add these tables/columns without losing existing generic OSCE data.

### 13.3 `document_processor.py`

Extend the extraction schema to recognize and automatically populate the physio-specific fields (categorized cardiovascular history, procedures, assessment by domain, vitals, incidents mentioned in the source document). The LLM extraction prompt must be updated to target these fields (see `response_template.json`, to be extended with a new physio template).

### 13.4 `evaluation_config.py`

Add both complete grids (sections 9.1 and 9.2) as structured configuration: sections, criteria, points, AI indicators per criterion, list of eliminatory errors per level, pass threshold, capping rule.

### 13.5 `evaluation_agent.py` / `enhanced_evaluation_agent.py`

- Load the grid based on `student.level`.
- Detect the presence of an eliminatory error in the transcript (dedicated LLM analysis or heuristic rule + LLM confirmation) → if detected, apply the cap (8/20) regardless of the sum of points otherwise earned.
- Return a detailed score per section (7 sections Licence / 8 sections Master) + qualitative justification per section, consistent with the format already used by the existing categorized engine.

### 13.6 New: virtual patient engine (extension of the existing prompt engineering)

- **No spontaneous disclosure**: strengthen the system prompt so the patient only answers the question asked, without adding unsolicited information.
- **Test value lookup**: intent detection ("I'm going to measure your..." / "I'm going to do a ... test") → look up the corresponding value in `PatientRecord`/the physio assessment instead of free LLM generation.
- **Blocking direct diagnosis**: explicit constraint — the patient must never state a physiotherapy diagnosis, only describe how they feel.
- **Emotional state**: inject the case's `emotional_state` into the system prompt, with corresponding tone instructions.
- **Incident triggering**: lightweight state machine — checks the current phase and the trigger conditions of the `Incident`s linked to the case; if triggered, injects the scripted reaction into the patient's next response and adapts behavior.
- Suggested file: `kine_patient_engine.py` (new), called in addition to the existing dialogue engine rather than replacing it, so as not to break the generic OSCE behavior.

### 13.7 New: progression management

- Suggested file: `progression_tracker.py`.
- State machine for the 10 phases (section 5).
- Training mode: free navigation (backward allowed).
- Exam mode: completed steps locked.
- Exposes the current state to the API/frontend for tracker display + progress percentage calculation.

### 13.8 New: timeline

- Every student action (message sent, test requested, phase change) is logged with a timestamp in `SimulationSession.timeline`.
- Endpoint to retrieve the formatted timeline (used by the teacher dashboard).

### 13.9 `simple_pdf_generator.py`

Extend to generate:
- The simulation report with the new grid format (7 or 8 sections depending on level), mention of the eliminatory error if any, and whether the pass threshold was reached.
- Excel/CSV export option for teacher dashboards (new function, or new file `export_generator.py` using `openpyxl`/`csv`).

### 13.10 `blueprints/`

Add a dedicated blueprint to separate physio routes from the generic OSCE ones, for example:
```
blueprints/kine/
    __init__.py
    routes_admin.py       # pathology folders, student level management
    routes_teacher.py     # case creation (full form, section 8), incidents, exams
    routes_student.py     # initial patient record, chat, tracker, history
    routes_dashboard.py   # teacher dashboard (stats, filters, export)
```
New routes needed (non-exhaustive list):
- `GET/POST /kine/folders` (pathology folder CRUD)
- `GET/POST /kine/cases` (case CRUD, with all fields from section 8)
- `GET/POST /kine/cases/<id>/incidents` (incident CRUD)
- `GET /kine/cases/<id>/patient-record` (initial medical record display before chat)
- `POST /kine/simulation/start`, `POST /kine/simulation/<id>/message`, `POST /kine/simulation/<id>/test-request`
- `GET /kine/simulation/<id>/progress` (tracker state)
- `GET /kine/simulation/<id>/timeline`
- `POST /kine/exams`, full exam management (dates, duration, authorized students)
- `GET /kine/dashboard/student/<id>`, `GET /kine/dashboard/export` (Excel/CSV)
- `PUT /kine/students/<id>/level` (Licence/Master assignment)

### 13.11 `templates/` and `static/` (frontend)

New views to create:
- `patient_record.html`: structured display of the initial medical record (before opening the chat)
- `progression_tracker` (reusable JS/CSS component): phase bar + progress %, different behavior for training/exam
- `case_form_kine.html`: case creation form exactly reproducing the structure of section 8 (repeatable fields with "+" buttons)
- `incident_manager.html`: teacher interface to create/manage a case's incidents
- `teacher_dashboard_kine.html`: dashboard with the indicators from section 11 (per-student stats, filters, export)
- `timeline_view.html`: display of a simulation's timestamped timeline
- Update the existing chat view to embed the permanently visible progression tracker + a conditional timer (exam mode only)

### 13.12 Server / configuration / deployment

- No major new infrastructure dependency in principle (still Flask + SQLite/SQLAlchemy). However, plan for:
  - `requirements.txt`: add `openpyxl` (Excel export) if not already present, check `python-dateutil` for exam date/timer handling.
  - Environment variables (`.env`): no new API key required if the same Groq model is reused; if a separate model/API is used for physio extraction, add the corresponding key.
  - `init_db.py`: update to create the new tables (section 13.2) and seed the initial pathology folders (section 7) as default, editable data (not hardcoded in application code).
  - Plan a scheduled task (or a per-request check) to automatically close exam sessions once the timer expires **server-side** (do not rely solely on client-side JS).
  - In the Flask config, clearly separate "generic OSCE" cases (`main` branch) from "physio" cases (`kinesitherapy` branch) if both are to eventually coexist in the same environment — plan a `specialty` field to filter at the query level.

### 13.13 Backward compatibility

- Do not modify the behavior of existing routes/models used by the generic OSCE — any extension should be done by **adding optional fields / new tables**, not by destructively modifying existing tables.
- The existing categorized evaluation engine (`enhanced_evaluation_agent.py`) must keep working for non-physio cases; the per-level grid logic and capping rule must be conditioned on `specialty == "kine"`.

---

## 14. Recommended execution order

1. Create the `kinesitherapy` branch.
2. Modify `models.py` + `init_db.py` (new tables/fields), test the migration on a copy of the database.
3. Build the initial medical record (static display — no AI required): quick to validate.
4. Build the full case creation form (section 8).
5. Build the progression tracker (frontend/backend state, no AI).
6. Extend the virtual patient's prompt engineering (no spontaneous disclosure, test values, diagnosis blocking, emotional state).
7. Build the incident engine.
8. Implement the two evaluation grids + the eliminatory-error capping logic.
9. Build the teacher dashboard + exports.
10. End-to-end testing: one complete cardiovascular case, at both Licence and Master level, with and without an eliminatory error, in both training and exam mode.

---

## 15. Acceptance criteria

- A teacher can create a pathology folder, create a complete case within it with all the fields from section 8, and attach incidents to it.
- A Licence student sees the medication record with effect/precautions; a Master student sees only the therapeutic class.
- The virtual patient never reveals unsolicited information and never states a diagnosis.
- A test value announced by the student returns exactly the value predefined in the case.
- An incident only triggers if defined in the case, and only under the predefined conditions.
- The final score respects the 8/20 cap in case of an eliminatory error, regardless of the grid (Licence/Master).
- Exam mode locks navigation between phases and closes automatically when time expires, server-side.
- The teacher dashboard displays all the indicators from section 11 and allows PDF/Excel/CSV export.
- No regression on the generic OSCE features of the `main` branch.
