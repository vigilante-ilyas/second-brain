from datetime import date

import database
from database import get_all_memories
from date_interpreter import interpret_date
from financial_direction import detect_direction
from repayment_manager import RepaymentManager, RepaymentError


def get_payment_statuses(today=None):
    if today is None:
        today = date.today()

    results = []
    grouped_events = {}
    # Follow the same path as database reads, including an isolated test DB.
    manager = RepaymentManager(database.DATABASE_NAME)

    for memory in get_all_memories():

        if memory.get("category") != "Finance":
            continue

        if memory.get("status") != "Pending":
            continue

        amount = memory.get("money_amount")

        if amount is None:
            continue

        event_id = memory.get("event_id")
        event_id = str(event_id).strip() if event_id is not None else None

        unique_key = (
            ("event", event_id)
            if event_id
            else ("memory", memory["id"])
        )

        direction = detect_direction(
            memory.get("information")
        )

        due_date_text = interpret_date(
            memory.get("event_date"),
            memory.get("date")
        )

        if due_date_text is None:
            payment_status = "Unknown due date"
        else:
            due_date = date.fromisoformat(
                due_date_text
            )

            if due_date < today:
                payment_status = "Overdue"
            elif due_date == today:
                payment_status = "Due today"
            else:
                payment_status = "Upcoming"

        payment = {
            "person": memory.get("person"),
            "amount": amount,
            "direction": direction,
            "due_date": due_date_text,
            "payment_status": payment_status,
            "memory_id": memory["id"],
            "event_id": event_id
        }
        payment["original_amount"] = amount
        try:
            balance = manager.get_balance(memory["id"])
            payment["amount"] = balance["outstanding_amount"]
            payment["repaid_amount"] = balance["repaid_amount"]
            payment["fully_repaid"] = balance["fully_repaid"]
            if balance["fully_repaid"]:
                # Retain history for person questions and the Finance screen.
                payment["payment_status"] = "Fully repaid"
        except RepaymentError as error:
            # Ambiguity and invalid ledgers must never become confirmed debt.
            payment["direction"] = "Needs review"
            payment["repayment_error"] = str(error)
            payment["amount"] = amount if type(amount) is int and amount > 0 else 0

        if unique_key not in grouped_events:
            grouped_events[unique_key] = payment
            results.append(payment)
        else:
            existing = grouped_events[unique_key]

            # Preserve a known due date if another
            # source for the same event provides it.
            if (
                existing["due_date"] is None
                and due_date_text is not None
            ):
                existing["due_date"] = due_date_text
                existing["payment_status"] = (
                    payment_status
                )

            # Shared event IDs remain one review item, even if sources agree.
            # Do not merge repayments or choose a canonical debt automatically.
            existing["direction"] = "Needs review"
            existing["repayment_error"] = payment.get(
                "repayment_error", "Duplicate event_id requires manual review."
            )

    return results


def summarize_payments(payments):

    totals = {
        "Someone owes me": 0,
        "I owe someone": 0,
        "Unknown": 0,
        "Needs review": 0
    }

    for payment in payments:
        direction = payment["direction"]

        if direction not in totals:
            direction = "Needs review"

        totals[direction] += payment["amount"]

    return totals


if __name__ == "__main__":

    print("\nSECOND BRAIN - DIRECTION-AWARE PAYMENT TRACKER")
    print("=" * 55)

    payments = get_payment_statuses()

    for payment in payments:

        print(
            f"\nPerson: {payment['person']}"
        )

        print(
            f"Amount: Rs. {payment['amount']:,}"
        )

        print(
            f"Direction: {payment['direction']}"
        )

        print(
            f"Due date: "
            f"{payment['due_date'] or 'Unknown'}"
        )

        print(
            f"Payment status: "
            f"{payment['payment_status']}"
        )

    totals = summarize_payments(payments)

    print("\n" + "=" * 55)
    print("FINANCIAL SUMMARY")
    print("=" * 55)

    print(
        f"Someone owes me: Rs. "
        f"{totals['Someone owes me']:,}"
    )

    print(
        f"I owe someone: Rs. "
        f"{totals['I owe someone']:,}"
    )

    print(
        f"Needs clarification: Rs. "
        f"{totals['Unknown'] + totals['Needs review']:,}"
    )
