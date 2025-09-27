# test_gemini.py
import core.gemini_client as gc

try:
    resp = gc.model.generate_content("Health check: reply with OK")
    print(getattr(resp, "text", resp))
except Exception as e:
    print("Gemini call failed:", e)