import os
import re
import json
import logging
from datetime import datetime
import tempfile
from langchain_core.messages import HumanMessage

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EvaluationAgent:
    """Agent-based evaluation processor that assesses medical student performance in OSCE simulations"""
    
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        # Initialize state
        self.state = {}
        # Add caching
        self._cache = {}
        
    def evaluate_conversation(self, conversation, case_data):
        """Main entry point to evaluate a conversation"""
        logger.info(f"Agent evaluating conversation for case {case_data.get('case_number')}")
        
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
            "feedback": "",
            "recommendations": [],
            "evaluation_complete": False
        }
        
        # Run the agent's main evaluation loop
        self._run_evaluation_loop()
        
        # Cache the results for future use
        self._cache[cache_key] = self.state["results"]
        
        # Return the final evaluation results
        return self.state["results"]
    
    def _create_cache_key(self, conversation):
        """Create a unique key for caching based on conversation content"""
        # Extract the actual content for doctor messages
        doctor_messages = [msg['content'] for msg in conversation if msg['role'] == 'human']
        # Create a hash of the combined content
        return hash(tuple(doctor_messages))
    
    def _run_evaluation_loop(self):
        """Main agent loop that coordinates the evaluation process"""
        try:
            # Step 1: Prepare conversation transcript
            self._prepare_transcript()
            
            # Step 2: Process the evaluation with LLM if available
            if self.llm_client:
                # Check conversation length and complexity to determine evaluation method
                analysis = self.state.get("conversation_analysis", {})
                message_count = analysis.get("message_count", 0)
                question_count = analysis.get("question_count", 0)
                
                # For very short conversations, use pattern-based evaluation
                if message_count < 3 or question_count < 2:
                    logger.info("Short conversation detected, using pattern-based evaluation")
                    self._evaluate_with_patterns()
                else:
                    # For longer conversations, use LLM-based evaluation
                    self._evaluate_with_llm()
            else:
                self._evaluate_with_patterns()
            
            # Step 3: Generate smart recommendations - only for substantial conversations
            if self.state.get("conversation_analysis", {}).get("message_count", 0) > 3:
                self._generate_recommendations()
            else:
                # Use basic recommendations for short conversations
                self._generate_basic_recommendations()
            
            # Step 4: Generate final feedback if not already present
            if not self.state.get("results", {}).get("feedback"):
                self._generate_feedback()
            
            # Mark evaluation as complete
            self.state["evaluation_complete"] = True
            logger.info("Evaluation process completed successfully")
            
        except Exception as e:
            logger.error(f"Error during evaluation process: {str(e)}")
            # Set a fallback result if evaluation fails
            if not self.state.get("results"):
                self.state["results"] = {
                    "checklist": self.state.get("checklist", []),
                    "feedback": "Une erreur est survenue lors de l'évaluation.",
                    "points_total": 0,
                    "points_earned": 0,
                    "percentage": 0
                }
    
    def _prepare_transcript(self):
        """Prepare the conversation transcript for evaluation"""
        transcript = []
        for msg in self.state.get("conversation", []):
            if msg['role'] != 'system':  # Skip system messages
                role = "Médecin" if msg['role'] == 'human' else "Patient"
                transcript.append(f"{role}: {msg['content']}")
        
        self.state["transcript"] = "\n\n".join(transcript)
        
        # Also prepare a structured analysis of the conversation
        self._analyze_conversation_structure()
    
    def _analyze_conversation_structure(self):
        """Analyze the conversation structure for patterns and key indicators"""
        conversation = self.state.get("conversation", [])
        
        # Skip if no conversation
        if not conversation:
            return
            
        # Extract only human (doctor) messages
        doctor_messages = [msg for msg in conversation if msg['role'] == 'human']
        
        # Analysis results
        analysis = {
            "message_count": len(doctor_messages),
            "avg_message_length": 0,
            "question_count": 0,
            "greeting_detected": False,
            "closing_detected": False,
            "diagnostic_keywords": False,
            "treatment_keywords": False
        }
        
        # Calculate average message length and count questions
        total_length = 0
        question_count = 0
        greeting_patterns = [r'bonjour', r'salut', r'bienvenue', r'comment allez[- ]vous']
        closing_patterns = [r'au revoir', r'bonne journée', r'merci pour', r'prenez soin']
        diagnostic_patterns = [r'diagnostic', r'vous souffrez', r'vous avez', r'il s\'agit']
        treatment_patterns = [r'traitement', r'médicament', r'prescrire', r'ordonnance', r'je vous recommande']
        
        for msg in doctor_messages:
            content = msg['content'].lower()
            total_length += len(content)
            
            # Count questions (simple approach)
            question_count += content.count('?')
            
            # Check for greeting in first message
            if doctor_messages.index(msg) == 0:
                analysis["greeting_detected"] = any(re.search(pattern, content) for pattern in greeting_patterns)
            
            # Check for closing in last message
            if doctor_messages.index(msg) == len(doctor_messages) - 1:
                analysis["closing_detected"] = any(re.search(pattern, content) for pattern in closing_patterns)
            
            # Check for diagnostic keywords in any message
            if not analysis["diagnostic_keywords"]:
                analysis["diagnostic_keywords"] = any(re.search(pattern, content) for pattern in diagnostic_patterns)
            
            # Check for treatment keywords in any message
            if not analysis["treatment_keywords"]:
                analysis["treatment_keywords"] = any(re.search(pattern, content) for pattern in treatment_patterns)
        
        # Calculate average if we have messages
        if doctor_messages:
            analysis["avg_message_length"] = total_length / len(doctor_messages)
        
        analysis["question_count"] = question_count
        
        # Store the analysis in the state
        self.state["conversation_analysis"] = analysis
    
    def _evaluate_with_llm(self):
        """Use LLM to evaluate the conversation against the checklist"""
        logger.info("Evaluating conversation using LLM")
        
        # Get prepared transcript and checklist
        transcript = self.state.get("transcript", "")
        checklist = self.state.get("checklist", [])
        case_data = self.state.get("case_data", {})
        conversation_analysis = self.state.get("conversation_analysis", {})
        
        if not checklist or len(checklist) == 0:
            self.state["results"] = {
                'checklist': [],
                'feedback': "Pas de grille d'évaluation disponible pour ce cas.",
                'points_total': 0,
                'points_earned': 0,
                'percentage': 0
            }
            return
        
        # Prepare additional context if available
        context = ""
        if 'diagnosis' in case_data:
            context += f"Diagnostic correct: {case_data['diagnosis']}\n"
        if 'symptoms' in case_data and len(case_data['symptoms']) > 0:
            # Limit to first 3 symptoms for shorter context
            symptoms_list = case_data['symptoms'][:3]
            context += f"Symptômes principaux: {', '.join(symptoms_list)}\n"
        
        # Add conversation analysis for more context - abbreviated
        analysis_context = f"""
Analyse: {conversation_analysis.get('message_count', 0)} messages, {conversation_analysis.get('question_count', 0)} questions
Salutation: {'Oui' if conversation_analysis.get('greeting_detected', False) else 'Non'}
Conclusion: {'Oui' if conversation_analysis.get('closing_detected', False) else 'Non'}
"""
        
        # Format checklist for prompt - optimize by limiting to key information
        checklist_text = ""
        for i, item in enumerate(checklist, 1):
            points = item.get('points', 1)
            checklist_text += f"{i}. {item['description']} - {points} points\n"
            
            # Limit to 15 items for faster processing
            if i >= 15:
                checklist_text += f"... et {len(checklist) - 15} autres éléments\n"
                break
        
        # Build the evaluation prompt - optimized and shortened
        prompt = f"""Évalue cette consultation médicale OSCE selon la grille fournie.

CONTEXTE:
{context}
{analysis_context}

GRILLE D'ÉVALUATION:
{checklist_text}

TRANSCRIPTION:
{transcript}

INSTRUCTIONS:
Évalue si le médecin a complété chaque élément de la grille.
Réponds au format JSON:
{{
"evaluation": [
    {{
    "description": "...",
    "completed": true/false,
    "justification": "...",
    "points_earned": 0,
    "points_possible": 1
    }},
    ...
],
"feedback": "...",
"points_total": 0,
"points_earned": 0,
"percentage": 0
}}
"""
        
        try:
            # Using a shorter max token limit for faster response
            response = self.llm_client.invoke(
                [HumanMessage(content=prompt)],
                {"max_tokens": 400}  # Limit token output
            )
            
            # Parse JSON response
            import json
            import re
            
            # Extract JSON from the response
            json_match = re.search(r'({.*})', response.content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                try:
                    evaluation_data = json.loads(json_str)
                    
                    # Map LLM evaluation back to checklist format
                    llm_evaluation = evaluation_data.get('evaluation', [])
                    for i, item in enumerate(checklist):
                        if i < len(llm_evaluation):
                            item['completed'] = llm_evaluation[i].get('completed', False)
                            item['justification'] = llm_evaluation[i].get('justification', '')
                        else:
                            item['completed'] = False
                    
                    # Calculate scores if not provided or for verification
                    total_points = sum(item.get('points', 1) for item in checklist)
                    earned_points = sum(item.get('points', 1) for item in checklist if item.get('completed', False))
                    percentage = round((earned_points / total_points) * 100) if total_points > 0 else 0
                    
                    # Store results in state
                    self.state["results"] = {
                        'checklist': checklist,
                        'feedback': evaluation_data.get('feedback', 'Évaluation complétée.'),
                        'points_total': total_points,
                        'points_earned': earned_points,
                        'percentage': percentage
                    }
                    
                except json.JSONDecodeError:
                    logger.error("Failed to parse LLM evaluation response as JSON")
                    self._evaluate_with_patterns()
            else:
                logger.error("No JSON found in LLM evaluation response")
                self._evaluate_with_patterns()
                
        except Exception as e:
            logger.error(f"Error in LLM evaluation: {str(e)}")
            self._evaluate_with_patterns()
    
    def _evaluate_with_patterns(self):
        """Pattern-based evaluation as fallback"""
        logger.info("Evaluating conversation using pattern matching")
        
        # Get conversation and checklist
        conversation = self.state.get("conversation", [])
        checklist = self.state.get("checklist", [])
        
        # Concatenate all the user's messages
        user_text = " ".join([msg['content'] for msg in conversation if msg['role'] == 'human'])
        
        # Simple evaluation logic - check for keywords in the checklist items
        for item in checklist:
            description = item.get('description', '')
            # Extract keywords from description (simplistic approach)
            keywords = [w for w in re.findall(r'\b\w{3,}\b', description.lower()) if len(w) > 3]
            # Mark as completed if any keyword is found in the user text
            if keywords and any(kw in user_text.lower() for kw in keywords):
                item['completed'] = True
                item['justification'] = f"Le médecin a mentionné les mots-clés pertinents dans sa conversation."
            else:
                item['completed'] = False
                item['justification'] = "Cet élément n'a pas été suffisamment abordé dans la conversation."
        
        # Calculate score for feedback
        total_points = sum(item.get('points', 1) for item in checklist)
        earned_points = sum(item.get('points', 1) for item in checklist if item.get('completed', False))
        percentage = round((earned_points / total_points) * 100) if total_points > 0 else 0
        
        # Generate feedback
        if percentage >= 80:
            feedback = "Excellent travail! Vous avez effectué une consultation très complète."
        elif percentage >= 60:
            feedback = "Bon travail. Quelques éléments importants ont été manqués."
        else:
            feedback = "Des éléments importants ont été manqués. Revoyez la grille d'évaluation attentivement."
        
        # Store results in state
        self.state["results"] = {
            'checklist': checklist,
            'feedback': feedback,
            'points_total': total_points,
            'points_earned': earned_points,
            'percentage': percentage
        }
    
    def _generate_feedback(self):
        """Generate comprehensive feedback based on the evaluation results"""
        # If we already have feedback from LLM, we can use it directly
        if 'feedback' in self.state.get("results", {}):
            return
            
        # Otherwise, generate feedback based on the results
        checklist = self.state.get("checklist", [])
        conversation_analysis = self.state.get("conversation_analysis", {})
        
        # Calculate score
        total_points = sum(item.get('points', 1) for item in checklist)
        earned_points = sum(item.get('points', 1) for item in checklist if item.get('completed', False))
        percentage = round((earned_points / total_points) * 100) if total_points > 0 else 0
        
        # Generate simplified feedback for performance
        feedback = ""
        
        # Overall assessment
        if percentage >= 90:
            feedback += "Excellent travail! Votre consultation était très complète et bien structurée. "
        elif percentage >= 75:
            feedback += "Très bon travail. Votre consultation était bien menée dans l'ensemble. "
        elif percentage >= 60:
            feedback += "Bon travail. Votre consultation était satisfaisante mais peut être améliorée. "
        else:
            feedback += "Votre consultation nécessite des améliorations significatives. "
        
        # Add feedback about conversation structure
        if conversation_analysis:
            if not conversation_analysis.get('greeting_detected'):
                feedback += "N'oubliez pas de commencer par une salutation appropriée. "
            if not conversation_analysis.get('closing_detected'):
                feedback += "Pensez à bien conclure votre consultation. "
                
            # Feedback on questions
            question_count = conversation_analysis.get('question_count', 0)
            if question_count < 5:
                feedback += "Posez davantage de questions pour recueillir suffisamment d'informations. "
        
        # Update the results with the generated feedback
        if 'results' not in self.state:
            self.state['results'] = {}
        
        self.state['results'].update({
            'feedback': feedback,
            'points_total': total_points,
            'points_earned': earned_points,
            'percentage': percentage
        })

    def _generate_recommendations(self):
        """Generate smart recommendations for improvement with performance optimization"""
        # Skip LLM calls for shorter conversations
        if (sum(1 for msg in self.state.get("conversation", []) if msg['role'] == 'human') < 3 or
            not self.llm_client):
            self._generate_basic_recommendations()
            return
            
        checklist = self.state.get("checklist", [])
        missed_items = [item for item in checklist if not item.get('completed', False)]
        
        if not missed_items:
            self.state["recommendations"] = ["Excellent travail! Continuez comme ça."]
            return
        
        try:
            # Simplified prompt for better performance AND ensure French recommendations
            missed_descriptions = [item.get('description', '') for item in missed_items[:5]]  # Limit to top 5
            missed_text = ", ".join(missed_descriptions)
            
            recommendations_prompt = f"""Génère 3 conseils concrets et détaillés en français de manière constructive et encourageante pour un étudiant en médecine qui a manqué ces éléments lors d'une consultation OSCE: {missed_text}


    Format: Liste de 3 conseils pratiques uniquement."""
            
            # Set a lower token limit for faster response
            response = self.llm_client.invoke(
                [HumanMessage(content=recommendations_prompt)],
                {"max_tokens": 250}  # Limit token output
            )
            
            # Extract recommendations from response
            recommendations = response.content.strip().split('\n')
            # Clean up formatting
            recommendations = [r.strip().lstrip('•-*0123456789. ') for r in recommendations if r.strip()]
            
            # Store recommendations
            self.state["recommendations"] = recommendations[:3]  # Limit to 3 recommendations
            
        except Exception as e:
            logger.error(f"Error generating smart recommendations: {str(e)}")
            self._generate_basic_recommendations()

    
    def _generate_basic_recommendations(self):
        """Generate basic recommendations as fallback"""
        logger.info("Generating basic recommendations")
        
        checklist = self.state.get("checklist", [])
        missed_items = [item for item in checklist if not item.get('completed', False)]
        
        if not missed_items:
            self.state["recommendations"] = ["Excellent travail! Continuez comme ça."]
            return
        
        # Generate basic recommendations
        recommendations = []
        
        # Group by category
        categories = {}
        for item in missed_items:
            cat = item.get('category', 'Général')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(item)
        
        # Generate one recommendation per category (up to 3 categories)
        for cat, items in list(categories.items())[:3]:
            if cat == "Anamnèse":
                recommendations.append(f"Améliorez votre anamnèse en posant des questions sur {items[0].get('description').lower()}")
            elif cat == "Examen physique":
                recommendations.append(f"N'oubliez pas de mentionner l'examen physique, notamment {items[0].get('description').lower()}")
            elif cat == "Communication":
                recommendations.append(f"Travaillez votre communication: {items[0].get('description')}")
            elif cat == "Diagnostic":
                recommendations.append(f"Soyez plus précis dans votre diagnostic et {items[0].get('description').lower()}")
            else:
                recommendations.append(f"Pour {cat}: n'oubliez pas de {items[0].get('description').lower()}")
        
        self.state["recommendations"] = recommendations[:3]  # Limit to 3 recommendations

    def get_recommendations(self):
        """Get the recommendations generated during evaluation"""
        return self.state.get("recommendations", [])
    
    def get_results(self):
        """Get full evaluation results"""
        return self.state.get("results", {})
        
    def clear_cache(self):
        """Clear the evaluation cache"""
        self._cache = {}
        logger.info("Evaluation cache cleared")