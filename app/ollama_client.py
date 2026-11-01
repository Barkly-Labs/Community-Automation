import requests
from .config import OLLAMA_BASE_URL, OLLAMA_MODEL

def check_ollama():
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=4)
        response.raise_for_status()
        models = [item.get("name", "") for item in response.json().get("models", [])]
        model_present = any(name == OLLAMA_MODEL or name.startswith(OLLAMA_MODEL + ":") for name in models)
        return {"connected": True, "model": OLLAMA_MODEL, "model_available": model_present, "installed_models": models}
    except requests.RequestException as exc:
        return {"connected": False, "model": OLLAMA_MODEL, "model_available": False, "error": str(exc)}

def generate(prompt: str, system: str):
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "system": system, "stream": False},
        timeout=300,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()
