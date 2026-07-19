import os
import json
import requests
import google.generativeai as genai

def call_llm(prompt: str, system_instruction: str = None, response_mime_type: str = None, provider: str = "gemini", model: str = None, api_key: str = None) -> str:
    # 1. Support mock calls for local sandboxed runs or offline validation
    if os.getenv("MOCK_LLM") == "true":
        print(f"[MOCK LLM] Calling {provider}/{model} with system_instruction: {system_instruction[:100] if system_instruction else 'None'}...")
        
        # Check if the process is about leave requests or vacancies
        is_leave = False
        is_sav = False
        if prompt and any(k in prompt.lower() for k in ["congé", "leave", "absence", "vacance"]):
            is_leave = True
        elif prompt and any(k in prompt.lower() for k in ["sav", "remplacement", "panne", "matériel", "rma"]):
            is_sav = True
            
        if system_instruction and any(k in system_instruction.lower() for k in ["congé", "leave", "absence", "vacance"]):
            is_leave = True
        elif system_instruction and any(k in system_instruction.lower() for k in ["sav", "remplacement", "panne", "matériel", "rma"]):
            is_sav = True

        # Extract dynamic topic keyword for custom processes in mock mode
        topic = "processus"
        search_text = (prompt or "") + " " + (system_instruction or "")
        search_text = search_text.lower()
        import re
        words = re.findall(r'[a-zA-Zéèàùçâêîôûëïü\-]+', search_text)
        stop_words = {
            "comment", "pourquoi", "quand", "chaque", "gestion", "processus", "etape", "etapes",
            "valider", "verifier", "concepteur", "expert", "analyste", "propose", "reponses", "logiques", "questions",
            "clarification", "brute", "demande", "standard", "pratiques", "operationnelles", "uniquement", "valide",
            "business", "analyste", "fusionne", "expert", "brief", "clarifie", "conception", "generer", "proceder",
            "procedure", "checklist", "logigramme", "mermaid", "conflit", "recrutement", "livraison", "expedition",
            "commande", "commandes", "client", "clients", "conge", "conges", "absences", "vacances", "panne", "pannes",
            "materiel", "remplacement", "retour", "garantie", "soumission", "enregistre", "disponibilite", "produits"
        }
        for w in words:
            if len(w) > 4 and w not in stop_words:
                topic = w
                break

        if system_instruction and "concepteur de processus" in system_instruction.lower():
            # Extract precisions from prompt if present
            user_precisions = []
            if "user_answers" in prompt or "Précision" in prompt or "Réponses" in prompt:
                import re
                matches = re.findall(r':\s*"([^"]+)"', prompt)
                user_precisions = [m for m in matches if len(m) > 2 and not m.startswith("step_")]

            base_instructions = [f"Ouvrir la fiche de {topic}.", f"Vérifier les données de la demande de {topic}."]
            if user_precisions:
                for p in user_precisions:
                    base_instructions.append(f"Précision utilisateur appliquée : {p}")

            if is_leave:
                return json.dumps({
                    "id": "leave_request",
                    "title": "Demande de Congés Annuels",
                    "version": "1.0.0",
                    "status": "draft",
                    "purpose": "Permettre aux collaborateurs de soumettre et faire valider leurs demandes de congés.",
                    "trigger": {"description": "L'employé soumet une demande sur le portail RH au moins 2 semaines à l'avance."},
                    "scope": {"included": ["Vérification des soldes", "Validation managériale", "Mise à jour du calendrier"], "excluded": ["Ajustement de la paie"]},
                    "actors": ["employé", "manager", "rh"],
                    "tools": ["portail RH", "Outlook Calendar"],
                    "steps": [
                        {
                            "id": "step_001",
                            "title": "Soumettre la demande",
                            "actor": "employé",
                            "instructions": base_instructions,
                            "output": "demande_soumise",
                            "transitions": "step_002"
                        },
                        {
                            "id": "step_002",
                            "title": "Vérifier le solde",
                            "actor": "rh",
                            "instructions": ["Vérifier le solde automatique sur le portail."],
                            "output": "solde_valide",
                            "transitions": {
                                "suffisant": "step_003",
                                "insuffisant": "step_004"
                            }
                        }
                    ],
                    "checklist": ["Demande déposée à temps", "Solde vérifié", "Approbation manager obtenue"],
                    "risks": [
                        {"description": "Absence simultanée de rôles clés", "control": "Vérification des calendriers d'équipe avant approbation"}
                    ]
                }, ensure_ascii=False)
            elif is_sav:
                return json.dumps({
                    "id": "sav_replacement",
                    "title": "Gestion du SAV & Remplacement Matériel",
                    "version": "1.0.0",
                    "status": "draft",
                    "purpose": "Traiter et valider les pannes matérielles pour l'envoi de remplacements sous garantie.",
                    "trigger": {"description": "Déclaration d'un incident matériel par le client sur le portail de support."},
                    "scope": {"included": ["Diagnostic à distance", "Gestion logistique du retour RMA", "Expédition du remplacement"], "excluded": ["Réparations payantes hors garantie"]},
                    "actors": ["agent_support_n1", "technicien_n2", "operateur_entrepot", "client"],
                    "tools": ["CRM Support", "Portail Expéditions", "Système Inventaire"],
                    "steps": [
                        {
                            "id": "step_001",
                            "title": "Vérifier la garantie dans le CRM",
                            "actor": "agent_support_n1",
                            "instructions": base_instructions,
                            "output": "statut_garantie",
                            "transitions": {
                                "valide": "step_002",
                                "invalide": "step_003"
                            }
                        },
                        {
                            "id": "step_002",
                            "title": "Effectuer le diagnostic technique",
                            "actor": "technicien_n2",
                            "instructions": ["Prendre contact avec le client.", "Exécuter les scripts de test à distance."],
                            "output": "verdict_diagnostic",
                            "transitions": {
                                "panne_materielle": "step_004",
                                "resolu_logiciel": "step_005"
                            }
                        }
                    ],
                    "checklist": ["Garantie CRM validée", "Diagnostic complété", "Bon RMA généré", "Inspection physique validée", "Remplacement livré"],
                    "risks": [
                        {"description": "Expédition sans réception du retour défectueux", "control": "Bloquer l'envoi dans le système d'inventaire tant que le RMA n'est pas scanné."}
                    ]
                }, ensure_ascii=False)
            else:
                # Dynamic Custom Process pack
                return json.dumps({
                    "id": f"{topic}_process",
                    "title": f"Gestion de : {topic.capitalize()}",
                    "version": "1.0.0",
                    "status": "draft",
                    "purpose": f"Assurer la bonne exécution et le contrôle qualité de : {topic}.",
                    "trigger": {"description": f"Déclenchement d'un événement ou demande concernant {topic}."},
                    "scope": {"included": [f"Vérification initiale de {topic}", f"Exécution des étapes de {topic}"], "excluded": ["Audit externe tiers"]},
                    "actors": ["gestionnaire_dossier", "superviseur"],
                    "tools": ["système d'information interne"],
                    "steps": [
                        {
                            "id": "step_001",
                            "title": f"Initier le dossier de {topic}",
                            "actor": "gestionnaire_dossier",
                            "instructions": base_instructions,
                            "output": f"{topic}_initialise",
                            "transitions": "step_002"
                        },
                        {
                            "id": "step_002",
                            "title": f"Valider la conformité de {topic}",
                            "actor": "superviseur",
                            "instructions": [f"Vérifier les critères opérationnels de {topic}."],
                            "output": f"{topic}_valide",
                            "transitions": {
                                "conforme": "step_003",
                                "refuse": "step_004"
                            }
                        }
                    ],
                    "checklist": [f"Fiche de {topic} créée", f"Conformité {topic} validée", "Notification finale transmise"],
                    "risks": [
                        {"description": f"Erreur de saisie dans {topic}", "control": "Vérification automatisée des champs obligatoires."}
                    ]
                }, ensure_ascii=False)
        elif system_instruction and "analyste de processus" in system_instruction.lower():
            if is_leave:
                return json.dumps({
                    "questions": [
                        {"question": "Sous quel délai le collaborateur doit-il poser sa demande ?", "category": "trigger", "blocking": True},
                        {"question": "Qui valide en cas d'absence du manager direct ?", "category": "actor", "blocking": True},
                        {"question": "Comment le solde est-il vérifié (automatique ou manuel) ?", "category": "tools", "blocking": True}
                    ]
                }, ensure_ascii=False)
            elif is_sav:
                return json.dumps({
                    "questions": [
                        {"question": "Quel est le délai maximum pour que le client renvoie son produit après réception du RMA ?", "category": "scope", "blocking": True},
                        {"question": "Quelle action mener si le produit de remplacement est en rupture de stock ?", "category": "exception", "blocking": True},
                        {"question": "Quel document de contrôle est exigé pour valider l'inspection du matériel à l'entrepôt ?", "category": "evidence_critical", "blocking": True}
                    ]
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "questions": [
                        {"question": f"Par quel canal ou outil le processus de {topic} commence-t-il ?", "category": "trigger", "blocking": True},
                        {"question": f"Qui est l'acteur ou responsable chargé d'exécuter la tâche de {topic} ?", "category": "actor", "blocking": True},
                        {"question": f"Quelle action corrective mener en cas d'erreur ou d'exception de {topic} ?", "category": "exception", "blocking": True}
                    ]
                }, ensure_ascii=False)
        elif system_instruction and "propose des réponses logiques" in system_instruction.lower():
            if is_leave:
                return json.dumps({
                    "Sous quel délai le collaborateur doit-il poser sa demande ?": "Au moins 2 semaines avant la date de début souhaitée.",
                    "Qui valide en cas d'absence du manager direct ?": "Le n+2 (directeur de département) ou le service RH.",
                    "Comment le solde est-il vérifié (automatique ou manuel) ?": "Automatiquement via le portail RH."
                }, ensure_ascii=False)
            elif is_sav:
                return json.dumps({
                    "Quel est le délai maximum pour que le client renvoie son produit après réception du RMA ?": "Le client dispose de 30 jours calendaires.",
                    "Quelle action mener si le produit de remplacement est en rupture de stock ?": "Proposer un modèle équivalent ou supérieur, ou émettre un remboursement.",
                    "Quel document de contrôle est exigé pour valider l'inspection du matériel à l'entrepôt ?": "Une fiche d'inspection technique signée et sauvegardée dans le CRM."
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    f"Par quel canal ou outil le processus de {topic} commence-t-il ?": f"Via le portail interne ou un formulaire dédié pour {topic}.",
                    f"Qui est l'acteur ou responsable chargé d'exécuter la tâche de {topic} ?": f"Le superviseur opérationnel en charge de {topic}.",
                    f"Quelle action corrective mener en cas d'erreur ou d'exception de {topic} ?": f"Mettre en attente et envoyer une notification au gestionnaire de {topic}."
                }, ensure_ascii=False)
        elif system_instruction and "business analyst expert" in system_instruction.lower():
            if is_leave:
                return json.dumps({
                    "title": "Demande de Congés Annuels",
                    "purpose": "Gérer et valider les demandes d'absence.",
                    "trigger": "Soumission d'une demande de congés.",
                    "expected_result": "Demande validée ou refusée.",
                    "scope": {"included": ["Validation manager", "Mise à jour planning"], "excluded": ["Ajustement de la paie"]},
                    "actors": ["employé", "manager", "rh"],
                    "tools": ["portail RH"],
                    "known_steps": ["Soumettre la demande", "Vérifier le solde"],
                    "decisions": ["Le manager valide-t-il la demande ?"],
                    "exceptions": ["Refus du manager", "Solde insuffisant"]
                }, ensure_ascii=False)
            elif is_sav:
                return json.dumps({
                    "title": "Gestion du SAV & Remplacement Matériel",
                    "purpose": "Traiter les pannes matérielles sous garantie, de la déclaration à l'expédition du produit de remplacement.",
                    "trigger": "Déclaration d'incident matériel par le client.",
                    "expected_result": "Client dépanné ou produit de remplacement livré, et ticket clôturé.",
                    "scope": {"included": ["Diagnostic à distance", "Gestion logistique du retour", "Expédition du remplacement"], "excluded": ["Réparation en atelier physique hors garantie"]},
                    "actors": ["agent_support_n1", "technicien_n2", "operateur_entrepot", "client"],
                    "tools": ["CRM Support", "Portail Expéditions", "Système Inventaire"],
                    "known_steps": ["Vérifier garantie", "Effectuer diagnostic", "Générer bon RMA", "Inspecter retour", "Expédier remplacement", "Clôturer ticket"],
                    "decisions": ["Garantie valide ?", "Résolu par logiciel ?", "Retour conforme ?"],
                    "exceptions": ["Garantie invalide", "Mauvaise utilisation détectée", "Rupture de stock remplacement"]
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "title": f"Gestion de : {topic.capitalize()}",
                    "purpose": f"Gérer efficacement la tâche de {topic}.",
                    "trigger": f"Détection du besoin de {topic}.",
                    "expected_result": f"Processus de {topic} clôturé et validé.",
                    "scope": {"included": [f"Vérification de {topic}", f"Enregistrement de {topic}"], "excluded": ["Intervention technique externe"]},
                    "actors": ["gestionnaire", "superviseur"],
                    "tools": ["système d'information"],
                    "known_steps": [f"Initier {topic}", f"Vérifier conformité {topic}"],
                    "decisions": [f"{topic.capitalize()} est-il valide ?"],
                    "exceptions": [f"Rejet ou non-conformité de {topic}"]
                }, ensure_ascii=False)
        elif system_instruction and "fusionne le brief" in system_instruction.lower():
            user_details = []
            if "Réponses apportées :" in prompt:
                answers_part = prompt.split("Réponses apportées :")[-1]
                import re
                vals = re.findall(r':\s*"([^"]+)"', answers_part)
                user_details = [v for v in vals if len(v) > 1]
                
            if is_leave:
                steps = ["Soumettre la demande", "Vérifier le solde"]
                if user_details:
                    steps.extend([f"Précision apportée : {ans}" for ans in user_details])
                return json.dumps({
                    "title": "Demande de Congés Annuels (Clarifié)",
                    "purpose": "Gérer et valider les demandes d'absence.",
                    "trigger": "Soumission d'une demande sur le portail RH avec 2 semaines de préavis.",
                    "expected_result": "Demande validée ou refusée.",
                    "scope": {"included": ["Validation manager", "Mise à jour planning"], "excluded": ["Ajustement de la paie"]},
                    "actors": ["employé", "manager", "rh"],
                    "tools": ["portail RH"],
                    "known_steps": steps,
                    "decisions": ["Le manager valide-t-il la demande ?"],
                    "exceptions": ["Refus du manager", "Solde insuffisant"]
                }, ensure_ascii=False)
            elif is_sav:
                steps = ["Vérifier garantie", "Effectuer diagnostic", "Générer bon RMA"]
                if user_details:
                    steps.extend([f"Précision apportée : {ans}" for ans in user_details])
                return json.dumps({
                    "title": "Gestion du SAV & Remplacement Matériel (Clarifié)",
                    "purpose": "Traiter les pannes matérielles sous garantie.",
                    "trigger": "Déclaration d'incident avec un délai RMA de 30 jours calendaires.",
                    "expected_result": "Remplacement conforme expédié, et ticket clôturé.",
                    "scope": {"included": ["Diagnostic à distance", "Gestion logistique du retour", "Expédition du remplacement"], "excluded": ["Réparation en atelier physique hors garantie"]},
                    "actors": ["agent_support_n1", "technicien_n2", "operateur_entrepot", "client"],
                    "tools": ["CRM Support", "Portail Expéditions", "Système Inventaire"],
                    "known_steps": steps,
                    "decisions": ["Garantie valide ?", "Résolu par logiciel ?", "Retour conforme ?"],
                    "exceptions": ["Garantie invalide", "Mauvaise utilisation détectée", "Rupture de stock remplacement"]
                }, ensure_ascii=False)
            else:
                steps = [f"Initier {topic}", f"Vérifier conformité {topic}"]
                if user_details:
                    steps.extend([f"Précision : {ans}" for ans in user_details])
                return json.dumps({
                    "title": f"Gestion de : {topic.capitalize()} (Clarifié avec précisions)",
                    "purpose": f"Gérer efficacement la tâche de {topic}.",
                    "trigger": f"Détection du besoin de {topic} (processus validé).",
                    "expected_result": f"Processus de {topic} clôturé et validé.",
                    "scope": {"included": [f"Vérification de {topic}", f"Enregistrement de {topic}"], "excluded": ["Intervention technique externe"]},
                    "actors": ["gestionnaire", "superviseur"],
                    "tools": ["système d'information"],
                    "known_steps": steps,
                    "decisions": [f"{topic.capitalize()} est-il valide ?"],
                    "exceptions": [f"Rejet ou non-conformité de {topic}"]
                }, ensure_ascii=False)
        else:
            return json.dumps({"status": "ok"}, ensure_ascii=False)

    provider = (provider or "gemini").lower()
    
    # 2. Branching on Providers
    if provider == "ollama":
        model_name = model
        
        # Query Ollama to get installed models
        url_tags = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/tags"
        available_models = []
        try:
            r_tags = requests.get(url_tags, timeout=2)
            if r_tags.status_code == 200:
                available_models = [m.get("name") for m in r_tags.json().get("models", [])]
        except Exception:
            pass

        # Match model to available models, fallback to gpt-oss or first available if invalid
        if available_models:
            if not model_name or model_name not in available_models:
                # Prioritize installed models
                prioritized = ["gpt-oss:20b-cloud", "gpt-oss:120b-cloud", "qwen3-coder:480b-cloud", "deepseek-v3.1:671b-cloud"]
                found_model = None
                for prio in prioritized:
                    if prio in available_models:
                        found_model = prio
                        break
                model_name = found_model or available_models[0]
        else:
            if not model_name:
                model_name = "llama3"

        url = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/chat"
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.0}
        }
        if response_mime_type == "application/json":
            payload["format"] = "json"
            
        print(f"[Ollama] Calling model '{model_name}' at {url}...")
        try:
            r = requests.post(url, json=payload, timeout=3)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except Exception as e:
            print(f"[Ollama Error] {e}. Basculement automatique en mode MOCK.")
            old_mock = os.environ.get("MOCK_LLM")
            os.environ["MOCK_LLM"] = "true"
            try:
                return call_llm(prompt, system_instruction, response_mime_type, provider, model, api_key)
            finally:
                if old_mock is not None:
                    os.environ["MOCK_LLM"] = old_mock
                else:
                    os.environ.pop("MOCK_LLM", None)
            
    elif provider == "deepseek":
        model_name = model or "deepseek-chat"
        url = "https://api.deepseek.com/v1/chat/completions"
        
        # Resolve key
        ds_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not ds_key:
            for p in [".env.local", "../.env.local", "../../.env.local"]:
                if os.path.exists(p):
                    with open(p) as f:
                        for line in f:
                            if "=" in line and not line.startswith("#"):
                                k, v = line.split("=", 1)
                                if k.strip() == "DEEPSEEK_API_KEY":
                                    ds_key = v.strip().strip('"').strip("'")
                                    break
                if ds_key:
                    break
        if not ds_key:
            print("[DeepSeek Error] Key missing. Basculement automatique en mode MOCK.")
            old_mock = os.environ.get("MOCK_LLM")
            os.environ["MOCK_LLM"] = "true"
            try:
                return call_llm(prompt, system_instruction, response_mime_type, provider, model, api_key)
            finally:
                if old_mock is not None:
                    os.environ["MOCK_LLM"] = old_mock
                else:
                    os.environ.pop("MOCK_LLM", None)
            
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {ds_key}"
        }
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.0
        }
        if response_mime_type == "application/json":
            payload["response_format"] = {"type": "json_object"}
            
        print(f"[DeepSeek] Calling model '{model_name}'...")
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=5)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[DeepSeek Error] {e}. Basculement automatique en mode MOCK.")
            old_mock = os.environ.get("MOCK_LLM")
            os.environ["MOCK_LLM"] = "true"
            try:
                return call_llm(prompt, system_instruction, response_mime_type, provider, model, api_key)
            finally:
                if old_mock is not None:
                    os.environ["MOCK_LLM"] = old_mock
                else:
                    os.environ.pop("MOCK_LLM", None)
            
    else:  # default: gemini
        model_name = model or "gemini-1.5-flash"
        
        gemini_key = api_key or os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            for p in [".env.local", "../.env.local", "../../.env.local"]:
                if os.path.exists(p):
                    with open(p) as f:
                        for line in f:
                            if "=" in line and not line.startswith("#"):
                                k, v = line.split("=", 1)
                                if k.strip() == "GEMINI_API_KEY":
                                    gemini_key = v.strip().strip('"').strip("'")
                                    break
                if gemini_key:
                    break
                    
        if not gemini_key:
            print("[Gemini] API key not found. Basculement automatique en mode MOCK.")
            old_mock = os.environ.get("MOCK_LLM")
            os.environ["MOCK_LLM"] = "true"
            try:
                return call_llm(prompt, system_instruction, response_mime_type, provider, model, api_key)
            finally:
                if old_mock is not None:
                    os.environ["MOCK_LLM"] = old_mock
                else:
                    os.environ.pop("MOCK_LLM", None)
            
        try:
            genai.configure(api_key=gemini_key)
            
            print(f"[Gemini] Calling model '{model_name}'...")
            model_obj = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_instruction
            )
            
            config = {}
            if response_mime_type:
                config["response_mime_type"] = response_mime_type
                
            response = model_obj.generate_content(prompt, generation_config=config)
            return response.text
        except Exception as e:
            print(f"[Gemini Error] {e}. Basculement automatique en mode MOCK.")
            old_mock = os.environ.get("MOCK_LLM")
            os.environ["MOCK_LLM"] = "true"
            try:
                return call_llm(prompt, system_instruction, response_mime_type, provider, model, api_key)
            finally:
                if old_mock is not None:
                    os.environ["MOCK_LLM"] = old_mock
                else:
                    os.environ.pop("MOCK_LLM", None)

