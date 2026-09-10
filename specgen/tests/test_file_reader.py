import pytest

from specgen.info_parse.file_reader import read_file


class TestFileReader:
    """File read and decode testing"""

    def test_normal_utf8_file(self, tmp_path):
        """Normal utf-8 file tests"""
        f = tmp_path/"tests.md"
        f.write_text("# Hello\n世界", encoding="utf-8")
        assert read_file(str(f)) == "# Hello\n世界"

    def test_gbk_encode_file(self, tmp_path):
        """GBK encode file tests"""
        f = tmp_path/"test.txt"
        f.write_bytes("你好世界".encode("gbk"))
        assert "你好世界" in read_file(str(f))

    def test_binary_file_return_empty(self, tmp_path):
        """Binary file return empty string"""
        f = tmp_path/"test.bin"
        f.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
        assert read_file(str(f)) == ""

    def test_file_not_exist_raise(self):
        """File not exist raise"""
        with pytest.raises(FileNotFoundError, match="-f parameter"):
            read_file("/noexistfilepath/path/tmp_file.txt")

    def test_max_char_truncation(self, tmp_path):
        """Max character truncation"""
        f = tmp_path/"test.txt"
        f.write_text("A" * 20000, encoding="utf-8")
        assert len(read_file(str(f), max_chars=100)) == 100

    def test_unsupported_encoding_return_empty(self, tmp_path):
        """Unsupported encoding return empty string"""
        f = tmp_path/"unsupported_encoding.txt"
        f.write_bytes(bytes(range(128, 256)))
        assert read_file(str(f)) == ""
