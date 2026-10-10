# Windows setup

Run these commands from this release folder, not an existing personal installation. The release contains no database. First launch initializes a new local database with memory and repayment tables; later launches preserve records.

## Python environment

The audited runtime was Python 3.14.8 on Windows. Use a matching installation for reproduction:

```cmd
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-audit.txt
```

The requirements file is the audited environment snapshot. The user successfully installed it into a fresh virtual environment on the original Windows computer. An independent-machine installation has not been verified. If installation fails, keep the error and check the package/runtime combination before changing versions.

## Local models and OCR

- Install and start Ollama with `qwen3:1.7b` available at `http://127.0.0.1:11434`.
- Provision the Sentence Transformers `all-MiniLM-L6-v2` and faster-whisper `tiny` model caches before use. The app requests cached files only and will not fetch absent caches.
- Install Tesseract and Poppler. Put their executable folders on your CMD PATH. Verify with `where tesseract` and `where pdftoppm`.
- Model provisioning and dependency installation can require network access; the app's answer generation uses localhost.

This release intentionally does not reference another installation's virtual environment or the Codex bundled tool directories. Follow each dependency's installation instructions for your own machine. Missing OCR tools prevent scanned imports; embedded PDF text does not require OCR.

## Initialize and start

```cmd
.venv\Scripts\python.exe bootstrap.py
start_local.cmd
```

Open `http://127.0.0.1:8503`. This release uses port 8503 to allow an existing application and demo to remain separate. The database is located alongside the release code. Use synthetic inputs for release validation.

## Tests

```cmd
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Focused regression tests cover the fixes and fresh storage bootstrap. The historical 168-test acceptance result belongs to the earlier audited app; it is not a claim that every historical test is included in this release.

## Before publication

The same-computer fresh environment passed dependency installation, bootstrap, five tests, dashboard launch, synthetic note save/Ask, scanned OCR and voice-model loading. That computer reused existing model caches and Codex's Poppler after adding its folder to the CMD session PATH; other users must install their own OCR tools. Independent-machine setup remains unverified. Review all files and any Git history before publication. No databases, backups, source media, private logs, secrets or virtual environments belong in the public repository. No license has been selected yet; choose one before inviting redistribution.
