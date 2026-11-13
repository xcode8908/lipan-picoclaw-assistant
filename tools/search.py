import requests
import re
from urllib.parse import unquote

def web_search(query, max_results=3):
    if not query:
        return "Search query khali hai."
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
    
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return f"Search error (HTTP {resp.status_code})"
        
        html = resp.text
        # Extract snippets using regex
        results = []
        links = re.findall(r'<a class="result__url"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html)
        snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html)
        titles = re.findall(r'<h2 class="result__title">[\s\S]*?<a class="result__a"[^>]*>(.*?)</a>', html)
        
        for i in range(min(len(titles), len(snippets), max_results)):
            t = re.sub(r'<[^>]+>', '', titles[i]).strip()
            s = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            results.append(f"📌 *{t}*\n{s}")
            
        if not results:
            return f"'{query}' ke liye koi result nahi mila."
            
        return "\n\n".join(results)
    except Exception as e:
        return f"Search error: {str(e)}"
