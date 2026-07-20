import os
import json
import requests
import google.generativeai as genai

def resolve_api_key(key_name: str, passed_key: str = None) -> str:
    if passed_key and passed_key.strip():
        return passed_key.strip()
    env_val = os.getenv(key_name)
    if env_val and env_val.strip():
        return env_val.strip()
    
    # Check .env files
    env_files = [".env", ".env.local", os.path.expanduser("~/.env"), "../.env"]
    for path in env_files:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if "=" in line and not line.startswith("#"):
                            k, v = line.split("=", 1)
                            if k.strip() == key_name:
                                val = v.strip().strip('"').strip("'")
                                if val:
                                    return val
            except Exception:
                pass
    return None

def call_llm_gateway(
    prompt: str, 
    system_instruction: str = None, 
    response_mime_type: str = None, 
    provider: str = "openai", 
    model: str = None, 
    api_key: str = None
) -> str:
    provider = (provider or "openai").lower()
    
    # 1. OpenAI Provider (GPT-4o / GPT-4o-mini)
    if provider in ["openai", "gpt"]:
        model_name = model or "gpt-4o-mini"
        openai_key = resolve_api_key("OPENAI_API_KEY", api_key)
        
        if not openai_key:
            print("[OpenAI Warning] OPENAI_API_KEY non trouvée. Basculement sur Gemini/Ollama.")
            # Fallback to Gemini or Ollama if OpenAI key is missing
            gemini_key = resolve_api_key("GEMINI_API_KEY")
            if gemini_key:
                return call_llm_gateway(prompt, system_instruction, response_mime_type, "gemini", "gemini-1.5-flash", gemini_key)
            return call_llm_gateway(prompt, system_instruction, response_mime_type, "ollama", None, None)
            
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_key}"
        }
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.2
        }
        if response_mime_type == "application/json":
            payload["response_format"] = {"type": "json_object"}
            
        print(f"[OpenAI] Call model '{model_name}'...")
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[OpenAI Error] {e}. Basculement sur Gemini.")
            gemini_key = resolve_api_key("GEMINI_API_KEY")
            if gemini_key:
                return call_llm_gateway(prompt, system_instruction, response_mime_type, "gemini", "gemini-1.5-flash", gemini_key)
            return call_llm_gateway(prompt, system_instruction, response_mime_type, "ollama", None, None)

    # 2. Google Gemini Provider
    elif provider == "gemini":
        model_name = model or "gemini-1.5-flash"
        gemini_key = resolve_api_key("GEMINI_API_KEY", api_key)
        
        if not gemini_key:
            print("[Gemini Warning] GEMINI_API_KEY non trouvée. Basculement sur Ollama.")
            return call_llm_gateway(prompt, system_instruction, response_mime_type, "ollama", None, None)
            
        try:
            genai.configure(api_key=gemini_key)
            print(f"[Gemini] Call model '{model_name}'...")
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
            print(f"[Gemini Error] {e}. Basculement sur Ollama.")
            return call_llm_gateway(prompt, system_instruction, response_mime_type, "ollama", None, None)

    # 3. DeepSeek Provider
    elif provider == "deepseek":
        model_name = model or "deepseek-chat"
        ds_key = resolve_api_key("DEEPSEEK_API_KEY", api_key)
        if not ds_key:
            return call_llm_gateway(prompt, system_instruction, response_mime_type, "ollama", None, None)
            
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {ds_key}"
        }
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.2
        }
        if response_mime_type == "application/json":
            payload["response_format"] = {"type": "json_object"}
            
        print(f"[DeepSeek] Call model '{model_name}'...")
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=20)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[DeepSeek Error] {e}. Basculement sur Ollama.")
            return call_llm_gateway(prompt, system_instruction, response_mime_type, "ollama", None, None)

    # 4. Ollama Local Provider (with auto-detection)
    else:  # provider == "ollama"
        model_name = model
        url_tags = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/tags"
        available_models = []
        try:
            r_tags = requests.get(url_tags, timeout=2)
            if r_tags.status_code == 200:
                available_models = [m.get("name") for m in r_tags.json().get("models", [])]
        except Exception:
            pass

        if available_models:
            if not model_name or model_name not in available_models:
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
            "options": {"temperature": 0.2}
        }
        if response_mime_type == "application/json":
            payload["format"] = "json"
            
        print(f"[Ollama] Call model '{model_name}' at {url}...")
        try:
            r = requests.post(url, json=payload, timeout=10)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except Exception as e:
            print(f"[Ollama Error] {e}. Mode MOCK de secours.")
            from llm_client import call_llm
            os.environ["MOCK_LLM"] = "true"
            return call_llm(prompt, system_instruction, response_mime_type, "ollama", model_name, api_key)
