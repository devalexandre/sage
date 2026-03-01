import os
from pathlib import Path

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.learn.machine import LearningMachine
from agno.models.openai import OpenAIChat

from core import config as cfg

DB_PATH = Path.home() / ".sage" / "sage.db"
USER_ID = "sage_user"

_agent: Agent | None = None


def reset_agent() -> None:
    """Discard the cached agent so it is rebuilt with the latest config."""
    global _agent
    _agent = None


def _build_model(conf: dict):
    provider = conf.get("provider", "openai")

    if provider == "ollama":
        from agno.models.ollama import Ollama
        return Ollama(
            id=conf.get("ollama_model", "llama3.1") or "llama3.1",
            host=conf.get("ollama_host", "http://localhost:11434") or None,
            cache_response=True,
            cache_ttl=3600,
        )

    if provider == "lmstudio":
        from agno.models.lmstudio import LMStudio
        return LMStudio(
            cache_response=True,
            cache_ttl=3600,
            id=conf.get("lmstudio_model", "") or "local-model",
            base_url=conf.get("lmstudio_base_url", "http://127.0.0.1:1234/v1"),
        )

    # Default: OpenAI
    api_key = conf.get("openai_api_key", "").strip()
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    return OpenAIChat(
        id=conf.get("openai_model", "gpt-4o-mini"),
        cache_response=True,
        cache_ttl=3600,
        )


def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        conf = cfg.load()
        model = _build_model(conf)

        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        db = SqliteDb(db_file=str(DB_PATH))
        _agent = Agent(
            model=model,
            db=db,
            learning=LearningMachine(
                db=db,
                user_memory=True,
                learned_knowledge=True,
            ),
            enable_agentic_memory=True,
            add_learnings_to_context=True,
            description=(
                "You are Sage, a personal knowledge assistant. "
                "You store facts shared by the user and answer questions based on what was memorized."
            ),
            instructions=[
                "When asked to store or remember something, save the fact and confirm with 'Saved.'",
                "When answering questions, search your memory for relevant information.",
                "If no relevant information is found in memory, reply: 'I couldn't find that in my knowledge.'",
                "Be concise. Short, direct answers only.",
            ],
        )
    return _agent


def store_fact(text: str) -> str:
    agent = _get_agent()
    response = agent.run(
        f"Remember this fact: {text}",
        user_id=USER_ID,
        stream=False,
    )
    return response.get_content_as_string() or "Saved."


def query_knowledge(question: str) -> str:
    agent = _get_agent()
    response = agent.run(
        question,
        user_id=USER_ID,
        stream=False,
    )
    return response.get_content_as_string() or "I couldn't find that in my knowledge."
