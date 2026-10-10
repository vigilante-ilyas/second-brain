from PIL import Image
import pytesseract
import hashlib
from pathlib import Path

def read_image(image_path):
    with Image.open(image_path) as image:
        text = pytesseract.image_to_string(image, timeout=60)
    return text.strip()

def get_image_hash(image_path):
    sha256 = hashlib.sha256()

    with open(image_path, "rb") as file:
        while True:
            chunk = file.read(8192)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def image_to_memory(image_path):
    image_path = str(Path(image_path).resolve())
    file_hash = get_image_hash(image_path)
    text = read_image(image_path)
    if get_image_hash(image_path) != file_hash:
        raise ValueError("Image changed during extraction; nothing was saved.")

    if not text:
        return None

    memory = {
        "person": "Document",
        "date": "Unknown",
        "information": text,
        "source": image_path,
        "page": None,
        "file_hash": file_hash
    }

    return memory


if __name__ == "__main__":
    image_path = input("Enter image filename: ").strip()

    try:
        text = read_image(image_path)

        print("\nEXTRACTED TEXT:")
        print("----------------")

        if text:
            print(text)
        else:
            print("No readable text found.")

    except FileNotFoundError:
        print("\nImage not found. Make sure it is inside the second-brain folder.")

    except Exception as error:
        print("\nSomething went wrong:")
        print(error)