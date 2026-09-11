# SpecGenerator v0.1.0

## 功能
根据用户需求及已有文档/代码文件，自动生成两份产物：
- `development_doc.md` — 开发文档
- `code_spec.md` — Code Spec（供 AI 自动生成功能代码使用）

## 前置条件
- Python 3.8+
- Ollama 本地运行（或兼容的 LLM 服务）
  - 已安装并运行，且已拉取所需模型：
  ```bash
  ollama pull <模型名称>  # 默认为qwen3.5:9b
  ```

## 安装
```bash
git clone https://github.com/KevinLee1987/SpecGenerator.git
cd SpecGenerator
#在SpecGenerator目录下运行以下命令
pip install .
```

## 使用
安装成功之后就可使用`specgen`命令
```bash
specgen -r "<具体需求>" -f <参考文档列表用空格分开> -o <输出目录>
```

## 快速开始
```bash
# 仅根据需求生成
specgen -r "实现用户登录功能" -o ./output
# 结合已有代码生成
specgen -r "重构排序模块" -f src/sort.py docs/design.md -o ./output
# 将需求以文件的方式传入
specgen -r /tmp/requirement.md -f src/sort.py docs/design.md -o ./output
# 指定模型 + 调试模式
specgen -r "排序" -f src/sort.py -o ./output -m llama3:8b --debug
```

## 命令参数说明

| 参数              | 说明                     | 默认值 |
|-----------------|------------------------|---|
| -h,--help       | 帮助信息                   | 无 |
| -r,--requirement | 需求描述 (文字或文件路径)         | 必填 |
| -f,--files      | 已有文档/代码文件路径列表，用空格分隔。   | 无 |
| -o,--output_dir | 输出目录                   | 必填 |
| -m,--model      | 模型名称                   | qwen3.5:9b |
| --debug         | 启用 DEBUG 级别日志          | false |
| --log_file      | 日志文件路径，如 ./specgen.log | 无 |
| --version       | 查看版本号                  | 无 |
> `-f` 支持格式：`.txt` `.md` `.py` `.java` 等纯文本格式。
> 不支持：`.doc` `.docx` `.pdf` 等二进制格式，请先转换为支持的格式后重试。

## 输出产物
执行成功后在 `-o` 指定的目录下生成：
- `development_doc.md` — 开发文档
- `code_spec.md` — Code Spec（供 AI 生成代码使用）

## 常见问题
- **PermissionError**: 确保 `-o` 指定的目录有写入权限
- **Ollama 连接失败**: 确认 `ollama serve` 正在运行，默认地址 http://localhost:11434
- **模型不存在**: 运行 `ollama pull <模型名>` 拉取模型
