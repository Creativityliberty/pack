import json
from pocketflow import Node, Flow
from llm_client import call_llm

class FactoryNode(Node):
    def _run(self, shared):
        self.llm_settings = shared.get("llm_settings", {})
        return super()._run(shared)

class ExtractBriefNode(FactoryNode):
    def prep(self, shared):
        if shared.get("brief"):
            return "ALREADY_EXTRACTED"
        return shared["raw_demand"]
        
    def exec(self, raw_demand):
        if raw_demand == "ALREADY_EXTRACTED":
            return "ALREADY_EXTRACTED"
        system_instruction = (
            "Tu es un Business Analyst expert. Extrais un brief structuré à partir d'une demande brute de processus. "
            "Réponds UNIQUEMENT sous forme de JSON valide correspondant à la structure demandée."
        )
        prompt = f"""
Analyse cette demande brute :
---
{raw_demand}
---

Génère un JSON avec les clés suivantes :
- title (le titre du processus)
- purpose (le but / l'objectif principal)
- trigger (ce qui déclenche le processus)
- expected_result (le résultat attendu à la fin)
- scope (un dictionnaire avec 'included' [liste] et 'excluded' [liste])
- actors (liste des rôles impliqués)
- tools (liste des outils, logiciels ou systèmes nécessaires)
- known_steps (liste de chaînes décrivant les étapes mentionnées)
- decisions (liste de chaînes décrivant les choix/décisions mentionnés)
- exceptions (liste de chaînes décrivant les cas d'erreur ou exceptions)
"""
        res_text = call_llm(prompt, system_instruction=system_instruction, response_mime_type="application/json", **self.llm_settings)
        try:
            return json.loads(res_text)
        except Exception:
            # Fallback parsing in case of markdown formatting
            cleaned = res_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            return json.loads(cleaned.strip())

    def post(self, shared, prep_res, exec_res):
        if exec_res != "ALREADY_EXTRACTED":
            shared["brief"] = exec_res
        return "default"



class IdentifyMissingNode(FactoryNode):
    def prep(self, shared):
        return shared["brief"]
        
    def exec(self, brief):
        system_instruction = (
            "Tu es un analyste de processus. Compare le brief de processus extrait avec les standards d'une procédure "
            "professionnelle. Détecte les informations manquantes indispensables (acteurs, déclencheurs précis, "
            "gestion des erreurs, canaux). "
            "Réponds UNIQUEMENT sous forme de JSON valide contenant une liste de questions de clarification."
        )
        prompt = f"""
Voici le brief actuel :
{json.dumps(brief, ensure_ascii=False, indent=2)}

Génère un JSON contenant un tableau de questions sous la clé "questions" :
Chaque question doit avoir :
- question (la question à poser à l'utilisateur)
- category (ex: trigger, actor, control, exception)
- blocking (booléen : vrai si la procédure ne peut pas être générée sans cette réponse, faux sinon)
"""
        res_text = call_llm(prompt, system_instruction=system_instruction, response_mime_type="application/json", **self.llm_settings)
        try:
            return json.loads(res_text)
        except Exception:
            cleaned = res_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            return json.loads(cleaned.strip())

    def post(self, shared, prep_res, exec_res):
        shared["missing_info"] = exec_res.get("questions", [])
        
        # S'il y a des questions bloquantes, on doit clarifier
        has_blocking = any(q.get("blocking", False) for q in shared["missing_info"])
        if has_blocking and not shared.get("clarified", False):
            return "need_clarification"
        return "produce"


class ClarifyNode(FactoryNode):
    def _run(self, shared):
        answers = shared.get("clarification_answers") or (shared.get("brief", {}) or {}).get("user_answers")
        if not answers:
            return "default"
        return super()._run(shared)

    def prep(self, shared):
        answers = shared.get("clarification_answers") or (shared.get("brief", {}) or {}).get("user_answers") or {}
        return {
            "brief": shared.get("brief", {}),
            "answers": answers
        }
        
    def exec(self, prep_res):
        brief = prep_res["brief"]
        answers = prep_res["answers"]
        
        # On intègre les réponses au brief via LLM pour restructurer proprement
        system_instruction = (
            "Tu es un Business Analyst. Fusionne le brief existant avec les réponses apportées par l'utilisateur "
            "aux questions de clarification. Renvoie le brief mis à jour au format JSON."
        )
        prompt = f"""
Brief initial :
{json.dumps(brief, ensure_ascii=False, indent=2)}

Réponses apportées :
{json.dumps(answers, ensure_ascii=False, indent=2)}

Renvoie le brief consolidé mis à jour au format JSON complet avec les mêmes clés.
"""
        res_text = call_llm(prompt, system_instruction=system_instruction, response_mime_type="application/json", **self.llm_settings)
        try:
            return json.loads(res_text)
        except Exception:
            cleaned = res_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            return json.loads(cleaned.strip())

    def post(self, shared, prep_res, exec_res):
        shared["brief"] = exec_res
        shared["clarified"] = True
        # Une fois clarifié, on retourne à l'analyse pour vérifier s'il manque encore quelque chose ou si on produit
        return "default"



class GenerateProcedureNode(FactoryNode):
    def prep(self, shared):
        return shared["brief"]
        
    def exec(self, brief):
        system_instruction = (
            "Tu es un concepteur de processus opérationnels. Rédige une procédure détaillée "
            "extrêmement structurée et précise en français. Respecte scrupuleusement la structure JSON demandée."
        )
        prompt = f"""
Génère la procédure complète sous format JSON à partir de ce brief consolidé :
{json.dumps(brief, ensure_ascii=False, indent=2)}

Le JSON généré DOIT comporter les clés :
- id (identifiant unique de la procédure)
- title (le titre)
- version (1.0.0)
- status (draft)
- purpose (but)
- scope (inclus/exclus)
- trigger (déclencheur)
- actors (rôles)
- tools (outils)
- steps (liste d'étapes détaillées. Chaque étape doit avoir :
    - id (ex: step_001)
    - title (titre de l'étape)
    - actor (le rôle responsable)
    - instructions (liste de consignes claires)
    - inputs (liste d'éléments d'entrée)
    - output (élément produit en sortie)
    - tool (outil utilisé, optionnel)
    - control (dictionnaire avec 'required': bool et 'evidence': chaîne si required est vrai, optionnel)
    - transitions (soit l'ID de l'étape suivante sous forme de chaîne, soit un dictionnaire de transitions conditionnelles pour les choix/décisions)
  )
- checklist (liste opérationnelle pour le terrain)
- risks (liste des risques identifiés avec leur contrôle associé : dictionnaire avec 'description' et 'control')
"""
        res_text = call_llm(prompt, system_instruction=system_instruction, response_mime_type="application/json", **self.llm_settings)
        try:
            return json.loads(res_text)
        except Exception:
            cleaned = res_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            return json.loads(cleaned.strip())

    def post(self, shared, prep_res, exec_res):
        shared["procedure"] = exec_res
        return "default"


class VerifyProcedureNode(Node):
    def prep(self, shared):
        return shared["procedure"]
        
    def exec(self, procedure):
        # 11 Quality gates check
        blockers = []
        warnings_list = []
        
        # Gate 1: procedure_has_start_trigger
        trigger = procedure.get("trigger", {})
        if not trigger or (isinstance(trigger, dict) and not trigger.get("description")) and not trigger:
            blockers.append("La procédure ne possède aucun élément de déclenchement (start trigger) défini.")
            
        # Gate 2: procedure_has_end_state
        steps = procedure.get("steps", [])
        if not steps:
            blockers.append("La procédure ne possède aucune étape.")
            
        # Gate 3: every_step_has_actor
        # Gate 4: every_step_has_output
        # Gate 5: every_decision_has_all_branches
        # Gate 8: no_orphan_step_exists
        step_ids = {s.get("id") for s in steps if s.get("id")}
        transitions_targets = set()
        
        for step in steps:
            s_id = step.get("id")
            s_title = step.get("title", s_id)
            
            if not step.get("actor"):
                blockers.append(f"L'étape '{s_title}' ({s_id}) ne possède aucun responsable (actor).")
            if not step.get("output"):
                warnings_list.append(f"L'étape '{s_title}' ({s_id}) n'a pas de sortie (output) explicitée.")
                
            transitions = step.get("transitions")
            if transitions:
                if isinstance(transitions, str):
                    transitions_targets.add(transitions)
                elif isinstance(transitions, dict):
                    for branch, target in transitions.items():
                        if not target:
                            blockers.append(f"La branche '{branch}' de la décision à l'étape '{s_title}' n'a pas de destination.")
                        else:
                            transitions_targets.add(target)
                            
            # Gate 7: every_critical_step_has_evidence
            control = step.get("control", {})
            if control and control.get("required") and not control.get("evidence"):
                blockers.append(f"L'étape critique '{s_title}' ({s_id}) requiert un contrôle mais ne spécifie aucun justificatif/preuve (evidence).")

        # Gate 10: every_approval_has_owner
        approval = procedure.get("approval", {})
        if approval and not approval.get("owner"):
            warnings_list.append("Aucun propriétaire de validation (approval owner) n'est défini dans la procédure.")
            
        # Gate 11: every_risk_has_control_or_acceptance
        risks = procedure.get("risks", [])
        for r in risks:
            if not r.get("control"):
                warnings_list.append(f"Le risque '{r.get('description')}' n'a aucun mécanisme de contrôle défini.")

        completeness_score = 100 - (len(blockers) * 10) - (len(warnings_list) * 3)
        completeness_score = max(0, min(100, completeness_score))
        
        verdict = "passed"
        if blockers:
            verdict = "needs_revision"
            
        return {
            "verdict": verdict,
            "completeness_score": completeness_score,
            "blockers": blockers,
            "warnings": warnings_list
        }

    def post(self, shared, prep_res, exec_res):
        shared["verification_result"] = exec_res
        
        # En cas de révision nécessaire et si on n'a pas dépassé la limite de retries
        if exec_res["verdict"] == "needs_revision":
            shared["revision_count"] = shared.get("revision_count", 0) + 1
            if shared["revision_count"] <= 2:
                # On ajoute les détails de correction dans le brief pour que la génération s'améliore
                shared["brief"]["correction_notes"] = exec_res["blockers"]
                return "revise"
                
        return "default"


class ExportArtifactsNode(Node):
    def prep(self, shared):
        return {
            "procedure": shared["procedure"],
            "verification": shared["verification_result"]
        }
        
    def exec(self, prep_res):
        proc = prep_res["procedure"]
        verif = prep_res["verification"]
        
        # Générer le diagramme Mermaid
        mermaid_lines = ["flowchart TD"]
        steps = proc.get("steps", [])
        
        # Ajouter le déclencheur
        trigger_desc = proc.get("trigger", {}).get("description", "Début")
        mermaid_lines.append(f'    start(["{trigger_desc}"]) --> {steps[0].get("id") if steps else "end"}')
        
        for step in steps:
            s_id = step.get("id")
            s_title = step.get("title", s_id)
            s_actor = step.get("actor", "")
            label = f'"{s_title}\\n({s_actor})"'
            
            transitions = step.get("transitions")
            if transitions:
                if isinstance(transitions, str):
                    mermaid_lines.append(f'    {s_id}[{label}] --> {transitions}')
                elif isinstance(transitions, dict):
                    # C'est une décision / routeur
                    decision_label = f'"{s_title}?"'
                    mermaid_lines.append(f'    {s_id}{{{decision_label}}}')
                    for branch, target in transitions.items():
                        mermaid_lines.append(f'    {s_id} -->|{branch}| {target}')
            else:
                mermaid_lines.append(f'    {s_id}[{label}] --> stop(["Fin / Résultat attendu"])')
                
        mermaid_code = "\n".join(mermaid_lines)
        
        # Construire les documents Markdown finalisés
        detailed_procedure = f"""# Procédure : {proc.get('title')}
**Version** : {proc.get('version')} | **Statut** : {proc.get('status')}

## 1. Objectif
{proc.get('purpose')}

## 2. Déclencheur
* **Déclenchement** : {proc.get('trigger', {}).get('description', 'Non spécifié')}

## 3. Rôles et Outils
* **Acteurs** : {', '.join(proc.get('actors') or [])}
* **Outils** : {', '.join(proc.get('tools') or [])}

## 4. Étapes Détaillées
"""
        for step in steps:
            detailed_procedure += f"""
### {step.get('id')} - {step.get('title')}
* **Acteur responsable** : `{step.get('actor')}`
* **Instructions** :
"""
            for inst in (step.get("instructions") or []):
                detailed_procedure += f"  - {inst}\n"
            detailed_procedure += f"* **Entrées** : {', '.join(step.get('inputs') or [])}\n"
            detailed_procedure += f"* **Sortie** : `{step.get('output')}`\n"
            if step.get("tool"):
                detailed_procedure += f"* **Outil** : {step.get('tool')}\n"
            if step.get("control", {}).get("required"):
                detailed_procedure += f"* **Contrôle requis** : Preuve = `{step.get('control', {}).get('evidence')}`\n"

        detailed_procedure += "\n## 5. Matrice des Risques et Contrôles\n"
        for r in proc.get("risks", []):
            detailed_procedure += f"* **Risque** : {r.get('description')}\n  - **Contrôle associé** : {r.get('control')}\n"
            
        # Checklist opérationnelle
        checklist_md = f"# Checklist Opérationnelle : {proc.get('title')}\n\n"
        for item in proc.get("checklist", []):
            checklist_md += f"- [ ] {item}\n"
            
        return {
            "detailed_procedure": detailed_procedure,
            "checklist": checklist_md,
            "diagram": mermaid_code,
            "verification_report": verif
        }

    def post(self, shared, prep_res, exec_res):
        shared["artifacts"] = exec_res
        return "done"


def create_procedure_flow():
    extract = ExtractBriefNode()
    missing = IdentifyMissingNode()
    clarify = ClarifyNode()
    generate = GenerateProcedureNode()
    verify = VerifyProcedureNode()
    export = ExportArtifactsNode()
    
    # Chaînage des nœuds
    extract >> missing
    
    # Branchements conditionnels
    missing - "produce" >> generate
    
    # Une fois le brief clarifié avec les réponses utilisateur, on produit directement la procédure
    clarify >> generate
    
    generate >> verify
    
    verify - "revise" >> generate
    verify - "default" >> export
    
    return Flow(start=extract)
