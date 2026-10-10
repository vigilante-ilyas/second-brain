"""Verified SQLite snapshots. Restore only into a NEW file; never overwrite."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile


def safe_path(value, *, existing=False):
    path = Path(value).expanduser().absolute()
    for component in (path, *path.parents):
        if component.is_symlink() or getattr(component, 'is_junction', lambda: False)():
            raise ValueError('Symlinks and junctions are not allowed.')
    if existing and not path.is_file():
        raise ValueError('Expected an existing regular file.')
    if not path.parent.is_dir():
        raise ValueError('Destination folder must already exist.')
    return path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate(path):
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
        conn.execute('PRAGMA query_only=ON')
        if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite integrity check failed.')
        if conn.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise ValueError('Foreign key check failed.')
        columns = {row[1] for row in conn.execute('PRAGMA table_info(memories)')}
        if not {'id', 'information', 'source', 'file_hash'} <= columns:
            raise ValueError('Not a supported Second Brain database.')
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'repayments' in tables:
            if conn.execute('SELECT 1 FROM repayments r LEFT JOIN memories m '
                            'ON m.id=r.debt_memory_id WHERE r.debt_memory_id IS NOT NULL '
                            'AND m.id IS NULL LIMIT 1').fetchone():
                raise ValueError('Orphan repayment history found.')


def backup(source, destination):
    source = safe_path(source, existing=True)
    destination = safe_path(destination)
    manifest = safe_path(str(destination) + '.json')
    if destination.exists() or manifest.exists():
        raise FileExistsError('Choose a new backup filename.')
    # SQLite backup captures committed WAL data too, unlike copying the main file.
    with tempfile.TemporaryDirectory(prefix='second_brain_backup_', dir=destination.parent) as folder:
        snapshot = Path(folder) / 'snapshot.db'
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(snapshot)) as dst:
                src.backup(dst)
        validate(snapshot)
        metadata = {'format': 1, 'sha256': digest(snapshot),
                    'created_utc': datetime.now(timezone.utc).isoformat()}
        # Exclusive creation refuses overwrite. A partial pair fails verification.
        with destination.open('xb') as target, snapshot.open('rb') as stream:
            import shutil
            shutil.copyfileobj(stream, target)
        with manifest.open('x', encoding='utf-8') as target:
            json.dump(metadata, target, indent=2)
    verify(destination)
    return destination


def verify(backup_file):
    path = safe_path(backup_file, existing=True)
    manifest = safe_path(str(path) + '.json', existing=True)
    metadata = json.loads(manifest.read_text(encoding='utf-8'))
    if metadata.get('format') != 1 or metadata.get('sha256') != digest(path):
        raise ValueError('Backup checksum/manifest mismatch.')
    validate(path)
    return path


def restore(backup_file, destination):
    path = verify(backup_file)
    destination = safe_path(destination)
    if destination.exists():
        raise FileExistsError('Restore requires a new file; existing files are preserved.')
    # Verify a private snapshot before publishing; source changes fail closed.
    with tempfile.TemporaryDirectory(prefix='second_brain_restore_', dir=destination.parent) as folder:
        snapshot = Path(folder) / 'restore.db'
        import shutil
        shutil.copyfile(path, snapshot)
        if digest(snapshot) != digest(path):
            raise ValueError('Backup changed during restore.')
        metadata = json.loads(Path(str(path) + '.json').read_text(encoding='utf-8'))
        if metadata.get('sha256') != digest(snapshot):
            raise ValueError('Backup changed during restore.')
        validate(snapshot)
        with destination.open('xb') as target, snapshot.open('rb') as stream:
            shutil.copyfileobj(stream, target)
    validate(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('backup', 'restore'):
        command = sub.add_parser(name)
        command.add_argument('source')
        command.add_argument('destination')
    sub.add_parser('verify').add_argument('source')
    args = parser.parse_args()
    try:
        if args.command == 'verify':
            verify(args.source)
        else:
            globals()[args.command](args.source, args.destination)
    except (OSError, ValueError, sqlite3.Error) as error:
        # Never print records, SQL results, or supplied paths.
        parser.exit(1, f'Recovery operation failed ({type(error).__name__}). Files were not overwritten.\n')
    print('Recovery operation completed and verified.')


if __name__ == '__main__':
    main()
