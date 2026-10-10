import re

from structured_query import answer_structured_question


def format_rag_answer(raw_answer, retrieved_memories):
    # Find the internal evidence numbers produced by the LLM.
    match = re.search(
        r"USED_EVIDENCE:\s*([0-9,\s]+)",
        raw_answer,
        re.IGNORECASE
    )

    sources = []

    if match:
        numbers = re.findall(r"\d+", match.group(1))

        for number in numbers:
            index = int(number) - 1

            if 0 <= index < len(retrieved_memories):
                memory = retrieved_memories[index]["memory"]
                source = memory.get("source")

                if source and source not in sources:
                    sources.append(source)

    # Remove the internal USED_EVIDENCE line.
    clean_answer = re.sub(
        r"\s*USED_EVIDENCE:\s*[0-9,\s]*",
        "",
        raw_answer,
        flags=re.IGNORECASE
    ).strip()

    if sources:
        clean_answer += "\n\nSource: " + ", ".join(sources)

    return clean_answer


def route_question(question, today=None):
    # First try reliable structured retrieval.
    structured_answer = answer_structured_question(question, today=today)

    if structured_answer is not None:
        return {
            "method": "structured",
            "answer": structured_answer
        }

    # Otherwise use semantic RAG retrieval.
    # Structured finance answers do not need to load the embedding model/LLM.
    from rag import retrieve_memories
    from llm import generate_answer
    retrieved_memories = retrieve_memories(question, top_k=3)

    if not retrieved_memories:
        return {
            "method": "rag",
            "answer": "I couldn't find any relevant memories."
        }

    raw_answer = generate_answer(question, retrieved_memories)

    answer = format_rag_answer(
        raw_answer,
        retrieved_memories
    )

    return {
        "method": "rag",
        "answer": answer
    }


if __name__ == "__main__":
    question = input("Ask your Second Brain: ")

    result = route_question(question)

    print()
    print("Method:", result["method"])
    print()
    print(result["answer"])
