from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim
from database import get_all_memories

model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)


def retrieve_memories(query, top_k=3, extra_memories=None):
    memories = get_all_memories()

    if extra_memories:
        memories = memories + extra_memories

    if not memories:
        return []

    memory_texts = []

    for memory in memories:
        text = (
            f"Person: {memory['person']}. "
            f"Date: {memory['date']}. "
            f"Information: {memory['information']}"
        )
        memory_texts.append(text)

    memory_embeddings = model.encode(memory_texts)
    query_embedding = model.encode(query)

    scores = cos_sim(query_embedding, memory_embeddings)[0]

    top_results = scores.argsort(descending=True)[:top_k]

    retrieved = []

    for index in top_results:
        index = index.item()

        retrieved.append({
            "memory": memories[index],
            "score": scores[index].item()
        })

    return retrieved
