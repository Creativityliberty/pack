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

app = FastAPI(title="Nümtema Pack Factory", description="Moteur de missions verticales basé sur PocketFlow")

# In-memory session store
SESSIONS: Dict[str, Dict[str, Any]] = {}
DB_PATH = "output/history.db"

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
        print(f"[DB] Pack {session_id} successfully saved/updated (status={status}).")
    except Exception as e:
        print(f"[DB] Error saving pack {session_id}: {e}")

@app.on_event("startup")
def startup():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        paths = [".env.local", "../.env.local", "../../.env.local"]
        for p in paths:
            if os.path.exists(p):
                with open(p) as f:
                    for line in f:
                        if "=" in line and not line.startswith("#"):
                            k, v = line.split("=", 1)
                            if k.strip() == "GEMINI_API_KEY":
                                api_key = v.strip().strip('"').strip("'")
                                os.environ["GEMINI_API_KEY"] = api_key
                                break
            if api_key:
                break
                
    if not api_key:
        print("[STARTUP] WARNING: GEMINI_API_KEY not found. Running in offline MOCK mode.")
        os.environ["MOCK_LLM"] = "true"
    else:
        print("[STARTUP] GEMINI_API_KEY found. Running in live Gemini API mode.")
        os.environ["MOCK_LLM"] = "false"

    # Initialize SQLite and create outputs folder
    init_db()

@app.post("/api/procedure/init")
def init_procedure(req: InitRequest):
    if not req.raw_demand.strip():
        raise HTTPException(status_code=400, detail="La demande brute ne peut pas être vide.")
        
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
    
    flow = create_procedure_flow()
    flow.run(shared)
    
    SESSIONS[session_id] = shared
    
    # Check current status
    has_blocking = any(q.get("blocking", False) for q in shared.get("missing_info", []))
    status = "waiting_clarification" if (has_blocking and not shared.get("clarified")) else "completed"
    
    # Save artifacts to file if completed
    if status == "completed" and shared.get("artifacts"):
        save_artifacts(session_id, shared["artifacts"])
        
    # Save to SQLite database
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
def submit_answers(session_id: str, req: AnswerRequest):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session non trouvée.")
        
    shared = SESSIONS[session_id]
    shared["clarification_answers"] = req.answers
    
    # Re-run flow
    flow = create_procedure_flow()
    flow.run(shared)
    
    # Check status
    has_blocking = any(q.get("blocking", False) for q in shared.get("missing_info", []))
    status = "waiting_clarification" if (has_blocking and not shared.get("clarified")) else "completed"
    
    if status == "completed" and shared.get("artifacts"):
        save_artifacts(session_id, shared["artifacts"])
        
    # Save to SQLite database
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
Exemple de format attendu :
{{
  "Question 1 ?": "Réponse suggérée 1",
  "Question 2 ?": "Réponse suggérée 2"
}}
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
            for q in questions:
                suggestions[q] = "À préciser par l'utilisateur."
            return {"suggestions": suggestions}

@app.post("/api/procedure/{session_id}/force-generate")
def force_generate(session_id: str):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session non trouvée.")
        
    shared = SESSIONS[session_id]
    shared["clarified"] = True  # bypass Q&A block
    
    flow = create_procedure_flow()
    flow.run(shared)
    
    if shared.get("artifacts"):
        save_artifacts(session_id, shared["artifacts"])
        
    # Save to SQLite database
    db_save_pack(session_id, shared, "completed")
        
    return {
        "session_id": session_id,
        "status": "completed",
        "brief": shared["brief"],
        "verification_result": shared["verification_result"],
        "artifacts": shared["artifacts"]
    }

@app.get("/api/procedure/{session_id}")
def get_session(session_id: str):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session non trouvée.")
    
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

def save_artifacts(session_id: str, artifacts: Dict[str, Any]):
    # Write to local outputs folder for export/traceability
    prefix = f"output/{session_id}"
    os.makedirs("output", exist_ok=True)
    
    with open(f"{prefix}_procedure.md", "w") as f:
        f.write(artifacts.get("detailed_procedure", ""))
        
    with open(f"{prefix}_checklist.md", "w") as f:
        f.write(artifacts.get("checklist", ""))
        
    with open(f"{prefix}_diagram.mermaid", "w") as f:
        f.write(artifacts.get("diagram", ""))
        
    with open(f"{prefix}_verification.json", "w") as f:
        json.dump(artifacts.get("verification_report", {}), f, ensure_ascii=False, indent=2)

@app.get("/api/procedure/{session_id}/zip")
def download_procedure_zip(session_id: str):
    if session_id not in SESSIONS:
        # Check database as fallback
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM packs WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Pack non trouvé.")
        artifacts = json.loads(row["artifacts"]) if row["artifacts"] else None
    else:
        shared = SESSIONS[session_id]
        artifacts = shared.get("artifacts")
        
    if not artifacts:
        raise HTTPException(status_code=400, detail="Aucun livrable disponible pour ce pack.")
        
    # Create ZIP in-memory using BytesIO
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        # Add detailed procedure
        zip_file.writestr("procedure.md", artifacts.get("detailed_procedure", ""))
        # Add checklist
        zip_file.writestr("checklist.md", artifacts.get("checklist", ""))
        # Add diagram
        zip_file.writestr("diagram.mermaid", artifacts.get("diagram", ""))
        # Add QC report
        zip_file.writestr("verification_report.json", json.dumps(artifacts.get("verification_report", {}), ensure_ascii=False, indent=2))
        
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=numtema_pack_{session_id}.zip"}
    )

@app.get("/api/history")
def get_history(q: str = None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if q:
        cursor.execute("""
            SELECT id, raw_demand, provider, model, brief, status, created_at 
            FROM packs 
            WHERE raw_demand LIKE ? OR brief LIKE ? OR procedure LIKE ?
            ORDER BY created_at DESC
        """, (f"%{q}%", f"%{q}%", f"%{q}%"))
    else:
        cursor.execute("""
            SELECT id, raw_demand, provider, model, brief, status, created_at 
            FROM packs 
            ORDER BY created_at DESC
        """)
        
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        brief_data = {}
        if r["brief"]:
            try:
                brief_data = json.loads(r["brief"])
            except Exception:
                pass
        
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

@app.get("/api/paa")
def search_people_also_ask(q: str):
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Requête de recherche vide.")
    from utils_scraping import get_people_also_ask_mined
    try:
        questions = get_people_also_ask_mined(q)
        return {"query": q, "questions": questions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_index():
    index_path = "static/index.html"
    if os.path.exists(index_path):
        return HTMLResponse(open(index_path).read())
    return HTMLResponse("<h1>Nümtema Pack Factory - Frontend non trouvé</h1>")

# Try to mount static directory for css/js if needed, otherwise serve index.html directly
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
