import sqlite3
from pathlib import Path

DATABASE_NAME = str(Path(__file__).resolve().with_name("second_brain.db"))



class MemoryDeletionBlocked(ValueError):
    """A memory must be retained to preserve its repayment history."""


def install_repayment_safeguards(connection):
    """Install persistent guards; they work even with foreign_keys OFF.

    Execute individual statements so the caller's transaction is preserved.
    Older databases without a repayment ledger need no guards yet.
    """
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )}
    if not {'memories', 'repayments'} <= tables:
        return
    guards = (
        ("protect_memory_repayment_delete", "BEFORE DELETE ON memories",
         "EXISTS (SELECT 1 FROM repayments WHERE debt_memory_id = OLD.id)",
         "memory_has_repayments"),
        ("protect_memory_repayment_id", "BEFORE UPDATE OF id ON memories",
         "NEW.id IS NOT OLD.id AND EXISTS "
         "(SELECT 1 FROM repayments WHERE debt_memory_id = OLD.id)",
         "memory_has_repayments"),
        ("protect_repayment_parent_insert", "BEFORE INSERT ON repayments",
         "NEW.debt_memory_id IS NOT NULL AND NOT EXISTS "
         "(SELECT 1 FROM memories WHERE id = NEW.debt_memory_id)",
         "repayment_parent_missing"),
        ("protect_repayment_parent_update",
         "BEFORE UPDATE OF debt_memory_id ON repayments",
         "NEW.debt_memory_id IS NOT NULL AND NOT EXISTS "
         "(SELECT 1 FROM memories WHERE id = NEW.debt_memory_id)",
         "repayment_parent_missing"),
    )
    for name, event, condition, message in guards:
        connection.execute(
            f"CREATE TRIGGER IF NOT EXISTS {name} {event} "
            f"WHEN {condition} BEGIN SELECT RAISE(ABORT, '{message}'); END"
        )


def get_connection():
    connection = sqlite3.connect(DATABASE_NAME)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise sqlite3.DatabaseError("SQLite foreign keys are not enabled.")
        install_repayment_safeguards(connection)
        return connection
    except BaseException:
        connection.close()
        raise


def create_database():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person TEXT,
            date TEXT,
            information TEXT NOT NULL,
            source TEXT,
            page INTEGER,
            file_hash TEXT,
            what TEXT,
            money_amount INTEGER,
            value REAL,
            category TEXT,
            status TEXT,
            location TEXT,
            event_date TEXT,
            event_id TEXT
        )
    """)

    install_repayment_safeguards(connection)
    connection.commit()
    connection.close()


def add_memory_to_db(memory):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO memories (
            person,
            date,
            information,
            source,
            page,
            file_hash,
            what,
            money_amount,
            value,
            category,
            status,
            location,
            event_date,
            event_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        memory.get("person"),
        memory.get("date"),
        memory.get("information"),
        memory.get("source"),
        memory.get("page"),
        memory.get("file_hash"),
        memory.get("what"),
        memory.get("money_amount"),
        memory.get("value"),
        memory.get("category"),
        memory.get("status"),
        memory.get("location"),
        memory.get("event_date"),
        memory.get("event_id")
    ))

    connection.commit()
    connection.close()


def get_all_memories():
    connection = get_connection()
    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()
    cursor.execute("SELECT * FROM memories")

    rows = cursor.fetchall()
    connection.close()

    return [dict(row) for row in rows]


def get_memory_by_id(memory_id):
    connection = get_connection()
    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM memories WHERE id = ?",
        (memory_id,)
    )

    row = cursor.fetchone()
    connection.close()

    if row is None:
        return None

    return dict(row)


def update_memory(memory_id, memory):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE memories
        SET
            person = ?,
            date = ?,
            information = ?,
            source = ?,
            page = ?,
            file_hash = ?,
            what = ?,
            money_amount = ?,
            value = ?,
            category = ?,
            status = ?,
            location = ?,
            event_date = ?,
            event_id = ?
        WHERE id = ?
    """, (
        memory.get("person"),
        memory.get("date"),
        memory.get("information"),
        memory.get("source"),
        memory.get("page"),
        memory.get("file_hash"),
        memory.get("what"),
        memory.get("money_amount"),
        memory.get("value"),
        memory.get("category"),
        memory.get("status"),
        memory.get("location"),
        memory.get("event_date"),
        memory.get("event_id"),
        memory_id
    ))

    connection.commit()

    updated_rows = cursor.rowcount

    connection.close()

    return updated_rows > 0


def delete_memory(memory_id):
    """Delete only memories without repayments, atomically.

    Keep the boolean contract for deleted/missing memories and raise a clear
    domain error for protected memories, regardless of category or status.
    """
    connection = get_connection()
    try:
        with connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE id = ?", (memory_id,)
            )
            return cursor.rowcount > 0
    except sqlite3.IntegrityError as error:
        if "memory_has_repayments" in str(error):
            raise MemoryDeletionBlocked(
                f"Memory #{memory_id} cannot be deleted because it has "
                "repayment history. The memory and all repayments were preserved."
            ) from error
        raise
    finally:
        connection.close()



def add_document_memories_to_db(document_memories, *, validate_before_insert=None):
    """Validate and save one whole file atomically, including duplicate checks."""
    if not document_memories:
        return 0
    document_memories = list(document_memories)
    if not document_memories:
        return 0
    new_hash = document_memories[0].get("file_hash")
    source = document_memories[0].get("source")
    if not new_hash or not source:
        raise ValueError("Document memories require a file hash and source.")
    pages = set()
    for memory in document_memories:
        if memory.get("file_hash") != new_hash or memory.get("source") != source:
            raise ValueError("A document batch must contain one file hash and source.")
        information = memory.get("information")
        if not isinstance(information, str) or not information.strip():
            raise ValueError("Document memories require readable text.")
        page = memory.get("page")
        if page is not None and (type(page) is not int or page < 1):
            raise ValueError("Document page numbers must be positive integers.")
        if page in pages:
            raise ValueError("A document batch cannot contain duplicate pages.")
        pages.add(page)
    connection = get_connection()
    try:
        # Serialize the check and insert; concurrent imports cannot both pass.
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM memories WHERE file_hash = ?", (new_hash,))
        if cursor.fetchone()[0] > 0:
            connection.rollback()
            return 0
        if validate_before_insert is not None:
            # Review against the same locked snapshot as the insertion.
            connection.row_factory = sqlite3.Row
            records = [dict(row) for row in connection.execute('SELECT * FROM memories')]
            validate_before_insert(records)
        for memory in document_memories:
    
            cursor.execute("""
                INSERT INTO memories (
                    person,
                    date,
                    information,
                    source,
                    page,
                    file_hash,
                    what,
                    money_amount,
                    value,
                    category,
                    status,
                    location,
                    event_date,
                    event_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                memory.get("person"),
                memory.get("date"),
                memory.get("information"),
                memory.get("source"),
                memory.get("page"),
                memory.get("file_hash"),
                memory.get("what"),
                memory.get("money_amount"),
                memory.get("value"),
                memory.get("category"),
                memory.get("status"),
                memory.get("location"),
                memory.get("event_date"),
                memory.get("event_id")
            ))
        connection.commit()
        return len(document_memories)
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    create_database()
    print("Second Brain database ready.")
