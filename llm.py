import ollama


MODEL_NAME = "qwen3:1.7b"


def generate_answer(question, retrieved_memories):
    evidence = ""

    for number, result in enumerate(retrieved_memories, start=1):
        memory = result["memory"]

        evidence += (
            f"[{number}]\n"
            f"Person: {memory['person']}\n"
            f"Date: {memory['date']}\n"
            f"Information: {memory['information']}\n"
            f"Source: {memory['source']}\n\n"
        )

    prompt = f"""
You are the reasoning engine for a personal Second Brain.

Answer the question using ONLY the stored evidence.

Rules:
- Never invent information.
- Pay attention to relationships such as owes, borrowed, paid, received and lent.
- Ignore evidence that does not help answer the question.
- If the answer is unavailable, say so.
- Keep the answer concise.
- Do not expose your internal reasoning.

After your answer, write:
USED_EVIDENCE: followed only by the evidence numbers you actually used.

Example:
Irfan owes you Rs. 8,500.
USED_EVIDENCE: 1

STORED EVIDENCE:

{evidence}

QUESTION:
{question}

ANSWER:
"""

    response = ollama.Client(host="http://127.0.0.1:11434", timeout=120).chat(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response["message"]["content"]