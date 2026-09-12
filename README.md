# ECOS — Simulateur de consultations cliniques

Plateforme Flask de formation médicale permettant de réaliser des consultations avec des patients virtuels pilotés par IA, d’évaluer les étudiants et de suivre leur progression.

Le projet propose deux espaces distincts :

- **ECOS standard** : stations cliniques générales, sessions et compétitions historiques ;
- **ECOS Kiné** : parcours spécialisé de kinésithérapie cardiovasculaire avec dossier patient, tracker pédagogique, modes entraînement et examen, incidents cliniques et grilles Licence/Master.

Les comptes sont affectés exclusivement à un espace par l’administrateur. Un étudiant ou un enseignant Kiné ne peut pas accéder à l’ECOS standard, et inversement.

## Fonctionnalités principales

### Administration

- Gestion des étudiants, enseignants et administrateurs.
- Affectation du type de compte : **ECOS standard** ou **ECOS Kiné**.
- Affectation du niveau Kiné : **Licence** ou **Master**.
- Séparation des cas, activités et statistiques par spécialité.
- Statistiques unifiées incluant les simulations Kiné terminées.
- Import de comptes depuis des fichiers CSV ou Excel.
- Gestion des sessions et compétitions de l’ECOS standard.

### ECOS standard

- Création manuelle ou automatique de cas cliniques.
- Import de documents PDF et Word et prise en charge d’images médicales.
- Conversations avec un patient virtuel.
- Chronomètre, consignes de station et grilles personnalisées.
- Sessions et compétitions multi-stations.
- Évaluation automatique, recommandations et rapports PDF.

## Extension ECOS Kiné

### Gestion des cas cliniques

L’enseignant Kiné peut :

- créer, consulter, modifier, télécharger, archiver ou supprimer un cas ;
- choisir son niveau : Licence, Master ou les deux ;
- choisir sa disponibilité : entraînement, examen ou les deux ;
- définir ses objectifs pédagogiques et l’état émotionnel du patient ;
- classer le cas dans un dossier pathologique ;
- renseigner l’identité, le contexte médical et social, l’histoire, les antécédents et les comorbidités ;
- ajouter des procédures, médicaments, prescriptions, examens, constantes et documents ;
- structurer le bilan kinésithérapique par domaine ;
- préparer les valeurs exactes des tests demandés pendant la simulation ;
- créer des incidents avec condition de déclenchement, réaction scénarisée et gravité.

Douze dossiers pathologiques Kiné sont ajoutés automatiquement et restent modifiables :

1. Cardiopathie ischémique
2. Cardiopathie non ischémique
3. Cardiopathie congénitale
4. Chirurgie cardiaque
5. Transplantation cardiaque
6. Hypertension artérielle (HTA)
7. Régulation hémodynamique
8. Artériopathie oblitérante des membres inférieurs (AOMI)
9. Pathologies artérielles particulières
10. Syndromes de compression vasculaire
11. Pathologies veineuses
12. Pathologies veineuses et lymphatiques légères

### Extraction automatique des documents

Les formulaires Kiné acceptent les documents PDF, DOC, DOCX, JPG, JPEG et PNG.

Le processeur :

- extrait le texte et les tableaux ;
- utilise le modèle Groq configuré pour produire des données structurées ;
- cible l’histoire par catégorie, les procédures, les médicaments, les prescriptions, les examens, les constantes, le bilan par domaine et les incidents ;
- préremplit le formulaire sans enregistrer immédiatement le cas ;
- demande à l’enseignant de vérifier les données avant l’enregistrement ;
- retourne des erreurs lisibles en cas d’expiration de session, de document trop volumineux ou d’indisponibilité du service.

La limite applicative d’un document est de **25 Mo**. En production, `client_max_body_size` de Nginx doit être configuré à une valeur au moins équivalente.

### Dossier patient initial

Avant la conversation, l’étudiant consulte une vue statique du dossier médical. Les valeurs absentes sont masquées ou représentées proprement, sans afficher de JSON brut ni dupliquer les examens.

Le dossier peut contenir :

- identité et contexte social ;
- histoire médicale et comorbidités ;
- examens biologiques, cardiaques, vasculaires et d’imagerie ;
- constantes et valeurs de référence ;
- traitement médicamenteux et précautions Kiné ;
- prescriptions ;
- bilan kinésithérapique ;
- documents disponibles.

### Patient virtuel Kiné

Le moteur patient applique des règles spécialisées :

- ne jamais donner spontanément une information non demandée ;
- ne jamais révéler directement le diagnostic ou la solution ;
- résister aux demandes de contournement et aux injections de prompt ;
- répondre comme le patient et non comme l’évaluateur ou l’enseignant ;
- intégrer l’état émotionnel défini dans le cas ;
- fournir uniquement la valeur prévue lorsqu’un étudiant annonce un test ou une mesure ;
- déclencher un incident seulement si le dossier et sa condition le prévoient ;
- adapter la réaction du patient à la conduite de l’étudiant.

### Tracker de progression

Le tracker reste visible pendant toute la simulation et comprend 11 étapes :

1. Accueil et présentation
2. Anamnèse
3. Analyse des antécédents et des facteurs de risque
4. Bilan kinésithérapique
5. Analyse et raisonnement clinique
6. Objectifs thérapeutiques
7. Élaboration du programme de rééducation
8. Gestion des incidents cliniques
9. Éducation thérapeutique
10. Fin de la prise en charge
11. Évaluation et feedback

Il affiche la phase actuelle, les étapes réalisées et restantes ainsi qu’un pourcentage global.

- En **mode entraînement**, l’étudiant peut revenir à une phase précédente, interrompre puis reprendre la séance.
- En **mode examen**, la navigation est verrouillée et les phases terminées ne peuvent pas être rouvertes.

### Mode entraînement

- Accès libre aux cas autorisés pour le niveau de l’étudiant.
- Nombre illimité de tentatives.
- Aucune durée maximale.
- Pause et reprise d’une simulation.
- Évaluation détaillée en fin de séance.
- Conservation de toutes les tentatives dans l’historique.
- Consultation ultérieure des commentaires de l’enseignant.

### Mode examen

L’enseignant peut :

- sélectionner un ou plusieurs cas compatibles avec le mode examen ;
- autoriser des étudiants précis ou des groupes ;
- programmer la date et l’heure d’ouverture et de fermeture ;
- définir une durée maximale ;
- ajouter des consignes spécifiques.

Pendant l’examen :

- seuls les examens ouverts et autorisés apparaissent pour l’étudiant ;
- seuls les cas sélectionnés sont accessibles ;
- un chronomètre est affiché ;
- chaque interaction est enregistrée ;
- la simulation est clôturée côté serveur lorsque le temps expire ;
- un étudiant ne peut réaliser qu’une tentative par combinaison examen/cas ;
- un examen déjà ouvert ne peut plus être modifié ou supprimé.

### Évaluation Licence et Master

La grille est choisie automatiquement selon `student.level` et seulement pour la spécialité `kine`.

| Niveau | Sections | Total | Seuil de validation | Erreurs éliminatoires |
|---|---:|---:|---:|---:|
| Licence | 7 | 20 points | 12/20 | 5 |
| Master | 8 | 20 points | 14/20 | 9, dont 4 supplémentaires |

Lorsqu’une erreur éliminatoire est détectée :

- elle est signalée dans le résultat ;
- la note finale est plafonnée à **8/20** ;
- le rapport indique le statut réussite/échec ;
- chaque section conserve sa note et sa justification.

Le flux d’évaluation générique de l’ECOS standard reste inchangé.

### Suivi enseignant

Le tableau de bord Kiné permet de :

- filtrer les résultats par étudiant, niveau, groupe, dossier, cas, mode, statut et période ;
- consulter les conversations et les chronologies ;
- consulter les évaluations automatiques ;
- sélectionner plusieurs conversations et générer un PDF ;
- télécharger le rapport PDF d’une simulation ;
- exporter les résultats vers Excel ;
- ajouter une note complémentaire et des commentaires personnalisés ;
- rendre ces commentaires consultables dans l’historique de l’étudiant ;
- consulter les statistiques calculées à partir des données réelles.

### Journalisation

Chaque action importante est ajoutée à `SimulationSession.timeline` avec un horodatage :

- démarrage, pause, reprise et fin ;
- message de l’étudiant et réponse du patient ;
- demande de test ;
- changement de phase ;
- déclenchement d’incident ;
- clôture automatique d’un examen ;
- évaluation et feedback.

Une vue dédiée permet à l’enseignant de consulter la chronologie formatée.

## Architecture

```text
ECOS/
├── app.py
├── auth.py
├── models.py
├── init_db.py
├── document_processor.py
├── evaluation_agent.py
├── enhanced_evaluation_agent.py
├── evaluation_config.py
├── kine_evaluation.py
├── kine_patient_engine.py
├── progression_tracker.py
├── timeline_logger.py
├── simple_pdf_generator.py
├── blueprints/
│   └── kine/
│       ├── routes_admin.py
│       ├── routes_teacher.py
│       ├── routes_student.py
│       └── routes_dashboard.py
├── templates/
├── static/
└── tests/
```

## Technologies

- Python 3 et Flask 3
- Flask-SQLAlchemy et SQLite
- Flask-Login et Flask-Session
- Groq et LangChain
- PyPDF2, python-docx et docx2txt
- ReportLab pour les PDF
- OpenPyXL pour les exports Excel
- HTML, CSS et JavaScript sans framework frontend
- Pytest et pytest-flask

## Installation locale

### 1. Cloner le dépôt et sélectionner la branche Kiné

```bash
git clone https://github.com/OussHBZ/ECOS
cd ECOS
git checkout kinesitherapy
```

### 2. Créer l’environnement virtuel

Sous Windows PowerShell :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Sous Linux :

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Configurer les variables d’environnement

Créez un fichier `.env` à la racine :

```env
GROQ_API_KEY=votre_cle_groq
GROQ_MODELS=openai/gpt-oss-20b,qwen/qwen3.8-27b,openai/gpt-oss-120b
SECRET_KEY=une_cle_longue_aleatoire
ADMIN_CODE=un_code_administrateur_secret
KINE_SPECIALTY=kine
SESSION_COOKIE_PATH=/
SEED_DEMO_ACCOUNTS=false
```

`GROQ_API_KEY` est obligatoire. Ne versionnez jamais `.env`.
`GROQ_MODELS` est facultatif et permet de remplacer la chaîne de modèles sans modifier le code.

En production, remplacez toujours les valeurs par défaut de `SECRET_KEY` et `ADMIN_CODE`.

### 4. Initialiser une nouvelle base

Uniquement pour une installation neuve :

```bash
python init_db.py
```

Le script crée les tables, les grilles et les dossiers pathologiques. Les comptes de démonstration sont contrôlés par `SEED_DEMO_ACCOUNTS`.

### 5. Démarrer

```bash
python app.py
```

Ouvrez :

```text
http://127.0.0.1:5000/
```

La page d’accueil donne accès à l’ECOS standard et affiche un bouton distinct pour l’ECOS Kiné.

## Tests

Exécuter toute la suite :

```bash
python -m pytest -q
```

La suite couvre notamment :

- les modèles et relations Kiné ;
- les grilles Licence/Master et le plafond éliminatoire ;
- le patient virtuel et les protections contre les injections ;
- le tracker et le verrouillage en examen ;
- le CRUD des cas, incidents et examens ;
- l’unicité des tentatives d’examen ;
- la chronologie, le dashboard et les exports ;
- la compatibilité des accès ECOS standard/Kiné.

## Mise à jour d’un serveur existant

Les évolutions Kiné sont additives. Le démarrage de l’application :

- crée les nouvelles tables manquantes ;
- ajoute les colonnes manquantes aux anciennes tables SQLite ;
- conserve les données ECOS standard ;
- ajoute les dossiers pathologiques sans écraser les dossiers personnalisés ;
- crée l’index empêchant les doubles tentatives d’examen.

Avant toute mise à jour, sauvegardez la base :

```bash
cd /home/fmpm/ECOS
mkdir -p database_backups
cp -a instance/osce_simulator.db \
  "database_backups/osce_simulator_$(date +%Y%m%d_%H%M%S).db"
```

Puis :

```bash
git pull --ff-only origin kinesitherapy
venv/bin/python -m pip install -r requirements.txt
sudo systemctl restart ecos
sudo systemctl status ecos --no-pager
```

Ne supprimez jamais `instance/osce_simulator.db` et n’exécutez pas `init_db.py` sur la base de production existante.

### Déploiement sous `/ecos`

Lorsque Nginx publie l’application sous le préfixe `/ecos`, configurez :

```text
SESSION_COOKIE_PATH=/ecos
```

Nginx doit transmettre `Host`, `X-Real-IP`, `X-Forwarded-For` et `X-Forwarded-Proto`, conserver les redirections sous `/ecos/`, autoriser les imports de 25 Mo et utiliser des délais compatibles avec les appels LLM.

Le service Gunicorn doit également laisser assez de temps aux appels LLM :

```ini
ExecStart=/home/fmpm/ECOS/venv/bin/gunicorn --workers 3 --timeout 120 --bind 127.0.0.1:8000 wsgi:app
```

Et dans le bloc `location` Nginx :

```nginx
proxy_connect_timeout 15s;
proxy_read_timeout 120s;
proxy_send_timeout 120s;
```

Un certificat auto-signé provoque un avertissement du navigateur. Pour une production sécurisée, utilisez un nom de domaine et un certificat reconnu. HTTP peut être utilisé sur un réseau interne/VPN, mais ne protège pas directement les identifiants et les données entre le navigateur et le serveur.

## Sécurité

- Conservez `.env`, la base SQLite, les sauvegardes et les environnements virtuels hors de Git.
- Ne placez jamais une clé Groq, un mot de passe SSH ou une clé privée dans le dépôt ou les journaux partagés.
- Renouvelez immédiatement toute clé exposée.
- Utilisez HTTPS avec un certificat reconnu dès que la plateforme est ouverte à plusieurs utilisateurs.
- Désactivez les comptes de démonstration en production.
- Sauvegardez la base avant chaque déploiement.

## Compatibilité

L’extension Kiné utilise un blueprint dédié sous `/kine` et filtre les données par spécialité. Les modèles et routes historiques sont étendus de manière additive afin de conserver le fonctionnement de l’ECOS standard.
