# Validation status

Original automated acceptance: 168 ran, 167 passed, one Windows symlink privilege test skipped. This historical result used synthetic isolated data in the audited installed environment.

Manual sandbox acceptance: text add/edit/Ask, missing-information abstention, restart persistence, due dates, partial/full repayments and history, deletion safeguards, duplicate blocking, corrected voice SAVE, repeated audio rejection, text/scanned/mixed PDFs, receipt OCR, source attribution, renamed media duplicates, document Ask, backup/verify/restore passed after recorded fixes.

Observed limitations: the user's voice sample was transcribed inaccurately and required correction. PDF/image imports store text/source/page but do not automatically assign structured finance fields. Duplicate and empty-evidence-marker fixes from manual testing are included here. The repeated “Nothing saved” wording on voice duplicate rejection remains cosmetic debt.

Release preparation adds an idempotent database bootstrap and project-local launchers. These do not modify the production installation. Public networking, authentication and encryption remain outside scope. Independent-machine portability remains unverified.

Five focused release regression tests passed: blank evidence-marker cleanup, valid citation/invalid-index handling, newline-before-period exact duplicate blocking, whitespace normalization, and fresh storage/repeated initialization with confirmation-protected repayment. These ran using the existing audited Python environment.

The release bootstrap also initialized an isolated empty code copy successfully. A dashboard AppTest startup probe did not complete in this execution environment and was stopped. The user subsequently verified interactive release launch. All Python source files were checked for syntax. The archive excludes generated caches and includes only selected code, configuration and documentation; no machine-specific user paths are included.

Subsequent user-confirmed fresh-environment checks supersede the pending interactive launch: dependency installation succeeded; database bootstrap and all five tests passed; the empty dashboard opened; Synthetic Lina's note saved; Ask answered red with source release-test; scanned-PDF OCR imported one page; voice transcription loaded. These checks used a new virtual environment on the original computer, with existing model caches. Tesseract was already installed; Poppler became available after adding the Codex bundled tool folder to the CMD session PATH. Voice wording remained inaccurate and needs correction. This validates the tested same-computer setup, not installation on a new machine.
