
import re
from datetime import date, timedelta

from database import get_all_memories
from financial_direction import detect_direction

from payment_tracker import get_payment_statuses
from date_interpreter import interpret_date


DEBT_LIST_PHRASES = [
    "who owes me money",
    "who owes me",
    "money owed to me",
    "pending debts",
    "pending debt"
]

DEBT_TOTAL_PHRASES = [
    "how much is owed to me",
    "how much money is owed to me",
    "how much do people owe me",
    "total owed to me",
    "total money owed to me"
]

DEBT_MAX_PHRASES = [
    "who owes me the most",
    "who owes me most",
    "largest debt",
    "biggest debt",
    "highest debt",
    "largest amount owed to me",
    "most money"
]

OWE_QUESTION_PHRASES = [
    "who do i owe",
    "do i owe anyone",
    "do i owe anybody",
    "how much do i owe",
    "money i owe",
    "my debts"
]

PERSON_DEBT_PHRASES = [
    "owe me",
    "owes me",
    "i owe",
    "debt",
    "borrowed",
    "borrow",
    "return",
    "repay",
    "payment"
]

DUE_TODAY_PHRASES = [
    "who needs to pay me today",
    "who has to pay me today",
    "who should pay me today",
    "who owes me today",
    "who is paying me today",
    "payments due today",
    "payment due today",
    "due to me today"
]

OVERDUE_PHRASES = [
    "which payments are overdue",
    "what payments are overdue",
    "who is overdue",
    "who has overdue payments",
    "overdue payments",
    "overdue debts",
    "overdue debt"
]

UPCOMING_PHRASES = [
    "what payments are coming up",
    "which payments are coming up",
    "upcoming payments",
    "upcoming debts",
    "who needs to pay me next",
    "who pays me next",
    "next payment due",
    "payments coming up"
]


def get_payments(today=None):
    return get_payment_statuses(today=today)


def answer_financial_date_range(question, today=None):
    """Return None only for unrecognized queries; never guess a deadline.

    Next N days = [today, today + N days), this week = [today, next
    Monday), before DATE = [today, DATE). All exclude overdue payments.
    Default today is the Windows local calendar date, not UTC.
    """
    text = " ".join(question.lower().split()).rstrip("?.!")
    finance = re.search(r"\b(payments?|debts?|repayments?|money|owe|owes|owed|pay|repay)\b", text)
    range_intents = re.findall(r"\bnext\s+\S+\s+days?\b|\bthis week\b|\bbefore\b", text)
    if not finance or not range_intents:
        return None
    today = today if today is not None else date.today()
    # Resolve query endpoints through the same interpreter as stored dates.
    before = re.search(r"\bbefore\s+(.+)$", text)
    next_days = re.search(r"\bnext\s+(\d+)\s+days?\b", text)
    if len(range_intents) != 1 or sum(bool(value) for value in (before, next_days, "this week" in text)) != 1:
        return "Please specify one date range: next N days, this week, or before a date."
    try:
        if before:
            resolved = interpret_date(before.group(1), today.isoformat())
            if resolved is None:
                return "I couldn't resolve that cutoff date. Please use an explicit date such as 2026-10-17."
            end = date.fromisoformat(resolved)
        elif next_days:
            days = int(next_days.group(1))
            if days < 1:
                return "Please specify a positive number of days."
            end = today + timedelta(days=days)
        else:
            end = today + timedelta(days=7 - today.weekday())
    except (ValueError, OverflowError):
        return "That date range is invalid or too large. Please specify a valid cutoff date or number of days."

    outgoing = bool(re.search(r"\bi owe\b|\bi (?:need to |have to |must )?pay\b|\bmy debts\b", text))
    direction = "I owe someone" if outgoing else "Someone owes me"
    payments = []
    for payment in get_payments(today=today):
        if (payment["direction"] != direction or payment["amount"] <= 0
                or payment.get("repayment_error")
                or payment["payment_status"] in ("Paid", "Fully repaid")
                or not payment.get("due_date")):
            continue
        due = date.fromisoformat(payment["due_date"])
        if today <= due < end:
            payments.append(payment)
    payments.sort(key=lambda payment: (payment["due_date"], payment["memory_id"]))
    scope = "you owe" if outgoing else "owed to you"
    lines = [f"Confirmed payments {scope} from {today.isoformat()} (inclusive) "
             f"to {end.isoformat()} (exclusive):", ""]
    if not payments:
        lines.append("No confirmed payments qualify.")
    for payment in payments:
        lines.append(f"{payment.get('person') or 'Unknown'}: Rs. {payment['amount']:,} "
                     f"(Due: {payment['due_date']})")
    lines.extend(["", f"Total outstanding: Rs. {sum(p['amount'] for p in payments):,}",
                  "Unknown due dates and records needing review are excluded."])
    return "\n".join(lines)


def get_money_owed_to_me():
    return [
        payment
        for payment in get_payments()
        if payment["direction"] == "Someone owes me" and payment["amount"] > 0
    ]


def get_money_i_owe():
    return [
        payment
        for payment in get_payments()
        if payment["direction"] == "I owe someone" and payment["amount"] > 0
    ]


def get_unclear_financial_records():
    return [
        payment
        for payment in get_payments()
        if payment["direction"] in {
            "Unknown",
            "Needs review"
        }
    ]


def question_has_person_debt_intent(question):
    question_lower = question.lower()

    return any(
        phrase in question_lower
        for phrase in PERSON_DEBT_PHRASES
    )


def get_person_payment_records():
    # Keep the tracker as the authority for pending records and due dates.
    # A pending record wins if the same event also has a Paid source:
    # do not silently clear an unresolved pending debt.
    records = [dict(payment) for payment in get_payments()]
    seen = {
        ("event", payment["event_id"])
        if payment.get("event_id")
        else ("memory", payment["memory_id"])
        for payment in records
    }

    for memory in get_all_memories():
        if (memory.get("category") != "Finance"
                or memory.get("status") != "Paid"
                or memory.get("money_amount") is None):
            continue
        event_id = memory.get("event_id")
        event_id = str(event_id).strip() if event_id is not None else None
        key = (("event", event_id) if event_id
               else ("memory", memory["id"]))
        if key in seen:
            continue
        seen.add(key)
        records.append({
            "person": memory.get("person"),
            "amount": memory["money_amount"],
            "direction": detect_direction(memory.get("information")),
            "due_date": None,
            "payment_status": "Paid",
            "memory_id": memory["id"],
            "event_id": event_id,
        })
    return records


def find_person_payments(question):
    if not question_has_person_debt_intent(question):
        return []
    question_lower = " ".join(question.lower().split())
    matches = []
    for payment in get_person_payment_records():
        person = " ".join((payment.get("person") or "").lower().split())
        if person and re.search(r"(?<!\w)" + re.escape(person) + r"(?!\w)",
                                question_lower):
            matches.append(payment)
    # Prefer the most specific name (Ann Smith over Ann).
    if matches:
        longest = max(len(payment["person"].strip()) for payment in matches)
        matches = [payment for payment in matches
                   if len(payment["person"].strip()) == longest]
    return matches


def find_person_payment(question):
    payments = find_person_payments(question)
    return payments[0] if payments else None


def answer_person_payments(question, payments):
    pending = [payment for payment in payments
               if payment["payment_status"] not in ("Paid", "Fully repaid")]
    settled = [payment for payment in payments
               if payment["payment_status"] == "Fully repaid"]
    paid = [payment for payment in payments
            if payment["payment_status"] == "Paid"]
    lines = []
    if not pending:
        person = payments[0].get("person") or "Unknown"
        lines.append(f"No pending debt is recorded involving {person}.")
    for payment in pending:
        lines.append(answer_person_payment(payment))
    for payment in settled:
        lines.append(answer_person_payment(payment))
    for payment in paid:
        person = payment.get("person") or "Unknown"
        amount = payment["amount"]
        direction = payment["direction"]
        if direction == "Someone owes me":
            text = f"{person} previously borrowed Rs. {amount:,} from you."
        elif direction == "I owe someone":
            text = f"You previously borrowed Rs. {amount:,} from {person}."
        else:
            text = (f"There is a historical Rs. {amount:,} financial record "
                    f"involving {person}, but its direction is unclear.")
        lines.append(text + " It is now marked Paid.\n"
                     + f"Memory ID: {payment['memory_id']}")
    return "\n\n".join(lines)


def format_due_date(payment):
    return payment.get("due_date") or "Unknown"


def answer_payments_by_status(status, heading, empty_message):
    payments = [
        payment
        for payment in get_money_owed_to_me()
        if payment["payment_status"] == status
    ]

    if not payments:
        return empty_message

    if status == "Upcoming":
        payments.sort(
            key=lambda payment: payment["due_date"] or "9999-12-31"
        )

    lines = [heading, ""]
    total = 0

    for payment in payments:
        person = payment.get("person") or "Unknown"
        amount = payment["amount"]
        due_date = format_due_date(payment)

        lines.append(
            f"{person}: Rs. {amount:,} "
            f"(Due: {due_date})"
        )

        total += amount

    lines.append("")
    lines.append(f"Total: Rs. {total:,}")

    return "\n".join(lines)


def answer_due_today():
    return answer_payments_by_status(
        "Due today",
        "People who owe you money due today:",
        "No confirmed incoming payments are due today."
    )


def answer_overdue():
    return answer_payments_by_status(
        "Overdue",
        "Overdue payments owed to you:",
        "No confirmed incoming payments are overdue."
    )


def answer_upcoming():
    return answer_payments_by_status(
        "Upcoming",
        "Upcoming payments owed to you:",
        "No confirmed incoming payments have a future due date."
    )


def answer_money_owed_to_me():
    payments = get_money_owed_to_me()
    unclear = get_unclear_financial_records()

    if not payments:
        lines = [
            "Nobody is clearly recorded as owing you money."
        ]
    else:
        lines = [
            "People clearly recorded as owing you money:",
            ""
        ]

        total = 0

        for payment in payments:
            person = payment.get("person") or "Unknown"
            amount = payment["amount"]

            lines.append(f"{person}: Rs. {amount:,}")
            total += amount

        lines.append("")
        lines.append(
            f"Total clearly owed to you: Rs. {total:,}"
        )

    if unclear:
        unclear_total = sum(
            payment["amount"]
            for payment in unclear
        )

        lines.append("")
        lines.append("Needs review:")

        for payment in unclear:
            person = payment.get("person") or "Unknown"
            amount = payment["amount"]

            lines.append(f"{person}: Rs. {amount:,}")

        lines.append(
            f"Unclear total: Rs. {unclear_total:,}"
        )
        lines.append(
            "These records are not included in "
            "the amount clearly owed to you."
        )

    return "\n".join(lines)


def answer_total_owed_to_me():
    payments = get_money_owed_to_me()
    unclear = get_unclear_financial_records()

    confirmed_total = sum(
        payment["amount"]
        for payment in payments
    )

    unclear_total = sum(
        payment["amount"]
        for payment in unclear
    )

    lines = [
        f"Total clearly owed to you: "
        f"Rs. {confirmed_total:,}."
    ]

    if unclear_total > 0:
        lines.append(
            f"An additional Rs. {unclear_total:,} "
            "is in records whose financial "
            "details need review."
        )
        lines.append(
            "The unclear amount is not included "
            "in the confirmed total."
        )

    return "\n".join(lines)


def answer_largest_debt_to_me():
    payments = get_money_owed_to_me()

    if not payments:
        return (
            "Nobody is clearly recorded as "
            "owing you money."
        )

    largest_amount = max(
        payment["amount"]
        for payment in payments
    )

    largest_payments = [
        payment
        for payment in payments
        if payment["amount"] == largest_amount
    ]

    if len(largest_payments) == 1:
        person = largest_payments[0].get("person") or "Unknown"

        return (
            f"{person} owes you the most money: "
            f"Rs. {largest_amount:,}."
        )

    people = ", ".join(
        payment.get("person") or "Unknown"
        for payment in largest_payments
    )

    return (
        f"The largest recorded debt is tied between "
        f"{people}: Rs. {largest_amount:,} each."
    )


def answer_money_i_owe():
    payments = get_money_i_owe()

    if not payments:
        return (
            "No pending record clearly shows "
            "that you owe someone money."
        )

    lines = [
        "People you are clearly recorded as owing:",
        ""
    ]

    total = 0

    for payment in payments:
        person = payment.get("person") or "Unknown"
        amount = payment["amount"]

        lines.append(f"{person}: Rs. {amount:,}")
        total += amount

    lines.append("")
    lines.append(
        f"Total you clearly owe: Rs. {total:,}"
    )

    return "\n".join(lines)


def answer_person_payment(payment):
    person = payment.get("person") or "Unknown"
    amount = payment["amount"]
    direction = payment["direction"]
    due_date = format_due_date(payment)
    payment_status = payment["payment_status"]

    if payment_status == "Fully repaid":
        lines = [
            f"The recorded debt involving {person} is fully repaid.",
            f"Original debt: Rs. {payment['original_amount']:,}.",
            f"Total repaid: Rs. {payment['repaid_amount']:,}.",
            "Remaining balance: Rs. 0.",
        ]
    elif direction == "Someone owes me":
        lines = [f"{person} owes you Rs. {amount:,}."]

    elif direction == "I owe someone":
        lines = [f"You owe {person} Rs. {amount:,}."]

    else:
        lines = [
            f"There is a pending Rs. {amount:,} "
            f"financial record involving {person}, "
            "and it needs review."
        ]
    if payment.get("repayment_error"):
        lines.append(f"Review reason: {payment['repayment_error']}")
    elif payment.get("repaid_amount", 0) > 0 and payment_status != "Fully repaid":
        lines.append(
            f"Original debt: Rs. {payment['original_amount']:,}; "
            f"total repaid: Rs. {payment['repaid_amount']:,}."
        )

    lines.append(f"Due date: {due_date}")
    lines.append(f"Payment status: {payment_status}")
    lines.append(f"Memory ID: {payment['memory_id']}")

    return "\n".join(lines)


def answer_structured_question(question, today=None):
    question_lower = " ".join(question.lower().split())
    question_lower = question_lower.rstrip("?.!")

    range_answer = answer_financial_date_range(question, today=today)
    if range_answer is not None:
        return range_answer

    # Date-specific questions must be handled before
    # broad debt phrases such as "who owes me".
    if any(
        phrase in question_lower
        for phrase in DUE_TODAY_PHRASES
    ):
        return answer_due_today()

    if any(
        phrase in question_lower
        for phrase in OVERDUE_PHRASES
    ):
        return answer_overdue()

    if any(
        phrase in question_lower
        for phrase in UPCOMING_PHRASES
    ):
        return answer_upcoming()

    if any(
        phrase in question_lower
        for phrase in DEBT_MAX_PHRASES
    ):
        return answer_largest_debt_to_me()

    if any(
        phrase in question_lower
        for phrase in DEBT_TOTAL_PHRASES
    ):
        return answer_total_owed_to_me()

    if any(
        phrase in question_lower
        for phrase in DEBT_LIST_PHRASES
    ):
        return answer_money_owed_to_me()

    if any(
        phrase in question_lower
        for phrase in OWE_QUESTION_PHRASES
    ):
        return answer_money_i_owe()

    person_payments = find_person_payments(question)

    if person_payments:
        return answer_person_payments(question, person_payments)

    return None


if __name__ == "__main__":
    question = input("Ask your Second Brain: ")

    answer = answer_structured_question(question)

    if answer is None:
        print(
            "This question is not handled "
            "by structured search yet."
        )
    else:
        print()
        print(answer)
