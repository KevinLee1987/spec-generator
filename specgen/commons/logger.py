"""
统一日志配置模块。
所有子模块通过 get_logger(__name__) 获取带命名空间的 logger。
"""
import logging
import sys


def set_logger(level: str = "INFO", log_file: str | None = None):
    """
        初始化全局日志配置。应在 main.py 入口处调用一次。

        Args:
            level: 日志级别 ("DEBUG", "INFO", "WARNING", "ERROR")
            log_file: 可选的日志文件路径，为 None 时仅输出到 stderr
    """

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    handles: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        handles.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handles,
        force=True # 覆盖可能已存在的配置
    )

    # 降低第三方库的噪音
    logging.getLogger("urllib3").setLevel(logging.WARNING)

def get_logger(name: str = ""):
    """获取带模块命名空间的 logger。"""
    return logging.getLogger(name)
