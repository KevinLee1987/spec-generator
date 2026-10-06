import json
import sys
import urllib.request
import urllib.error
from datetime import datetime

from specgen.commons.logger import get_logger

DEFAULT_CONTEXT_LENGTH = 4096       # 无法探测时的安全回退值
MAX_CONTEXT_LENGTH = 131072         # 产品级硬上限（防止 OOM）
MIN_OUTPUT_TOKENS = 1024            # 最低保证输出长度
OUTPUT_RATIO = 0.75                 # 输出占上下文窗口的比例（预留输入空间）
MAX_OUTPUT_RATIO = 0.85             # 最多只用 85% 的窗口给输出，留 15% 给输入

# 已知云端模型的上下文窗口（tokens）。
# 值来自各厂商官方文档，仅用于估算 max_tokens 上限。
# 未列出的模型使用 DEFAULT_CLOUD_CONTEXT。
DEFAULT_CLOUD_CONTEXT = 32768

CLOUD_MODEL_CONTEXT = {
    # DeepSeek
    "deepseek-chat": 65536,
    "deepseek-reasoner": 65536,
    # OpenAI
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-3.5-turbo": 16385,
    # Anthropic（通过 OpenAI 兼容网关时）
    "claude-sonnet-4-6": 200000,
    "claude-opus-4-7": 200000,
    # Moonshot
    "moonshot-v1-8k": 8192,
    "moonshot-v1-32k": 32768,
    "moonshot-v1-128k": 128000,
    # MiniMax
    "abab6.5s-chat": 245760,
}

# 模型能力缓存（进程生命周期内有效，避免重复调用 /api/show）
_model_capabilities_cache = {}

logger = get_logger(__name__)

def _get_model_info(model, base_url):
    try:
        data = json.dumps({"name": model}).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/api/show", data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"[Warn] Cannot get {model} model info：{e}")
        return None

def _extract_context_length(model_info_response):
    """
        从 /api/show 响应中提取模型的最大上下文长度。

        查找策略（按优先级）：
        1. model_info 中的 <arch>.context_length（如 qwen2.context_length）
        2. parameters 字符串中的 num_ctx 值
        3. 回退到默认值
    """
    if not model_info_response:
        return DEFAULT_CONTEXT_LENGTH

    logger.debug(f"The info from the api/show is {model_info_response}")

    # --- 策略1：从 model_info 字典中查找 ---
    model_info = model_info_response.get("model_info", {})
    for key, value in model_info.items():
        if key.endswith("context_length") or key.endswith("context_window"):
            try:
                ctx = int(value)
                if ctx > 0:
                    return ctx
            except (ValueError, TypeError):
                continue

    # --- 策略2：从 parameters 字符串中查找 ---
    params_str = model_info_response.get("parameters", "")
    if params_str:
        for line in params_str.split("\n"):
            line = line.strip()
            if line.startswith("num_ctx"):
                try:
                    return int(line.split()[-1])
                except (ValueError, IndexError):
                    continue

    # --- 策略3：回退默认值 ---
    return DEFAULT_CONTEXT_LENGTH

def get_model_maximum_context(model, base_url = "http://localhost:11434"):
    """
        获取模型的最大上下文长度（带缓存）。
        返回值：模型支持的最大 context_length（tokens）
    """
    cache_key = f"{base_url}/{model}"
    if cache_key in _model_capabilities_cache:
        return _model_capabilities_cache[cache_key]

    model_info = _get_model_info(model, base_url)
    max_ctx = _extract_context_length(model_info)

    # 获取模型硬上限
    max_ctx = min(max_ctx, MAX_CONTEXT_LENGTH)

    _model_capabilities_cache[cache_key] = max_ctx
    logger.info(f"[ModelCap] {model} maximum context： {max_ctx} tokens")
    return max_ctx

def compute_safe_options(model, base_url = "http://localhost:11434", prompt_tokens_estimate = 0):
    """
    根据模型实际能力动态计算安全的 options 参数。

    参数:
        model: 模型名称
        base_url: Ollama 服务地址
        prompt_tokens_estimate: 预估输入 token 数（可选，用于更精确计算）

    返回:
        dict: {"num_ctx": int, "num_predict": int}
    """
    max_ctx = get_model_maximum_context(model, base_url)

    # num_ctx: 使用模型最大值，但不超过产品硬上限
    num_ctx = max_ctx

    if prompt_tokens_estimate > 0:
        # 精确模式，已知输入长度
        available_output = num_ctx - prompt_tokens_estimate - 64 # 64 为安全余量
        num_predict = min(int(available_output), int(num_ctx * MAX_OUTPUT_RATIO))
        num_predict = max(num_predict, MIN_OUTPUT_TOKENS)
    else:
        # 通用模式，按比例分配
        num_predict = int(num_ctx * OUTPUT_RATIO)

    # 确保数值合理
    num_predict = max(num_predict, MIN_OUTPUT_TOKENS)
    num_predict = min(num_ctx, num_predict)

    return {"num_ctx": num_ctx, "num_predict": num_predict}

def compute_cloud_max_tokens(model, prompt_tokens_estimate=0):
    """
    为 OpenAI 兼容云端 API 计算安全的 max_tokens。

    云端 API 不支持 num_ctx，只能设置 max_tokens。
    策略：
      1. 查映射表获得模型上下文窗口；
      2. 预留输入空间，输出不超过窗口的 50%；
      3. 保证最小值 MIN_OUTPUT_TOKENS。
    """
    ctx = CLOUD_MODEL_CONTEXT.get(model, DEFAULT_CLOUD_CONTEXT)

    # 输出最多占窗口的 50%（云端输入输出共享窗口，留足安全余量）
    max_output_ratio = 0.5
    max_tokens = int(ctx * max_output_ratio)

    # 如果已知输入长度，进一步收紧
    if prompt_tokens_estimate > 0:
        available = ctx - prompt_tokens_estimate - 256  # 256 为安全余量
        max_tokens = min(max_tokens, available)

    # 保证上下限
    max_tokens = max(max_tokens, MIN_OUTPUT_TOKENS)

    logger.info(f"[CloudConfig] model={model}, context_window={ctx}, "
                f"prompt_tokens≈{prompt_tokens_estimate}, max_tokens={max_tokens}")
    return max_tokens

def _do_chat_request(url, data, headers, is_ollama=True):
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=3000) as response:
        response_body = json.loads(response.read().decode("utf-8"))
        logger.debug(f"The response of LLM is {response_body}")
        if is_ollama:
            content = response_body["message"]["content"]
            done_reason = response_body.get("done_reason", "stop")
        else:
            content = response_body["choices"][0]["message"]["content"]
            finish_reason = response_body["choices"][0].get("finish_reason", "stop")
            done_reason = "length" if finish_reason == "length" else "stop"
        logger.info(f"The length of the context from LLM is {len(content)} characters")
        logger.debug(f"The content of the response body from LLm is {content}...")
        return content, done_reason

def _ensure_long_model(model, base_url):
    """自动创建长输出版本模型（幂等，已存在则直接返回名称）"""
    long_model = f"{model}-longctx"
    # 检查模型是否已经存在
    try:
        check_data = json.dumps({"name": long_model}).encode("utf-8")
        check_req = urllib.request.Request(f"{base_url}/api/show", data=check_data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(check_req, timeout=1000)
        logger.info(f"[Auto] The long output model {long_model} has been existed")
        return long_model
    except Exception:
        pass

    # 动态获取模型能力， 计算参数
    safe_opts = compute_safe_options(model, base_url)

    # 创建新的模型
    logger.info(f"[Autofix] The long output model {long_model} is creating. (ctx={safe_opts['num_ctx']}, predict={safe_opts['num_predict']}) ...")
    create_payload = {
        "name": long_model,
        "from": model,
        "parameters": {"num_predict": safe_opts["num_predict"],
                       "num_ctx": safe_opts["num_ctx"]},
        "stream": False}
    create_data = json.dumps(create_payload, ensure_ascii=False).encode("utf-8")
    create_req = urllib.request.Request(
        f"{base_url}/api/create",
        data=create_data,
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(create_req, timeout=3000)
        logger.info(f"The long output model {long_model} created successfully.")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error(f"[Error] Failed to create the long output model due to：{error_body}")
        return None
    return long_model

def _estimate_prompt_tokens(messages):
    """
    粗略估算prompt的token数。
    中文约 1.5个字符一个token, 英文约4个字符一个token
    产品及可替换为tiktoken等精确分词器
    """
    total_chars = sum(len(m.get("content", "")) for m in messages)
    # 保守估计：1个字符大约0.7个token （中英文混合）
    return int(total_chars * 0.7)

def _is_ollama(base_url):
    """判断base_url是否指向本地ollama服务"""
    return any(kw in base_url for kw in ("11434", "localhost", "172.0,0,1"))

def validate_llm_config(base_url, model, api_key):
    """
    校验 LLM 配置，提前拦截错误组合。返回 （is_ollama, error_msg)。
    error_msg 非空时表示配置错误，调用方应报错推出。
    """
    is_ollams = _is_ollama(base_url)
    if is_ollams:
        if api_key:
            logger.warning(f"[Warning] You provided a api_key, but the base_url looks like local Ollama. The API key will be ignored.")
            return True, None
    elif not api_key:
        return False, (f"The base_url looks like a Cloud API, but no --api_key was provided.\n "
                       f"Please provide a --api_key or set the SPECGEN_API_KEY environment variable.\n "
                       f"Example: --base_url https://api.deepseek.com --api_key sk-xxxx")
    elif ":" in model:
        return False, (f"base_url is a cloud API, but model '{model}' looks like a local Ollama model name "
            f"(contains ':').\n"
            f"  Cloud APIs usually expect names like 'deepseek-chat', 'gpt-4o', 'claude-sonnet-4-6'.\n"
            f"  Did you forget to change --model? Example: -m deepseek-chat")

    return True, None

def call_ollama(model, prompt, system_prompt = None, base_url="http://localhost:11434", api_key=None):
    """调用ollama API 或者 OpenAI API 生成文本, 使用标准库urllib避免额外依赖"""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    is_ollama = _is_ollama(base_url)

    prompt_tokens = _estimate_prompt_tokens(messages)
    headers = {"Content-Type": "application/json"}
    if is_ollama:
        url = f"{base_url}/api/chat"
        # 动态计算安全参数
        safe_opts = compute_safe_options(model, base_url, prompt_tokens)
        logger.info(f"[Config] num_ctx={safe_opts['num_ctx']}, num_predict={safe_opts['num_predict']}, the estimated input need {prompt_tokens} tokens")

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": safe_opts
        }
    else:
        logger.info(f"[Config] Using OpenAI-compatible API at {base_url}, model={model}")
        max_tokens = compute_cloud_max_tokens(model, prompt_tokens)
        # OpenAI兼容API (Deepseek, OpenAI等）
        url = f"{base_url.rstrip('/')}/chat/completions"
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens
        }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    try:
        logger.info(f"Start time：{datetime.now()}")
        content, done_reason = _do_chat_request(url, data=data, headers=headers, is_ollama=is_ollama)
        logger.info(f"End time：{datetime.now()}")
        if is_ollama and done_reason == "length":
            logger.info(f"[AutoFix] The output of the model {model} has been truncated (done_reason=length)，The auto recovery is starting...")
            long_model = _ensure_long_model(model, base_url)
            if long_model is not None:
                logger.info(f"The long output model has been create successfully, will using the new model to invoke.")
                payload["model"] = long_model
                payload["options"] = compute_safe_options(long_model, base_url, prompt_tokens)
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            logger.info(f"Start to retry：{datetime.now()}")
            content, done_reason = _do_chat_request(url, data=data, headers=headers)
            if done_reason == "length":
                logger.warning(f"[Warn] Even if the {long_model} content is used, it is still truncated. Please check the context limitations of the model itself.")
            logger.info(f"Retry completed：{datetime.now()}")
        return content
    except urllib.error.URLError as e:
        logger.error(f"Cannot connect the LLM，Please confirm the LLM is normal： {e}")
        print(f"❌ Cannot connect the LLM，Please confirm the LLM is normal： {e}")
        sys.exit(1)
    except KeyError as e:
        logger.error(f"The field message.content does not existed in LLM response")
        print(f"❌ The field message.content does not existed in LLM response")
        sys.exit(1)
    except TimeoutError as e:
        logger.error("❌ LLM timeout. Please ensure the Ollama status is normal.")
        print("❌ LLM timeout. Please ensure the Ollama status is normal.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"LLM invoking failed due to： {e}")
        print(f"❌ LLM invoking failed due to： {e}")
        sys.exit(1)
