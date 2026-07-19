import os
import json
from procedure_flow import create_procedure_flow

def test_procedure_pack_workflow():
    print("--- Démarrage de la vérification du flux de procédure ---")
    
    # Activer le mode MOCK pour éviter d'appeler l'API réelle lors des tests si nécessaire
    # (ou pour s'assurer que ça tourne hors ligne sans clé)
    os.environ["MOCK_LLM"] = "true"
    
    # 1. Préparation du state partagé initial
    shared = {
        "raw_demand": "Quand une commande arrive, on vérifie puis on la prépare.",
        "brief": None,
        "missing_info": [],
        "clarified": False,
        "procedure": None,
        "verification_result": None,
        "artifacts": None,
        "revision_count": 0,
        "llm_settings": {
            "provider": "ollama",
            "model": "llama3"
        }
    }
    
    # 2. Premier run du flux (Extraction + Détection des informations manquantes)
    print("\n[Run 1] Exécution initiale du flux...")
    flow = create_procedure_flow()
    last_action = flow.run(shared)
    
    print(f"Action de retour finale : {last_action}")
    print(f"Brief extrait : {json.dumps(shared['brief'], ensure_ascii=False, indent=2)}")
    print(f"Questions identifiées : {len(shared['missing_info'])} questions.")
    for q in shared['missing_info']:
        print(f"  - [{q.get('category')}] {q.get('question')} (Bloquant: {q.get('blocking')})")
        
    # Vérification que le flux s'est bien arrêté pour clarification
    assert last_action == "wait_answers", "Le flux aurait dû s'arrêter en attente de réponses (wait_answers)."
    print("✓ Run 1 validé : Le flux s'est arrêté correctement en attente d'interaction.")
    
    # 3. Simulation des réponses utilisateur
    print("\n[Simulation] Saisie des réponses de clarification...")
    answers = {}
    for q in shared['missing_info']:
        q_text = q['question']
        if "canal" in q_text.lower():
            answers[q_text] = "Via l'interface d'administration e-commerce Shopify."
        elif "vérifie" in q_text.lower():
            answers[q_text] = "Le responsable de stock (stock_manager)."
        elif "insuffisant" in q_text.lower():
            answers[q_text] = "Suspendre la commande et envoyer un e-mail au client."
        else:
            answers[q_text] = "Information par défaut."
            
    shared["clarification_answers"] = answers
    
    # 4. Deuxième run du flux (Fusion + Génération + Vérification + Export)
    print("\n[Run 2] Reprise de l'exécution avec les réponses...")
    last_action_2 = flow.run(shared)
    
    print(f"Action de retour finale (Run 2) : {last_action_2}")
    print(f"Procédure générée : {shared['procedure'].get('title')} v{shared['procedure'].get('version')}")
    print(f"Étapes générées : {len(shared['procedure'].get('steps', []))}")
    print(f"Rapport de validation : Verdict = {shared['verification_result'].get('verdict')}, Score = {shared['verification_result'].get('completeness_score')}%")
    
    # Vérification que la procédure et les exports sont complets
    assert shared['procedure'] is not None, "La procédure n'a pas été générée."
    assert shared['artifacts'] is not None, "Les livrables d'export (artifacts) sont absents."
    assert last_action_2 == "done", "Le flux aurait dû se terminer avec l'action 'done'."
    
    # Vérification de la création des exports
    artifacts = shared['artifacts']
    print("\n[Vérification des fichiers de sortie] :")
    print(f"Taille de la procédure détaillée : {len(artifacts.get('detailed_procedure', ''))} caractères.")
    print(f"Taille de la checklist : {len(artifacts.get('checklist', ''))} caractères.")
    print(f"Taille du diagramme Mermaid : {len(artifacts.get('diagram', ''))} lignes.")
    
    print("\n✓ Run 2 validé : Flux complété avec succès de bout en bout.")
    print("--- Vérification du flux de procédure terminée avec succès ! ---")

if __name__ == "__main__":
    test_procedure_pack_workflow()
