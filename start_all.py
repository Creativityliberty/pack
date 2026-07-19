import subprocess
import sys
import time
import os

def main():
    print("=" * 60)
    print("🚀 NÜMTEMA AGENTIC HUB - LANCEMENT DES MICROSERVICES")
    print("=" * 60)
    
    python_bin = sys.executable
    
    processes = []
    
    services = [
        {"name": "Pack Factory (Module B)", "script": "server_pack.py", "port": 8000},
        {"name": "People Also Ask (Module C)", "script": "server_paa.py", "port": 8001},
        {"name": "Hub Dashboard (Portail Commun)", "script": "server_hub.py", "port": 8002},
    ]
    
    for s in services:
        print(f"--> Démarrage de {s['name']} sur http://127.0.0.1:{s['port']}...")
        p = subprocess.Popen([python_bin, s["script"]])
        processes.append(p)
        time.sleep(1)
        
    print("\n" + "=" * 60)
    print("✅ TOUS LES SERVICES SONT EN COURS D'EXÉCUTION !")
    print("=" * 60)
    print("  • Hub Dashboard (Accueil)  : http://127.0.0.1:8002")
    print("  • Pack Factory (Module B)  : http://127.0.0.1:8000")
    print("  • People Also Ask (Module C): http://127.0.0.1:8001")
    print("=" * 60)
    print("Appuyez sur Ctrl+C pour arrêter tous les services.\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nArrêt des services...")
        for p in processes:
            p.terminate()
        print("Tous les services ont été arrêtés proprements.")

if __name__ == "__main__":
    main()
