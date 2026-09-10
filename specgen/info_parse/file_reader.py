from specgen.commons.logger import get_logger

logger = get_logger(__name__)

def read_file(file_path, max_chars=15000):
    """
    读取文件内容，自动检测编码，跳过二进制文件
    """
    try:
        with open(file_path, "rb") as f:
            raw = f.read(512)
            if b'\x00' in raw:
                logger.info(f"Warn： {file_path} It is a suspected binary file，skip")
                return ""
    except FileNotFoundError:
        logger.error(f"Error：file not exist - {file_path}")
        raise FileNotFoundError("Please verify whether the file path specified by the -f parameter is correct.")
    except Exception as e:
        pass
        logger.warning(f"Warn：file {file_path} was reading failed： {e}")
        return ""


    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312"]
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read(max_chars)
        except UnicodeDecodeError:
            continue
        except Exception as e:
            logger.warning(f"Warn：the file {file_path} was reading failed： {e}")
            return ""

    logger.warning(f"Warn：Cannot read the file {file_path} in any of the supported encoding formats")
    return ""
