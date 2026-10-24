# playlist-relocate 中文说明

使用明确的挂载路径映射，把本地 M3U/M3U8 播放列表迁移到新磁盘或系统。
默认只预览，核实全部媒体目标存在后，使用 `--write` 写出全新的列表。
不移动音乐、不覆盖旧列表，也不按相似文件名猜测曲目。

按 [英文 README](README.md) 克隆并建立、激活 Python 3.11+ 虚拟环境后：

```sh
python -m pip install .
python examples/make_demo.py
playlist-relocate playlist-demo/old.m3u8 --map playlist-demo/mounts.json --output playlist-demo/moved.m3u8 --json
playlist-relocate playlist-demo/old.m3u8 --map playlist-demo/mounts.json --output playlist-demo/moved.m3u8 --write --json
```

演示生成一个明确标注的合成 WAV，不下载音乐。Windows 盘符和 UNC 旧路径可以在
任何系统上按语义映射，目标目录使用当前系统路径。相对目标根目录以 JSON 文件所在
目录为基准；相对媒体条目必须配置 `source_base`。最长目录前缀优先。

退出码 0 表示预览就绪或写入成功，1 表示有媒体路径无法解析且没有写出，2 表示输入、
限制或发布错误。写出采用同目录临时文件及不覆盖目标的原子硬链接，需要目标文件系统
支持硬链接。默认只接受 UTF-8、本地文件；不支持流媒体、HLS、file URI 或模糊修复。
输出保留标题与注释，并统一为 UTF-8/LF，因此不是隐私脱敏工具。

报告默认不含路径与曲名。工具无第三方运行依赖，无 HTTP 请求或后台服务。
卸载用 `python -m pip uninstall playlist-relocate`；删除专用虚拟环境和演示目录
即可清理。详细边界、并发限制及测试命令见英文说明。
