from document import pdf_to_memories
from database import add_document_memories_to_db


file_path = input("📄 Enter PDF filename: ").strip()

try:
    document_memories = pdf_to_memories(file_path)

    if not document_memories:
        print("\n❌ No readable text was found in this PDF.")

    else:
        pages_added = add_document_memories_to_db(document_memories)

        if pages_added == 0:
            print("\n⚠️ This document has already been added.")

        else:
            print("\n🧠 Document added successfully.")
            print(f"Pages remembered: {pages_added}")
            print(f"Source: {file_path}")

except FileNotFoundError:
    print("\n❌ File not found. Make sure the PDF is inside the second-brain folder.")

except Exception as error:
    print("\n❌ Something went wrong:")
    print(error)