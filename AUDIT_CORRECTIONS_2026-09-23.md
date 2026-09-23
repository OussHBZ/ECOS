# Vérification et corrections — 23 septembre 2026

Les corrections sont présentes dans le projet local. Le serveur utilisé par les enseignants n'a pas été modifié pendant cette intervention.

## Problèmes signalés

| Signalement | Cause identifiée dans le code | Correction |
| --- | --- | --- |
| Page affichant `Case number already exists` | Une soumission classique quittait le formulaire pour afficher la réponse JSON d'erreur. | Enregistrement asynchrone avec erreur en français dans le formulaire, saisies conservées, bouton protégé contre les doubles clics et redirection après succès. Les conflits sont aussi vérifiés lors des modifications. |
| Enseignants bloqués malgré une réinitialisation | La connexion cherchait uniquement un email exact ; les anciens identifiants et les différences de casse/espaces n'étaient pas pris en charge. | Connexion par email ou ancien identifiant, comparaison normalisée, prévention des nouveaux doublons, tests de connexion après réinitialisation. Les identifiants ambigus ne sélectionnent pas arbitrairement un compte. |
| Phrases du patient incomplètes | Budget de sortie partagé limité à 150 tokens, sans contrôle de fin de génération. | Budget porté à 2048 tokens, instruction de terminer les phrases et une nouvelle tentative si la réponse est tronquée, vide ou finit par certains mots de liaison. Une génération encore incomplète n'est pas enregistrée. |
| Refus hors sujet du patient | Le contrôle de divulgation pouvait interpréter des mots français courants comme une copie du dossier. | Comparaison sur des mots significatifs ; maintien des protections contre la divulgation du diagnostic et les conseils cliniques. Les questions de suivi sont explicitement contextualisées. |
| Tests sans données | Alias appliqués de manière inégale et libellés `description` du bilan ignorés. | Résolution de TM6/6MWT, FEVG/fraction d'éjection et Sit-to-stand, prise en charge des descriptions et des anciens résultats explicites `libellé : valeur`. Correspondance sur des mots complets. |
| Panneau « Paramètres obtenus » vide | Seuls les paramètres vitaux structurés y étaient ajoutés. | Les résultats trouvés dans les constantes, examens et bilans y sont aussi conservés. |
| Suppression d'un enseignant | Les cas sont indépendants du compte, mais l'attribution des commentaires n'avait pas de relation inverse pour détacher l'enseignant. | Détachement explicite de l'auteur des commentaires. Conservation vérifiée des cas, dossiers, imports, examens, commentaires et notes, avec les contraintes de clés étrangères activées. |

## Autres corrections

- Les champs et lignes volontairement effacés dans le formulaire ne sont plus réintroduits depuis les anciennes données d'extraction.
- Les critères d'évaluation et les anciennes catégories d'examens sont conservés dans l'export du cas. Une ancienne valeur modifiée ne reste pas prioritaire sur sa nouvelle valeur.
- Un dossier pathologique inexistant, archivé ou appartenant à une autre spécialité est refusé à l'enregistrement.
- La suppression directe d'un cas ayant des simulations est bloquée, comme l'était déjà sa suppression depuis la gestion du cycle de vie. L'archivage reste disponible.
- En examen, la progression prend en compte le message qui vient d'être enregistré.
- Un changement de rôle lors de la connexion nettoie l'ancien état de session.
- Une erreur du chat restitue la saisie et apparaît comme un message du service.
- La version des ressources statiques est incrémentée pour renouveler le cache après déploiement.
- Le lancement direct de l'application désactive le débogueur par défaut. `FLASK_DEBUG=true` le réactive pour le développement.
- `SESSION_COOKIE_SECURE=true` permet d'activer les cookies réservés à HTTPS sur un déploiement HTTPS.

## Validation

- **71 tests Python réussis** : les 53 tests existants et 18 régressions supplémentaires. Ils couvrent notamment les accès, les cas, les imports, les simulations, les examens, l'historique, l'évaluation et les exports.
- **3 tests JavaScript réussis** sur les véritables gestionnaires de soumission : doublon, expiration de session et double clic/redirection sous `/ecos`.
- Syntaxe des deux fichiers JavaScript modifiés vérifiée avec Node ; `git diff --check` sans erreur.
- Les tests Python utilisent une base SQLite temporaire en mémoire et des réponses IA simulées. Ils ne modifient pas la base réelle.
- Quelques avertissements de dépréciation existants concernent PyPDF2 et `Query.get()` ; aucun échec de test.

Commandes depuis le dossier `ECOS` :

```text
python -m pytest -q
node --test tests/test_case_form_ui.cjs
node --check static/js/kine-components.js
node --check static/js/kine-chat.js
```

## Mise en service et vérification des signalements réels

1. Sauvegarder la base du serveur, déployer les fichiers modifiés avec la procédure habituelle puis redémarrer le service. Aucune nouvelle colonne n'est nécessaire pour ces corrections ; ne pas réinitialiser la base avec `init_db.py`.
2. Dans **Administration → Enseignants**, vérifier que les comptes concernés sont affectés à **ECOS Kiné**. Une réinitialisation de mot de passe ne modifie pas cette affectation. Un compte ECOS standard reste réservé à cet espace.
3. Tester le compte concerné avec son email ou son ancien identifiant. Les comptes ambigus dans une ancienne base nécessitent une correction de leurs identifiants ; aucun compte réel n'a été fusionné ou réaffecté ici.
4. Reprendre le cas concerné et vérifier que ses résultats TM6, FEVG et Sit-to-stand sont effectivement renseignés. Le logiciel renvoie les valeurs enregistrées ; il ne crée pas de résultats médicaux absents du dossier.
5. Vérifier une conversation réelle, la soumission d'un cas avec un numéro déjà utilisé et l'affichage sur les navigateurs employés par les enseignants.

L'accès au serveur, la base de production, le comportement réel du fournisseur IA et un parcours dans un navigateur graphique n'ont pas été vérifiés pendant cette intervention. Les tests JavaScript utilisent un DOM simulé, pas un navigateur complet. Ce rapport décrit les défauts corrigés et leur couverture ; il ne garantit pas l'absence de tout autre défaut.
