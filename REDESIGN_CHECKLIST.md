# ECOS / KardioX — interface coverage

## Révision après captures — 13 novembre 2026

Complément ETP / attribution : classes de formulaire partagées ajoutées à la bibliothèque et aux adaptations ETP ; catégories et paroles du patient disposées en grilles responsive ; libellés au-dessus des champs ; listes multiples d’attribution élargies. Passage `etp-layout-2026-11-13` : 20 tests Python et 29 tests JavaScript réussis, aucun fichier protégé modifié. Rendu navigateur toujours non vérifié.

Les captures fournies ont été examinées. Le contrôle ci-dessous distingue la lecture du code et les tests automatisés d’une validation visuelle dans un navigateur.

| Écrans / composants inspectés dans le code | Corrections partagées |
|---|---|
| Administration : étudiants, enseignants, import CSV/Excel, création et réinitialisation de comptes | Suppression du `nowrap` global de la dernière cellule ; actions regroupées dans un conteneur flex à l’intérieur des cellules ; dates protégées ; défilement local avec accès clavier. Suppression des marges négatives des actions et du minimum de 600 px appliqué au tableau d’exemple. |
| Modification de profil et étudiants suivis | Même composant de dialogue natif centré, titre et fermeture, corps défilant, grille responsive, pied d’actions ; noms des champs, validations et requêtes conservés. |
| Modales ECOS : détails de stations et étudiants, édition de cas, résultats de compétition, images et surveillance | Structure partagée appliquée aux nœuds existants sans recréer leurs événements. Suppression de la rotation des boutons textuels. Aperçu d’image enseignant intégré au composant partagé. |
| Tous rôles : navigation, statistiques, formulaires et tableaux | Anciens fond/ombre/trait de navigation retirés dans la barre latérale ; décor des statistiques retiré ; actions de formulaire sans marges négatives ; cellules conservées en cellules de tableau. |
| KardioX : tableaux de bord, dossier, simulation, éditeur, évaluations et historique | Relecture des composants hérités, des grilles et contraintes de largeur ; libellés longs des graphiques visibles ; compétences et contrôles répétés adaptés au petit écran. |
| Clavier / fermeture | Blocage du défilement de fond, focus dans le dialogue et restitution au déclencheur, Tab/Échap, confirmation avant abandon d’une saisie modifiée. Les fermetures après enregistrement restent pilotées par leurs événements existants. |

Vérifications de cette révision : 29 tests JavaScript réussis, dont conservation du profil après erreur puis nouvelle soumission, contenu des attributions enseignant, navigation et focus des modales ; syntaxe des 19 fichiers JavaScript vérifiée. Les tests de formulaire et de focus utilisent des doubles DOM, pas un moteur de rendu.

Le premier passage ciblé (`design-review-2026-11-12`) a réussi ses 52 tests Python et 27 tests JavaScript. Son contrôle global a toutefois détecté la modification concurrente d’un fichier de session du serveur local : ce passage n’est donc pas présenté comme une preuve d’intégrité globale. Le garde d’accès du processus de tests n’a enregistré aucune écriture hors bac à sable. Un passage final est consigné séparément.

Passage final `design-review-final-2026-11-13` : **52 tests Python + 29 tests JavaScript réussis**, zéro fichier protégé modifié, résultat global `success: true`. Les 42 templates compilent via les tests de pages ; `git diff --check` passe. Aperçu isolé lancé sur le port 5091 : réponses HTTP 200 pour les espaces étudiant et enseignant KardioX, étudiant et enseignant ECOS standard, administration technique et administration pédagogique, ainsi que la feuille de style partagée. Ces réponses HTTP ne constituent pas une validation visuelle.

**Non vérifié visuellement** : 375 px, 768 px, 1366 px, 1920 px, fenêtre de faible hauteur, zoom 200 %, formulaires et fenêtres réellement ouverts, contenus longs et navigation clavier dans un navigateur. L’outil a répondu « The browser access host is unavailable », puis l’outil navigateur a été retiré de la session. Aucune capture après correction disponible. La validation visuelle reste à effectuer ; les tests ci-dessous ne la remplacent pas.

---

Brand source: `static/css/styles.css`, original primary **#a35119**. Existing Flask/Jinja and JavaScript architecture retained. All existing changes present before this redesign are preserved.

Inventory completed before implementation: **39 templates (26 pages/layouts and 13 fragments)**, plus dynamically generated ECOS screens and dialogs in `student.js`, `teacher.js`, `admin.js` and KardioX component scripts. Three shared templates were added: `app_base`, `_app_sidebar`, `_public_brand`. “Implemented” below means the screen uses the shared theme and applicable layout; it does not mean browser visual verification has passed.

| Coverage | Screens / source | State |
|---|---|---|
| Shared shell | `kine_base`, standard role pages, account identity, logout, mobile menu | Implemented |
| Public access | `home`, `login`, `error` | Implemented |
| Student KardioX | `student_kine_home`, `patient_record`, `student_history_kine` (history / portfolio) | Implemented |
| Simulation | `chat_kine`, `patient_record_embedded`, progression, effort tests, session actions, assistance, results | Implemented |
| Teacher dashboard | `teacher_dashboard_kine`: filters, reports, exams, case assignments / versions, student progression, conversations | Implemented |
| Authoring | `case_form_kine`, `case_imports_kine`, `case_import_batch_kine`; information policy, personality, effort tests | Implemented |
| Clinical configuration | `rehabilitation_kine` / FITT-VP, `incident_manager`, `criteria_kine`, `teaching_aids_kine`, `patient_preview_kine`, `effort_observer_kine` | Implemented |
| ETP / assessment | `etp_library_kine` / versions, `etp_case_kine`, `evaluation_thresholds_kine`, `timeline_view`, human review / feedback | Implemented |
| Standard ECOS student | `student`: practice, conversation, competitions / waiting / results, statistics, image / result dialogs | Implemented |
| Standard ECOS teacher | `teacher`: manual / file creation, editing, stations, performance / reports, dialogs | Implemented |
| Administration | `admin`: overview, stations, students, teachers, accounts / resets / assignments, competition setup / monitoring | Implemented |
| Shared states | Tables, search / filters, pagination, messages, empty / loading / validation states, dialogs | Implemented |
| Reports | Brown/beige PDF palette in `simple_pdf_generator` / `kine_personal_pdf`; shared print CSS; content / visibility unchanged | Implemented |

No standalone self-service account recovery or settings route exists. Password reset, account status and account editing are administrator dialogs; included above. No standalone group page exists: group fields and assignments are in account administration and exam / case forms.

All 13 original fragments inherit the shared design: `_criteria_result`, `_criteria_review`, `_effort_student`, `_effort_tests_form`, `_etp_categories`, `_etp_prompts`, `_information_policy_form`, `_kine_evaluation_details`, `_patient_personality_form`, `_patient_record_content`, `_progression_tracker`, `_report_totals`, `_session_student`.

The embedded dossier intentionally has no second sidebar: its parent simulation supplies navigation. It loads the same tokens/components. Existing JSON responses and downloads remain APIs/exports; no new routes or modules were invented.

Verification:

- Existing full regression: **400 Python + 21 JavaScript passed** (`redesign-first-2026-11-11`).
- Focused route, report and visibility checks: **80 Python + 25 JavaScript passed** (`redesign-coverage-2026-11-11`). New coverage includes standard and KardioX roles, secondary clinical pages, shared script loading and reserved-information exclusion.
- Shared navigation tests exercise mobile open/close, Tab in both directions, Escape, backdrop, resizing and dynamic dialog focus restoration with DOM doubles.
- All **42 templates compile**. All **19 JavaScript files pass syntax checks**. `git diff --check` passes (existing Git line-ending notices remain).
- Token contrast: white on brown **5.60:1**; muted text on warm white **5.81:1**; body text **13.85:1**; active navigation **5.97:1**.
- Final full regression: **420 Python passed**, zero failures/errors/skips, in 284.72 seconds (`redesign-final-2026-11-12`). Its source snapshot also passed 25 JavaScript tests. After the additional dialog test and final text-control cleanup, **all 26 JavaScript tests passed**; see `../output/redesign/javascript-tests.txt` and `static-checks.json`.

Evidence is under `../output/cahier-charge-21-10/preuves/t20-t22/`. The guards reported no protected data changes and no forbidden access. Existing user changes were retained; the starting presentation snapshot is under `../tmp/redesign-original/`.

Remaining verification limitation: **browser visual QA is blocked**. The browser tool reported “The browser access host is unavailable”; the native Edge fallback timed out waiting for app access. A retry on 12 November returned the same browser-host error. No screenshots were captured. Desktop/tablet/mobile rendering, 200% zoom, real browser keyboard/screen-reader behavior and visual PDF layout have therefore **not** been certified. Responsive CSS and keyboard behavior are implemented, with automated checks as described above.

An isolated preview helper is available at `../tmp/redesign_preview.py` (memory database, existing synthetic fixtures, no production factory or real AI). From the workspace root: `tmp/t01/venv-2026-11-03/Scripts/python.exe -I -X utf8 tmp/redesign_preview.py`; it serves localhost port 5091 with `/ui/student`, `/ui/teacher`, `/ui/standard-student`, `/ui/standard-teacher`, `/ui/admin`, `/ui/pedagogical`. Do not deploy this fixture helper.
