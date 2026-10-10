from database import get_all_memories


def view_source():
    memories = get_all_memories()

    if not memories:
        print("No memories available.")
        return

    print()
    print("VIEW MEMORY SOURCES")
    print()

    search = input("Enter a person or source name: ").strip().lower()

    if not search:
        print("Please enter a search term.")
        return

    matches = []

    for memory in memories:
        person = str(memory.get("person") or "").lower()
        source = str(memory.get("source") or "").lower()

        if search in person or search in source:
            matches.append(memory)

    if not matches:
        print("No matching memories found.")
        return

    for memory in matches:
        print()
        print("-" * 40)
        print("Memory ID:", memory["id"])
        print("Person:", memory["person"])
        print("Original information:", memory["information"])
        print("Recorded date:", memory["date"])
        print("Event date:", memory["event_date"])
        print("Source:", memory["source"])
        print("Page:", memory["page"])
        print("-" * 40)


if __name__ == "__main__":
    view_source()