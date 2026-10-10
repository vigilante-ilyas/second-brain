"""Initialize this checkout's empty storage, preserving existing records."""
from contextlib import closing
from pathlib import Path
import database
from repayment_manager import RepaymentManager

def initialize():
    expected = Path(__file__).resolve().with_name('second_brain.db')
    if Path(database.DATABASE_NAME).resolve() != expected or RepaymentManager().db_path.resolve() != expected:
        raise RuntimeError('Memory and repayment storage must use this checkout.')
    database.create_database()
    with closing(database.get_connection()) as conn, conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS repayments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            debt_memory_id INTEGER NOT NULL REFERENCES memories(id),
            amount INTEGER NOT NULL CHECK(amount > 0),
            payment_date TEXT, source TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        columns = {row[1] for row in conn.execute('PRAGMA table_info(repayments)')}
        if not {'id','debt_memory_id','amount','payment_date','source','created_at'} <= columns:
            raise RuntimeError('Unsupported repayment schema; review a backup before migrating.')
        database.install_repayment_safeguards(conn)
        if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise RuntimeError('Database integrity check failed.')
        if conn.execute('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError('Database reference check failed.')
    print('Local memory and repayment storage initialized and checked.')

if __name__ == '__main__': initialize()
