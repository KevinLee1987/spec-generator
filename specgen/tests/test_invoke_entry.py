import os
from unittest.mock import patch
import pytest

from specgen.service.invoke_entry import get_file_content, system_prompt_generator, operator


class TestGetFileContent:

    def test_multiple_files_concatenated(self, tmp_path):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.md"
        f1.write_text("print('a')", encoding="utf-8")
        f2.write_text("# B", encoding="utf-8")

        result = get_file_content([str(f1), str(f2)])
        assert "--file：" in result
        assert "print('a')" in result
        assert "# B" in result

    def test_truncated_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("a" * 60000, encoding="utf-8")
        result = get_file_content([str(f)])
        assert len(result) <= 50000 * 100

    def test_file_not_exist(self):
        with pytest.raises(FileNotFoundError):
            get_file_content(["/file/not/exist.txt"])

class TestSystemPromptGenerate:

    def test_dev_doc_with_required_sections(self):
        result = system_prompt_generator()
        assert "需求分析" in result
        assert "Markdown" in result

    def test_code_spec_with_required_sections(self):
        result = system_prompt_generator("code_spec")
        assert "Claude Code" in result
        assert "测试要求" in result

class TestOperator:

    @patch("specgen.service.invoke_entry.call_ollama", side_effect=["dev doc content", "code spec content"])
    @patch("specgen.service.invoke_entry.read_file", return_value="file content")
    def test_generate_two_files(self, mock_read, mock_llm, tmp_path):
        out_dir = tmp_path / "output"
        operator("实现登录", ["ref.py"], "test_model", out_dir)

        assert os.path.exists(os.path.join(out_dir, "development_doc.md"))
        assert os.path.exists(os.path.join(out_dir, "code_spec.md"))
        assert mock_llm.call_count == 2

    @patch("specgen.service.invoke_entry.call_ollama", return_value="")
    @patch("specgen.service.invoke_entry.read_file", return_value="file content")
    def test_empty_llm_response_exists(self, mock_read, mock_llm):
        with pytest.raises(SystemExit):
            operator("实现登录", [], "test_model", "/tmp/output")

    def test_requirement_too_long_exception(self):
        with pytest.raises(SystemExit):
            operator("abc" * 1000, [], "test_model", "/tmp/output")

    @patch("specgen.service.invoke_entry.read_file", side_effect=FileNotFoundError("path error"))
    def test_missing_ref_file_exists(self, mock_read):
        with pytest.raises(SystemExit):
            operator("实现登录", ["missing.py"], "test_model", "/tmp/output")
