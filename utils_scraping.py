import requests
import urllib.parse
import json

def get_google_suggestions(query: str) -> list:
    """
    Option 2: Public open API for Google Autocomplete search suggestions.
    No API keys required, extremely fast and stable.
    """
    if not query.strip():
        return []
    
    url = f"https://suggestqueries.google.com/complete/search?client=chrome&q={urllib.parse.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        # The response format for client=chrome is [query, [suggestions], [descriptions], ...]
        data = response.json()
        if len(data) > 1:
            return data[1]
    except Exception as e:
        print(f"[Error suggestions] {e}")
    return []

def get_people_also_ask_mined(query: str) -> list:
    """
    Option 3 (Mined suggestions): Since direct Google HTML scraping is blocked by JS client redirection
    in standard Python scripts without browser rendering (Playwright/Selenium), we use Google Autocomplete
    Search Suggestion Mining.
    
    It queries the open autocomplete API recursively with a wide variety of question modifiers
    to collect real queries asked by users.
    """
    if not query.strip():
        return []
        
    modifiers = [
        "comment", "pourquoi", "quel", "quelle", "quels", "quelles", 
        "qui", "combien", "est-ce que", "où", "quand", "comment faire pour",
        "avis sur", "tuto", "prix", "meilleur"
    ]
    mined_questions = []
    
    # Simple search clean up
    base_query = query.lower()
    for m in modifiers:
        if base_query.startswith(m):
            base_query = base_query.replace(m, "").strip()
            
    # Try querying with modifiers
    for mod in modifiers:
        search_term = f"{mod} {base_query}"
        suggestions = get_google_suggestions(search_term)
        for sugg in suggestions:
            # Clean and standardise suggestion
            sugg_clean = sugg.strip()
            # Avoid duplicate variations
            sugg_lower = sugg_clean.lower()
            if sugg_clean and not any(x.lower() == sugg_lower for x in mined_questions):
                # Add question mark if it starts with a question word and lacks it
                if any(sugg_clean.lower().startswith(x) for x in ["comment", "pourquoi", "quel", "quelle", "qui", "combien", "est-ce que", "où", "quand"]) and not sugg_clean.endswith('?'):
                    sugg_clean += ' ?'
                mined_questions.append(sugg_clean)
                
    # Also query the original query itself to grab standard autocompletes
    original_suggestions = get_google_suggestions(query)
    for sugg in original_suggestions:
        sugg_clean = sugg.strip()
        sugg_lower = sugg_clean.lower()
        if sugg_clean and not any(x.lower() == sugg_lower for x in mined_questions):
            mined_questions.append(sugg_clean)
            
    return mined_questions

if __name__ == "__main__":
    # Test queries
    test_query = "debuter le violon"
    print(f"--- Test de l'Option 2 (Suggestions d'auto-complétion) pour '{test_query}' ---")
    suggestions = get_google_suggestions(test_query)
    print(json.dumps(suggestions, indent=2, ensure_ascii=False))
    
    print(f"\n--- Test de l'Option 3 (Questions Minées via Autocomplete) pour '{test_query}' ---")
    paa = get_people_also_ask_mined(test_query)
    print(json.dumps(paa, indent=2, ensure_ascii=False))
