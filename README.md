# ECOS - Simulateur de Consultations OSCE

Un système avancé de formation médicale utilisant l'intelligence artificielle pour simuler des consultations OSCE (Objective Structured Clinical Examination) avec des patients virtuels réalistes.

## Vue d'ensemble

ECOS (Examen Clinique Objectif Structuré) permet aux étudiants en médecine de s'entraîner aux consultations cliniques avec des patients simulés par IA. Les enseignants peuvent créer des cas médicaux détaillés, tandis que les étudiants interagissent avec des patients virtuels alimentés par des modèles Llama-4 avancés via l'API Groq. Le système fournit une évaluation automatisée et génère des rapports PDF complets.

## Fonctionnalités

### Pour les Enseignants
- **Création de Cas** : Téléchargement de fichiers de cas médicaux (PDF, Word) ou saisie manuelle
- **Extraction Automatique** : Extraction IA des informations patient, symptômes et critères d'évaluation
- **Support d'Images** : Téléchargement et gestion d'images médicales (radiographies, scanners)
- **Configuration d'Évaluation** : Création de grilles d'évaluation personnalisées avec notation par points
- **Gestion des Consignes** : Définition d'instructions spécifiques et timing pour les stations OSCE
- **Gestion des Cas** : Visualisation, édition et suppression des cas existants

### Pour les Étudiants
- **Sélection de Cas** : Navigation des cas disponibles par spécialité
- **Chat en Temps Réel** : Conversations interactives avec des patients simulés par IA
- **Affichage des Consignes** : Accès aux instructions de station et exigences de timing
- **Intégration Chronomètre** : Chronomètre de consultation intégré avec alertes visuelles
- **Visualisation d'Images** : Affichage d'images médicales avec zoom et navigation
- **Évaluation Automatisée** : Retour de performance immédiat
- **Mode Compétition** : Participation à des sessions de compétition chronométrées

### Fonctionnalités Système
- **Simulation Patient IA Avancée** : Patients virtuels réalistes utilisant Llama-4-Scout
- **Évaluation Intelligente** : Évaluation automatisée des performances de consultation
- **Rapports PDF** : Rapports de consultation complets avec transcriptions et scores
- **Support Multi-langues** : Interface française avec terminologie médicale
- **Design Responsive** : Fonctionne sur ordinateur et mobile
- **Gestion de Sessions** : Gestion sécurisée des sessions de consultation et compétition

## Stack Technologique

### Backend
- **Framework** : Flask (Python)
- **IA/LLM** : LangChain avec API Groq (Llama-4-Scout-17B)
- **Traitement de Documents** : PyPDF2, python-docx, docx2txt
- **Génération PDF** : ReportLab
- **Traitement d'Images** : Pillow (PIL)
- **Base de Données** : SQLAlchemy avec SQLite

### Frontend
- **HTML/CSS/JavaScript** : JavaScript vanilla avec CSS moderne
- **Composants UI** : Boîtes de dialogue modales personnalisées et layouts responsifs
- **Fonctionnalités Temps Réel** : API Fetch pour communication asynchrone

### Stockage
- **Données de Cas** : Base de données SQLite pour stockage des cas
- **Images** : Stockage système de fichiers avec chemins accessibles web
- **Sessions** : Gestion de sessions Flask

## Installation

### Prérequis
- Python 3.8+
- Clé API Groq
- 4GB RAM minimum (recommandé 8GB pour Llama-4-Scout)

### Configuration

1. **Cloner le dépôt**
```bash
git clone https://github.com/votre-repo/ecos-simulator
cd ecos-simulator
```

2. **Installer les dépendances**
```bash
pip install -r requirements.txt
```

3. **Configuration environnement**
```bash
# Créer fichier .env
echo "GROQ_API_KEY=votre_cle_api_groq" > .env
echo "SECRET_KEY=votre_cle_secrete_longue_et_aleatoire" >> .env
```

4. **Initialiser la base de données**
```bash
python init_db.py
```

5. **Lancer l'application**
```bash
python app.py
```

## Structure du Projet

```
ecos-simulator/
├── app.py                     # Application Flask principale
├── auth.py                    # Logique d'authentification
├── document_processor.py      # Agent d'extraction de documents
├── evaluation_agent.py        # Traitement d'évaluation
├── simple_pdf_generator.py    # Génération de rapports PDF
├── init_db.py                 # Script d'initialisation base de données
├── models.py                  # Modèles SQLAlchemy
├── requirements.txt           # Dépendances Python
├── response_template.json     # Template de simulation patient
├── .env                       # Variables d'environnement
├── blueprints/
│   ├── admin.py               # Routes administrateur
│   ├── student.py             # Routes étudiant
│   └── teacher.py             # Routes enseignant
├── templates/
│   ├── home.html              # Page d'accueil
│   ├── login.html             # Page de connexion
│   ├── admin.html             # Interface administrateur
│   ├── teacher.html           # Interface enseignant
│   └── student.html           # Interface étudiant
├── static/
│   ├── css/
│   │   └── styles.css         # Styles application
│   ├── js/
│   │   ├── admin.js           # Logique interface admin
│   │   ├── teacher.js         # Logique interface enseignant
│   │   └── student.js         # Logique interface étudiant
│   └── images/
│       └── cases/             # Images médicales téléchargées
├── uploads/                   # Téléchargements temporaires
├── logs/                      # Fichiers de logs
└── instance/
    └── ecos_simulator.db      # Base de données SQLite
```

## Nouveautés Version 2.0

### Simulation Patient Améliorée
- **Modèle Llama-4-Scout** : Simulation patient plus réaliste et cohérente
- **Réponses Contextuelles** : Les patients répondent uniquement aux questions posées
- **Comportement Authentique** : Émotions, langage et réactions appropriés au contexte médical

### Mode Compétition
- **Sessions Chronométrées** : Compétitions avec rotation automatique entre stations
- **Classements en Temps Réel** : Suivi des performances et classements
- **Gestion Avancée** : Contrôles administrateur pour démarrage/arrêt/pause

### Interface Modernisée
- **Design Responsive** : Interface optimisée mobile et desktop
- **Visualisation de Données** : Graphiques et statistiques de performance
- **Expérience Utilisateur** : Navigation intuitive et retours visuels

## Utilisation

### Configuration Initiale
1. Accéder à `http://localhost:5000`
2. Se connecter en tant qu'enseignant pour créer des cas
3. Créer des comptes étudiants
4. Démarrer les consultations ou compétitions

### Création de Cas
1. Télécharger un document PDF/Word ou saisir manuellement
2. L'IA extrait automatiquement les informations patient
3. Réviser et ajuster le cas extrait
4. Ajouter des images médicales si nécessaire
5. Configurer les critères d'évaluation

### Consultation Étudiant
1. Sélectionner un cas disponible
2. Lire les consignes de la station
3. Démarrer la consultation avec le patient IA
4. Recevoir l'évaluation automatique
5. Télécharger le rapport PDF

## API et Configuration

### Modèle IA
- **Modèle Principal** : `meta-llama/llama-4-scout-17b-16e-instruct`
- **Fallback** : `llama3-8b-8192`
- **Température** : 0.1 (réponses cohérentes)
- **Tokens Max** : 150 (réponses concises)

### Variables d'Environnement
```env
GROQ_API_KEY=votre_cle_api_groq
SECRET_KEY=cle_secrete_pour_sessions
FLASK_ENV=development
```

## Contribution

1. Fork le projet
2. Créer une branche feature (`git checkout -b feature/nouvelle-fonctionnalite`)
3. Commit les changements (`git commit -am 'Ajouter nouvelle fonctionnalité'`)
4. Push vers la branche (`git push origin feature/nouvelle-fonctionnalite`)
5. Créer une Pull Request

## Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## Support

- **Documentation** : Consulter le wiki du projet
- **Issues** : Reporter les bugs via GitHub Issues
- **Contact** : [votre-email@exemple.com]

## Changelog

### v2.0.0 (2025)
- Migration vers Llama-4-Scout pour simulation patient améliorée
- Ajout du mode compétition avec classements
- Interface utilisateur modernisée
- Simulation patient plus réaliste et cohérente
- Optimisations de performance

### v1.0.0 (2024)
- Version initiale avec simulation OSCE de base
- Support des consultations individuelles
- Évaluation automatique simple
- Interface web basique