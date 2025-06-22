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
        return """
Analysez cette conversation médicale pour évaluer les aspects de communication.

CRITÈRE À ÉVALUER: {criterion_description}

CONVERSATION:
{conversation_text}

Évaluez si le médecin a satisfait ce critère de communication. Concentrez-vous sur:
- La qualité de l'écoute et de l'empathie
- La clarté des explications
- L'adaptation du langage au patient
- Les salutations et politesse
- La gestion des émotions du patient

Répondez UNIQUEMENT par:
- "OUI" si le critère est clairement satisfait
- "NON" si le critère n'est pas satisfait
- "PARTIELLEMENT" si le critère est partiellement satisfait

Justification en une phrase courte.

Format: OUI/NON/PARTIELLEMENT - [justification]
"""

    def _get_anamnesis_prompt(self):
        return """
Analysez cette conversation médicale pour évaluer la qualité de l'anamnèse.

CRITÈRE À ÉVALUER: {criterion_description}

CONVERSATION:
{conversation_text}

Évaluez si le médecin a correctement exploré ce point d'anamnèse. Vérifiez:
- Les questions sur les symptômes principaux
- L'exploration des antécédents
- Les questions sur les facteurs déclenchants
- L'histoire de la maladie actuelle
- Les questions sur le mode de vie

Répondez UNIQUEMENT par:
- "OUI" si le critère est clairement satisfait
- "NON" si le critère n'est pas satisfait
- "PARTIELLEMENT" si le critère est partiellement satisfait

Format: OUI/NON/PARTIELLEMENT - [justification]
"""

    def _get_physical_exam_prompt(self):
        return """
Analysez cette conversation médicale pour évaluer l'examen physique.

CRITÈRE À ÉVALUER: {criterion_description}

CONVERSATION:
{conversation_text}

Évaluez si le médecin a mentionné ou proposé l'examen physique approprié:
- Inspection, palpation, percussion, auscultation
- Examen ciblé selon les symptômes
- Mention des gestes techniques
- Explication des manœuvres au patient

Répondez UNIQUEMENT par:
- "OUI" si le critère est clairement satisfait
- "NON" si le critère n'est pas satisfait
- "PARTIELLEMENT" si le critère est partiellement satisfait

Format: OUI/NON/PARTIELLEMENT - [justification]
"""

    def _get_diagnostic_prompt(self):
        return """
Analysez cette conversation médicale pour évaluer le raisonnement diagnostique.

CRITÈRE À ÉVALUER: {criterion_description}

CONVERSATION:
{conversation_text}

DIAGNOSTIC ATTENDU: {expected_diagnosis}

Évaluez si le médecin a:
- Proposé le bon diagnostic ou s'en approche
- Expliqué son raisonnement
- Évoqué des diagnostics différentiels
- Justifié ses hypothèses

Répondez UNIQUEMENT par:
- "OUI" si le critère est clairement satisfait
- "NON" si le critère n'est pas satisfait
- "PARTIELLEMENT" si le critère est partiellement satisfait

Format: OUI/NON/PARTIELLEMENT - [justification]
"""

    def _get_treatment_prompt(self):
        return """
Analysez cette conversation médicale pour évaluer la prise en charge thérapeutique.

CRITÈRE À ÉVALUER: {criterion_description}

CONVERSATION:
{conversation_text}

Évaluez si le médecin a:
- Proposé un traitement approprié
- Expliqué les options thérapeutiques
- Donné des conseils de prévention
- Planifié le suivi

Répondez UNIQUEMENT par:
- "OUI" si le critère est clairement satisfait
- "NON" si le critère n'est pas satisfait
- "PARTIELLEMENT" si le critère est partiellement satisfait

Format: OUI/NON/PARTIELLEMENT - [justification]
"""

    def _get_general_prompt(self):
        return """
Analysez cette conversation médicale pour évaluer ce critère général.

CRITÈRE À ÉVALUER: {criterion_description}

CONVERSATION:
{conversation_text}

Évaluez objectivement si le médecin a satisfait ce critère basé sur la conversation.

Répondez UNIQUEMENT par:
- "OUI" si le critère est clairement satisfait
- "NON" si le critère n'est pas satisfait
- "PARTIELLEMENT" si le critère est partiellement satisfait

Format: OUI/NON/PARTIELLEMENT - [justification]
"""
        
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
                role = "Médecin" if msg.get('role') == 'human' else "Patient"
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
            "has_greeting": False,
            "has_closing": False,
            "communication_quality": "basic"
        }
        
        if doctor_messages:
            analysis["avg_message_length"] = analysis["total_words"] / len(doctor_messages)
            
            # Count questions
            for msg in doctor_messages:
                content = msg.get('content', '').lower()
                analysis["question_count"] += content.count('?')
                
                # Check for greeting
                if any(word in content for word in ['bonjour', 'salut', 'comment allez-vous']):
                    analysis["has_greeting"] = True
                
                # Check for closing
                if any(word in content for word in ['au revoir', 'bonne journée', 'prenez soin']):
                    analysis["has_closing"] = True
            
            # Assess communication quality
            if analysis["question_count"] >= 5 and analysis["has_greeting"]:
                analysis["communication_quality"] = "good"
            elif analysis["question_count"] >= 8 and analysis["has_greeting"] and analysis["has_closing"]:
                analysis["communication_quality"] = "excellent"
        
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
            item['justification'] = result['justification']
            
            logger.info(f"Evaluated '{criterion_description}': {result['completed']}")
            
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
                    completed = True  # Consider partial as completed for scoring
                    justification = f"Partiellement satisfait: {justification.strip()}"
                elif status_part in ['NON', 'NO']:
                    completed = False
                    justification = justification.strip()
            else:
                # Fallback parsing
                response_lower = response_text.lower()
                if any(word in response_lower for word in ['oui', 'yes', 'satisfait', 'réalisé']):
                    completed = True
                    justification = "Critère satisfait selon l'analyse LLM"
                elif any(word in response_lower for word in ['partiellement', 'partially']):
                    completed = True
                    justification = "Critère partiellement satisfait selon l'analyse LLM"
                else:
                    completed = False
                    justification = "Critère non satisfait selon l'analyse LLM"
        
        except Exception as e:
            logger.error(f"Error parsing LLM response: {str(e)}")
            justification = f"Erreur de parsing: {response_text[:100]}"
        
        return {
            'completed': completed,
            'justification': justification
        }
    
    def _calculate_final_scores(self, checklist):
        """Calculate final scores based on evaluated checklist"""
        total_points = sum(item.get('points', 1) for item in checklist)
        earned_points = sum(item.get('points', 1) for item in checklist if item.get('completed', False))
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
        """Generate enhanced recommendations based on evaluation results"""
        checklist = self.state.get("results", {}).get('checklist', [])
        conversation_analysis = self.state.get("conversation_analysis", {})
        missed_items = [item for item in checklist if not item.get('completed', False)]
        
        recommendations = []
        
        # Category-based recommendations
        missed_categories = {}
        for item in missed_items:
            category = item.get('category', 'Général')
            if category not in missed_categories:
                missed_categories[category] = []
            missed_categories[category].append(item)
        
        # Generate targeted recommendations
        for category, items in missed_categories.items():
            if category.lower() in ['communication']:
                recommendations.append(
                    f"Améliorez votre communication : travaillez les salutations, l'empathie et l'explication claire des procédures."
                )
            elif category.lower() in ['anamnèse', 'anamnese']:
                recommendations.append(
                    f"Approfondissez votre anamnèse : posez plus de questions sur les antécédents, les symptômes et leur évolution."
                )
            elif category.lower() in ['examen physique', 'examen']:
                recommendations.append(
                    f"N'oubliez pas l'examen physique : mentionnez les gestes d'inspection, palpation et auscultation appropriés."
                )
            elif category.lower() in ['diagnostic']:
                recommendations.append(
                    f"Renforcez votre raisonnement diagnostique : expliquez vos hypothèses et évoquezles diagnostics différentiels."
                )
            elif category.lower() in ['traitement', 'thérapeutique']:
                recommendations.append(
                    f"Complétez la prise en charge : proposez un traitement adapté et planifiez le suivi."
                )
            else:
                recommendations.append(
                    f"Attention aux points de {category} : {items[0].get('description', 'critère manqué')}"
                )
        
        # Communication quality recommendations
        comm_quality = conversation_analysis.get("communication_quality", "basic")
        if comm_quality == "basic":
            recommendations.append(
                "Améliorez la qualité de votre communication en posant plus de questions et en structurant mieux vos interactions."
            )
        
        # Limit to 3 most important recommendations
        self.state["recommendations"] = recommendations[:3] if recommendations else [
            "Très bon travail ! Continuez à perfectionner votre approche clinique."
        ]
    
    def _generate_enhanced_feedback(self):
        """Generate comprehensive feedback based on enhanced evaluation"""
        results = self.state.get("results", {})
        conversation_analysis = self.state.get("conversation_analysis", {})
        percentage = results.get('percentage', 0)
        
        # Base feedback on performance
        if percentage >= 90:
            base_feedback = "Excellente consultation ! Vous maîtrisez très bien l'approche clinique."
        elif percentage >= 80:
            base_feedback = "Très bonne consultation. Quelques points mineurs à améliorer."
        elif percentage >= 70:
            base_feedback = "Bonne consultation dans l'ensemble. Certains aspects demandent plus d'attention."
        elif percentage >= 60:
            base_feedback = "Consultation satisfaisante mais perfectible. Revoyez les points manqués."
        else:
            base_feedback = "Consultation à améliorer significativement. Entraînez-vous sur les points fondamentaux."
        
        # Add communication feedback
        comm_quality = conversation_analysis.get("communication_quality", "basic")
        if comm_quality == "excellent":
            comm_feedback = " Votre communication avec le patient est excellente."
        elif comm_quality == "good":
            comm_feedback = " Votre communication est bonne, continuez ainsi."
        else:
            comm_feedback = " Travaillez votre communication pour créer une meilleure relation avec le patient."
        
        # Add conversation structure feedback
        message_count = conversation_analysis.get("message_count", 0)
        if message_count < 5:
            structure_feedback = " Posez plus de questions pour recueillir suffisamment d'informations."
        elif message_count > 15:
            structure_feedback = " Excellente interaction, vous avez su mener une consultation complète."
        else:
            structure_feedback = " Bon niveau d'interaction avec le patient."
        
        feedback = base_feedback + comm_feedback + structure_feedback
        
        # Update results with feedback
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