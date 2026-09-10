import urllib.error
from unittest.mock import patch

import pytest
from specgen.invoke_llm.call_llm import (
    _model_capabilities_cache,
    _extract_context_length,
    compute_safe_options,
    call_ollama)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before execute test case"""
    _model_capabilities_cache.clear()
    yield
    _model_capabilities_cache.clear()

class TestExtractContextLength:
    """Get infomation from /api/show API testing"""

    def test_from_model_info(self):
        resp = {"model_info": {"qwen2.context_length": 12345}}
        assert _extract_context_length(resp) == 12345

    def test_from_parameters_string(self):
        resp = {"parameters": "num_ctx 16384\nstop [INST]"}
        assert _extract_context_length(resp) == 16384

    def test_model_info_takes_priority(self):
        """The key model_info has higher priority than key parameters"""
        resp = resp = {
            "model_info": {"arch.context_length": 32768},
            "parameters": "num_ctx 16384",
        }
        assert _extract_context_length(resp) == 32768

    def test_fallback_to_default(self):
        assert _extract_context_length(None) == 4096
        assert _extract_context_length({}) == 4096

class TestComputeSafeOptions:
    """Safe options calculation test"""
    @patch("specgen.invoke_llm.call_llm.get_model_maximum_context", return_value=8192)
    def test_generic_model(self, mock_ctx):
        opts = compute_safe_options("test_model")
        assert opts["num_ctx"] == 8192
        assert opts["num_predict"] == int(8192 * 0.75)

    @patch("specgen.invoke_llm.call_llm.get_model_maximum_context", return_value=8192)
    def test_precise_model_with_large_input(self, mock_ctx):
        opts = compute_safe_options("test_model", prompt_tokens_estimate=6000)
        assert opts["num_predict"] == 8192 - 6000 - 64

    @patch("specgen.invoke_llm.call_llm.get_model_maximum_context", return_value=8192)
    def test_min_output_guarantee(self, mock_ctx):
        opts = compute_safe_options("test_model", prompt_tokens_estimate=9000)
        assert opts["num_predict"] >= 1024

class TestCallOllama:
    """LLM invoke testing"""
    @patch("specgen.invoke_llm.call_llm._do_chat_request", return_value=("generated content", "stop"))
    def test_normal_response(self, mock_ctx):
        result = call_ollama("test_model", "hello")
        assert result == "generated content"

    @patch("specgen.invoke_llm.call_llm._ensure_long_model", return_value="test-model-longctx")
    @patch("specgen.invoke_llm.call_llm._do_chat_request", side_effect=[("truncated...", "length"), ("full content", "stop")])
    def test_truncation_auto_recovery(self, mock_chat, mock_long):
        result = call_ollama("test_model", "hello")
        assert result == "full content"
        assert mock_chat.called

    @patch("specgen.invoke_llm.call_llm._do_chat_request", side_effect=urllib.error.URLError("refused"))
    def test_connection_error_exists(self, mock_ctx):
        with pytest.raises(SystemExit):
            call_ollama("test_model", "hello")
