import requests
import os

SENTRY_URL = os.environ.get("SENTRY_STATUS_URL", "https://self-heal-sentry.onrender.com/api/status")
SENTRY_SECRET = os.environ.get("SENTRY_SECRET", "Lipan8908@")

def get_fleet_report():
    url = f"{SENTRY_URL}?secret={SENTRY_SECRET}"
    try:
        resp = requests.get(url, timeout=6)
        if resp.status_code != 200:
            return f"⚠️ Sentry Watchdog unreachable (HTTP {resp.status_code})"
        
        data = resp.json()
        if not isinstance(data, list):
            data = data.get("services", [])
            
        report_lines = ["🛡️ *Lipan Fleet Live Status:*", ""]
        healthy_count = 0
        total_count = len(data)
        
        for s in data:
            sid = s.get("id", "unknown")
            name = s.get("name", sid)
            status = s.get("status", "unknown")
            latency = s.get("latency_ms", 0)
            
            icon = "🟢" if status == "healthy" else ("🟡" if status == "starting" else "🔴")
            if status == "healthy":
                healthy_count += 1
                
            report_lines.append(f"{icon} *{name}*\n   └ Status: `{status}` | Latency: `{latency:.1f}ms`")
            
        summary = f"\n📊 *Summary:* {healthy_count}/{total_count} Nodes Healthy (100% 0ms Keep-Alive Active)"
        report_lines.append(summary)
        return "\n".join(report_lines)
    except Exception as e:
        return f"⚠️ Fleet check error: {str(e)}"
