import re
from database import get_all_memories


def normalize_text(text):
    text = text.lower().strip()
    text = re.sub(r"[.,!?]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def find_duplicate(information):
    new_text = normalize_text(information)

    for memory in get_all_memories():
        existing_text = normalize_text(
            memory.get("information") or ""
        )

        if new_text == existing_text:
            return memory

    return None


# Semantic matches are review suggestions, never automatic duplicate verdicts.
from functools import lru_cache
from decimal import Decimal, InvalidOperation
import sys
from date_interpreter import interpret_date, parse_absolute_date

SEMANTIC_THRESHOLD = 0.82


@lru_cache(maxsize=1)
def get_embedding_model():
    # Reuse the retrieval model if it is already loaded. Do not import rag:
    # importing it would initialize another model as a side effect.
    rag_module = sys.modules.get("rag")
    if rag_module is not None and hasattr(rag_module, "model"):
        return rag_module.model
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)


def _known(value):
    return normalize_text(str("" if value is None else value)) not in {"", "unknown", "none", "null", "n/a"}


def _amounts(memory):
    if _known(memory.get("money_amount")):
        values = [str(memory["money_amount"])]
    else:
        values = re.findall(r"(?:rs\.?|pkr|rupees)\s*([\d,]+(?:\.\d+)?)",
                            memory.get("information") or "", re.I)
    try:
        return {Decimal(value.replace(",", "")) for value in values}
    except InvalidOperation:
        return set()


def _dates(memory):
    resolved = interpret_date(memory.get("event_date"), memory.get("date"))
    if resolved:
        return {resolved}
    text = memory.get("information") or ""
    expressions = re.findall(
        r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]+\s+\d{4}|"
        r"[A-Za-z]+\s+\d{1,2},?\s+\d{4})\b", text)
    return {parsed.isoformat() for expression in expressions
            if (parsed := parse_absolute_date(expression)) is not None}


def _normalize_location(value):
    """Treat the observed home wording variants as the same location.

    Keep other place names intact: removing prepositions generally could
    collapse distinct named places. This changes comparison only, not storage.
    """
    text = normalize_text(str(value))
    return "home" if text in {"home", "at home"} else text


def _conflicting_events(new, existing):
    for field in ("event_id", "person", "location"):
        a, b = new.get(field), existing.get(field)
        normalizer = _normalize_location if field == "location" else normalize_text
        if _known(a) and _known(b) and normalizer(str(a)) != normalizer(str(b)):
            return True
    for getter in (_amounts, _dates):
        a, b = getter(new), getter(existing)
        if a and b and a != b:
            return True
    return False


def review_duplicates(memory, memories=None, model=None):
    """Return exact protection and all plausible semantic/event-ID matches.

    Missing facts are uncertainty, not evidence of a distinct event. A score
    is similarity, not probability. No database writes occur here.
    """
    if not (memory.get("information") or "").strip():
        raise ValueError("Information cannot be empty.")
    records = get_all_memories() if memories is None else memories
    exact = next((item for item in records if normalize_text(item.get("information") or "")
                  == normalize_text(memory["information"])), None)
    if exact:
        return {"exact": exact, "candidates": []}
    eligible = [item for item in records if (item.get("information") or "").strip()
                and not _conflicting_events(memory, item)]
    if not eligible:
        return {"exact": None, "candidates": []}
    from sentence_transformers.util import cos_sim
    encoder = model if model is not None else get_embedding_model()
    embeddings = encoder.encode([memory["information"]] +
                                [item["information"] for item in eligible])
    scores = cos_sim(embeddings[:1], embeddings[1:])[0].tolist()
    candidates = []
    for item, score in zip(eligible, scores):
        same_event = _known(memory.get("event_id")) and memory.get("event_id") == item.get("event_id")
        if same_event or score >= SEMANTIC_THRESHOLD:
            candidates.append({"memory": item, "score": float(score),
                               "reason": "Same event ID" if same_event else "Similar wording / meaning"})
    candidates.sort(key=lambda item: (-item["score"], item["memory"]["id"]))
    return {"exact": None, "candidates": candidates}


def require_duplicate_approval(review, approved_ids=None):
    """Exact duplicates cannot be overridden; every candidate needs approval."""
    if review["exact"]:
        raise ValueError(f"Exact duplicate of memory #{review['exact']['id']}. Nothing was saved.")
    candidate_ids = {item["memory"]["id"] for item in review["candidates"]}
    if not candidate_ids.issubset(set(approved_ids or ())):
        raise ValueError("Potential duplicates require explicit approval. Review the matches again.")


if __name__ == "__main__":
    test_memory = (
        "Fahad borrowed Rs. 1,200 from me for a taxi "
        "and will return it tomorrow."
    )

    duplicate = find_duplicate(test_memory)

    if duplicate:
        print("Duplicate found!")
        print("Memory ID:", duplicate["id"])
        print("Person:", duplicate["person"])
        print("Source:", duplicate["source"])
    else:
        print("No duplicate found.")
