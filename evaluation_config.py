# evaluation_config.py
# Configuration file for customizing evaluation prompts and settings

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