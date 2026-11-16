# Référence actuelle — T04 complétée le 06/11/2026

**303 Python + 9 JavaScript réussis**, zéro échec/erreur/skip Python. T04 ajoute la politique atomique/versionnée, le journal immuable des informations révélées, les projections serveur communes et la migration 004 répétable. [Rapport T04](../output/cahier-charge-21-10/10_ACCES_INFORMATION.md).

```powershell
& tmp/t01/venv-2026-11-03/Scripts/python.exe -I ECOS/scripts/run_tests.py --label full-regression-verified-2026-11-06 --task t04
```

Le label ci-dessus est déjà utilisé ; en choisir un nouveau pour rejouer. Preuve : `output/cahier-charge-21-10/preuves/t04/full-regression-verified-2026-11-06/summary.json`. La suite s’exécute sur copie temporaire, avec réseau/base réelle/écritures externes bloqués et fichiers réels protégés.

---

# Référence actuelle — T03 complétée le 06/11/2026

**299 Python + 9 JavaScript réussis**, zéro échec/erreur/skip Python. T03 raccorde publications immuables, attribution explicite, démarrage public, versions d'examen, capture niveau/seuil/référentiel et migration reconstruite signalée. Trois cas nets ont été ajoutés ; les attentes qui lisaient une copie de travail modifiée ont été adaptées pour publier puis attribuer la nouvelle version, conformément aux pages 3, 8 et 93. [Rapport T03](../output/cahier-charge-21-10/08_VERSIONS_ET_REFERENTIEL.md).

```powershell
& tmp/t01/venv-2026-11-03/Scripts/python.exe -I ECOS/scripts/run_tests.py --task t03 --label activation-final-candidate-2026-11-06
```

Le label ci-dessus est déjà utilisé ; en choisir un nouveau pour rejouer. La suite reste exécutée dans une copie temporaire avec les gardes T01. Aucune base réelle, dépendance ou secret n'a été modifié.

---

# Référence actuelle — T02 complétée le 06/11/2026

**296 Python + 9 JavaScript réussis**, après relecture T01/D02 et corrections ciblées. 28 cas ajoutés, 268 anciens cas conservés ; échecs reproduits avant correction archivés. Cycle des comptes, révocation de sessions, périmètres et séparation des espaces contrôlés ; brouillons privés, historiques mixtes et collision de fichiers d'export corrigés. [Rapport T02](../output/cahier-charge-21-10/07_COMPTES_ET_PERMISSIONS.md).

Depuis le workspace (label exécuté déjà utilisé ; en choisir un neuf pour rejouer) :

```powershell
& tmp/t01/venv-2026-11-03/Scripts/python.exe -I ECOS/scripts/run_tests.py --task t02 --label permissions-final-2026-11-06
```

Environnement, verrou, garde et stratégie de migration T01 conservés ; aucune base réelle ouverte. Le lanceur exécute aussi les deux fichiers Node, dont `tests/test_case_form_ui.cjs`. Pas de nouvelle migration, ni changement des règles cliniques. Les blocs ci-dessous sont historiques ; les [décisions](../output/cahier-charge-21-10/DECISIONS.md) et la [passation](../output/cahier-charge-21-10/PASSATION.md) du dossier de cahier des charges font référence.

---

# Référence actuelle — T01 revérifiée le 03/11/2026

T00 et l'arbre actuel ont été contrôlés. Nouveau venv `tmp/t01/venv-2026-11-03` : Python 3.12.14/Windows AMD64, 61 distributions du verrou existant installées hors ligne, ABI/hashes/contraintes et pip check vérifiés. **268 Python + 9 JS réussis**, commande exacte `node --test tests/test_case_form_ui.cjs` également exécutée dans la copie (**3/3**, sous-ensemble des 9). Aucun code/test/dependency modifié pour cette revalidation.

Depuis la racine du workspace, pour rejouer la suite avec l'environnement préparé et un **label neuf** :

```powershell
& tmp/t01/venv-2026-11-03/Scripts/python.exe -I ECOS/scripts/run_tests.py --task t01 --label votre-nouveau-label
```

Ne pas réutiliser `.venv` Python 3.11 ni mélanger ses site-packages avec Python 3.12. Pour recréer un environnement, choisir un répertoire inexistant et suivre les [commandes d'installation/reproduction et la stratégie actualisée](../output/cahier-charge-21-10/06_BASE_TESTS_ET_MIGRATIONS.md). Ce rapport détaille la commande Node exacte, les gardes et les limites de couverture. Le lanceur exécute déjà les deux fichiers JS (9 cas) dans la copie.

Les anciens blocs ci-dessous conservent la chronologie. Les références métier actuelles sont [DECISIONS.md](../output/cahier-charge-21-10/DECISIONS.md) et [PASSATION.md](../output/cahier-charge-21-10/PASSATION.md) dans le dossier de cahier des charges : D08 est définie et T03-ACC-a/b est tranchée pour T03. Ne pas lire les anciennes mentions D08/T02/T03-ACC comme l'état courant.

---

# Référence de tests T01

Validé le 30/10/2026 : CPython **3.12.14**, Windows amd64, Node **24.13.0**. Le venv applicatif `.venv/` en Python 3.11 reste intact mais son interpréteur Windows Store n'est pas lançable sur cette machine. Ne pas ajouter ses site-packages à un Python 3.12.

`requirements.txt` est inchangé. `requirements-test.lock` fige les 61 distributions résolues dans ses contraintes et les SHA-256 des roues effectivement utilisées. Les empreintes natives sont propres à Windows amd64/CPython 3.12 : ne pas les présenter comme un verrou Linux ou Python 3.11. Ne pas remplacer les dépendances de production avec ce fichier sans validation de sa plateforme.

## Reproduire depuis la racine du workspace

PowerShell ; choisir un interpréteur CPython 3.12 compatible. Le chemin ci-dessous est celui réellement disponible pendant T01, pas un prérequis universel :

```powershell
$taskPython = 'C:/Users/oussa/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $taskPython -m venv tmp/t01/venv
& tmp/t01/venv/Scripts/python.exe -I -m pip install --require-hashes -r ECOS/requirements-test.lock
& tmp/t01/venv/Scripts/python.exe -I -m pip check
& tmp/t01/venv/Scripts/python.exe -I ECOS/scripts/run_tests.py --label recette-unique
```

Utiliser un chemin de venv neuf si celui proposé existe déjà ; ne pas écraser l'ancien environnement. Chaque label doit être inédit : le lanceur refuse de remplacer des preuves précédentes. L'installation nécessite l'accès au dépôt de paquets ; les tests eux-mêmes n'utilisent pas de service externe.

Pour la reproduction **hors ligne réellement exécutée dans T01**, les roues locales sont dans `tmp/t01/wheels/` :

```powershell
& $taskPython -m venv tmp/t01/repro-venv
& tmp/t01/repro-venv/Scripts/python.exe -I -m pip install --no-index --find-links tmp/t01/wheels --require-hashes -r ECOS/requirements-test.lock
& tmp/t01/repro-venv/Scripts/python.exe -I -m pip check
& tmp/t01/repro-venv/Scripts/python.exe -I ECOS/scripts/run_tests.py --label reproduction-offline
```

Ces deux chemins et ce label ont déjà été utilisés pendant T01 ; pour une nouvelle exécution choisir un nouveau venv/label. Les roues sont un cache local non versionné. Le lock et le rapport d'installation permettent aussi de les récupérer puis de vérifier leurs empreintes.

Sélection ciblée, toujours dans une copie temporaire :

```powershell
& tmp/t01/venv/Scripts/python.exe -I ECOS/scripts/run_tests.py --label migrations-ciblees tests/test_migration_baseline.py
```

Le lanceur exécute également la commande réelle `node --test tests/test_case_form_ui.cjs` dans la copie. Le code de sortie global est non nul si Python/Node échouent, si les données réelles changent ou si les gardes constatent un accès interdit. Consulter `summary.json`, pas seulement la dernière commande affichée.

## Isolation et effets de bord

- Copie des sources suivies et des nouveaux fichiers de test non ignorés, sans `.env`, données, uploads, journaux, sessions ou `.venv` existants. Les tests écrivent sous un nouveau `tmp/t01/<label>-.../` ; la copie reste disponible pour diagnostic.
- Environnement enfant limité : aucune clé IA ou variable de tracing héritée, autochargement des plugins pytest désactivé, pas de compte démo créé. Le répertoire temporaire système de l'enfant est local au run.
- Garde Python vérifiée au démarrage : connexions/DNS réseau, lecture du dépôt réel, connexion à sa base et écriture externe refusées. SQLite seulement en mémoire ou sous le run. Le périphérique sans stockage `nul` est permis ; la sonde IPv6 locale d'urllib3 est refusée et comptée séparément des connexions sortantes.
- Import d'`app.py` par les tests de la fonction additive : il configure des journaux dans la **copie**. La fabrique `create_app` n'est pas appelée par la suite mesurée. `init_database`, `reset_database` et la commande `init_db.py` ne sont jamais lancés.
- Empreintes des fichiers réels sous instance/uploads/images de cas/sessions/logs, et de `.venv/pyvenv.cfg`, comparées avant/après. Aucune connexion à la base réelle. Ces gardes de régression ne sont pas un bac à sable OS destiné à exécuter du code hostile.

Ne pas lancer directement `flask run`, `app.create_app()` ou `init_db.py` pour vérifier une migration : la fabrique cible une base locale fixe, effectue des migrations/seeds et tente un ping Groq. Le lancement applicatif et les migrations au démarrage ne sont pas certifiés par cette référence de tests.

## Portée des résultats

Suite initiale : 102 cas paramétrés réussis. Ajouts T01 : deux tests de migration sur fichiers SQLite fictifs, soit 104 cas. JavaScript : trois tests de handlers/DOM/fetch simulés, sans navigateur. Les clients IA sont simulés ou absents selon le comportement historique testé ; aucun appel à une vraie IA, aucun test clinique ni charge réelle.

Les tests de règles anciennes restent présents : phase obligatoire, plafond 8/20, incidents Master seulement et calcul par motifs. Leur réussite décrit la référence actuelle ; elle ne certifie pas ces règles conformes à KardioX. Le rapport T01 identifie précisément leurs remplacements futurs et les pages du PDF. Aucun test existant n'a été supprimé ni modifié pour T01.

Preuves et stratégie : [rapport T01](../output/cahier-charge-21-10/06_BASE_TESTS_ET_MIGRATIONS.md), [résultats](../output/cahier-charge-21-10/preuves/t01/), [décisions métier](../DECISIONS.md).

## Actualisation T02 - 30/10/2026

Le code local comporte maintenant T02. Référence finale exécutée : **235 tests Python réussis, 0 échec/erreur/skip ; 9 JS réussis**, sans appel IA réel. Le harness conserve les preuves dans le sous-dossier de tâche choisi ; les données temporaires restent sous `tmp/t01/` par compatibilité avec T01.

```powershell
# Commande réellement exécutée ; choisir un label neuf pour la reproduire.
& tmp/t01/repro-venv/Scripts/python.exe -I ECOS/scripts/run_tests.py --task t02 --label permissions-final
```

La commande JS enfant exécutée est désormais `node --test tests/test_case_form_ui.cjs tests/test_security_ui.cjs`. Les clients de test envoient le vrai jeton CSRF de leur session ; aucun bypass `TESTING` n'existe côté serveur. Les scénarios négatifs peuvent omettre/forger le jeton. Les attributions enseignant/étudiant des fixtures sont explicites, jamais déduites en production.

La migration `account_migrations.upgrade_account_lifecycle` est testée sur des fichiers SQLite fictifs uniquement (ajout répété, défaillance/reprise, schéma incompatible, checksum, sauvegarde/restauration, résultats historiques intacts). Ne pas utiliser `init_db.py` ou `create_app()` pour reproduire ces tests. Le lancement complet reste non exécuté.

Les anciens scénarios restent présents. Le scénario de recherche d'examen reçoit maintenant une attribution fictive explicite (D02, pp.97–98). Le test de suppression d'enseignant vérifie désormais refus 409 et références intactes, conformément au choix utilisateur « Suspension uniquement pour l'instant ; suppression à décider plus tard », p.100 pour conservation. Le test n'a pas été supprimé.

[Rapport et matrice des permissions T02](../output/cahier-charge-21-10/07_COMPTES_ET_PERMISSIONS.md), [preuve finale](../output/cahier-charge-21-10/preuves/t02/permissions-final/summary.json), [manifeste des fichiers/commandes/contrôles statiques](../output/cahier-charge-21-10/preuves/t02/livraison.json). Les contrôles `node --check`/`git diff --check` ne sont pas des tests fonctionnels. Navigateur, charge/concurrence, vraie IA et production restent non testés.

## Actualisation T03 partielle — 30/10/2026

Dernière suite exécutée : **268 Python + 9 JS réussis**. Commande depuis le workspace (choisir un label neuf pour reproduire) :

```powershell
& tmp/t01/repro-venv/Scripts/python.exe -I ECOS/scripts/run_tests.py --task t03 --label verified-foundation-pending-decisions
```

Sélection ciblée réellement exécutée également : `--task t03 --label migration-target tests/test_case_version_migration.py tests/test_case_versions.py` (31 Python + 9 JS). Le label et les logs sont conservés. Le socle de versions est testé après capture explicite du service ; ces réussites ne prouvent pas le raccordement du démarrage public, encore en attente D08. Le helper additif existant appelle désormais la migration de stockage 003 après 002 ; les tests correspondants utilisent toujours des bases fictives et ne réécrivent aucun résultat historique.

[Rapport et limites](../output/cahier-charge-21-10/08_VERSIONS_ET_REFERENTIEL.md), [preuve finale](../output/cahier-charge-21-10/preuves/t03/verified-foundation-pending-decisions/summary.json). Aucun test hérité n'a été supprimé. Fabrique complète, navigateur, vraie IA, charge et production non exécutés. Continuer T03 avant T04.
