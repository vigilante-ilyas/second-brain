# Second Brain synthetic demo

Goal: a 4–6 minute walkthrough showing review, retrieval, finance and recovery. Record only an isolated sandbox with fictional records and generated source files.

## Prepare

Use a separate code copy, not the production folder. Its database must contain only synthetic records and include the repayment ledger schema. Verify both memory access and repayment access resolve to that sandbox. Do not copy an existing production database or restore a real backup into the demo.

Use these fictional examples:

| Type | Synthetic content |
|---|---|
| Note | Synthetic Alex keeps a green notebook in locker seven. |
| Debt | Synthetic Maya owes me Rs. 1,000, due on 12 October 2026. |
| Receipt | SYNTHETIC RECEIPT — Notebook shop — TOTAL RS 2500 — 10 October 2026 |
| PDF | A two-page fictional project brief with a clearly labeled synthetic title. |
| Voice | Synthetic Alex paid twelve hundred rupees for a green notebook on October tenth twenty twenty six. |

Use explicit dates. If recording after the debt's due date, replace it with a future calendar date and use that same date in the narration. Use fictional file names and a generic sandbox folder in screenshots. Generate new PDFs, receipt images and audio; do not reuse personal sources.

## Record

1. **Introduce the app.** “Second Brain stores reviewed memories locally and lets me ask questions about them.” Show the localhost URL.
2. **Add and review.** Enter the notebook note. Extract fields, correct the person to Synthetic Alex if needed, review duplicates and explicitly save. Explain that suggestions need review.
3. **Ask and abstain.** Ask what color the notebook is. Show the answer and source. Ask for Synthetic Alex's passport number and show the refusal to invent it. Model wording may vary.
4. **Edit and persist.** Change the locker number, save, restart the sandbox and show the edited record still exists. Do not promise exact AI wording.
5. **Finance.** Add the fictional debt with category Finance, status Pending, amount 1,000 and an explicit due date. Show the due-date view. Preview a 250 repayment, show that saving is disabled until confirmation, then confirm. Preview and confirm the remaining 750; inspect both history entries.
6. **Imports.** Import the synthetic PDF and receipt through the existing import tools. Show source/page attribution where available. Import the same file under another name and show duplicate rejection. Use a brief pre-recorded segment if OCR takes time.
7. **Voice.** Upload the synthetic audio. Transcribe locally, correct its text and fields, acknowledge correction, preview duplicates and explicitly SAVE. Show that re-uploading the same audio is blocked.
8. **Recovery and close.** Back up the synthetic database, verify it and restore to a new file. Summarize: “167 tests passed, one privilege-dependent test was skipped. Human review remains part of the workflow.”

## Before sharing

- Confirm every visible memory, source filename, browser tab and terminal output is synthetic.
- Complete the acceptance report's manual checklist in the sandbox.
- Check repository contents and Git history for databases, backups, private sources and secrets.
- Label the project as local-use software with no authentication or encryption.
- Include tested setup prerequisites; finish the fresh-clone bootstrap check before offering a runnable public repository.

This document remains the full recording plan. A shorter [synthetic demo is available in the v0.1.0 release](https://github.com/vigilante-ilyas/second-brain/releases/tag/v0.1.0). The 1:28 clip shows sourced answers, missing-information abstention and repayment history; long waiting periods were removed while preserving picture quality.
