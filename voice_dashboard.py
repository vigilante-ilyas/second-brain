"""Offline upload review. No database writes until the final SAVE action."""
import hashlib
import math
import tempfile
from pathlib import Path
from urllib.parse import quote

import streamlit as st
from voice_reader import transcribe_audio
from extractor import extract_memory, VALID_CATEGORIES, VALID_STATUSES
from duplicate_checker import review_duplicates, require_duplicate_approval
from database import add_document_memories_to_db, get_all_memories

MAX_UPLOAD = 50 * 1024 * 1024
EXTENSIONS = ['m4a', 'mp3', 'wav', 'ogg', 'opus', 'aac', 'mp4', 'webm']
FIELDS = ('person', 'what', 'money_amount', 'value', 'event_date', 'location')


def upload_identity(upload):
    data = upload.getvalue()
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError('Choose a nonempty audio file up to 50 MB.')
    name = Path(upload.name.replace('\\', '/')).name
    suffix = Path(name).suffix.lower()
    if suffix.lstrip('.') not in EXTENSIONS:
        raise ValueError('Unsupported audio extension.')
    digest = hashlib.sha256(data).hexdigest()
    return data, suffix, digest, f'voice-upload://{digest}/{quote(name, safe="")}'


def transcribe_upload(upload, model, language):
    data, suffix, digest, source = upload_identity(upload)
    # Never use the supplied filename as a filesystem path. Remove on all exits.
    with tempfile.TemporaryDirectory(prefix='second_brain_voice_') as directory:
        path = Path(directory) / ('audio' + suffix)
        path.write_bytes(data)
        transcript = transcribe_audio(str(path), model_size=model, language=language)
    if not transcript.strip():
        raise ValueError('No speech detected. Nothing saved.')
    return dict(information=transcript.strip(), source=source, file_hash=digest, page=None)


def local_extract(text):
    import ollama
    # Pin to this computer even if OLLAMA_HOST points to a remote service.
    client = ollama.Client(host='http://127.0.0.1:11434', timeout=120)
    def structured_chat(**request):
        # A short fact extraction should not spend its budget on reasoning.
        # Bound generation; truncated/invalid JSON stays a manual-review failure.
        return client.chat(**request, think=False, format='json',
                           options={'temperature': 0, 'num_predict': 512},
                           keep_alive='5m')
    result = extract_memory(text, chat=structured_chat)
    if result is None:
        raise ValueError('The local model did not return valid fields. Enter them manually.')
    return result


def build_memory(base, transcript, recorded, values, category, status):
    if not transcript.strip():
        raise ValueError('Corrected transcript cannot be empty.')
    result = dict(base, information=transcript.strip(), date=recorded.strip() or None,
                  category=category, status=status, event_id=None)
    for field in FIELDS:
        result[field] = str(values.get(field) or '').strip() or None
    money = result['money_amount']
    result['money_amount'] = int(money.replace(',', '')) if money else None
    if result['money_amount'] is not None and result['money_amount'] < 0:
        raise ValueError('Money amount cannot be negative.')
    result['value'] = float(result['value']) if result['value'] else None
    if result['value'] is not None and not math.isfinite(result['value']):
        raise ValueError('Value must be a finite number.')
    return result


def checked_review(memory, records=None):
    records = get_all_memories() if records is None else records
    if any(row.get('file_hash') == memory['file_hash'] for row in records):
        raise ValueError('This audio has already been imported. Nothing saved.')
    return review_duplicates(memory, memories=records)


def save_preview(preview, *, approved=False, approved_ids=()):
    if approved is not True:
        raise ValueError('Explicit SAVE approval required.')
    memory, old = preview['memory'], preview['review']
    def validate(records):
        fresh = checked_review(memory, records)
        old_records = {c['memory']['id']: c['memory'] for c in old['candidates']}
        new_records = {c['memory']['id']: c['memory'] for c in fresh['candidates']}
        if old_records != new_records:
            raise ValueError('Duplicate matches changed. Preview again before approving.')
        require_duplicate_approval(fresh, approved_ids)
    return add_document_memories_to_db([memory], validate_before_insert=validate)


def reset_voice():
    for key in list(st.session_state):
        if key.startswith('voice_') and key not in ('voice_upload', 'voice_model', 'voice_language', 'voice_transcribe'):
            del st.session_state[key]


def render_voice_dashboard():
    st.subheader('Voice Note')
    st.caption('Local transcription only. Check names, amounts, dates and who owes whom. '
               'Urdu / mixed-language accuracy is unverified. One reviewed memory per note; '
               'keep multiple facts in the transcript and summary or split the note manually.')
    st.info('Audio is used temporarily and deleted after transcription. SAVE stores your corrected '
            'transcript, fields, original filename and SHA-256 reference, not the audio. '
            'Keep the original recording on your phone if you need it later.')
    upload = st.file_uploader('Upload a phone / WhatsApp voice note (up to 50 MB)',
                              type=EXTENSIONS, key='voice_upload')
    if upload is None:
        reset_voice()
        return
    try:
        _, _, digest, source = upload_identity(upload)
    except Exception as error:
        reset_voice()
        st.error(str(error))
        return
    identity = (digest, source)
    if st.session_state.get('voice_identity') != identity:
        reset_voice()
        st.session_state['voice_identity'] = identity
    if st.session_state.get('voice_saved'):
        st.success(st.session_state['voice_saved'])
        st.caption('Remove this upload or choose another note to start again.')
        return
    model = st.selectbox('Cached transcription model', ['tiny', 'base'], key='voice_model')
    language = st.selectbox('Speech language', ['Detect', 'English', 'Urdu'], key='voice_language')
    if st.button('Transcribe locally', key='voice_transcribe'):
        revision = st.session_state.get('voice_revision', 0) + 1
        reset_voice()
        st.session_state.update(voice_identity=identity, voice_revision=revision)
        try:
            with st.spinner('Transcribing locally...'):
                base = transcribe_upload(upload, model, {'Detect': None, 'English': 'en', 'Urdu': 'ur'}[language])
            st.session_state['voice_base'] = base
        except Exception as error:
            st.error(f'Transcription failed: {error}. Nothing saved.')
    base = st.session_state.get('voice_base')
    if not base:
        return
    revision = st.session_state['voice_revision']
    prefix = f'voice_{revision}_'
    if st.button('Discard transcript and start again', key=prefix+'discard'):
        reset_voice()
        st.rerun()
    transcript = st.text_area('Correct the transcript', value=base['information'], key=prefix+'transcript', height=180)
    corrected = st.checkbox('I listened to the note and corrected the transcript.', key=prefix+'corrected')
    recorded = st.text_input('Recording date (optional; do not guess)', key=prefix+'recorded')
    if st.button('Suggest fields locally (optional)', disabled=not corrected, key=prefix+'extract'):
        st.session_state.pop('voice_preview', None)
        try:
            with st.spinner('Suggesting fields locally (may take up to two minutes)...'):
                proposal = local_extract(transcript)
            if not isinstance(proposal, dict):
                raise ValueError('No valid structured result returned')
            for field in FIELDS:
                st.session_state[prefix+field] = str(proposal.get(field) if proposal.get(field) is not None else '')
            for field, allowed in [('category', VALID_CATEGORIES), ('status', VALID_STATUSES)]:
                st.session_state[prefix+field] = proposal.get(field) if proposal.get(field) in allowed else ('Other' if field == 'category' else 'Unknown')
            st.caption('Suggestions are unverified. Review every field below.')
        except Exception as error:
            st.warning(f'Local extraction unavailable: {error}. Fill in the fields manually.')
    st.markdown('### Review structured fields')
    st.caption('Unknown fields may stay blank. Summary defaults to the full corrected transcript. Money uses whole rupees.')
    for field in FIELDS:
        if prefix+field not in st.session_state:
            st.session_state[prefix+field] = transcript if field == 'what' else ''
    values = {field: st.text_input(field.replace('_', ' ').title(), key=prefix+field) for field in FIELDS}
    if prefix+'category' not in st.session_state:
        st.session_state[prefix+'category'] = 'Other'
    if prefix+'status' not in st.session_state:
        st.session_state[prefix+'status'] = 'Unknown'
    category = st.selectbox('Voice category', sorted(VALID_CATEGORIES), key=prefix+'category')
    status = st.selectbox('Voice status', sorted(VALID_STATUSES), key=prefix+'status')
    try:
        memory = build_memory(base, transcript, recorded, values, category, status)
    except Exception as error:
        st.session_state.pop('voice_preview', None)
        st.error(f'Check fields: {error}')
        return
    pending = st.session_state.get('voice_preview')
    if pending and (pending['memory'] != memory or not corrected):
        st.session_state.pop('voice_preview', None)
        pending = None
    if st.button('Preview fields and duplicate check', disabled=not corrected, key=prefix+'preview'):
        st.session_state.pop('voice_preview', None)
        try:
            review = checked_review(memory)
            require_duplicate_approval(dict(exact=review['exact'], candidates=[]))
            version = st.session_state.get('voice_preview_version', 0) + 1
            st.session_state['voice_preview_version'] = version
            pending = dict(memory=memory, review=review, version=version)
            st.session_state['voice_preview'] = pending
        except Exception as error:
            pending = None
            st.error(f'Cannot preview: {error}. Nothing saved.')
    if not pending:
        return
    st.markdown('### Final SAVE review')
    st.json(pending['memory'])
    approval_prefix = f"voice_approval_{pending['version']}_"
    approved_ids = []
    for candidate in pending['review']['candidates']:
        row = candidate['memory']
        st.warning(f"Possible duplicate #{row['id']} (similarity {candidate['score']:.3f}): {row['information']}")
        st.json(row)
        if st.checkbox(f"I reviewed #{row['id']} and approve an additional memory.", key=approval_prefix+str(row['id'])):
            approved_ids.append(row['id'])
    approve = st.checkbox('I approve storing this corrected transcript and these fields.', key=approval_prefix+'confirm')
    ready = approve and len(approved_ids) == len(pending['review']['candidates'])
    if st.button('SAVE approved voice memory', disabled=not ready, key=approval_prefix+'save'):
        try:
            count = save_preview(pending, approved=approve, approved_ids=approved_ids)
        except Exception as error:
            st.session_state.pop('voice_preview', None)
            st.error(f'Not saved: {error}. Preview again to retry.')
        else:
            reset_voice()
            st.session_state.update(voice_identity=identity, voice_saved='Voice memory saved.' if count else 'Audio already imported. Nothing saved.')
            st.rerun()
    if st.button('Cancel voice review', key=approval_prefix+'cancel'):
        reset_voice()
        st.rerun()
