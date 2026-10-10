"""Reviewed voice ingestion. Importing this module performs no work."""
import hashlib
from pathlib import Path
from voice_reader import transcribe_audio
from database import add_document_memories_to_db
from duplicate_checker import review_duplicates, require_duplicate_approval

def get_file_hash(path):
    with open(path, 'rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()

def prepare_voice(audio_path, **options):
    path = str(Path(audio_path).expanduser().resolve(strict=True))
    before = get_file_hash(path)
    transcript = transcribe_audio(path, **options)
    if get_file_hash(path) != before:
        raise ValueError('Audio changed during transcription. Start again.')
    if not transcript.strip():
        raise ValueError('No speech detected. Nothing saved.')
    return dict(person='Voice Note', date='Unknown', information=transcript, source=path, page=None, file_hash=before)

def save_reviewed_voice(memory, *, approved=False, approved_ids=None, reviewed_records=None):
    if approved is not True:
        raise ValueError('Explicit approval required. Nothing saved.')
    if get_file_hash(memory['source']) != memory['file_hash']:
        raise ValueError('Audio changed since review. Start again.')
    review = review_duplicates(memory)
    if reviewed_records is not None and any(
        reviewed_records.get(item['memory']['id']) != item['memory']
        for item in review['candidates']
    ):
        raise ValueError('Duplicate matches changed since review. Review again.')
    require_duplicate_approval(review, approved_ids)
    if get_file_hash(memory['source']) != memory['file_hash']:
        raise ValueError('Audio changed during duplicate review. Start again.')
    return add_document_memories_to_db([memory])

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Offline voice review and ingestion')
    parser.add_argument('audio', nargs='?')
    parser.add_argument('--model', choices=['tiny', 'base'], default='tiny')
    parser.add_argument('--language', help='Language code, e.g. en or ur; default: detect')
    args = parser.parse_args()
    try:
        memory = prepare_voice(args.audio or input('Voice note path: ').strip(), model_size=args.model, language=args.language)
        print('\nCheck names, amounts, dates and relationship direction:\n', memory['information'])
        choice = input('E to replace transcript, Y to review saving, anything else to cancel: ').strip().lower()
        if choice == 'e':
            memory['information'] = input('Corrected transcript: ').strip()
        elif choice != 'y':
            print('Cancelled. Nothing saved.')
            return
        if not memory['information']:
            raise ValueError('Empty transcript. Nothing saved.')
        memory['date'] = input('Recording date (blank if unknown): ').strip() or 'Unknown'
        review = review_duplicates(memory)
        require_duplicate_approval(dict(exact=review['exact'], candidates=[]))
        approved_ids = []
        for candidate in review['candidates']:
            record = candidate['memory']
            print(f"Possible duplicate #{record['id']}: {record['information']}")
            if input('Type ADD to approve an additional record: ').strip() != 'ADD':
                print('Cancelled. Nothing saved.')
                return
            approved_ids.append(record['id'])
        print('\nFinal memory:', memory['information'], '\nDate:', memory['date'], '\nSource:', memory['source'])
        if input('Type SAVE to ingest this reviewed transcript: ').strip() != 'SAVE':
            print('Cancelled. Nothing saved.')
            return
        reviewed_records = {item['memory']['id']: item['memory'] for item in review['candidates']}
        count = save_reviewed_voice(memory, approved=True, approved_ids=approved_ids, reviewed_records=reviewed_records)
        print('Voice memory saved.' if count else 'Audio already ingested. Nothing saved.')
    except Exception as error:
        print(f'Voice ingestion failed: {error}')

if __name__ == '__main__':
    main()
