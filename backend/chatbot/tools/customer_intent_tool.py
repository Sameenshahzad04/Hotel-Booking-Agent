"""
Customer Intent and Sentiment Analyzer for Pearl Continental (PC) Hotel Lahore.

Performs intent classification and sentiment detection in ONE single LLM call
and returns a clean dictionary directly.
"""

import sys
from pathlib import Path
from typing import Dict
from langchain_core.tools import tool

# Ensure backend root directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import get_llm

VALID_INTENTS = ["BOOKING", "CANCEL", "REFUND", "CLAIM", "INFORMATION", "ESCALATE", "OTHER"]

VALID_SENTIMENTS = [
    "positive", "appreciative", "neutral", "confused",
    "frustrated", "angry", "urgent", "distressed"
]

CLASSIFIER_PROMPT = """You are the official Customer Interaction Classifier for Pearl Continental (PC) Hotel Lahore.

Analyze the customer message and determine BOTH their INTENT and their EMOTIONAL SENTIMENT using ONLY the categories below.

Customer Message:
"{message}"

Categories for INTENT (Choose EXACTLY ONE):
- BOOKING: Inquiring about available rooms, checking rates/dates, or wanting to book a room.
- CANCEL: Wants to cancel a reservation or release a booking hold.
- REFUND: Asking for money back, refund terms, payment disputes, or financial reversal.
- CLAIM: Wants to link/find an existing booking using their confirmation code and email.
- INFORMATION: Asking about hotel rules, check-in/out times, breakfast, pool, gym, spa, dining, or general hotel policies.
- ESCALATE: Asks to speak with a human, manager, live agent, or displays severe anger/threats.
- OTHER: Query is completely unrelated to hotel stays or hospitality (coding, math, cooking, etc.).

Categories for SENTIMENT (Choose EXACTLY ONE):
- neutral: Objective, standard matter-of-fact question.
- positive: Happy, expressing thanks or compliments.
- confused: Unsure, needs clarification or guidance.
- frustrated: Annoyed, complaining about delays or difficulties.
- angry: Highly aggressive, demanding, furious.
- urgent: Time-sensitive panic, needs immediate assistance.

Output strictly in this format (nothing else):
<INTENT> | <SENTIMENT> | <ONE_SENTENCE_REASON>
"""


@tool
def analyze_customer_intent_sentiment_tool(message: str) -> Dict[str, str]:
    """
    Analyzes customer intent and emotional sentiment in ONE single LLM call.
    Returns:
        dict: {"intent": str, "sentiment": str, "reason": str, "summary": str}
    """
    if not message or not message.strip():
        return {
            "intent": "INFORMATION",
            "sentiment": "neutral",
            "reason": "Empty message.",
            "summary": "Intent: INFORMATION | Sentiment: neutral | Reason: Empty message."
        }

    text_lower = message.lower()

    # Fast-path for human representative requests
    human_keywords = [
        "talk to human", "speak to human", "real person", "human agent",
        "live agent", "talk to manager", "connect to agent"
    ]
    if any(kw in text_lower for kw in human_keywords):
        return {
            "intent": "ESCALATE",
            "sentiment": "frustrated",
            "reason": "Customer explicitly requested human representative.",
            "summary": "Intent: ESCALATE | Sentiment: frustrated | Reason: Customer requested human representative."
        }

    intent = "INFORMATION"
    sentiment = "neutral"
    reason = "Standard inquiry."

    try:
        llm = get_llm()
        response = llm.invoke(CLASSIFIER_PROMPT.format(message=message.strip()))
        raw = response.content.strip()

        # Parse "INTENT | SENTIMENT | REASON"
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) >= 2:
            intent_raw = parts[0].upper()
            sentiment_raw = parts[1].lower()
            reason = parts[2] if len(parts) > 2 else "Message analyzed."

            intent = next((i for i in VALID_INTENTS if i in intent_raw), "INFORMATION")
            sentiment = next((s for s in VALID_SENTIMENTS if s in sentiment_raw), "neutral")

    except Exception as e:
        print(f"⚠️ Intent & Sentiment tool fallback due to: {e}")
        if any(k in text_lower for k in ["cancel", "cancel hold", "cancel booking"]):
            intent = "CANCEL"
        elif any(k in text_lower for k in ["refund", "money back", "reversal"]):
            intent = "REFUND"
        elif any(k in text_lower for k in ["claim", "find booking", "link booking"]):
            intent = "CLAIM"
        elif any(k in text_lower for k in ["book", "room", "availability", "reserve", "dates"]):
            intent = "BOOKING"
        elif any(k in text_lower for k in ["manager", "angry", "terrible", "worst", "complaint"]):
            intent = "ESCALATE"
        else:
            intent = "INFORMATION"

        sentiment = "angry" if "angry" in text_lower or "worst" in text_lower else "neutral"
        reason = "Keyword fallback analysis."

    return {
        "intent": intent,
        "sentiment": sentiment,
        "reason": reason,
        "summary": f"Intent: {intent} | Sentiment: {sentiment} | Reason: {reason}"
    }
