import logging
import os
import re
import unicodedata
from typing import Any

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIChat

from core import config as cfg
from core.sqlite_memory import MEMORY_DB_PATH, MEMORY_TABLE, SESSION_TABLE, USER_ID

logger = logging.getLogger("sage.agent")

_NOT_FOUND = {
    "pt-BR": "Nao encontrei isso no meu conhecimento.",
    "en": "I couldn't find that in my knowledge.",
    "es": "No encontre eso en mi conocimiento.",
}

_agent: Agent | None = None
_DIRECT_REVEAL_HINTS = (
    "dado", "dados", "credencial", "credenciais", "acesso", "senha", "password",
    "token", "api key", "api_key", "email", "e-mail", "telefone", "phone",
    "cpf", "cnpj", "login",
)
_TITLE_TOKEN_RE = re.compile(r"[a-z0-9]+")
_TITLE_STOPWORDS = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "no", "na", "nos", "nas",
    "em", "para", "por", "com", "sem", "e", "ou",
    "meu", "minha", "meus", "minhas", "seu", "sua", "seus", "suas",
    "qual", "quais", "que",
}


def _response_to_text(response: Any) -> str:
    """Extract plain text from Agno responses across library versions."""
    if response is None:
        return ""

    getter = getattr(response, "get_content_as_string", None)
    if callable(getter):
        try:
            text = getter()
        except Exception:
            logger.debug("Agno response getter failed", exc_info=True)
        else:
            if isinstance(text, str):
                return text
            if text is not None:
                return str(text)

    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if content is not None:
        return str(content)

    if isinstance(response, str):
        return response
    return str(response)


def reset_agent() -> None:
    """Discard the cached agent so it is rebuilt with the latest config."""
    global _agent
    _agent = None
    from core.rag import reset_knowledge
    reset_knowledge()
    from core.sqlite_memory import reset
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
        db = SqliteDb(
            db_file=str(MEMORY_DB_PATH),
            memory_table=MEMORY_TABLE,
            session_table=SESSION_TABLE,
        )

        language = conf.get("language", "pt-BR")
        not_found_msg = _NOT_FOUND.get(language, _NOT_FOUND["en"])

        agent_kwargs: dict = dict(
            model=model,
            db=db,
            user_id=USER_ID,
            session_id="sage-local-session",
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
    """Store a fact in the local SQLite memory backend. No LLM call needed."""
    from core.sqlite_memory import store
    from core.vault import sanitize_for_retrieval

    retrieval_text = sanitize_for_retrieval(text)
    store(retrieval_text, original_text=text)
    return "Saved."


def _memory_title(memory: dict[str, Any]) -> str:
    from core.vault import retrieval_text

    content = retrieval_text(memory)
    for line in content.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _normalize_tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return {
        token for token in _TITLE_TOKEN_RE.findall(normalized.lower())
        if len(token) >= 3 and token not in _TITLE_STOPWORDS
    }


def _should_return_direct_memory(question: str, memories: list[dict[str, Any]]) -> bool:
    if not memories:
        return False

    lowered = question.lower()
    if not any(hint in lowered for hint in _DIRECT_REVEAL_HINTS):
        return False

    top = memories[0]
    title = _memory_title(top).lower()
    score = float(top.get("score", 0.0) or 0.0)
    if not title:
        return False

    title_tokens = _normalize_tokens(title)
    question_tokens = _normalize_tokens(question)
    token_match = bool(title_tokens) and title_tokens.issubset(question_tokens)
    return token_match or score >= 0.85 or title in lowered


def _direct_memory_answer(memories: list[dict[str, Any]]) -> str:
    from core.vault import extract_full_text

    top = memories[0]
    full_text = extract_full_text(top).strip()
    if full_text:
        return full_text
    return ""


def query_knowledge(question: str) -> str:
    from core.vault import retrieval_text
    from core.sqlite_memory import search as memory_search

    conf = cfg.load()
    language = conf.get("language", "pt-BR")
    not_found_msg = _NOT_FOUND.get(language, _NOT_FOUND["en"])

    # 1) Search the local memory store for relevant memories
    memories = memory_search(question, limit=10)
    logger.info("Memory search returned %d memories", len(memories))

    direct_answer = _direct_memory_answer(memories) if _should_return_direct_memory(question, memories) else ""
    if direct_answer:
        logger.info("Returning direct local memory answer for question=%r", question)
        return direct_answer

    # 2) Build memory context block (documents are searched by the agent knowledge tool)
    context_lines = []

    if memories:
        for m in memories:
            content = retrieval_text(m)
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
        stream=False,
    )
    raw = _response_to_text(response)
    logger.debug("Agent response text: %r", raw)
    if not raw:
        raw = not_found_msg
    return raw
