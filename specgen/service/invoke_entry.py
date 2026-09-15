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
        prompt = """You are a senior software engineer. 
        Based on the user's requirements and provided existing file contents, 
        generate a comprehensive development document in Markdown format for a new feature.
        
        The document MUST include the following sections (include only if applicable):
        1. Overview
        2. Requirements Analysis
        3. Functional Design
        4. Technical Approach
        5. API Design
        6. Data Structures
        7. Test Plan
        8. Additional Considerations
        
        CRITICAL INSTRUCTIONS:
        1. Output ONLY valid Markdown content. Do NOT include any preamble, explanation, or postscript.
        2. Ensure COMPLETE traceability from original requirements to design elements, 
        so that downstream code specification generation does NOT require referencing the original requirements again.
        3. Use precise technical language and avoid ambiguous terms.
        """
    else:
        prompt = """You are a tech lead. Based on the user's requirements and provided existing file contents, 
        generate a detailed Code Specification document in Markdown format that is explicitly structured for consumption by Claude Code (or similar AI coding agents) to auto-generate implementation code.

        The specification MUST include the following sections:
        1. Project Context & Objectives
        2. Technical Constraints (language, framework, dependencies — infer from provided files)
        3. Existing Codebase Structure Summary (based on provided files)
        4. Files to Create/Modify: list each file with a detailed functional description
        5. Key Functions/Classes: include signature, parameters, return type, and purpose
        6. Data Models / Database Schema (if applicable)
        7. Error Handling Strategy
        8. Testing Requirements
        9. Implementation Notes
        
        CRITICAL INSTRUCTIONS:
        1. Output ONLY valid Markdown content. Do NOT include any preamble, explanation, or postscript.
        2. Use clear hierarchical structure (headings, bullet points, code blocks) optimized for machine parsing.
        3. Be explicit and unambiguous — assume the consumer is an AI agent with zero contextual memory beyond this document.
        """

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
