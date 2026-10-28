"""Router: decides which crew should work. One small, cheap LLM call (no crew, no agents)."""
import re

from app.core.llm import run_with_fallback

CATEGORIES = ("planning", "my_documents", "procedure", "general")

PROMPT = """Classify the user's message into exactly ONE label.
planning     = planning a trip, event or outing, travel with a budget
my_documents = questions about the user's OWN saved documents, expiry dates, deadlines, or asking to set a reminder
procedure    = how to do an official procedure: required documents, steps, fees, rules (passport, driving licence, tax)
general      = greetings, thanks, "what can you do", anything else

Examples:
"ঈদে ৩ জন সিলেট যাব, বাজেট ১৫ হাজার" -> planning
"আমার পাসপোর্ট কবে শেষ হবে?" -> my_documents
"আমার লাইসেন্সের জন্য রিমাইন্ডার দাও" -> my_documents
"পাসপোর্ট নবায়নে কী কী কাগজ লাগে?" -> procedure
"ধন্যবাদ" -> general

Reply with ONLY the label.
Message: {message}"""

GREETINGS = ("hi", "hello", "hey", "thanks", "thank you", "ধন্যবাদ", "হ্যালো", "হাই", "ok", "okay")


def route(message: str) -> tuple[str, str]:
    """Returns (category, tier_used). Very short greetings skip the LLM completely (saves tokens)."""
    text = message.strip().lower()
    if len(text) < 16 and any(text.startswith(g) for g in GREETINGS):
        return "general", "none"

    def task(llm):
        return str(llm.call(PROMPT.format(message=message.strip()[:500])))

    raw, tier = run_with_fallback(task, temperature=0.0, prefer_small=True)
    match = re.search(r"(planning|my_documents|procedure|general)", raw.lower())
    return (match.group(1) if match else "general"), tier
