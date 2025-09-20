# ECOS - Simulateur de Consultations OSCE

Un système avancé de formation médicale utilisant l'intelligence artificielle pour simuler des consultations OSCE (Objective Structured Clinical Examination) avec des patients virtuels réalistes et un **système d'évaluation LLM amélioré**.

## Vue d'ensemble

ECOS (Examen Clinique Objectif Structuré) permet aux étudiants en médecine de s'entraîner aux consultations cliniques avec des patients simulés par IA. Les enseignants peuvent créer des cas médicaux détaillés, tandis que les étudiants interagissent avec des patients virtuels alimentés par des modèles Llama-4 avancés via l'API Groq. Le système fournit une évaluation automatisée intelligente basée sur l'analyse LLM de chaque critère et génère des rapports PDF complets.


## Fonctionnalités

### Pour les Enseignants
- **Création de Cas** : Téléchargement de fichiers de cas médicaux (PDF, Word) ou saisie manuelle
- **Extraction Automatique** : Extraction IA des informations patient, symptômes et critères d'évaluation
- **Support d'Images** : Téléchargement et gestion d'images médicales (radiographies, scanners)
- **🆕 Grilles d'Évaluation Intelligentes** : Création de critères avec catégorisation automatique
- **Configuration d'Évaluation** : Création de grilles d'évaluation personnalisées avec notation par points et **analyse LLM**
- **Gestion des Consignes** : Définition d'instructions spécifiques et timing pour les stations OSCE
- **Gestion des Cas** : Visualisation, édition et suppression des cas existants
- **🆕 Analytics Avancées** : Statistiques détaillées sur les performances par catégorie

### Pour les Étudiants
- **Sélection de Cas** : Navigation des cas disponibles par spécialité
- **Chat en Temps Réel** : Conversations interactives avec des patients simulés par IA
- **Affichage des Consignes** : Accès aux instructions de station et exigences de timing
- **Intégration Chronomètre** : Chronomètre de consultation intégré avec alertes visuelles
- **Visualisation d'Images** : Affichage d'images médicales avec zoom et navigation
- **🆕 Évaluation Intelligente** : Retour de performance détaillé avec justifications LLM
- **🆕 Recommandations Personnalisées** : Conseils adaptés aux lacunes identifiées
- **Mode Compétition** : Participation à des sessions de compétition chronométrées

### Fonctionnalités Système
- **🆕 Simulation Patient IA Avancée** : Patients virtuels réalistes utilisant Llama-4-Scout
- **🆕 Évaluation LLM Intelligente** : Analyse contextuelle de chaque critère avec prompts spécialisés
- **🆕 Système de Fallback** : Basculement automatique vers l'analyse par mots-clés si nécessaire
- **Rapports PDF** : Rapports de consultation complets avec transcriptions et scores détaillés
- **Support Multi-langues** : Interface française avec terminologie médicale
- **Design Responsive** : Fonctionne sur ordinateur et mobile
- **Gestion de Sessions** : Gestion sécurisée des sessions de consultation et compétition
- **🆕 Cache Intelligent** : Mise en cache des évaluations pour optimiser les performances

## Stack Technologique

### Backend
- **Framework** : Flask (Python)
- **IA/LLM** : LangChain avec API Groq (Llama-4-Scout-17B)
- **🆕 Évaluation Avancée** : Système LLM avec prompts catégorisés et analyse contextuelle
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
- **🆕 Cache Évaluations** : Système de cache en mémoire pour optimiser les évaluations répétées

## Installation
### Configuration

1. **Cloner le dépôt**
```bash
git clone https://github.com/OussHBZ/ECOS
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


## Utilisation

### Configuration Initiale
1. Accéder à `http://localhost:5000`
2. Se connecter en tant qu'enseignant pour créer des cas
3. 🆕 **Structurer les grilles d'évaluation** avec les bonnes catégories
4. Créer des comptes étudiants
5. Démarrer les consultations ou compétitions

### 🆕 Création de Cas avec Évaluation Optimisée
1. Télécharger un document PDF/Word ou saisir manuellement
2. L'IA extrait automatiquement les informations patient
3. **Réviser et catégoriser les critères d'évaluation**
4. Assigner les bonnes catégories (`Communication`, `Anamnèse`, etc.)
5. Ajouter des images médicales si nécessaire
6. Tester l'évaluation avec des conversations d'exemple

### Consultation Étudiant
1. Sélectionner un cas disponible
2. Lire les consignes de la station
3. Démarrer la consultation avec le patient IA
4. 🆕 **Recevoir une évaluation détaillée** avec justifications LLM
5. 🆕 **Consulter les recommandations personnalisées**
6. Télécharger le rapport PDF amélioré


## API et Configuration

### Modèle IA
- **Modèle Principal** : `meta-llama/llama-4-scout-17b-16e-instruct`
- **Fallback** : `llama3-8b-8192`
- **Température** : 0.1 (réponses cohérentes)
- **Tokens Max** : 150 (réponses concises)
- **🆕 Timeout Évaluation** : 30s par critère

### 🆕 Configuration Évaluation
```env
# Variables d'évaluation
EVALUATION_TEMPERATURE=0.1
EVALUATION_MAX_TOKENS=150
EVALUATION_CACHE_ENABLED=true
EVALUATION_FALLBACK_ENABLED=true
```

### Variables d'Environnement
```env
GROQ_API_KEY=votre_cle_api_groq
SECRET_KEY=cle_secrete_pour_sessions
FLASK_ENV=development
```

**ECOS** offre maintenant une expérience d'apprentissage véritablement intelligente et adaptative pour la formation médicale.
