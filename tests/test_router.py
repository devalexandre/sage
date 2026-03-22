import os
import unittest
from unittest.mock import patch

from core.agent import _build_model
from core.router import route


class RouterTests(unittest.TestCase):
    def test_plain_text_defaults_to_memory_flow(self) -> None:
        with patch("core.router.save_memory", return_value="Saved.") as save_mock, \
             patch("core.router.search_knowledge") as search_mock:
            kind, response = route("bank password 123456")

        self.assertEqual((kind, response), ("memory", "Saved."))
        save_mock.assert_called_once_with("bank password 123456")
        search_mock.assert_not_called()

    def test_question_mark_uses_answer_flow(self) -> None:
        with patch("core.router.search_knowledge", return_value="Hello there.") as search_mock, \
             patch("core.router.save_memory") as save_mock:
            kind, response = route("who are you?")

        self.assertEqual((kind, response), ("answer", "Hello there."))
        search_mock.assert_called_once_with("who are you?")
        save_mock.assert_not_called()


class OpenAIModelConfigTests(unittest.TestCase):
    def test_build_model_passes_saved_openai_api_key(self) -> None:
        conf = {
            "provider": "openai",
            "openai_api_key": "sk-test",
            "openai_model": "gpt-4o-mini",
        }

        with patch("core.agent.OpenAIChat") as openai_chat:
            _build_model(conf)

        openai_chat.assert_called_once_with(
            id="gpt-4o-mini",
            temperature=0.0,
            api_key="sk-test",
        )
        self.assertEqual(os.environ.get("OPENAI_API_KEY"), "sk-test")


if __name__ == "__main__":
    unittest.main()
