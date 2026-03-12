import unittest

from agno.run.agent import RunCompletedEvent

from core.agent import _direct_memory_answer, _response_to_text, _should_return_direct_memory
from core.config import _DEFAULTS
from core.milvus_memory import _query_tokens, _select_lexical_matches
from core.vault import sanitize_for_retrieval


class _LegacyResponse:
    def get_content_as_string(self) -> str:
        return "legacy-ok"


class AgentCompatibilityTests(unittest.TestCase):
    def test_response_to_text_supports_legacy_getter(self) -> None:
        self.assertEqual(_response_to_text(_LegacyResponse()), "legacy-ok")

    def test_response_to_text_supports_current_agno_content_field(self) -> None:
        response = RunCompletedEvent(content="current-ok")
        self.assertEqual(_response_to_text(response), "current-ok")

    def test_new_configs_default_to_free_plan(self) -> None:
        self.assertEqual(_DEFAULTS["user_plan"], "free")

    def test_query_tokens_remove_common_words(self) -> None:
        self.assertEqual(_query_tokens("qual meus dados do chamaelas?"), ["dados", "chamaelas"])

    def test_lexical_match_recovers_memory_by_title(self) -> None:
        rows = [
            {"id": "1", "content": "dados chamaelas\n\n[VAULT:abc]", "meta_data": {}},
            {"id": "2", "content": "outra anotacao", "meta_data": {}},
        ]
        matches = _select_lexical_matches(rows, "qual meus dados do chamaelas?", limit=3)
        self.assertEqual([match["id"] for match in matches], ["1"])

    def test_sanitize_for_retrieval_redacts_sensitive_values(self) -> None:
        text = "dados chamaelas\nsenha: 123456\nemail: contato@chamaelas.com.br\ncnpj: 12.345.678/0001-90"
        sanitized = sanitize_for_retrieval(text)
        self.assertIn("dados chamaelas", sanitized)
        self.assertIn("senha: [PASSWORD]", sanitized)
        self.assertIn("email: [EMAIL]", sanitized)
        self.assertIn("cnpj: [CNPJ]", sanitized)

    def test_direct_memory_answer_returns_full_note_locally(self) -> None:
        memory = {
            "content": "dados chamaelas\nsenha: [PASSWORD]",
            "score": 1.0,
            "meta_data": {"vault_ciphertext": "dados chamaelas\nsenha: 123456"},
        }
        self.assertTrue(_should_return_direct_memory("qual meus dados do chamaelas?", [memory]))
        self.assertEqual(_direct_memory_answer([memory]), "dados chamaelas\nsenha: 123456")

    def test_direct_memory_answer_matches_title_tokens(self) -> None:
        memory = {
            "content": "dados chamaelas\nsenha: [PASSWORD]",
            "score": 0.63,
            "meta_data": {"vault_ciphertext": "dados chamaelas\nsenha: 123456"},
        }
        self.assertTrue(_should_return_direct_memory("qual meus dados do chamaelas?", [memory]))


if __name__ == "__main__":
    unittest.main()
