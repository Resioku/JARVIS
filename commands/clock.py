"""
VOICE COMMAND: Clock
Answers "what time is it" / "what's the date". Shows a command whose
reply isn't a fixed sentence.

Command file rules (same idea as games/sections):
  NAME      any label
  TRIGGERS  phrases that fire it (matched against what you said)
  handle()  gets what you said (lowercase, no punctuation), returns what JARVIS says
"""
from datetime import datetime

# ---------- Contract ----------
NAME = "Clock"
TRIGGERS = [
    "what time is it", "what's the time", "what is the time", "current time",
    "what day is it", "what's the date", "what is the date", "today's date",
]


# ---------- Functions ----------

def handle(text: str) -> str:
    now = datetime.now()
    words = text.split()
    if "day" in words or "date" in words:
        return f"Today is {now:%A, %B} {now.day}."
    return "It is " + now.strftime("%I:%M %p").lstrip("0") + "."