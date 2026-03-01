from core.agent import query_knowledge


def search_knowledge(question: str) -> str:
    """Search stored knowledge and answer the question."""
    return query_knowledge(question)
