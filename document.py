from pypdf import PdfReader
import hashlib
from pathlib import Path
import warnings
import shutil
import subprocess
import tempfile

from image_reader import read_image

PDF_RENDER_TIMEOUT = 60
PDF_OCR_MAX_DIMENSION = 3000

def get_file_hash(file_path):
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as file:
        while True:
            chunk = file.read(8192)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def _ocr_pdf_page(snapshot, page_number, directory):
    """Render only the requested page, with bounded size and execution time."""
    renderer = shutil.which("pdftoppm")
    if not renderer:
        raise RuntimeError("Poppler pdftoppm is not available on PATH")
    prefix = Path(directory) / "ocr_page"
    subprocess.run(
        [renderer, "-f", str(page_number), "-l", str(page_number),
         "-singlefile", "-scale-to", str(PDF_OCR_MAX_DIMENSION),
         "-png", str(snapshot), str(prefix)],
        check=True, capture_output=True, timeout=PDF_RENDER_TIMEOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    image_path = prefix.with_suffix(".png")
    try:
        return read_image(image_path)
    finally:
        image_path.unlink(missing_ok=True)


def read_pdf(file_path):
    """Keep embedded text; OCR textless pages from one disposable snapshot.

    OCR failures skip only that page and produce a warning. The caller checks
    the source hash before returning any memories for database insertion.
    """
    pages = []
    source_hash = get_file_hash(file_path)
    with tempfile.TemporaryDirectory(prefix="second_brain_pdf_") as directory:
        snapshot = Path(directory) / "source.pdf"
        with open(file_path, "rb") as source, open(snapshot, "wb") as target:
            shutil.copyfileobj(source, target)
        if get_file_hash(snapshot) != source_hash:
            raise ValueError("PDF changed while creating extraction snapshot; nothing was saved.")
        with open(snapshot, "rb") as stream:
            reader = PdfReader(stream)
            for page_number, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if not text:
                    try:
                        text = _ocr_pdf_page(snapshot, page_number, directory).strip()
                    except Exception as error:
                        warnings.warn(
                            f"PDF page {page_number}: OCR failed "
                            f"({type(error).__name__}: {error}); page skipped.",
                            UserWarning, stacklevel=2,
                        )
                        continue
                    if not text:
                        warnings.warn(
                            f"PDF page {page_number}: no readable text after OCR; "
                            "blank or unreadable page skipped.",
                            UserWarning, stacklevel=2,
                        )
                if text:
                    pages.append({"page": page_number, "text": text})
    return pages


def pdf_to_memories(file_path):
    file_path = str(Path(file_path).resolve())
    file_hash = get_file_hash(file_path)
    pages = read_pdf(file_path)
    if get_file_hash(file_path) != file_hash:
        raise ValueError("PDF changed during extraction; nothing was saved.")

    memories = []

    for page in pages:
        memory = {
            "person": "Document",
            "date": "Unknown",
            "information": page["text"],
            "source": file_path,
            "page": page["page"],
            "file_hash": file_hash
        }

        memories.append(memory)

    return memories