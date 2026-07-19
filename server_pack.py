import os
import uuid
import json
import sqlite3
import requests
import io
import zipfile
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

app = FastAPI(title="Nümtema Pack Factory", description="Service d'ingénierie des procédures opérationnelles (Module B)")

# In-memory session store
SESSIONS: Dict[str, Dict[str, Any]] = {}
DB_PATH = "output/history_pack.db"

from procedure_flow import create_procedure_flow

class InitRequest(BaseModel):
    raw_demand: str
    provider: Optional[str] = "gemini"
    model: Optional[str] = None
    api_key: Optional[str] = None

class AnswerRequest(BaseModel):
    answers: Dict[str, str]

def init_db():
    os.makedirs("output", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS packs (
            id TEXT PRIMARY KEY,
            raw_demand TEXT,
            provider TEXT,
            model TEXT,
            brief TEXT,
            procedure TEXT,
            verification TEXT,
            artifacts TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def db_save_pack(session_id: str, shared: Dict[str, Any], status: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        brief_json = json.dumps(shared.get("brief"), ensure_ascii=False) if shared.get("brief") else None
        procedure_json = json.dumps(shared.get("procedure"), ensure_ascii=False) if shared.get("procedure") else None
        verification_json = json.dumps(shared.get("verification_result"), ensure_ascii=False) if shared.get("verification_result") else None
        artifacts_json = json.dumps(shared.get("artifacts"), ensure_ascii=False) if shared.get("artifacts") else None
        
        llm_settings = shared.get("llm_settings", {})
        provider = llm_settings.get("provider", "gemini")
        model = llm_settings.get("model")
        
        cursor.execute("""
            INSERT INTO packs (id, raw_demand, provider, model, brief, procedure, verification, artifacts, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                raw_demand=excluded.raw_demand,
                provider=excluded.provider,
                model=excluded.model,
                brief=excluded.brief,
                procedure=excluded.procedure,
                verification=excluded.verification,
                artifacts=excluded.artifacts,
                status=excluded.status
        """, (
            session_id,
            shared.get("raw_demand"),
            provider,
            model,
            brief_json,
            procedure_json,
            verification_json,
            artifacts_json,
            status
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB Error] Failed to save pack {session_id}: {e}")

init_db()

def save_artifacts(session_id: str, artifacts: Dict[str, Any]):
    os.makedirs("output", exist_ok=True)
    for filename, content in artifacts.items():
        filepath = os.path.join("output", f"{session_id}_{filename}")
        with open(filepath, "w", encoding="utf-8") as f:
            if isinstance(content, (dict, list)):
                f.write(json.dumps(content, ensure_ascii=False, indent=2))
            else:
                f.write(str(content or ""))

@app.post("/api/procedure/init")
def init_procedure(req: InitRequest):
    session_id = str(uuid.uuid4())
    shared = {
        "raw_demand": req.raw_demand,
        "brief": None,
        "missing_info": [],
        "clarified": False,
        "procedure": None,
        "verification_result": None,
        "artifacts": None,
        "revision_count": 0,
        "llm_settings": {
            "provider": req.provider,
            "model": req.model,
            "api_key": req.api_key
        }
    }
    
    SESSIONS[session_id] = shared
    flow = create_procedure_flow()
    flow.run(shared)
    
    # Check status
    has_blocking = any(q.get("blocking", False) for q in shared.get("missing_info", []))
    status = "waiting_clarification" if (has_blocking and not shared.get("clarified")) else "completed"
    
    if status == "completed" and shared.get("artifacts"):
        save_artifacts(session_id, shared["artifacts"])
        
    db_save_pack(session_id, shared, status)
        
    return {
        "session_id": session_id,
        "status": status,
        "brief": shared["brief"],
        "missing_info": shared["missing_info"],
        "verification_result": shared["verification_result"],
        "artifacts": shared["artifacts"]
    }

@app.post("/api/procedure/{session_id}/answer")
def answer_procedure(session_id: str, req: AnswerRequest):
    try:
        if session_id not in SESSIONS:
            try:
                get_historical_session(session_id)
            except Exception:
                pass
            if session_id not in SESSIONS:
                raise HTTPException(status_code=404, detail="Session non trouvée.")
            
        shared = SESSIONS[session_id]
        
        # Update brief and top-level shared with user answers
        shared["clarification_answers"] = req.answers
        if shared.get("brief"):
            shared["brief"]["user_answers"] = req.answers
        shared["clarified"] = True
        
        flow = create_procedure_flow()
        flow.run(shared)
        
        has_blocking = any(q.get("blocking", False) for q in shared.get("missing_info", []))
        status = "waiting_clarification" if (has_blocking and not shared.get("clarified")) else "completed"
        
        if status == "completed" and shared.get("artifacts"):
            save_artifacts(session_id, shared["artifacts"])
            
        db_save_pack(session_id, shared, status)
            
        return {
            "session_id": session_id,
            "status": status,
            "brief": shared["brief"],
            "missing_info": shared["missing_info"],
            "verification_result": shared["verification_result"],
            "artifacts": shared["artifacts"]
        }
    except Exception as exc:
        import traceback
        err_msg = f"[ERROR in answer_procedure] {exc}\n{traceback.format_exc()}"
        print(err_msg)
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/procedure/{session_id}/force-generate")
def force_generate_procedure(session_id: str):
    if session_id not in SESSIONS:
        try:
            get_historical_session(session_id)
        except Exception:
            pass
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session non trouvée.")
        
    shared = SESSIONS[session_id]
    shared["clarified"] = True
    
    try:
        flow = create_procedure_flow()
        flow.run(shared)
    except Exception as e:
        print(f"[Flow Error in force_generate] {e}")
        if not shared.get("procedure"):
            from procedure_flow import GenerateProcedureNode, VerifyProcedureNode, ExportArtifactsNode
            gen_node = GenerateProcedureNode()
            gen_node._run(shared)
            ver_node = VerifyProcedureNode()
            ver_node._run(shared)
            exp_node = ExportArtifactsNode()
            exp_node._run(shared)
    
    status = "completed"
    if shared.get("artifacts"):
        save_artifacts(session_id, shared["artifacts"])
        
    db_save_pack(session_id, shared, status)
        
    return {
        "session_id": session_id,
        "status": status,
        "brief": shared["brief"],
        "missing_info": shared["missing_info"],
        "verification_result": shared["verification_result"],
        "artifacts": shared["artifacts"]
    }

@app.post("/api/procedure/{session_id}/suggest-answers")
def suggest_answers(session_id: str):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session non trouvée.")
        
    shared = SESSIONS[session_id]
    raw_demand = shared.get("raw_demand")
    questions = [q.get("question") for q in shared.get("missing_info", [])]
    
    if not questions:
        return {"suggestions": {}}
        
    from llm_client import call_llm
    
    system_instruction = (
        "Tu es un Business Analyst expert. Propose des réponses logiques aux questions de clarification "
        "en te basant sur la demande brute. Si l'information n'est pas dans la demande brute, "
        "propose une réponse standard basée sur les meilleures pratiques opérationnelles. "
        "Réponds UNIQUEMENT sous forme de JSON valide associant chaque question à sa suggestion de réponse."
    )
    
    prompt = f"""
Demande brute de processus :
---
{raw_demand}
---

Questions à répondre :
{json.dumps(questions, ensure_ascii=False, indent=2)}

Renvoie un dictionnaire JSON où les clés sont exactement les questions et les valeurs sont les réponses suggérées (maximum 20 mots par réponse).
"""
    llm_settings = shared.get("llm_settings", {})
    
    res_text = call_llm(
        prompt, 
        system_instruction=system_instruction, 
        response_mime_type="application/json", 
        **llm_settings
    )
    
    try:
        suggestions = json.loads(res_text)
        return {"suggestions": suggestions}
    except Exception:
        try:
            cleaned = res_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            suggestions = json.loads(cleaned.strip())
            return {"suggestions": suggestions}
        except Exception:
            suggestions = {}
            
    return {"suggestions": suggestions}

@app.get("/api/procedure/artifact/{session_id}/{filename}")
def download_artifact(session_id: str, filename: str):
    filepath = os.path.join("output", f"{session_id}_{filename}")
    if os.path.exists(filepath):
        return FileResponse(filepath, filename=filename)
    raise HTTPException(status_code=404, detail="Fichier non trouvé.")

@app.get("/api/procedure/export-zip/{session_id}")
def export_all_artifacts_zip(session_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM packs WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Pack non trouvé.")
        
    brief_data = json.loads(row["brief"]) if row["brief"] else {}
    title = brief_data.get("title", "pack_procedure").lower().replace(" ", "_")
    zip_filename = f"{title}_{session_id[:8]}.zip"
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        prefix = f"{session_id}_"
        if os.path.exists("output"):
            for f in os.listdir("output"):
                if f.startswith(prefix):
                    arcname = f[len(prefix):]
                    filepath = os.path.join("output", f)
                    zip_file.write(filepath, arcname)
                    
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
    )

@app.get("/api/history")
def list_historical_sessions():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, raw_demand, provider, model, brief, status, created_at FROM packs ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        brief_data = json.loads(r["brief"]) if r["brief"] else {}
        results.append({
            "session_id": r["id"],
            "raw_demand": r["raw_demand"],
            "provider": r["provider"],
            "model": r["model"],
            "title": brief_data.get("title", "Sans titre"),
            "purpose": brief_data.get("purpose", ""),
            "status": r["status"],
            "created_at": r["created_at"]
        })
    return results

@app.get("/api/history/{session_id}")
def get_historical_session(session_id: str):
    if session_id in SESSIONS:
        shared = SESSIONS[session_id]
        has_blocking = any(q.get("blocking", False) for q in shared.get("missing_info", []))
        status = "waiting_clarification" if (has_blocking and not shared.get("clarified")) else "completed"
        return {
            "session_id": session_id,
            "status": status,
            "brief": shared["brief"],
            "missing_info": shared["missing_info"],
            "verification_result": shared["verification_result"],
            "artifacts": shared["artifacts"]
        }
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM packs WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Pack non trouvé.")
        
    shared = {
        "raw_demand": row["raw_demand"],
        "brief": json.loads(row["brief"]) if row["brief"] else None,
        "missing_info": [],
        "clarified": True if row["status"] == "completed" else False,
        "procedure": json.loads(row["procedure"]) if row["procedure"] else None,
        "verification_result": json.loads(row["verification"]) if row["verification"] else None,
        "artifacts": json.loads(row["artifacts"]) if row["artifacts"] else None,
        "revision_count": 0,
        "llm_settings": {
            "provider": row["provider"],
            "model": row["model"],
            "api_key": None
        }
    }
    
    SESSIONS[session_id] = shared
    
    return {
        "session_id": session_id,
        "status": row["status"],
        "brief": shared["brief"],
        "missing_info": shared["missing_info"],
        "verification_result": shared["verification_result"],
        "artifacts": shared["artifacts"]
    }

@app.get("/api/ollama/models")
def get_ollama_models():
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=1.0)
        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("name") for m in data.get("models", [])]
            return {"models": models, "online": True}
    except Exception:
        pass
    
    fallback_models = ["llama3:latest", "mistral:latest", "codegemma:latest", "phi3:latest"]
    return {"models": fallback_models, "online": False}

@app.get("/")
def read_index():
    index_path = "static/index_pack.html"
    if os.path.exists(index_path):
        return HTMLResponse(open(index_path).read())
    return HTMLResponse("<h1>Pack Factory - Frontend non trouvé</h1>")

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_pack:app", host="127.0.0.1", port=8000, reload=True)
