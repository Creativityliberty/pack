import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Nümtema People Also Ask", description="Service d'extraction sémantique et cartographie PAA (Module C)")

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
    index_path = "static/index_paa.html"
    if os.path.exists(index_path):
        return HTMLResponse(open(index_path).read())
    return HTMLResponse("<h1>People Also Ask - Frontend non trouvé</h1>")

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_paa:app", host="127.0.0.1", port=8001, reload=True)
