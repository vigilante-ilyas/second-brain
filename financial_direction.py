import re

from database import get_all_memories


def detect_direction(information):
    if not information:
        return "Unknown"

    text = re.sub(
        r"\s+",
        " ",
        str(information).lower()
    ).strip()

    # Money you owe someone else
    outgoing_patterns = [
        r"\bi borrowed\b.*\bfrom\b",
        r"\bi owe\b",
        r"\bmy debt to\b",
        r"\bi need to repay\b",
        r"\bi have to repay\b",
        r"\bi borrowed\b"
    ]

    # Money someone owes you
    incoming_patterns = [
        r"\bborrowed\b.*\bfrom me\b",
        r"\bowes me\b",
        r"\bowe me\b",
        r"\bi lent\b",
        r"\bi loaned\b",
        r"\bi gave\b.*\bloan\b"
    ]

    outgoing = any(
        re.search(pattern, text)
        for pattern in outgoing_patterns
    )

    incoming = any(
        re.search(pattern, text)
        for pattern in incoming_patterns
    )

    if outgoing and incoming:
        return "Needs review"

    if outgoing:
        return "I owe someone"

    if incoming:
        return "Someone owes me"

    return "Unknown"


def review_financial_memories():
    memories = get_all_memories()

    print("\nSECOND BRAIN - FINANCIAL DIRECTION")
    print("=" * 50)

    for memory in memories:

        if memory.get("category") != "Finance":
            continue

        if memory.get("status") != "Pending":
            continue

        direction = detect_direction(
            memory.get("information")
        )

        print(
            f"\nMemory ID: {memory['id']}"
        )

        print(
            f"Person: {memory.get('person')}"
        )

        print(
            f"Amount: Rs. "
            f"{memory.get('money_amount') or 0:,}"
        )

        print(
            f"Information: {memory.get('information')}"
        )

        print(
            f"Direction: {direction}"
        )


if __name__ == "__main__":
    review_financial_memories()