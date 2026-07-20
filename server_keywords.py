import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from llm_gateway import call_llm_gateway

app = FastAPI(
    title="Nümtema Keywords & Intent Clustering API",
    description="Service d'analyse sémantique, classification d'intentions de recherche et clustering de mots-clés (Module A)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

class KeywordAnalysisRequest(BaseModel):
    query_or_keywords: str
    provider: Optional[str] = "openai"
    model: Optional[str] = "gpt-4o-mini"
    api_key: Optional[str] = None

@app.post("/api/keywords/analyze", summary="Analyser et classifier les intentions de mots-clés via LLM")
def analyze_keywords(req: KeywordAnalysisRequest):
    if not req.query_or_keywords or not req.query_or_keywords.strip():
        raise HTTPException(status_code=400, detail="Veuillez fournir un sujet ou une liste de mots-clés.")
        
    system_instruction = (
        "Tu es un expert SEO et Analyste d'Intention Sémantique. "
        "Analyse le sujet ou la liste de mots-clés fournis. "
        "Génère un cocon sémantique structuré en regroupant les mots-clés par Intention de recherche : "
        "1. Informatique / Pédagogique (Qu'est-ce que, Comment...)\n"
        "2. Commercial / Comparatif (Meilleur, Avis, Prix, vs...)\n"
        "3. Transactionnel / Achat (Acheter, Tarif, Devis, Inscription...)\n"
        "4. Navigationnel / Marque (Accès, Connexion...)\n\n"
        "Réponds UNIQUEMENT sous forme de JSON valide structuré comme suit :\n"
        "{\n"
        '  "main_topic": "sujet principal",\n'
        '  "total_keywords": 12,\n'
        '  "clusters": [\n'
        "    {\n"
        '      "intent": "Informatique",\n'
        '      "description": "Explication de l\'intention",\n'
        '      "keywords": [\n'
        '        {"keyword": "mot-clé", "volume_est": "Élevé", "difficulty": "Moyenne"}\n'
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}"
    )
    
    prompt = f"Effectue le clustering sémantique pour : '{req.query_or_keywords.strip()}'"
    
    try:
        res_text = call_llm_gateway(
            prompt=prompt,
            system_instruction=system_instruction,
            response_mime_type="application/json",
            provider=req.provider,
            model=req.model,
            api_key=req.api_key
        )
        
        try:
            data = json.loads(res_text)
            return data
        except Exception:
            cleaned = res_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            return json.loads(cleaned.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'analyse : {str(e)}")

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def read_index():
    index_path = "static/index_keywords.html"
    if os.path.exists(index_path):
        return HTMLResponse(open(index_path).read())
    return HTMLResponse("<h1>Keywords & Intents - Frontend non trouvé</h1>")

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_keywords:app", host="127.0.0.1", port=8003, reload=True)
