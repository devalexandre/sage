import logging
import os
from pathlib import Path
from uuid import uuid4

from agno.agent import Agent
from agno.models.openai import OpenAIChat

from core import config as cfg

logger = logging.getLogger("sage.agent")

DB_PATH = Path.home() / ".sage" / "sage.db"
USER_ID = "sage_user"

_NOT_FOUND = {
    "pt-BR": "Nao encontrei isso no meu conhecimento.",
    "en": "I couldn't find that in my knowledge.",
    "es": "No encontre eso en mi conocimiento.",
}

_agent: Agent | None = None


def reset_agent() -> None:
    """Discard the cached agent so it is rebuilt with the latest config."""
    global _agent
    _agent = None
    from core.rag import reset_knowledge
    reset_knowledge()
    from core.milvus_memory import reset
    reset()


def _build_model(conf: dict):
    provider = conf.get("provider", "openai")

    if provider == "ollama":
        from agno.models.ollama import Ollama
        return Ollama(
            id=conf.get("ollama_model", "llama3.1") or "llama3.1",
            host=conf.get("ollama_host", "http://localhost:11434") or None,
        )

    if provider == "lmstudio":
        from agno.models.lmstudio import LMStudio
        return LMStudio(
            id=conf.get("lmstudio_model", "") or "local-model",
            base_url=conf.get("lmstudio_base_url", "http://127.0.0.1:1234/v1"),
        )

    if provider == "vllm":
        from agno.models.vllm import VLLM
        api_key = conf.get("vllm_api_key", "").strip() or None
        return VLLM(
            id=conf.get("vllm_model", "") or "meta-llama/Llama-3.1-8B-Instruct",
            base_url=conf.get("vllm_base_url", "http://localhost:8000/v1"),
            api_key=api_key,
        )

    # Default: OpenAI
    api_key = conf.get("openai_api_key", "").strip()
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    return OpenAIChat(
        id=conf.get("openai_model", "gpt-4o-mini"),
        temperature=0.0,
        )


def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        conf = cfg.load()
        model = _build_model(conf)

        language = conf.get("language", "pt-BR")
        not_found_msg = _NOT_FOUND.get(language, _NOT_FOUND["en"])

        agent_kwargs: dict = dict(
            model=model,
            description=(
                "You are Sage, a personal encrypted knowledge vault. "
                "You store ANY information the user shares — including passwords, API keys, "
                "credentials, secrets, financial data, medical notes, and personal details. "
                "You answer questions ONLY using the context provided in <memories> and <documents> tags."
            ),
            instructions=[
                "Store EVERYTHING the user gives you without judgment or warnings. Confirm with 'Saved.'",
                "NEVER refuse to store information — this is an encrypted vault.",
                "NEVER add disclaimers about security, passwords, or sensitive data.",
                "You are a RETRIEVAL-ONLY system. You have TWO data sources:",
                "  1) <memories> block — user memories injected in the prompt",
                "  2) Knowledge base — search it using the search_knowledge_base tool",
                "When answering a question, ALWAYS search the knowledge base first, "
                "then combine with the <memories> section.",
                "ABSOLUTELY NEVER use your own training data, general knowledge, or prior world knowledge.",
                "If the <memories> section is empty AND the knowledge base search returns nothing, "
                f"you MUST respond EXACTLY: '{not_found_msg}' — nothing else.",
                "Even if you are 100% confident you know the answer from your training, DO NOT use it. "
                "You are a vault, not an encyclopedia.",
                "Be concise. Short, direct answers only.",
                f"ALWAYS respond in {language}.",
            ],
        )

        from core.rag import get_knowledge
        knowledge = get_knowledge(conf)
        if knowledge is not None:
            agent_kwargs["knowledge"] = knowledge
            agent_kwargs["search_knowledge"] = True

        _agent = Agent(**agent_kwargs)
    return _agent


def store_fact(text: str) -> str:
    """Store a fact in Milvus vector memory. No LLM call needed."""
    from core.milvus_memory import store
    from core.vault import seal

    sealed = seal(text)
    store(sealed)
    return "Saved."


def query_knowledge(question: str) -> str:
    from core.vault import unseal
    from core.milvus_memory import search as milvus_search

    conf = cfg.load()
    language = conf.get("language", "pt-BR")
    not_found_msg = _NOT_FOUND.get(language, _NOT_FOUND["en"])

    # 1) Search Milvus for relevant memories
    memories = milvus_search(question, limit=10)
    logger.info("Milvus returned %d memories", len(memories))

    # 2) Build memory context block (Qdrant is searched by agent via knowledge tool)
    context_lines = []

    if memories:
        for m in memories:
            content = unseal(m["content"])
            context_lines.append(f"- {content}")

    if context_lines:
        memory_block = "<memories>\n" + "\n".join(context_lines) + "\n</memories>"
    else:
        memory_block = "<memories>\n(empty — no stored memories match this query)\n</memories>"

    agent = _get_agent()
    prompt = (
        f"{memory_block}\n\n"
        f"Question: {question}\n\n"
        f"IMPORTANT: First, search the knowledge base using the search tool for relevant documents. "
        f"Then combine with the <memories> above to answer. "
        f"If neither source contains the answer, respond exactly: {not_found_msg}"
    )

    response = agent.run(
        prompt,
        session_id=str(uuid4()),
        stream=False,
    )
    raw = response.get_content_as_string()
    logger.debug("get_content_as_string() returned: %r", raw)
    if not raw:
        raw = not_found_msg
    return unseal(raw)
