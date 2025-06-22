# test_enhanced_evaluation.py
# Example script to test the enhanced evaluation system

from enhanced_evaluation_agent import EnhancedEvaluationAgent
from langchain_groq import ChatGroq
import json

def test_enhanced_evaluation():
    """Test the enhanced evaluation system with sample data"""
    
    # Initialize the LLM client (replace with your actual API key)
    client = ChatGroq(
        api_key="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",
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        temperature=0.1,
        max_tokens=150
    )
    
    # Initialize the enhanced evaluation agent
    evaluator = EnhancedEvaluationAgent(llm_client=client)
    
    # Sample conversation (doctor-patient interaction)
    sample_conversation = [
        {"role": "system", "content": "Simulation OSCE - Cas de douleur thoracique"},
        {"role": "human", "content": "Bonjour Monsieur, je suis le Dr Martin. Comment puis-je vous aider aujourd'hui?"},
        {"role": "assistant", "content": "Bonjour docteur, j'ai des douleurs dans la poitrine depuis ce matin."},
        {"role": "human", "content": "Je comprends votre inquiétude. Pouvez-vous me décrire cette douleur? Où exactement la ressentez-vous?"},
        {"role": "assistant", "content": "C'est une douleur qui serre, ici au centre de la poitrine. Ça fait comme une étau."},
        {"role": "human", "content": "D'accord. Cette douleur irradie-t-elle quelque part? Dans le bras, le cou ou la mâchoire?"},
        {"role": "assistant", "content": "Oui, ça descend dans mon bras gauche parfois."},
        {"role": "human", "content": "Avez-vous des antécédents cardiaques dans votre famille? Votre père ou votre mère ont-ils eu des problèmes de cœur?"},
        {"role": "assistant", "content": "Mon père a fait un infarctus à 55 ans."},
        {"role": "human", "content": "Je vais maintenant procéder à un examen physique. Je vais d'abord prendre votre tension artérielle et écouter votre cœur."},
        {"role": "assistant", "content": "D'accord docteur."},
        {"role": "human", "content": "D'après vos symptômes et vos antécédents familiaux, je pense à un problème cardiaque. Il faudrait faire un électrocardiogramme rapidement."},
        {"role": "assistant", "content": "C'est grave docteur?"},
        {"role": "human", "content": "Ne vous inquiétez pas, nous allons prendre soin de vous. Je vais demander des examens complémentaires pour confirmer le diagnostic."}
    ]
    
    # Sample case data with evaluation checklist
    sample_case_data = {
        "case_number": "CARD001",
        "specialty": "Cardiologie",
        "diagnosis": "Syndrome coronarien aigu",
        "evaluation_checklist": [
            {
                "description": "Salue le patient et se présente professionnellement",
                "category": "Communication",
                "points": 2
            },
            {
                "description": "Pose des questions ouvertes sur la douleur thoracique",
                "category": "Anamnèse",
                "points": 3
            },
            {
                "description": "Explore les caractéristiques de la douleur (localisation, irradiation)",
                "category": "Anamnèse",
                "points": 3
            },
            {
                "description": "Recherche les antécédents familiaux cardiovasculaires",
                "category": "Anamnèse",
                "points": 2
            },
            {
                "description": "Mentionne l'examen cardiovasculaire (tension, auscultation)",
                "category": "Examen physique",
                "points": 3
            },
            {
                "description": "Évoque un diagnostic cardiaque cohérent",
                "category": "Diagnostic",
                "points": 4
            },
            {
                "description": "Propose des examens complémentaires appropriés",
                "category": "Traitement",
                "points": 3
            },
            {
                "description": "Rassure le patient et explique la démarche",
                "category": "Communication",
                "points": 2
            }
        ]
    }
    
    print("🔍 Testing Enhanced Evaluation System...")
    print("=" * 50)
    
    # Run the evaluation
    try:
        results = evaluator.evaluate_conversation(sample_conversation, sample_case_data)
        
        print(f"📊 RÉSULTATS D'ÉVALUATION")
        print(f"Score: {results['points_earned']}/{results['points_total']} ({results['percentage']}%)")
        print(f"Feedback: {results.get('feedback', 'Pas de feedback')}")
        print()
        
        print("📋 DÉTAIL PAR CRITÈRE:")
        for item in results['checklist']:
            status = "✅" if item['completed'] else "❌"
            print(f"{status} {item['description']} ({item.get('points', 1)} pts)")
            if item.get('justification'):
                print(f"   💭 {item['justification']}")
        print()
        
        # Get recommendations
        recommendations = evaluator.get_recommendations()
        if recommendations:
            print("💡 RECOMMANDATIONS:")
            for i, rec in enumerate(recommendations, 1):
                print(f"{i}. {rec}")
        
        print("=" * 50)
        print("✅ Test completed successfully!")
        
        return results
        
    except Exception as e:
        print(f"❌ Error during evaluation: {str(e)}")
        return None

def compare_with_old_system():
    """Compare results between enhanced and pattern-based evaluation"""
    print("\n🔄 COMPARISON TEST: Enhanced vs Pattern-based")
    print("=" * 50)
    
    # This would compare the new system with the old one
    # You can implement this to see the improvement in accuracy
    pass

def test_different_categories():
    """Test evaluation with different category types"""
    print("\n🎯 CATEGORY-SPECIFIC TESTS")
    print("=" * 50)
    
    # Test conversations focused on different categories
    categories_to_test = [
        'Communication',
        'Anamnèse', 
        'Examen physique',
        'Diagnostic',
        'Traitement'
    ]
    
    for category in categories_to_test:
        print(f"Testing {category} category...")
        # You can create specific test cases for each category
    
if __name__ == "__main__":
    # Run the basic test
    test_enhanced_evaluation()
    
    # Optional: run additional tests
    # compare_with_old_system()
    # test_different_categories()

# Usage in your ECOS application:
