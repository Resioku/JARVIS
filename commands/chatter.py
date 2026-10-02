"""
VOICE COMMAND: Chatter
Canned lines. THIS IS THE EASIEST FILE TO ADD TO: to teach JARVIS a new
phrase, add a line to LINES. Write the phrase in lowercase with no
punctuation. If you give a list of replies, it picks one at random.
"""
import random

# ---------- Lines (add yours here) ----------
LINES = {
    "hello": ["Hello, sir.", "At your service.", "Good to hear from you, sir."],
    "how are you": ["Fully operational, sir.", "All systems nominal."],
    "thank you": ["You're welcome, sir.", "Any time."],
    "thanks": ["You're welcome, sir.", "Any time."],
    "who are you": ["I'm JARVIS. Just a rather very intelligent system."],
    "good night": ["Good night, sir."],
    "open the pod bay doors": ["I'm afraid I can't do that."],
}

# ---------- Contract ----------
NAME = "Chatter"
TRIGGERS = list(LINES)


# ---------- Functions ----------

def handle(text: str) -> str:
    padded = f" {text} "
    matches = [phrase for phrase in LINES if f" {phrase} " in padded]
    best = max(matches, key=len)   # the most specific phrase wins
    return random.choice(LINES[best])