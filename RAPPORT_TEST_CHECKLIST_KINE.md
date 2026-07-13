# Rapport de test — ECOS Kinésithérapie

Date : 13 juillet 2026

## Synthèse

- 89 contrôles analysés
- 65 validés
- 17 partiellement validés ou nécessitant un test manuel/réel
- 7 non conformes
- Suite automatisée : 25 tests réussis sur 25

Légende :

- ✅ validé par test automatisé ou chemin serveur directement vérifiable
- 🟡 partiel, implémenté mais non testé de bout en bout, ou incomplet dans l’interface
- ❌ non conforme ou absent

## 1. Comptes et rôles

| Contrôle | Résultat | Observation |
|---|---:|---|
| Création compte Admin | ❌ | L’administration repose sur un code `ADMIN_CODE` et `AdminAccess`. Il n’existe pas de véritable modèle/écran de création de compte Admin. |
| Création compte Enseignant par admin | ✅ | Route `/admin/add-teacher`, mot de passe haché et affectation Standard/Kiné. |
| Création comptes Étudiants par admin | ✅ | Route `/admin/add-student`, validation Apogée, mot de passe haché et affectation Standard/Kiné. |
| Attribution Licence/Master | 🟡 | L’API `/kine/students/<id>/level` existe, mais le formulaire Admin de création ne propose pas le niveau et aucun contrôle de niveau n’est exposé dans son tableau. |
| Modification ultérieure du niveau | 🟡 | Modification persistée par l’API et utilisée immédiatement pour les cas/grilles, mais aucun bouton Admin/Enseignant ne l’appelle actuellement. |
| Réinitialisation mot de passe | ✅ | Routes présentes pour étudiants et enseignants, validation minimale de longueur et hachage. |
| Restrictions par rôle et par espace | ✅ | Test automatisé réussi : étudiant, enseignant, admin et séparation exclusive Standard/Kiné. |

## 2. Création de cas cliniques

| Contrôle | Résultat | Observation |
|---|---:|---|
| Cas Licence complet | ✅ | Niveau accepté, dossier patient et relations persistés. |
| Cas Master complet | ✅ | Niveau accepté et grille Master sélectionnée selon le niveau réel de l’étudiant. |
| Assignation dossier pathologique | ✅ | `folder_id` obligatoire dans le formulaire et persisté. |
| Identité, antécédents, facteurs de risque | ✅ | Champs structurés présents et enregistrés dans `PatientRecord`. |
| Plusieurs interventions | ✅ | Répéteur `+`, parsing et relation N-1 présents. |
| Plusieurs médicaments | ✅ | Répéteur présent ; affichage DCI/effet/vigilance uniquement pour Licence vérifié dans le rendu. |
| Prescriptions médicale et kiné | ✅ | Deux champs distincts persistés. |
| Examens complémentaires | ✅ | Répéteur catégorisé avec valeur et unité. |
| Constantes initiales | ✅ | Répéteur de paramètres et stockage structuré. |
| Bilan kiné complet | ✅ | Onze domaines plus cinétique à l’effort sont disponibles. |
| Plusieurs incidents | ✅ | Répéteur et CRUD séparé ; une réaction et une gravité sont persistées. |
| Modification d’un cas | ✅ | Le même formulaire est prérempli par JSON structuré puis met à jour le cas et ses relations. |

## 3. Extraction automatique

| Contrôle | Résultat | Observation |
|---|---:|---|
| Upload PDF réel | 🟡 | Route multipart et intégration formulaire testées avec un agent simulé. La qualité d’une extraction Groq réelle n’a pas été mesurée pendant cet audit. |
| Upload Word réel | 🟡 | Le parseur `.docx` et le schéma existent. Le test réel avec le document clinique n’a pas été lancé car il transférerait son contenu privé au service Groq externe. |
| Champs Kiné reconnus | ✅ | Test du prompt et du schéma : histoire catégorisée, procédures, bilan, constantes et incidents. |
| Document/réponse mal formaté | ✅ | Une réponse LLM sans JSON déclenche une erreur explicite ; aucun faux dossier silencieux n’est produit. |
| Correction manuelle avant sauvegarde | ✅ | Les données extraites préremplissent le formulaire et ne sont sauvegardées qu’après validation de l’enseignant. |

## 4. Dossiers de pathologie

| Contrôle | Résultat | Observation |
|---|---:|---|
| Création | ✅ | Test CRUD réussi. |
| Modification du nom | ✅ | Validation du nom vide et des doublons. |
| Déplacement d’un cas | ✅ | Le changement de `folder_id` est pris en compte à la modification du cas. |
| Archivage invisible étudiant | ❌ | Le dossier est marqué archivé, mais la requête étudiante ne filtre que `PatientCase.is_archived`. Un cas actif contenu dans un dossier archivé reste visible. |
| Suppression d’un dossier non vide | 🟡 | Le dossier non vide est transformé en archive, mais hérite du défaut de visibilité précédent. Un dossier vide est supprimé physiquement. |

## 5. Mode Entraînement

| Contrôle | Résultat | Observation |
|---|---:|---|
| Liste filtrée par dossier | ❌ | Le nom du dossier est affiché sur chaque carte, mais aucun filtre/sélecteur de dossier n’est disponible côté étudiant. |
| Dossier médical avant chat | ✅ | Page statique dédiée et contrôle d’accès testés. |
| Visibilité médicaments Licence/Master | ✅ | Licence voit DCI, effet et vigilance ; Master ne voit que la classe. |
| Tracker affiché et synchronisé | ✅ | Onze phases, état courant, étapes terminées/restantes et pourcentage testés. |
| Retour arrière en entraînement | ✅ | Navigation libre testée. |
| Anamnèse sans divulgation spontanée | 🟡 | Les instructions et garde-fous existent ; la stabilité conversationnelle nécessite une campagne avec le LLM réel. |
| Reformulation cohérente | 🟡 | Historique envoyé au modèle, mais cohérence non déterministe non testée avec un LLM réel. |
| Valeur exacte d’un test prévu | ✅ | FC et 6MWT vérifiés automatiquement. |
| Test non prévu | ✅ | Retour `test_result_unavailable`, sans valeur inventée. |
| Diagnostic kiné non révélé | ✅ | Demande directe bloquée et sortie LLM dangereuse filtrée. |
| Incident prévu | ✅ | Phase, condition et réaction scriptée testées. |
| Incident absent | ✅ | Aucun incident synthétique si la liste est vide. |
| État émotionnel cohérent | 🟡 | Injecté dans le prompt ; résultat réel non déterministe non testé. |
| Fin et évaluation automatique | ✅ | Clôture, grille, sauvegarde et phase 11 testées. |
| Pause/reprise | ✅ | Interdit d’écrire pendant la pause ; progression et durée de pause conservées. |
| Tentatives multiples | ✅ | Chaque démarrage d’entraînement crée une nouvelle `SimulationSession`. |

## 6. Évaluation automatique

| Contrôle | Résultat | Observation |
|---|---:|---|
| Grille selon niveau | ✅ | 7 sections Licence et 8 Master, total 20. |
| Score et justification par partie | ✅ | Normalisation et rendu HTML/PDF vérifiés. |
| Erreur éliminatoire et plafond | ✅ | Note brute 20 transformée en 8/20 dans le test. |
| Seuil et statut | ✅ | Licence 12, Master 14, échec obligatoire en présence d’une erreur éliminatoire. |
| Simulation propre : score réaliste | 🟡 | Le calcul est correct, mais la pertinence qualitative dépend du LLM. Le fallback local ne couvre pas encore les neuf erreurs Master. |
| PDF complet | ✅ | PDF ouvert et texte de la septième section et score final vérifiés. |

## 7. Historique étudiant

| Contrôle | Résultat | Observation |
|---|---:|---|
| Cas, date, durée, score, conversation | 🟡 | Cas, mode, date, score et accès au chat sont présents. La durée n’est pas affichée dans le tableau étudiant. |
| PDF depuis l’historique | ❌ | Aucun lien PDF n’est présent dans `student_history_kine.html`. |
| Progression dans le temps | ❌ | Pas de graphique ni de synthèse longitudinale côté étudiant. |

## 8. Création d’examen

| Contrôle | Résultat | Observation |
|---|---:|---|
| Plusieurs cas | ✅ | Relations N-N et validation des cas examen. |
| Étudiants/groupes autorisés | ✅ | Affectations synchronisées et limitées aux comptes Kiné. |
| Début et fin | ✅ | Conversion heure navigateur vers UTC testée. |
| Durée maximale | ✅ | Valeur positive obligatoire. |
| Consignes | ✅ | Persistées et affichées à l’étudiant. |
| Modification avant ouverture | 🟡 | API PATCH opérationnelle, mais l’interface ne propose que créer ou supprimer, sans bouton Modifier. |
| Modification pendant l’examen | ✅ | PATCH et DELETE renvoient 409 dès l’heure d’ouverture ou dès qu’une tentative existe. |

## 9. Passage d’examen

| Contrôle | Résultat | Observation |
|---|---:|---|
| Étudiant autorisé/cas sélectionnés | ✅ | Contrôle croisé examen, étudiant et cas au démarrage. |
| Étudiant non autorisé | ✅ | Réponse 403. |
| Avant ouverture | ✅ | Démarrage refusé et examen affiché comme à venir. |
| Après fermeture | ✅ | Démarrage refusé côté serveur. |
| Chronomètre continu | ✅ | Visible uniquement en examen et calculé depuis une échéance serveur. |
| Tracker verrouillé | ✅ | Retour arrière et saut de phase refusés. |
| Expiration côté serveur | ✅ | Test avec session dépassée puis rafraîchissement : statut automatiquement `completed`. |
| Fin normale et évaluation | ✅ | Même workflow de clôture et d’évaluation. |
| Interdiction de repasser | ✅ | Une seule tentative est autorisée par étudiant, examen et cas. Les autres cas du même examen restent accessibles une fois chacun. Une contrainte unique protège aussi les requêtes concurrentes. |

## 10. Suivi enseignant

| Contrôle | Résultat | Observation |
|---|---:|---|
| Tableau de bord complet | ✅ | Étudiant, dossier, terminés/en cours, tentatives, temps, dernière connexion et progression présents. |
| Filtres | ✅ | Étudiant, groupe, classe, dossier, cas, mode et période appliqués côté serveur. |
| Historique détaillé étudiant | ❌ | Le lien retourne seulement un JSON résumé et omet durée, temps par étape et vue HTML détaillée. |
| Détail structuré d’une simulation | 🟡 | Conversation, timeline, tests demandés, incidents et évaluation sont disponibles ; décisions/diagnostic/programme ne sont pas structurés séparément. |
| Timeline horodatée | ✅ | Ordre, séquence, fuseau et affichage testés. |
| Commentaire personnalisé | ✅ | Sauvegardé, horodaté et visible enseignant/étudiant. |
| Note complémentaire distincte | ✅ | Stockée séparément de la note IA. |
| PDF tableau de bord | ✅ | PDF individuel et archive ZIP de conversations testés. |
| Excel/CSV | ✅ | Deux générateurs et deux routes fonctionnent ; seul le bouton Excel est visible conformément à la demande précédente. |
| Séparation examen/entraînement | ✅ | Filtre mode et libellés distincts. |
| Graphiques | ❌ | Le bloc « Temps par simulation » reste un placeholder ; aucun JavaScript ne transforme les données en graphique. |

## 11. Cas limites

| Contrôle | Résultat | Observation |
|---|---:|---|
| Cas sans incident | ✅ | Aucun déclenchement. |
| Plusieurs incidents conditionnels | ✅ | Le moteur déclenche le premier incident satisfait et mémorise les IDs déjà déclenchés. |
| Coupure réseau en examen | 🟡 | Messages et état sont persistés après chaque requête et récupérables au rafraîchissement ; aucune simulation explicite de coupure réseau n’a été exécutée. |
| Messages longs/hors sujet | 🟡 | Injection et divulgation sont bloquées ; aucun test de charge avec messages très longs n’existe. |
| Licence bloquée sur cas Master | ✅ | Filtre de liste et contrôle serveur direct. |
| Modification du cas pendant une simulation | 🟡 | La session ne devrait pas casser, mais elle référence le dossier vivant : les nouvelles valeurs peuvent modifier le comportement du patient en cours de séance. Aucun instantané du cas n’est conservé. |

## 12. Non-régression OSCE générique

| Contrôle | Résultat | Observation |
|---|---:|---|
| Fonctionnalités génériques opérationnelles | 🟡 | L’évaluation générique et l’extraction générique ont un test de non-régression réussi ; le parcours navigateur générique complet n’est pas couvert. |
| Routes/données existantes intactes | 🟡 | Les changements sont additifs et les cas Kiné sont filtrés des requêtes génériques, mais aucune suite historique complète du projet initial n’est présente. |

## Anomalies prioritaires

1. Masquer aux étudiants les cas appartenant à un dossier pathologique archivé.
2. Ajouter une interface de modification des examens avant leur ouverture.
3. Ajouter le niveau Licence/Master dans l’administration des étudiants.
4. Ajouter durée, PDF et progression longitudinale dans l’historique étudiant.
5. Remplacer la fiche JSON d’un étudiant par une vraie vue détaillée enseignant.
6. Ajouter un filtre de dossier dans l’accueil étudiant.
7. Remplacer le placeholder de durée par un graphique réel ou le retirer.
8. Compléter la détection locale de secours des erreurs éliminatoires.
9. Ajouter une véritable gestion des comptes Admin si elle est exigée par le cahier des charges.

## Commande exécutée

```text
python -m pytest -vv
```

Résultat : `25 passed`, avec deux avertissements de dépendances et des avertissements SQLAlchemy liés à l’ancienne méthode `Query.get()`.
