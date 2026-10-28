"""
LLM loader + mid-flight fallback (ported from the Leo project).

Differences from Leo:
  * no Streamlit session_state -> we remember "primary is failing" in a small cooldown timer
  * agents/crews are built PER REQUEST with the llm we pass in, so a fallback run really uses the backup model
"""
import logging
import time
from typing import Any, Callable, TypeVar

from app.core.config import settings

log = logging.getLogger("jibon.llm")
T = TypeVar("T")

PRIMARY_COOLDOWN_SECONDS = 300  # after a primary failure, prefer the backup model for 5 minutes
_primary_blocked_until = 0.0
_llm_cache: dict[tuple[str, float], Any] = {}


class LLMUnavailableError(RuntimeError):
    """Both primary and fallback models failed."""


def get_llm(tier: str = "primary", temperature: float = 0.5):
    """Returns a CrewAI LLM for 'primary' or 'fallback' (same as Leo's get_llm)."""
    from crewai import LLM  # imported lazily so the API starts fast and /health stays light

    key = (tier, temperature)
    if key in _llm_cache:
        return _llm_cache[key]

    if tier == "primary":
        token, endpoint, model = settings.PRIMARY_API_KEY, settings.PRIMARY_BASE_URL, settings.PRIMARY_MODEL
    elif tier == "fallback":
        token, endpoint, model = settings.FALLBACK_API_KEY, settings.FALLBACK_BASE_URL, settings.FALLBACK_MODEL
    else:
        raise ValueError(f"Unknown LLM tier: {tier}")

    if not token or not model:
        raise RuntimeError(f"{tier} LLM credentials are missing in the environment.")

    # Same trick as Leo: Groq is OpenAI-compatible, so the model is prefixed with 'openai/'
    llm = LLM(model=f"openai/{model}", api_key=token, base_url=endpoint, temperature=temperature)
    _llm_cache[key] = llm
    return llm


def run_with_fallback(task: Callable[[Any], T], temperature: float = 0.5, prefer_small: bool = False) -> tuple[T, str]:
    """
    Runs task(llm). If the model fails (rate limit, token limit, server error)
    the SAME task is run again with the other model.

    prefer_small=True  -> start with the small/cheap fallback model (used for the Router and simple chat)

    Returns (result, tier_used) so the API can tell the frontend that the backup AI was used.
        result, tier = run_with_fallback(lambda llm: build_planning_crew(llm, ...).kickoff())
    """
    global _primary_blocked_until

    order = ["fallback", "primary"] if prefer_small else ["primary", "fallback"]
    if time.time() < _primary_blocked_until:
        order = ["fallback", "primary"]

    last_error: Exception | None = None
    for tier in order:
        try:
            result = task(get_llm(tier, temperature))
            return result, tier
        except Exception as exc:  # same broad catch as Leo: any LLM failure triggers the other model
            last_error = exc
            log.warning("LLM tier '%s' failed: %s", tier, exc, exc_info=True)
            if tier == "primary":
                _primary_blocked_until = time.time() + PRIMARY_COOLDOWN_SECONDS

    raise LLMUnavailableError("The AI service is busy right now. Please try again in a few minutes.") from last_error
