import os
import sys

from specgen.commons.logger import get_logger
from specgen.info_parse.file_reader import read_file
from specgen.invoke_llm.call_llm import call_ollama

MAX_LENGTH_OF_REQUIREMENT = 1000

logger = get_logger(__name__)

def get_file_content(files):
    files_content = ""
    total_chars = 0
    for file_path in files:
        content = read_file(file_path)
        if content:
            files_content += f"\n\n--file： {file_path} --\n {content}"
            total_chars += len(content)
            if total_chars > 50000:
                logger.warning("Warn： The length of content in file is more than 50000，it will be truncated")
                files_content = files_content[:50000]
                break
    return files_content

def system_prompt_generator(prompt_type="dev_spec"):
    prompt = ""
    if prompt_type == "dev_spec":
        prompt = """你是一个资深软件工程师。请根据用户需求和提供的现有文件内容，生成一份新功能的开发文档（Markdown格式）。
        请生成详细的开发文档，包括以下部分（如适用）：
        1. 概述
        2. 需求分析
        3. 功能设计
        4. 技术方案
        5. 接口设计
        6. 数据结构
        7. 测试计划
        8. 其他注意事项

        请只输出Markdown格式的文档内容，不要包含任何前缀或后缀解释。
        请确保开发文档中包含对原始需求的完整映射，以便后续基于本文档生成代码规格时无需回溯原始需求。
        """
    else:
        prompt = """你是一个技术负责人。请根据用户需求和提供的现有文件内容，生成一份Claude Code可识别的代码规格说明（Markdown格式）。
        该spec将被Claude Code工具读取，用于自动生成实现代码。请确保spec足够详细，包含以下内容：

        1. 项目背景与目标
        2. 技术约束（语言、框架、依赖等，基于现有文件推断）
        3. 现有代码结构概述（基于提供的文件）
        4. 需要新增/修改的文件列表及每个文件的详细功能描述
        5. 关键函数/类定义（包括签名、参数、返回值、功能说明）
        6. 数据模型/数据库设计（如需）
        7. 错误处理策略
        8. 测试要求
        9. 其他实施细节

        请使用清晰的Markdown结构（标题、列表、代码块等），便于Claude Code解析并执行。
        请只输出Markdown格式的spec内容，不要包含任何前缀或后缀解释。"""

    return prompt

def operator(requirements, files, model, target_dir):
    # 判断用户是否以文件的形式题需求
    if os.path.isfile(requirements):
        with open(requirements, "r", encoding="utf-8") as f:
            requirements = f.read().strip()
    # 判断requirements长度
    req_len = len(requirements)
    logger.info(f"The current length of the requirements is：{req_len} characters")
    if req_len > MAX_LENGTH_OF_REQUIREMENT:
        logger.error(f"The length of the requirement content exceeds the specified limit. (1000 characters)，please adjust requirements and recall.")
        sys.exit(1)

    # 读取参考文件列表
    try:
        files_content = get_file_content(files)
    except FileNotFoundError as e:
        print(f"❌ Generation stoped：{e}", file=sys.stderr)
        sys.exit(1)

    # 创建目标目录
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"Cannot created the folder {target_dir}: {e}")
        print(f"❌ Cannot created the folder {target_dir}: {e}", file=sys.stderr)
        sys.exit(1)

    # 组装user prompt
    user_prompt = f"用户需求：\n{requirements}\n\n现有文件内容：\n{files_content}"

    # 生成开发文档的提示词
    system_dev_prompt = system_prompt_generator()

    logger.info("The development documentation is generating...")
    dev_spec  = call_ollama(model, user_prompt ,system_prompt=system_dev_prompt)
    if not dev_spec or not dev_spec.strip():
        logger.error("Error：The documentation is empty in model response，please check the model status or prompt")
        sys.exit(1)

    # 保存刚刚生成的dev_spec
    dev_path = os.path.join(target_dir, "development_doc.md")
    try:
        with open(dev_path, "w", encoding="utf-8") as f:
            f.write(dev_spec)
        logger.info(f"The development documentation has been saved to {dev_path}")
    except Exception as e:
        logger.error(f"Failed to saved development documentation due to：{e}")
        print(f"❌ Failed to saved development documentation due to：{e}")
        sys.exit(1)

    # 生成Code Spec的提示词
    system_spec_prompt = system_prompt_generator("code_spec")
    enriched_user_prompt = (
        f"以下是已生成的开发文档，请基于此生成精确的代码规格说明：\n\n"
        f"{dev_spec}"
    )

    logger.info("The code spec is generating...")
    code_spec = call_ollama(model, enriched_user_prompt ,system_prompt=system_spec_prompt)
    if not code_spec or not code_spec.strip():
        logger.error("Error：The documentation is empty in model response，please check the model status or prompt")
        sys.exit(1)

    # 保存刚刚生成的code_spec
    spec_path = os.path.join(target_dir, "code_spec.md")
    try:
        with open(spec_path, "w", encoding="utf-8") as f:
            f.write(code_spec)
            logger.info(f"The code spec has been saved to {spec_path}")
    except Exception as e:
        logger.error(f"Failed to save code spec to {spec_path} due to: {e}")
        print(f"❌ Failed to save code spec to {spec_path} due to: {e}")
        sys.exit(1)
