import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from llm_gateway import call_llm_gateway

app = FastAPI(
    title="Nümtema People Also Ask API",
    description="Service d'extraction sémantique et cartographie PAA augmentée par IA (Module C)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

class SynthesizeRequest(BaseModel):
    question: str
    context_topic: Optional[str] = None
    provider: Optional[str] = "openai"
    model: Optional[str] = "gpt-4o-mini"
    api_key: Optional[str] = None

@app.get("/api/paa", summary="Extraire les questions People Also Ask de Google")
def search_people_also_ask(q: str):
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Requête de recherche vide.")
    from utils_scraping import get_people_also_ask_mined
    try:
        questions = get_people_also_ask_mined(q)
        return {"query": q, "questions": questions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/paa/synthesize", summary="Générer une réponse synthétique IA à une question PAA")
def synthesize_paa_answer(req: SynthesizeRequest):
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="Question vide.")
        
    system_instruction = (
        "Tu es un Rédacteur Expert et Consultant d'Entreprise. "
        "Rédige une réponse synthétique, professionnelle et claire (maximum 100 mots) "
        "à la question posée par l'internaute. "
        "Structure la réponse avec des puces d'action si nécessaire."
    )
    prompt = f"Question de l'internaute : '{req.question}'"
    if req.context_topic:
        prompt += f"\nContexte du sujet : {req.context_topic}"
        
    try:
        answer_text = call_llm_gateway(
            prompt=prompt,
            system_instruction=system_instruction,
            provider=req.provider,
            model=req.model,
            api_key=req.api_key
        )
        return {"question": req.question, "answer": answer_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la génération : {str(e)}")

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def read_index():
    index_path = "static/index_paa.html"
    if os.path.exists(index_path):
        return HTMLResponse(open(index_path).read())
    return HTMLResponse("<h1>People Also Ask - Frontend non trouvé</h1>")

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_paa:app", host="127.0.0.1", port=8001, reload=True)
