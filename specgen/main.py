import argparse
import os

from specgen.commons.logger import set_logger
from specgen.service.invoke_entry import operator


def cli():
    parser = argparse.ArgumentParser(
        prog="specgen",
        description="根据用户需求和用户提供的现有文档/代码文件，生成一份新功能的开发文档和Claude code spec"
    )
    parser.add_argument("--requirement", "-r", required=True, type=str, help="用户需求描述（文本）或包含需求的文件路径")
    parser.add_argument("--files", "-f", nargs="+", default="", help="已有文档/代码文件路径列表，用空格分隔")
    parser.add_argument("--output_dir", "-o", required=True, help="目标存放文件的路径（支持windows和linux文件路径）")
    parser.add_argument("--model", "-m", default="qwen3.5:9b", help="Ollama模型名称，默认qwen3.5:9b")
    parser.add_argument("--debug", action="store_true", help="启用 DEBUG 级别日志")
    parser.add_argument("--log_file", type=str, default=None, help="日志文件路径，如 ./specgen.log")
    parser.add_argument("--version", action="version", version="specgen 0.1.0")

    args = parser.parse_args()

    log_level = "DEBUG" if args.debug else os.environ.get("SPECGEN_LOG_LEVEL", "INFO")
    log_path = os.path.join(args.output_dir, "../specgen.log") if not args.log_file else args.log_file
    set_logger(level=log_level, log_file=log_path)

    operator(args.requirement, args.files, args.model, args.output_dir)


if __name__ == "__main__":
    cli()
