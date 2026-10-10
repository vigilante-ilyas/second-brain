import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from duplicate_checker import normalize_text, review_duplicates, require_duplicate_approval
from query_router import format_rag_answer

class DisplayAndDuplicateTests(unittest.TestCase):
    def test_blank_evidence_marker_removed(self):
        self.assertEqual(format_rag_answer('Information unavailable.\nUSED_EVIDENCE:', []), 'Information unavailable.')

    def test_valid_citation_kept_and_invalid_index_ignored(self):
        rows = [{'memory': {'source':'synthetic-note'}}]
        self.assertEqual(format_rag_answer('Green.\nUSED_EVIDENCE: 1,99', rows), 'Green.\n\nSource: synthetic-note')

    def test_newline_before_period_is_exact_duplicate(self):
        review = review_duplicates({'information':'Synthetic Alex uses locker nine.'},
            memories=[{'id':1,'information':'Synthetic Alex uses locker nine\n.'}])
        self.assertEqual(review['exact']['id'], 1)
        with self.assertRaises(ValueError): require_duplicate_approval(review, {1})

    def test_whitespace_and_punctuation_normalize(self):
        self.assertEqual(normalize_text('  HELLO!\n '), normalize_text('hello'))

class BootstrapTests(unittest.TestCase):
    def test_fresh_storage_repeat_launch_and_confirmed_repayment(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            target=Path(folder)
            for name in ('bootstrap.py','database.py','repayment_manager.py','financial_direction.py'):
                shutil.copyfile(ROOT/name,target/name)
            command=[sys.executable,str(target/'bootstrap.py')]
            subprocess.run(command,cwd=target,check=True,capture_output=True)
            db=target/'second_brain.db'
            with closing(sqlite3.connect(db)) as c, c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM memories').fetchone()[0],0)
                c.execute("INSERT INTO memories(person,information,category,status,money_amount) VALUES('Synthetic Omar','Synthetic Omar owes me','Finance','Pending',600)")
            subprocess.run(command,cwd=target,check=True,capture_output=True)
            code="""from repayment_manager import RepaymentManager, RepaymentError
m=RepaymentManager()
try: m.record_repayment(1,100)
except RepaymentError: pass
else: raise AssertionError('confirmation bypass')
assert m.record_repayment(1,100,confirmed=True)['outstanding_amount']==500
"""
            subprocess.run([sys.executable,'-c',code],cwd=target,check=True,capture_output=True)
            with closing(sqlite3.connect(db)) as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM memories').fetchone()[0],1)
                self.assertEqual(c.execute('SELECT amount FROM repayments').fetchone()[0],100)
                self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

if __name__=='__main__': unittest.main()
