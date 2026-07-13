# evaluation_config.py
# Configuration file for customizing evaluation prompts and settings

from copy import deepcopy

EVALUATION_SETTINGS = {
    # Minimum conversation requirements for LLM evaluation
    'min_messages_for_llm': 3,
    'min_words_for_llm': 20,
    
    # LLM settings
    'max_tokens_per_evaluation': 150,
    'temperature': 0.1,
    'timeout_seconds': 30,
    
    # Caching
    'enable_cache': True,
    'cache_size_limit': 100,
    
    # Fallback settings
    'use_pattern_fallback': True,
    'enable_keyword_matching': True
}

# Custom prompt templates
CUSTOM_PROMPTS = {
    'communication': """
    Analysez cette conversation pour évaluer la COMMUNICATION médicale.
    
    CRITÈRE: {criterion_description}
    CONVERSATION: {conversation_text}
    
    Évaluez si le médecin communique efficacement:
    - Salutations et politesse
    - Clarté des explications  
    - Empathie et écoute active
    - Adaptation du langage
    
    Réponse: OUI/NON/PARTIELLEMENT - [justification courte]
    """,
    
    'anamnese': """
    Analysez cette conversation pour évaluer l'ANAMNÈSE médicale.
    
    CRITÈRE: {criterion_description}
    CONVERSATION: {conversation_text}
    
    Évaluez si le médecin recueille bien l'anamnèse:
    - Questions sur les symptômes principaux
    - Exploration des antécédents
    - Recherche de facteurs déclenchants
    - Histoire de la maladie actuelle
    
    Réponse: OUI/NON/PARTIELLEMENT - [justification courte]
    """,
    
    'examen_physique': """
    Analysez cette conversation pour évaluer l'EXAMEN PHYSIQUE.
    
    CRITÈRE: {criterion_description}
    CONVERSATION: {conversation_text}
    
    Évaluez si le médecin aborde l'examen physique:
    - Mention des gestes d'examen
    - Inspection, palpation, auscultation
    - Explication des manœuvres au patient
    - Examen adapté aux symptômes
    
    Réponse: OUI/NON/PARTIELLEMENT - [justification courte]
    """,
    
    'diagnostic': """
    Analysez cette conversation pour évaluer le RAISONNEMENT DIAGNOSTIQUE.
    
    CRITÈRE: {criterion_description}
    CONVERSATION: {conversation_text}
    DIAGNOSTIC ATTENDU: {expected_diagnosis}
    
    Évaluez si le médecin démontre un bon raisonnement:
    - Propose un diagnostic cohérent
    - Justifie ses hypothèses
    - Évoque des diagnostics différentiels
    - Explique son raisonnement
    
    Réponse: OUI/NON/PARTIELLEMENT - [justification courte]
    """,
    
    'traitement': """
    Analysez cette conversation pour évaluer la PRISE EN CHARGE.
    
    CRITÈRE: {criterion_description}
    CONVERSATION: {conversation_text}
    
    Évaluez si le médecin propose une prise en charge:
    - Traitement approprié
    - Explications des options thérapeutiques
    - Conseils de prévention
    - Planification du suivi
    
    Réponse: OUI/NON/PARTIELLEMENT - [justification courte]
    """
}

# Keywords for pattern matching fallback (when LLM is not available)
FALLBACK_KEYWORDS = {
    'communication': [
        'bonjour', 'salut', 'comment allez-vous', 'merci', 'au revoir',
        'je comprends', 'rassurez-vous', 'ne vous inquiétez pas'
    ],
    'anamnese': [
        'depuis quand', 'combien de temps', 'antécédents', 'famille',
        'allergies', 'médicaments', 'facteurs', 'déclenchants'
    ],
    'examen_physique': [
        'examen', 'ausculter', 'palper', 'inspecter', 'tension',
        'température', 'pouls', 'abdomen', 'thorax', 'cœur'
    ],
    'diagnostic': [
        'diagnostic', 'vous souffrez', 'il s\'agit', 'probablement',
        'différentiel', 'hypothèse', 'pensons à'
    ],
    'traitement': [
        'traitement', 'médicament', 'prescription', 'conseils',
        'repos', 'suivi', 'revoir', 'contrôle'
    ]
}

# Scoring thresholds for recommendations
SCORING_THRESHOLDS = {
    'excellent': 90,
    'very_good': 80,
    'good': 70,
    'satisfactory': 60,
    'needs_improvement': 0
}

# Recommendation templates based on missing categories
RECOMMENDATION_TEMPLATES = {
    'communication': [
        "Améliorez votre communication : saluez le patient, montrez de l'empathie et expliquez clairement vos gestes.",
        "Travaillez la relation médecin-patient : écoutez activement et adaptez votre langage.",
        "Perfectionnez vos compétences relationnelles : rassurez le patient et concluez appropriément."
    ],
    'anamnese': [
        "Approfondissez votre anamnèse : explorez davantage les antécédents et l'histoire de la maladie.",
        "Posez plus de questions ouvertes sur les symptômes et leurs caractéristiques.",
        "N'oubliez pas de rechercher les facteurs déclenchants et les antécédents familiaux."
    ],
    'examen_physique': [
        "Mentionnez systématiquement l'examen physique adapté aux symptômes présentés.",
        "Expliquez au patient les gestes d'examen que vous souhaitez réaliser.",
        "N'oubliez pas l'inspection, la palpation et l'auscultation selon le contexte."
    ],
    'diagnostic': [
        "Renforcez votre raisonnement diagnostique : proposez un diagnostic et justifiez-le.",
        "Pensez aux diagnostics différentiels et expliquez votre démarche.",
        "Verbalisez votre réflexion diagnostique pour montrer votre raisonnement."
    ],
    'traitement': [
        "Complétez votre prise en charge : proposez un traitement adapté et des conseils.",
        "N'oubliez pas de planifier le suivi et de donner des recommandations préventives.",
        "Expliquez les options thérapeutiques et leurs bénéfices au patient."
    ]
}

# Configuration for different case types 
CASE_TYPE_CONFIG = {
    'urgence': {
        'communication_weight': 1.2,  # More emphasis on quick, clear communication
        'examen_physique_weight': 1.3,  # Critical in emergency
        'diagnostic_weight': 1.4,  # Fast diagnosis crucial
        'time_pressure_factor': True
    },
    'consultation': {
        'communication_weight': 1.5,  # Very important in consultation
        'anamnese_weight': 1.3,  # Thorough history taking
        'traitement_weight': 1.2,  # Comprehensive management
        'time_pressure_factor': False
    },
    'pediatrie': {
        'communication_weight': 1.4,  # Adapted communication for children/parents
        'anamnese_weight': 1.2,  # Often requires parent history
        'examen_physique_weight': 1.1,  # Gentle approach needed
        'specific_keywords': ['parents', 'enfant', 'âge', 'croissance']
    }
}


# Physiotherapy evaluation grids. They are intentionally separate from the
# generic OSCE checklist configuration above and must only be selected for
# cases whose specialty is ``kine``.
KINE_ELIMINATION_CAP = 8.0

KINE_LICENCE_ELIMINATORY_ERRORS = [
    {
        'id': 'missing_initial_vitals',
        'description': 'Début de séance sans contrôle des constantes initiales (PA, FC, SpO₂).',
    },
    {
        'id': 'absolute_contraindication_ignored',
        'description': "Non-respect d'une contre-indication absolue.",
    },
    {
        'id': 'stopping_criterion_ignored',
        'description': "Ignorer un critère d'arrêt de la séance.",
    },
    {
        'id': 'dangerous_exercise_or_intensity',
        'description': "Prescription d'un exercice dangereux ou d'une intensité inadaptée.",
    },
    {
        'id': 'missing_exertion_monitoring',
        'description': "Absence de surveillance clinique pendant l'effort.",
    },
]

KINE_MASTER_EXTRA_ELIMINATORY_ERRORS = [
    {
        'id': 'serious_incident_not_recognized',
        'description': 'Incident grave non reconnu ou ignoré.',
    },
    {
        'id': 'poor_emergency_response',
        'description': "Mauvaise conduite devant une urgence.",
    },
    {
        'id': 'unsafe_resume_after_major_incident',
        'description': "Reprise de la séance après un incident majeur sans avis médical.",
    },
    {
        'id': 'direct_patient_endangerment',
        'description': 'Prescription mettant directement le patient en danger.',
    },
]

KINE_EVALUATION_GRIDS = {
    'licence': {
        'name': 'Fondamentaux cliniques',
        'level': 'licence',
        'total_points': 20,
        'validation_threshold': 12,
        'elimination_cap': KINE_ELIMINATION_CAP,
        'elimination_rules': KINE_LICENCE_ELIMINATORY_ERRORS,
        'sections': [
            {
                'id': 'medical_record_analysis',
                'title': 'I. Analyse du dossier médical',
                'criterion': 'Exploitation du dossier médical initial',
                'points': 2,
                'ai_indicators': [
                    'Diagnostic identifié', 'Intervention comprise',
                    'Traitement pris en compte', 'Examens interprétés',
                    'Facteurs de risque et contre-indications repérés',
                ],
            },
            {
                'id': 'history_taking',
                'title': 'II. Anamnèse',
                'criterion': "Qualité de l'entretien clinique",
                'points': 3,
                'ai_indicators': [
                    'Symptômes, douleur, dyspnée et fatigue recherchés',
                    'Limitations fonctionnelles et activité physique recherchées',
                    'Profession, situation familiale et logement explorés',
                    'Objectifs, attentes, peurs et motivation explorés',
                    'Questions pertinentes et écoute active',
                ],
            },
            {
                'id': 'physiotherapy_assessment',
                'title': 'III. Bilan kinésithérapique',
                'criterion': 'Réalisation du bilan clinique',
                'points': 4,
                'ai_indicators': [
                    'Constantes évaluées : PA, FC, SpO₂, FR, poids et IMC',
                    'Échelles NYHA et Borg évaluées',
                    'Douleur, dyspnée et fatigue évaluées',
                    'Inspection, œdèmes et cicatrice évalués',
                    'Bilans musculaire et articulaire, équilibre, marche et autonomie évalués',
                ],
            },
            {
                'id': 'clinical_reasoning',
                'title': 'IV. Raisonnement clinique',
                'criterion': 'Analyse et prise de décision',
                'points': 3,
                'ai_indicators': [
                    'Diagnostic kinésithérapique cohérent', 'Priorités identifiées',
                    'Facteurs limitants et précautions identifiés',
                    'Objectifs SMART adaptés',
                ],
            },
            {
                'id': 'session_prescription',
                'title': 'V. Prescription de la séance',
                'criterion': 'Construction de la séance',
                'points': 3,
                'ai_indicators': [
                    'Échauffement, exercices et retour au calme inclus',
                    'Surveillance et éducation thérapeutique incluses',
                    'FITT cohérent : fréquence, intensité, temps et type',
                    "Critères d'arrêt et de progression adaptés",
                ],
            },
            {
                'id': 'therapeutic_communication',
                'title': 'VI. Communication thérapeutique',
                'criterion': 'Relation thérapeutique',
                'points': 2,
                'ai_indicators': [
                    'Empathie et écoute active', 'Reformulation',
                    'Langage vulgarisé', 'Relation de confiance',
                ],
            },
            {
                'id': 'therapeutic_education',
                'title': 'VII. Éducation thérapeutique',
                'criterion': 'Conseils au patient',
                'points': 3,
                'ai_indicators': [
                    'Pathologie et traitements expliqués',
                    "Signes d'alerte et auto-surveillance expliqués",
                    "Conseils d'activité physique fournis",
                    'Conseils de retour à domicile personnalisés',
                ],
            },
        ],
    },
    'master': {
        'name': 'Expertise clinique & gestion de crise',
        'level': 'master',
        'total_points': 20,
        'validation_threshold': 14,
        'elimination_cap': KINE_ELIMINATION_CAP,
        'elimination_rules': (
            KINE_LICENCE_ELIMINATORY_ERRORS
            + KINE_MASTER_EXTRA_ELIMINATORY_ERRORS
        ),
        'sections': [
            {
                'id': 'expert_medical_record_analysis',
                'title': 'I. Analyse experte du dossier médical',
                'criterion': 'Exploitation avancée du dossier',
                'points': 2,
                'ai_indicators': [
                    'Analyse critique des examens complémentaires',
                    'Interactions médicamenteuses prises en compte',
                    'Comorbidités et physiopathologie intégrées',
                    'Facteurs pronostiques et priorisation des problèmes',
                ],
            },
            {
                'id': 'expert_history_taking',
                'title': 'II. Anamnèse experte',
                'criterion': 'Entretien clinique approfondi',
                'points': 2,
                'ai_indicators': [
                    'Drapeaux rouges et facteurs limitants recherchés',
                    'Contexte psychosocial exploré',
                    'Compréhension du patient évaluée',
                    'Questions de relance pertinentes',
                ],
            },
            {
                'id': 'expert_physiotherapy_assessment',
                'title': 'III. Bilan kinésithérapique expert',
                'criterion': 'Bilan clinique complet',
                'points': 3,
                'ai_indicators': [
                    'Constantes et orthostatisme évalués', 'Tests fonctionnels sélectionnés',
                    'Bilans musculaire, respiratoire et cardiovasculaire réalisés',
                    'Équilibre, marche, cicatrice et fonction évalués',
                ],
            },
            {
                'id': 'advanced_clinical_reasoning',
                'title': 'IV. Raisonnement clinique avancé',
                'criterion': 'Analyse complexe',
                'points': 3,
                'ai_indicators': [
                    'Diagnostic kinésithérapique formulé', 'Problèmes hiérarchisés',
                    'Interactions entre comorbidités intégrées',
                    'Prise en charge adaptée avec projection clinique',
                ],
            },
            {
                'id': 'advanced_prescription_fitt',
                'title': 'V. Prescription avancée (FITT)',
                'criterion': 'Construction du programme',
                'points': 3,
                'ai_indicators': [
                    'Prescription individualisée et progression définie',
                    'Justification scientifique fournie',
                    'Programme adapté selon les symptômes',
                    "Critères de progression et d'arrêt définis",
                ],
            },
            {
                'id': 'dynamic_session_management',
                'title': 'VI. Conduite de séance dynamique',
                'criterion': 'Adaptation en temps réel',
                'points': 2,
                'ai_indicators': [
                    'Ajustement permanent selon FC, PA et SpO₂',
                    'Borg, douleur, dyspnée, fatigue, comportement et évolution clinique intégrés',
                ],
            },
            {
                'id': 'incident_management',
                'title': 'VII. Gestion des incidents',
                'criterion': "Gestion des situations d'urgence",
                'points': 3,
                'ai_indicators': [
                    'Détection précoce et interprétation des signes',
                    'Arrêt de séance et sécurisation du patient',
                    'Positionnement et conduite adaptés',
                    "Décision de reprise, d'arrêt ou d'appel médical adaptée",
                ],
            },
            {
                'id': 'advanced_therapeutic_education',
                'title': 'VIII. Éducation thérapeutique avancée',
                'criterion': 'Autonomisation du patient',
                'points': 2,
                'ai_indicators': [
                    'Explication personnalisée et Teach-Back utilisés',
                    "Plan d'autogestion et prévention secondaire définis",
                    'Reprise des activités abordée',
                    'Critères de passage en phase III expliqués',
                ],
            },
        ],
    },
}


def get_kine_evaluation_grid(level):
    """Return an isolated grid copy for ``licence`` or ``master``."""
    normalized_level = str(level or '').strip().lower()
    if normalized_level not in KINE_EVALUATION_GRIDS:
        raise ValueError("Le niveau d'évaluation Kiné doit être 'licence' ou 'master'")
    return deepcopy(KINE_EVALUATION_GRIDS[normalized_level])


def apply_kine_elimination_cap(score, eliminatory_errors):
    """Cap a /20 score at 8 when at least one eliminatory error is present."""
    numeric_score = max(0.0, min(20.0, float(score)))
    return min(numeric_score, KINE_ELIMINATION_CAP) if eliminatory_errors else numeric_score
