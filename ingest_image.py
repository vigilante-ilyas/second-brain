from image_reader import image_to_memory
from database import add_document_memories_to_db


image_path = input("Enter image filename: ").strip()

try:
    memory = image_to_memory(image_path)

    if not memory:
        print("\nNo readable text was found in this image.")

    else:
        memories = [memory]
        memories_added = add_document_memories_to_db(memories)

        if memories_added == 0:
            print("\nThis image has already been added.")

        else:
            print("\nImage added successfully.")
            print("Memories added:", memories_added)
            print("Source:", image_path)

except FileNotFoundError:
    print("\nImage not found. Make sure it is inside the second-brain folder.")

except Exception as error:
    print("\nSomething went wrong:")
    print(error)