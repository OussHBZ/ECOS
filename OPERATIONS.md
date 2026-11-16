# Exploitation KardioX — préparation, sans déploiement

Référence : cahier des charges p. 100, décisions du dossier `output/cahier-charge-21-10/DECISIONS.md`. Ce document décrit le code livré et les conditions à remplir ; il ne vaut ni validation d'hébergement ni autorisation de mise en service. Preuves et limites : `../output/cahier-charge-21-10/preuves/t20-t22/VERIFICATION.md`.

## Architecture et prérequis

Application Flask 3, Flask-Login, sessions serveur filesystem, SQLAlchemy/SQLite, HTML/CSS/JavaScript, ReportLab, extraction DOCX/PDF ; dépendances dans `requirements.txt`. Environnement de recette : Windows, CPython 3.12, dépendances verrouillées dans `requirements-test.lock`, Node pour les tests. Ce verrou contient des roues Windows : une installation Linux exige une résolution compatible et une recette sur cette plateforme. Aucun changement de framework ni de base imposé par ce lot.

Avant toute mise en service, choisir l'hôte/région, l'exploitant, le domaine, le serveur WSGI adapté à l'OS, le reverse proxy HTTPS, la supervision et le volume persistant local. Ne pas utiliser le serveur Flask de développement en production. SQLite et les sessions fichier supposent un stockage local partagé entre les processus d'un seul hôte ; ni NFS, ni répartition multi-hôtes ne sont certifiés. Les essais locaux à huit clients ne constituent pas une capacité de production. Fixer la cible, la durée, les critères de latence/erreur, puis rejouer avec la configuration et les quotas IA retenus.

Configurer **dans l'environnement du processus avant l'import de l'application** : `SECRET_KEY` aléatoire robuste, `ADMIN_CODE` et `PEDAGOGICAL_ADMIN_CODE` distincts, `SEED_DEMO_ACCOUNTS=false`, `SESSION_COOKIE_SECURE=true`, `GROQ_API_KEY`, éventuellement `GROQ_MODELS` et `SESSION_COOKIE_PATH`. Ne pas se fier aux valeurs de développement, ni au chargement tardif de `.env` pour la clé de session et les codes admin importés plus tôt. Ne jamais copier les clés dans le dépôt, les logs, les preuves ou les sauvegardes ordinaires. Limiter les droits du compte système aux données nécessaires. Limite d'import applicative : 25 Mo ; aligner le proxy. Synchroniser l'horloge ; les échéances sont stockées en UTC.

Au démarrage, `create_app()` applique des migrations additives, prépare des répertoires et initialise l'IA ; il exige une clé Groq et effectue un ping via le client ECOS. Un échec réseau du ping est toléré, une clé absente empêche le démarrage. Ne pas lancer cette fabrique sur la base réelle pour « tester ». Préparer une copie, effectuer les migrations avec un seul processus pendant maintenance, vérifier, puis seulement démarrer les workers autorisés. Ne jamais utiliser `reset_database` comme procédure de mise à jour.

Prévoir un ordonnanceur pour `flask --app app:create_app kine expire-exams`, au rythme choisi par l'exploitant (proposition : une minute, à valider). Chaque appel crée l'application et peut donc effectuer son ping de démarrage ; cela fait partie du trafic/coût à mesurer. Les écritures après échéance sont refusées même sans ordonnanceur ; la clôture matérielle survient à la commande ou à une requête autorisée. Surveiller les échecs de commande et ne pas confondre fin du navigateur et abandon explicite.

## IA, transmissions et services

Le fournisseur configuré est **Groq** via `langchain-groq`/HTTPS. La chaîne par défaut dans le code est `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`, `openai/gpt-oss-120b` ; ce sont des identifiants de configuration, **pas une attestation de disponibilité, de prix ou de licence actuels**. Le modèle effectif dépend aussi de `GROQ_MODELS`. Vérifier disponibilité, conditions d'utilisation, traitement/région des données, conservation, sous-traitants, réutilisation éventuelle et quotas avec le fournisseur avant activation. Aucun contrat fournisseur ou accord de transfert n'a été vérifié pendant cette recette.

| Flux | Données susceptibles d'être transmises | Contrôle / limite |
|---|---|---|
| Patient KardioX | Question étudiante, historique autorisé, contexte patient publié et accessible, style/personnalité | Les attentes réservées sont exclues du contexte patient ; TLS ; clé uniquement serveur |
| Routage de question | Question et candidats d'information autorisés | Sélection bornée aux identifiants autorisés ; jamais validation de nouveaux faits |
| Évaluation | Conversation, critères/attentes et contexte de la version figée | Flux enseignant distinct du patient ; incertitude et panne = vérification, pas note inventée |
| Import de cas | Texte extrait et références d'images/documents traités par l'agent | Les originaux restent locaux ; le contenu extrait peut contenir des données personnelles : anonymiser en amont ; validation enseignante obligatoire |
| Aperçu patient | Saisie d'essai et contexte du brouillon autorisé | Même fournisseur ; aucune tentative étudiante créée |
| ECOS standard | Conversations et contexte de ses cas via le client historique | Flux et règles historiques conservés ; inclure ces données dans la décision de transfert |

Aucun nouveau service d'analytics, e-mail, stockage distant ou CDN n'est ajouté à KardioX. Le proxy/hébergeur et le dépôt de dépendances restent des services à inventorier dans l'environnement retenu. Garder le tracing LangChain/LangSmith désactivé ; aucune intégration de tracing n'est nécessaire au fonctionnement testé. Les journaux d'extraction ne contiennent plus de fragments/réponses LLM bruts. **Limite** : les journaux du module ECOS standard comportent encore des extraits de conversations ; les protéger et inclure leur minimisation dans une intervention dédiée, sans prétendre à une confidentialité globale déjà certifiée.

Le client KardioX utilise le premier modèle configuré, un timeout transport de 10 s et zéro retry SDK ; le routage, le patient et une éventuelle régénération de réponse tronquée peuvent constituer plusieurs appels successifs. Ce timeout n'est pas une garantie de délai total sous toutes les conditions réseau. L'import conserve son client séparé (90 s par appel et chaîne historique). Le budget transport et la configuration sont testés ; aucun fournisseur réel n'a été sollicité.

## Incidents, conservation et restauration

Un message accepté est enregistré avant l'appel patient. Un échec renvoie 503, conserve la saisie et permet de réessayer avec la même clé. Les envois actifs renvoient un conflit 409 ; après arrêt d'un worker, une réservation technique devient récupérable après 300 s. Ce délai ne suspend jamais le chrono d'examen et n'autorise aucune nouvelle tentative. Les réponses d'un ancien worker sont refusées par comparaison de révision. Les clés sont propres à la tentative ; le navigateur conserve seulement clé + empreinte de la saisie, dans l'onglet. Une saisie volontairement modifiée est un nouvel envoi. Un ancien client sans clé n'offre pas la garantie de déduplication.

Les pages et résultats autorisés restent consultables si le serveur fonctionne alors que l'IA est indisponible. Hors connexion au serveur, la page déjà ouverte et son brouillon peuvent rester visibles ; aucun mode hors ligne synchronisé ni cache persistant de dossiers n'est fourni. Ne pas annoncer un accès complet hors réseau. Reconnexion examen jusqu'à l'échéance sans pause, abandon explicite définitif, pause uniquement entraînement : D01-c.

La durée de conservation, le cycle des sauvegardes, la suppression future des comptes, les responsabilités et les objectifs RPO/RTO sont **à décider** (Q-DATA/D02). En attendant : aucune purge automatique des tentatives, résultats ou comptes ; suspension seulement. Les fichiers de session ont une durée de vie d'authentification distincte des résultats. Les sauvegardes contiennent des données personnelles et doivent être chiffrées au repos, protégées par ACL, conservées sur un stockage séparé et contrôlées ; le ZIP fourni **n'est pas chiffré**. Choisir et gérer les clés hors du bundle. Ne pas conserver indéfiniment les copies de recette contenant des données réelles ; celles de cette livraison sont fictives.

Outil autonome `scripts/backup_restore.py`, sans chemin de production par défaut :

```powershell
# Arrêter les writers ET l'ordonnanceur ; vérifier les chemins explicitement.
python scripts/backup_restore.py backup <racine-app-arretee> <sauvegarde-hors-racine.zip> --quiesced
python scripts/backup_restore.py restore <sauvegarde.zip> <nouveau-repertoire-isole>
```

Le bundle contient `instance/osce_simulator.db`, `uploads/` et `static/images/cases/`, plus les SHA-256. L'API SQLite produit un snapshot ; intégrité et clés étrangères sont contrôlées. La restauration vérifie chemins et empreintes, refuse une destination existante et ne remplace jamais l'application courante. Si l'application utilise d'autres répertoires de documents, les ajouter explicitement au périmètre avant exploitation. Secrets, sessions, logs, code et dépendances sont exclus et doivent avoir leur propre stratégie protégée. Conserver avec le bundle le code exact, son manifeste, le verrou compatible et la configuration non secrète ; les identifiants de versions cliniques sont dans la base.

Les chemins de fichiers historiques sont absolus. Pour une vérification dans un autre répertoire sur le même OS, configurer `KINE_RESTORED_UPLOAD_ROOT` avec `original_upload_root` du manifeste, et lancer depuis la nouvelle racine (son `uploads/` devient `UPLOAD_FOLDER`). La résolution des téléchargements utilise ce préfixe sans réécrire les snapshots ni leurs empreintes. Le bundle refuse les fichiers référencés absents ou hors `uploads/`, au lieu de livrer une sauvegarde silencieusement incomplète. Pour la reprise opérationnelle, conserver le chemin de montage original : des déplacements successifs avec plusieurs anciens préfixes ne sont pas pris en charge par ce paramètre unique ; changement d'OS également non vérifié.

Après restauration isolée : vérifier les nombres/identifiants, résultats et versions, télécharger des originaux, exercer une connexion de chaque rôle, générer les bilans, tester ECOS standard ; vérifier les migrations deux fois et leurs checksums. Mesurer le RTO avec une taille représentative avant d'en promettre un. RPO dépend de la fréquence de sauvegarde et des écritures depuis la dernière copie, aucune valeur n'est validée ici.

## Mise à jour, retour arrière et réversibilité

Conserver la version précédente et une sauvegarde cohérente avant chaque migration. La recette comporte interruption/reprise, répétition, checksum et historique intact sur bases synthétiques. Pas de migration descendante automatique : revenir avec le code précédent **et** sa sauvegarde précédente dans un nouveau répertoire, après analyse des écritures à récupérer depuis la bascule. Ne pas remettre un ancien code sur une base migrée en supposant une compatibilité. Le retour peut perdre des écritures postérieures à la sauvegarde ; obtenir la procédure de réconciliation et la fenêtre de maintenance avant bascule. Ne jamais supprimer la copie récente pour « nettoyer » un retour arrière.

Portabilité : base SQLite et documents originaux conservés, JSON des versions/résultats/audit, exports CSV/XLSX enseignants et PDF individuels selon droits. Ces exports ne remplacent pas le bundle complet. À un changement de prestataire, remettre code/dépendances/configuration non secrète et bundle à un destinataire autorisé ; reprovisionner les secrets séparément, invalider les sessions et vérifier les permissions. Les exports fonctionnels respectent les périmètres ; le bundle technique complet exige une habilitation d'exploitation distincte.

## Coûts — modèle de calcul, sans devis tarifé

Hypothèses à faire approuver : nombre d'étudiants actifs, séances mensuelles, messages par séance, tokens réellement facturés par flux, taux de retries/imports/évaluations, durée et taille des sauvegardes, nombre d'environnements et heures de maintenance. Ne pas assimiler 1 message à 1 appel : routage, génération et régénération peuvent se cumuler. La clôture automatique n'appelle pas l'évaluateur IA, mais le démarrage de sa commande peut effectuer le ping mentionné plus haut.

Coût initial = préparation hébergement/HTTPS + reprise/anonymisation des données + validation pédagogique + recette cible + formation + procédure de restauration. Coût récurrent = hébergement + stockage primaire/sauvegardes + trafic + maintenance/supervision + éventuelles licences + IA.

Pour l'IA : somme par modèle de `(tokens entrants / 1 000 000 × tarif entrant) + (tokens sortants / 1 000 000 × tarif sortant)`, plus tout autre poste facturé au contrat. Pour le stockage : volume retenu × tarif de stockage, plus opérations/transferts s'ils sont facturés. Pour maintenance : heures convenues × taux convenu. **Aucun montant, gratuité, plafond de budget ou tarif actuel n'est affirmé** ; Q-BUD reste ouvert. Vérifier les prix officiels à la date d'un futur devis chiffré. Les licences et conditions de redistribution des dépendances et modèles doivent être vérifiées pour l'usage et l'hôte retenus.
