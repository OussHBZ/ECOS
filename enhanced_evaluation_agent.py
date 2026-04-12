import os
import re
import json
import logging
from datetime import datetime
import tempfile
from langchain_core.messages import HumanMessage
import asyncio
from typing import List, Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnhancedEvaluationAgent:
    """Enhanced agent-based evaluation processor with LLM-based analysis for each checklist item"""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self.state = {}
        self._cache = {}

        # Enhanced prompts for different types of evaluation criteria
        self.evaluation_prompts = {
            'communication': self._get_communication_prompt(),
            'anamnese': self._get_anamnesis_prompt(),
            'examen_physique': self._get_physical_exam_prompt(),
            'diagnostic': self._get_diagnostic_prompt(),
            'traitement': self._get_treatment_prompt(),
            'general': self._get_general_prompt()
        }

    def _get_communication_prompt(self):
        return """Vous êtes un évaluateur ECOS/OSCE expérimenté. Analysez cette consultation médicale simulée.

CRITÈRE DE COMMUNICATION À ÉVALUER :
{criterion_description}

TRANSCRIPTION DE LA CONSULTATION :
{conversation_text}

Évaluez STRICTEMENT si l'étudiant en médecine a satisfait ce critère de communication.

Points à vérifier :
- L'étudiant s'est-il présenté (nom, fonction) ?
- A-t-il recueilli le consentement ou mis le patient à l'aise ?
- A-t-il fait preuve d'écoute active (reformulation, empathie verbale) ?
- A-t-il adapté son langage au niveau du patient (pas de jargon non expliqué) ?
- A-t-il vérifié la compréhension du patient ?
- A-t-il conclu la consultation de manière appropriée (résumé, questions, au revoir) ?

IMPORTANT : Évaluez uniquement ce qui est explicitement présent dans la conversation. Ne supposez rien.

Répondez STRICTEMENT au format suivant :
OUI/NON/PARTIELLEMENT - [justification factuelle en une phrase, citant un élément concret de la conversation]"""

    def _get_anamnesis_prompt(self):
        return """Vous êtes un évaluateur ECOS/OSCE expérimenté. Analysez cette consultation médicale simulée.

CRITÈRE D'ANAMNÈSE À ÉVALUER :
{criterion_description}

TRANSCRIPTION DE LA CONSULTATION :
{conversation_text}

Évaluez STRICTEMENT si l'étudiant a correctement exploré ce point d'anamnèse.

Vérifiez si l'étudiant a posé des questions sur :
- Le motif de consultation et l'histoire de la maladie actuelle (HMA)
- Les caractéristiques du symptôme principal (ATCD, localisation, intensité, durée, facteurs aggravants/calmants, irradiation, évolution)
- Les antécédents personnels médicaux et chirurgicaux
- Les antécédents familiaux pertinents
- Les traitements en cours et allergies
- Le mode de vie (tabac, alcool, profession, habitudes)
- La revue des systèmes pertinents

IMPORTANT : Le critère doit être explicitement abordé par une question de l'étudiant. Une réponse spontanée du patient ne compte pas.

Répondez STRICTEMENT au format suivant :
OUI/NON/PARTIELLEMENT - [justification factuelle en une phrase, citant la question posée ou son absence]"""

    def _get_physical_exam_prompt(self):
        return """Vous êtes un évaluateur ECOS/OSCE expérimenté. Analysez cette consultation médicale simulée.

CRITÈRE D'EXAMEN PHYSIQUE À ÉVALUER :
{criterion_description}

TRANSCRIPTION DE LA CONSULTATION :
{conversation_text}

Évaluez STRICTEMENT si l'étudiant a proposé ou mentionné l'examen physique approprié.

Vérifiez si l'étudiant a :
- Demandé la permission avant d'examiner le patient
- Mentionné les gestes d'examen pertinents (inspection, palpation, percussion, auscultation)
- Proposé un examen ciblé en rapport avec les symptômes
- Expliqué ce qu'il allait faire avant de le faire
- Recherché les signes physiques attendus pour la pathologie suspectée
- Interprété ou commenté les résultats de l'examen

IMPORTANT : Dans un ECOS simulé par chat, l'étudiant doit VERBALISER ses intentions d'examen. Évaluez ce qu'il a dit vouloir examiner.

Répondez STRICTEMENT au format suivant :
OUI/NON/PARTIELLEMENT - [justification factuelle en une phrase]"""

    def _get_diagnostic_prompt(self):
        return """Vous êtes un évaluateur ECOS/OSCE expérimenté. Analysez cette consultation médicale simulée.

CRITÈRE DE RAISONNEMENT DIAGNOSTIQUE À ÉVALUER :
{criterion_description}

TRANSCRIPTION DE LA CONSULTATION :
{conversation_text}

DIAGNOSTIC ATTENDU : {expected_diagnosis}

Évaluez STRICTEMENT si l'étudiant a démontré un raisonnement diagnostique adéquat.

Vérifiez si l'étudiant a :
- Formulé une hypothèse diagnostique (même si imparfaite)
- Proposé le bon diagnostic ou un diagnostic cohérent avec les données recueillies
- Évoqué au moins un diagnostic différentiel pertinent
- Justifié son raisonnement en s'appuyant sur les éléments cliniques recueillis
- Proposé des examens complémentaires pour confirmer le diagnostic
- Expliqué le diagnostic au patient en termes compréhensibles

IMPORTANT : Comparez le diagnostic proposé par l'étudiant au diagnostic attendu. Un diagnostic approchant ou un synonyme acceptable compte comme correct.

Répondez STRICTEMENT au format suivant :
OUI/NON/PARTIELLEMENT - [justification factuelle en une phrase, précisant le diagnostic proposé vs attendu si pertinent]"""

    def _get_treatment_prompt(self):
        return """Vous êtes un évaluateur ECOS/OSCE expérimenté. Analysez cette consultation médicale simulée.

CRITÈRE DE PRISE EN CHARGE THÉRAPEUTIQUE À ÉVALUER :
{criterion_description}

TRANSCRIPTION DE LA CONSULTATION :
{conversation_text}

Évaluez STRICTEMENT si l'étudiant a proposé une prise en charge thérapeutique appropriée.

Vérifiez si l'étudiant a :
- Proposé un traitement pharmacologique adapté (molécule, posologie, durée)
- Expliqué le traitement au patient (bénéfices, effets secondaires possibles)
- Donné des mesures hygiéno-diététiques ou des conseils de prévention
- Planifié un suivi (quand revenir, signes d'alerte à surveiller)
- Donné des consignes claires en cas d'aggravation
- Vérifié que le patient a compris le plan de traitement

IMPORTANT : Évaluez uniquement ce qui a été explicitement dit dans la conversation.

Répondez STRICTEMENT au format suivant :
OUI/NON/PARTIELLEMENT - [justification factuelle en une phrase]"""

    def _get_general_prompt(self):
        return """Vous êtes un évaluateur ECOS/OSCE expérimenté. Analysez cette consultation médicale simulée.

CRITÈRE À ÉVALUER :
{criterion_description}

TRANSCRIPTION DE LA CONSULTATION :
{conversation_text}

Évaluez OBJECTIVEMENT et STRICTEMENT si l'étudiant en médecine a satisfait ce critère, en vous basant uniquement sur ce qui est explicitement présent dans la conversation.

Ne supposez rien. Ne donnez pas le bénéfice du doute. Évaluez factuellement.

Répondez STRICTEMENT au format suivant :
OUI/NON/PARTIELLEMENT - [justification factuelle en une phrase, citant un élément concret ou son absence]"""

    def evaluate_conversation(self, conversation, case_data):
        """Main entry point to evaluate a conversation with enhanced LLM analysis"""
        logger.info(f"Enhanced evaluation for case {case_data.get('case_number')}")

        # Create a cache key based on the conversation
        cache_key = self._create_cache_key(conversation)

        # Check if we have a cached result
        if cache_key in self._cache:
            logger.info("Using cached evaluation results")
            return self._cache[cache_key]

        # Initialize state for this evaluation
        self.state = {
            "conversation": conversation,
            "case_data": case_data,
            "checklist": case_data.get('evaluation_checklist', []),
            "results": {},
            "evaluation_complete": False
        }

        # Run the enhanced evaluation
        self._run_enhanced_evaluation()

        # Cache the results
        self._cache[cache_key] = self.state["results"]

        return self.state["results"]

    def _create_cache_key(self, conversation):
        """Create a unique key for caching based on conversation content"""
        doctor_messages = [msg.get('content', '') for msg in conversation if msg.get('role') == 'human']
        return hash(tuple(doctor_messages))

    def _run_enhanced_evaluation(self):
        """Enhanced evaluation loop with LLM-based analysis"""
        try:
            # Step 1: Prepare conversation transcript
            self._prepare_transcript()

            # Step 2: Enhanced LLM evaluation for each checklist item
            if self.llm_client and self._has_substantial_conversation():
                self._evaluate_with_enhanced_llm()
            else:
                self._evaluate_with_patterns()

            # Step 3: Generate smart recommendations
            self._generate_enhanced_recommendations()

            # Step 4: Generate comprehensive feedback
            self._generate_enhanced_feedback()

            self.state["evaluation_complete"] = True
            logger.info("Enhanced evaluation completed successfully")

        except Exception as e:
            logger.error(f"Error during enhanced evaluation: {str(e)}")
            self._fallback_evaluation()

    def _prepare_transcript(self):
        """Prepare conversation transcript for analysis"""
        transcript = []
        for msg in self.state.get("conversation", []):
            if msg.get('role') != 'system':
                role = "Étudiant (médecin)" if msg.get('role') == 'human' else "Patient"
                content = msg.get('content', '')
                transcript.append(f"{role}: {content}")

        self.state["transcript"] = "\n\n".join(transcript)
        self.state["conversation_analysis"] = self._analyze_conversation_structure()

    def _analyze_conversation_structure(self):
        """Analyze conversation structure for patterns"""
        conversation = self.state.get("conversation", [])
        doctor_messages = [msg for msg in conversation if msg.get('role') == 'human']

        analysis = {
            "message_count": len(doctor_messages),
            "total_words": sum(len(msg.get('content', '').split()) for msg in doctor_messages),
            "avg_message_length": 0,
            "question_count": 0,
            "open_question_count": 0,
            "has_greeting": False,
            "has_presentation": False,
            "has_closing": False,
            "has_empathy": False,
            "has_physical_exam": False,
            "has_diagnosis": False,
            "has_treatment": False,
            "communication_quality": "basic"
        }

        if doctor_messages:
            analysis["avg_message_length"] = analysis["total_words"] / len(doctor_messages)

            for msg in doctor_messages:
                content = msg.get('content', '').lower()
                analysis["question_count"] += content.count('?')

                # Check for open-ended questions
                if any(q in content for q in ['comment', 'décrivez', 'parlez-moi', 'racontez', 'expliquez']):
                    analysis["open_question_count"] += 1

                # Check for greeting
                if any(word in content for word in ['bonjour', 'bonsoir', 'salut']):
                    analysis["has_greeting"] = True

                # Check for self-presentation
                if any(phrase in content for phrase in ['je suis', 'je m\'appelle', 'docteur', 'dr ', 'interne', 'médecin']):
                    analysis["has_presentation"] = True

                # Check for empathy
                if any(phrase in content for phrase in ['je comprends', 'ne vous inquiétez', 'rassurez', 'je vois', 'ça doit être']):
                    analysis["has_empathy"] = True

                # Check for closing
                if any(word in content for word in ['au revoir', 'bonne journée', 'prenez soin', 'bon rétablissement', 'n\'hésitez pas']):
                    analysis["has_closing"] = True

                # Check for physical exam mentions
                if any(word in content for word in ['examiner', 'ausculter', 'palper', 'inspecter', 'tension', 'température', 'pouls']):
                    analysis["has_physical_exam"] = True

                # Check for diagnosis
                if any(word in content for word in ['diagnostic', 'vous avez', 'il s\'agit', 'je pense que', 'hypothèse']):
                    analysis["has_diagnosis"] = True

                # Check for treatment
                if any(word in content for word in ['traitement', 'médicament', 'prescription', 'prescrire', 'suivi', 'contrôle']):
                    analysis["has_treatment"] = True

            # Assess communication quality
            score = 0
            if analysis["has_greeting"]: score += 1
            if analysis["has_presentation"]: score += 1
            if analysis["has_empathy"]: score += 1
            if analysis["has_closing"]: score += 1
            if analysis["question_count"] >= 5: score += 1
            if analysis["open_question_count"] >= 2: score += 1

            if score >= 5:
                analysis["communication_quality"] = "excellent"
            elif score >= 3:
                analysis["communication_quality"] = "good"
            else:
                analysis["communication_quality"] = "basic"

        return analysis

    def _has_substantial_conversation(self):
        """Check if conversation is substantial enough for LLM evaluation"""
        analysis = self.state.get("conversation_analysis", {})
        return (analysis.get("message_count", 0) >= 3 and
                analysis.get("total_words", 0) >= 20)

    def _evaluate_with_enhanced_llm(self):
        """Enhanced LLM evaluation with specific prompts for each checklist item"""
        logger.info("Starting enhanced LLM evaluation")

        transcript = self.state.get("transcript", "")
        checklist = self.state.get("checklist", [])
        case_data = self.state.get("case_data", {})

        if not checklist:
            self._set_empty_results()
            return

        # Evaluate each checklist item individually
        for item in checklist:
            try:
                self._evaluate_single_criterion(item, transcript, case_data)
            except Exception as e:
                logger.error(f"Error evaluating criterion '{item.get('description', 'Unknown')}': {str(e)}")
                item['completed'] = False
                item['justification'] = f"Erreur lors de l'évaluation: {str(e)}"

        # Calculate final scores
        self._calculate_final_scores(checklist)

    def _evaluate_single_criterion(self, item, transcript, case_data):
        """Evaluate a single checklist criterion using targeted LLM prompts"""
        criterion_description = item.get('description', '')
        category = item.get('category', 'general').lower()

        # Select appropriate prompt based on category
        prompt_template = self._select_prompt_template(category)

        # Prepare the prompt
        prompt = prompt_template.format(
            criterion_description=criterion_description,
            conversation_text=transcript,
            expected_diagnosis=case_data.get('diagnosis', 'Non spécifié')
        )

        try:
            # Get LLM response
            response = self.llm_client.invoke(
                [HumanMessage(content=prompt)],
                {"max_tokens": 150, "temperature": 0.1}
            )

            # Parse the response
            result = self._parse_evaluation_response(response.content)

            # Update the item
            item['completed'] = result['completed']
            item['partial'] = result.get('partial', False)
            item['justification'] = result['justification']

            logger.info(f"Evaluated '{criterion_description}': completed={result['completed']}, partial={result.get('partial', False)}")

        except Exception as e:
            logger.error(f"LLM evaluation failed for '{criterion_description}': {str(e)}")
            item['completed'] = False
            item['justification'] = f"Évaluation impossible: {str(e)}"

    def _select_prompt_template(self, category):
        """Select the appropriate prompt template based on category"""
        category_mapping = {
            'communication': 'communication',
            'anamnèse': 'anamnese',
            'anamnese': 'anamnese',
            'examen physique': 'examen_physique',
            'examen': 'examen_physique',
            'diagnostic': 'diagnostic',
            'traitement': 'traitement',
            'thérapeutique': 'traitement'
        }

        for key, template_key in category_mapping.items():
            if key in category:
                return self.evaluation_prompts[template_key]

        return self.evaluation_prompts['general']

    def _parse_evaluation_response(self, response_text):
        """Parse LLM response to extract completion status and justification"""
        response_text = response_text.strip()

        # Default values
        completed = False
        partial = False
        justification = "Évaluation non concluante"

        try:
            # Look for the expected format: OUI/NON/PARTIELLEMENT - [justification]
            if ' - ' in response_text:
                status_part, justification = response_text.split(' - ', 1)
                status_part = status_part.strip().upper()

                if status_part in ['OUI', 'YES']:
                    completed = True
                    justification = justification.strip()
                elif status_part in ['PARTIELLEMENT', 'PARTIALLY']:
                    completed = True
                    partial = True
                    justification = f"Partiellement satisfait : {justification.strip()}"
                elif status_part in ['NON', 'NO']:
                    completed = False
                    justification = justification.strip()
            else:
                # Fallback parsing
                response_lower = response_text.lower()
                if any(word in response_lower for word in ['oui', 'yes', 'satisfait', 'réalisé']):
                    completed = True
                    justification = response_text
                elif any(word in response_lower for word in ['partiellement', 'partially']):
                    completed = True
                    partial = True
                    justification = response_text
                else:
                    completed = False
                    justification = response_text

        except Exception as e:
            logger.error(f"Error parsing LLM response: {str(e)}")
            justification = f"Erreur de parsing: {response_text[:100]}"

        return {
            'completed': completed,
            'partial': partial,
            'justification': justification
        }

    def _calculate_final_scores(self, checklist):
        """Calculate final scores with partial credit support"""
        total_points = sum(item.get('points', 1) for item in checklist)
        earned_points = 0

        for item in checklist:
            if item.get('completed', False):
                points = item.get('points', 1)
                if item.get('partial', False):
                    earned_points += points * 0.5  # Half credit for partial
                else:
                    earned_points += points

        earned_points = round(earned_points, 1)
        percentage = round((earned_points / total_points) * 100) if total_points > 0 else 0

        self.state["results"] = {
            'checklist': checklist,
            'points_total': total_points,
            'points_earned': earned_points,
            'percentage': percentage
        }

    def _evaluate_with_patterns(self):
        """Fallback pattern-based evaluation"""
        logger.info("Using pattern-based fallback evaluation")

        conversation = self.state.get("conversation", [])
        checklist = self.state.get("checklist", [])

        # Simple keyword matching for fallback
        user_text = " ".join([msg.get('content', '') for msg in conversation if msg.get('role') == 'human'])

        for item in checklist:
            description = item.get('description', '').lower()
            keywords = [w for w in re.findall(r'\b\w{3,}\b', description) if len(w) > 3]

            if keywords and any(kw.lower() in user_text.lower() for kw in keywords):
                item['completed'] = True
                item['justification'] = "Critère détecté par analyse de mots-clés"
            else:
                item['completed'] = False
                item['justification'] = "Critère non détecté dans la conversation"

        self._calculate_final_scores(checklist)

    def _generate_enhanced_recommendations(self):
        """Generate targeted OSCE recommendations based on evaluation results"""
        checklist = self.state.get("results", {}).get('checklist', [])
        conversation_analysis = self.state.get("conversation_analysis", {})
        missed_items = [item for item in checklist if not item.get('completed', False)]
        partial_items = [item for item in checklist if item.get('partial', False)]

        recommendations = []

        # Category-based recommendations with specific OSCE guidance
        missed_categories = {}
        for item in missed_items:
            category = item.get('category', 'Général')
            if category not in missed_categories:
                missed_categories[category] = []
            missed_categories[category].append(item)

        for category, items in missed_categories.items():
            cat_lower = category.lower()
            item_descriptions = ', '.join([f'"{it.get("description", "")}"' for it in items[:2]])

            if 'communication' in cat_lower:
                recommendations.append(
                    f"Communication : Structurez votre consultation (présentation → écoute → empathie → explication → conclusion). "
                    f"Points manqués : {item_descriptions}."
                )
            elif 'anamnèse' in cat_lower or 'anamnese' in cat_lower:
                recommendations.append(
                    f"Anamnèse : Utilisez une approche systématique — motif, HMA, ATCD personnels/familiaux, médicaments, allergies, mode de vie. "
                    f"Points manqués : {item_descriptions}."
                )
            elif 'examen' in cat_lower:
                recommendations.append(
                    f"Examen clinique (station) : Verbalisez vos intentions d'examen (\"Je vais vous examiner...\") et recherchez les signes pertinents. "
                    f"Points manqués : {item_descriptions}."
                )
            elif 'diagnostic' in cat_lower:
                recommendations.append(
                    f"Raisonnement diagnostique : Formulez clairement votre hypothèse, justifiez-la par les éléments cliniques, et évoquez les diagnostics différentiels. "
                    f"Points manqués : {item_descriptions}."
                )
            elif 'traitement' in cat_lower or 'thérapeutique' in cat_lower:
                recommendations.append(
                    f"Prise en charge : Proposez un plan thérapeutique complet (traitement, mesures hygiéno-diététiques, suivi, signes d'alerte). "
                    f"Points manqués : {item_descriptions}."
                )
            else:
                recommendations.append(
                    f"{category} : Attention aux points suivants — {item_descriptions}."
                )

        # Specific structural recommendations
        if not conversation_analysis.get("has_greeting") or not conversation_analysis.get("has_presentation"):
            recommendations.append(
                "Pensez à toujours commencer par vous présenter et saluer le patient. C'est un item systématiquement évalué en ECOS."
            )

        if not conversation_analysis.get("has_closing"):
            recommendations.append(
                "Concluez la consultation : résumez le plan, vérifiez la compréhension du patient, et donnez des consignes claires."
            )

        # Limit to 4 most important recommendations
        self.state["recommendations"] = recommendations[:4] if recommendations else [
            "Très bonne performance ! Continuez à vous entraîner pour maintenir ce niveau en conditions d'examen."
        ]

    def _generate_enhanced_feedback(self):
        """Generate comprehensive OSCE feedback"""
        results = self.state.get("results", {})
        conversation_analysis = self.state.get("conversation_analysis", {})
        percentage = results.get('percentage', 0)
        checklist = results.get('checklist', [])

        # Count categories performance
        categories_stats = {}
        for item in checklist:
            cat = item.get('category', 'Général')
            if cat not in categories_stats:
                categories_stats[cat] = {'total': 0, 'completed': 0}
            categories_stats[cat]['total'] += 1
            if item.get('completed', False):
                categories_stats[cat]['completed'] += 1

        # Base feedback
        if percentage >= 90:
            base_feedback = "Excellente consultation ! Vous démontrez une maîtrise solide de l'approche clinique ECOS."
        elif percentage >= 80:
            base_feedback = "Très bonne consultation. Vous maîtrisez les éléments essentiels avec quelques points à perfectionner."
        elif percentage >= 70:
            base_feedback = "Bonne consultation dans l'ensemble. Certains aspects importants nécessitent plus d'attention."
        elif percentage >= 60:
            base_feedback = "Consultation acceptable mais plusieurs compétences clés sont à renforcer."
        elif percentage >= 40:
            base_feedback = "Consultation insuffisante. Revoyez les fondamentaux de l'approche clinique structurée."
        else:
            base_feedback = "Consultation très insuffisante. Un entraînement intensif sur les bases de la consultation médicale est nécessaire."

        # Identify strongest and weakest categories
        best_cat = None
        worst_cat = None
        best_pct = -1
        worst_pct = 101

        for cat, stats in categories_stats.items():
            if stats['total'] > 0:
                pct = (stats['completed'] / stats['total']) * 100
                if pct > best_pct:
                    best_pct = pct
                    best_cat = cat
                if pct < worst_pct:
                    worst_pct = pct
                    worst_cat = cat

        category_feedback = ""
        if best_cat and worst_cat and best_cat != worst_cat:
            category_feedback = f" Point fort : {best_cat} ({best_pct:.0f}%). Point à améliorer : {worst_cat} ({worst_pct:.0f}%)."

        # Communication quality feedback
        comm_quality = conversation_analysis.get("communication_quality", "basic")
        if comm_quality == "excellent":
            comm_feedback = " Votre communication avec le patient est remarquable."
        elif comm_quality == "good":
            comm_feedback = " Votre communication est bonne."
        else:
            comm_feedback = " Travaillez votre communication pour améliorer la relation médecin-patient."

        # Conversation depth feedback
        message_count = conversation_analysis.get("message_count", 0)
        question_count = conversation_analysis.get("question_count", 0)
        if message_count < 5:
            depth_feedback = f" Consultation trop courte ({message_count} interventions, {question_count} questions). Explorez davantage."
        elif message_count > 15:
            depth_feedback = f" Consultation complète et approfondie ({question_count} questions posées)."
        else:
            depth_feedback = f" Consultation de durée correcte ({question_count} questions posées)."

        feedback = base_feedback + category_feedback + comm_feedback + depth_feedback

        if 'results' not in self.state:
            self.state['results'] = {}

        self.state['results']['feedback'] = feedback

    def _set_empty_results(self):
        """Set empty results when no checklist is available"""
        self.state["results"] = {
            'checklist': [],
            'feedback': "Pas de grille d'évaluation disponible pour ce cas.",
            'points_total': 0,
            'points_earned': 0,
            'percentage': 0
        }

    def _fallback_evaluation(self):
        """Fallback evaluation in case of errors"""
        checklist = self.state.get("checklist", [])
        self.state["results"] = {
            'checklist': [
                {**item, 'completed': False, 'justification': "Erreur lors de l'évaluation automatique."}
                for item in checklist
            ],
            'feedback': "Une erreur est survenue lors de l'évaluation. Veuillez réessayer.",
            'points_total': sum(item.get('points', 1) for item in checklist),
            'points_earned': 0,
            'percentage': 0
        }
        self.state["recommendations"] = ["Contactez le support technique pour résoudre le problème d'évaluation."]

    def get_recommendations(self):
        """Get the recommendations generated during evaluation"""
        return self.state.get("recommendations", [])

    def get_results(self):
        """Get full evaluation results"""
        return self.state.get("results", {})

    def clear_cache(self):
        """Clear the evaluation cache"""
        self._cache = {}
        logger.info("Enhanced evaluation cache cleared")
