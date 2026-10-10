"""Standalone repayment ledger. Running this file never records a payment.

Future UI: show get_balance(), ask the user to confirm the debt and amount,
then call record_repayment(..., confirmed=True). Pass amount=None for full
repayment. Amounts are positive integer rupees, matching the existing schema.
Duplicate event IDs require manual review; this module never merges debts.
"""

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from financial_direction import detect_direction
from database import install_repayment_safeguards


class RepaymentError(ValueError):
    """A repayment cannot safely proceed."""


class RepaymentManager:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path is not None else (
            Path(__file__).resolve().with_name("second_brain.db")
        )

    @contextmanager
    def _connection(self, writable=False):
        # mode=rw refuses to create a missing database; reads are read-only.
        uri = self.db_path.resolve().as_uri() + (
            "?mode=rw" if writable else "?mode=ro"
        )
        connection = sqlite3.connect(uri, uri=True, isolation_level=None,
                                     timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                raise RepaymentError("SQLite foreign keys are not enabled.")
            if writable:
                install_repayment_safeguards(connection)
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _positive_integer(value, label):
        if type(value) is not int or value <= 0:
            raise RepaymentError(f"{label} must be a positive integer.")

    def _balance(self, connection, debt_memory_id):
        self._positive_integer(debt_memory_id, "Debt memory ID")
        debt = connection.execute(
            "SELECT * FROM memories WHERE id = ?", (debt_memory_id,)
        ).fetchone()
        if debt is None:
            raise RepaymentError("Debt memory does not exist.")
        if debt["category"] != "Finance" or debt["status"] != "Pending":
            raise RepaymentError("Debt must be a Pending Finance memory.")
        self._positive_integer(debt["money_amount"], "Original debt amount")
        direction = detect_direction(debt["information"])
        if direction not in ("Someone owes me", "I owe someone"):
            raise RepaymentError("Debt direction needs clarification.")
        if debt["event_id"] and str(debt["event_id"]).strip():
            siblings = connection.execute(
                "SELECT id FROM memories WHERE trim(event_id) = trim(?)",
                (debt["event_id"],)
            ).fetchall()
            if len(siblings) > 1:
                ids = ", ".join(str(row["id"]) for row in siblings)
                raise RepaymentError(
                    f"Duplicate event_id on memories {ids}; review before repayment."
                )
        amounts = connection.execute(
            "SELECT amount FROM repayments WHERE debt_memory_id = ?",
            (debt_memory_id,)
        ).fetchall()
        for row in amounts:
            self._positive_integer(row["amount"], "Existing repayment amount")
        repaid = sum(row["amount"] for row in amounts)
        outstanding = debt["money_amount"] - repaid
        if outstanding < 0:
            raise RepaymentError("Existing repayments exceed the original debt.")
        return {
            "debt_memory_id": debt_memory_id,
            "person": debt["person"],
            "direction": direction,
            "original_amount": debt["money_amount"],
            "repaid_amount": repaid,
            "outstanding_amount": outstanding,
            "fully_repaid": outstanding == 0,
        }

    def get_balance(self, debt_memory_id):
        """Read a consistent balance without changing any data."""
        with self._connection() as connection:
            connection.execute("BEGIN")
            try:
                result = self._balance(connection, debt_memory_id)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def get_repayment_history(self, debt_memory_id):
        """Read this exact memory's ledger in recording order (oldest first).

        History stays readable for Paid, unclear or duplicate memories so it
        can be reviewed. It never merges events or authorizes a new payment.
        """
        self._positive_integer(debt_memory_id, "Debt memory ID")
        with self._connection() as connection:
            connection.execute("BEGIN")
            try:
                debt = connection.execute(
                    "SELECT category FROM memories WHERE id = ?",
                    (debt_memory_id,)
                ).fetchone()
                if debt is None:
                    raise RepaymentError("Debt memory does not exist.")
                if debt["category"] != "Finance":
                    raise RepaymentError("Repayment history requires a Finance memory.")
                rows = connection.execute(
                    "SELECT id, debt_memory_id, amount, payment_date, source, created_at "
                    "FROM repayments WHERE debt_memory_id = ? ORDER BY id ASC",
                    (debt_memory_id,)
                ).fetchall()
                result = [dict(row) for row in rows]
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def record_repayment(self, debt_memory_id, amount=None, *, confirmed=False,
                         payment_date=None, source=None):
        """Record partial/full repayment after the UI obtains confirmation.

        confirmed must be exactly True. No confirmation is inferred. The UI
        must obtain it for each action; this boolean is a guard, not a UI.
        """
        if confirmed is not True:
            raise RepaymentError("Explicit user confirmation is required.")
        if amount is not None:
            self._positive_integer(amount, "Repayment amount")
        if payment_date is None:
            payment_date = date.today().isoformat()
        if not isinstance(payment_date, str):
            raise RepaymentError("Payment date must be YYYY-MM-DD.")
        try:
            parsed = date.fromisoformat(payment_date)
        except ValueError as exc:
            raise RepaymentError("Payment date must be YYYY-MM-DD.") from exc
        if parsed.isoformat() != payment_date:
            raise RepaymentError("Payment date must be YYYY-MM-DD.")
        if source is not None and not isinstance(source, str):
            raise RepaymentError("Source must be text or None.")
        with self._connection(writable=True) as connection:
            # Serialize balance check and insert, including competing writers.
            connection.execute("BEGIN IMMEDIATE")
            try:
                balance = self._balance(connection, debt_memory_id)
                payable = balance["outstanding_amount"]
                actual_amount = payable if amount is None else amount
                if payable == 0:
                    raise RepaymentError("Debt is already fully repaid.")
                if actual_amount > payable:
                    raise RepaymentError("Repayment exceeds the outstanding balance.")
                cursor = connection.execute(
                    "INSERT INTO repayments "
                    "(debt_memory_id, amount, payment_date, source) "
                    "VALUES (?, ?, ?, ?)",
                    (debt_memory_id, actual_amount, payment_date, source)
                )
                result = self._balance(connection, debt_memory_id)
                result.update(repayment_id=cursor.lastrowid,
                              payment_amount=actual_amount,
                              payment_date=payment_date)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise


if __name__ == "__main__":
    print("Repayment manager ready. No payment was recorded.")
    print("Use RepaymentManager.get_balance() to preview a debt.")
    print("Recording requires explicit user confirmation.")
