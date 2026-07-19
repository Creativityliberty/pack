import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Nümtema Agentic Hub", description="Portail d'accueil commun et tableau de bord unifié (Port 8002)")

@app.get("/")
def read_index():
    index_path = "static/index_hub.html"
    if os.path.exists(index_path):
        return HTMLResponse(open(index_path).read())
    return HTMLResponse("<h1>Nümtema Hub - Frontend non trouvé</h1>")

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_hub:app", host="127.0.0.1", port=8002, reload=True)
