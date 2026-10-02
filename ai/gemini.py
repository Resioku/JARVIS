"""AI PROVIDER: Gemini. Needs GEMINI_API_KEY in keys.env."""
import logging
import google.generativeai as genai
from core.keys import get_key

log = logging.getLogger(__name__)
NAME = "Gemini"
MODEL_NAME = "gemini-3.8-flash"
PERSONA = "You are JARVIS, a calm and brief AI assistant. Keep answers to 1-3 short sentences."
_model = None


def ask(text: str) -> str:
    global _model
    try:
        if _model is None:
            key = get_key("GEMINI_API_KEY")
            if not key:
                return "No Gemini API key set in keys.env, sir."
            genai.configure(api_key=key)
            _model = genai.GenerativeModel(MODEL_NAME, system_instruction=PERSONA)
        return _model.generate_content(text).text.strip()
    except Exception:
        log.exception("Gemini request failed")
        return "I couldn't reach Gemini just now, sir."