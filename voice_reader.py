"""Offline transcription; importing this module loads no model."""
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=2)
def get_model(model_size='tiny'):
    from faster_whisper import WhisperModel
    try:
        return WhisperModel(model_size, device='cpu', compute_type='int8', local_files_only=True)
    except Exception as error:
        raise RuntimeError('Cannot load cached Whisper model. No download attempted.') from error

def decode_audio(audio_path):
    import av
    import numpy as np
    path = Path(audio_path).expanduser().resolve(strict=True)
    resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
    chunks, size = [], 0
    with av.open(str(path), mode='r') as container:
        if not container.streams.audio:
            raise ValueError('File has no audio stream.')
        for frame in container.decode(audio=0):
            frame.pts = None
            for output in resampler.resample(frame):
                samples = output.to_ndarray().reshape(-1)
                size += samples.size
                if size > 1800 * 16000:
                    raise ValueError('Voice notes must be at most 30 minutes long.')
                chunks.append(samples)
        for output in resampler.resample(None):
            samples = output.to_ndarray().reshape(-1)
            size += samples.size
            chunks.append(samples)
    if size > 1800 * 16000:
        raise ValueError('Voice notes must be at most 30 minutes long.')
    if not chunks:
        raise ValueError('Empty audio stream.')
    return np.concatenate(chunks).astype(np.float32) / 32768.0

def transcribe_audio(audio_path, model_size='tiny', language=None):
    segments, _ = get_model(model_size).transcribe(decode_audio(audio_path), language=language, vad_filter=True, beam_size=5)
    return ' '.join(segment.text.strip() for segment in segments).strip()

if __name__ == '__main__':
    try:
        print(transcribe_audio(input('Voice note path: ').strip()) or 'No speech detected.')
    except Exception as error:
        print(f'Transcription failed: {error}')
