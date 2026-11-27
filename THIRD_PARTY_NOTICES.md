# 资源来源说明

本仓库包含程序运行必需的资源，不使用“先删掉素材、运行前再补齐”的分发方式。第三方资源的原有来源与版权归属不因打包或转码改变。

- `packstudio/data/vanilla-assets.zip`：按内容哈希去重存储的 Minecraft 原版资源，供素材浏览、模型预览和版本适配使用。
- `packstudio/data/slice_rules.json`：来自 Mojang slicer 的声明式切片规则，附带 `Mojang-slicer-LICENSE`。
- `packstudio/data/models/*.xml`：已有实体预览模型，来自 MCSkin3D 参考模型；`boat_legacy.xml` 用于旧船预览。
- `packstudio/data/game_names_zh.json`：游戏名称数据。
- `packstudio/assets/`：工具图标、程序图标及界面图片；其中部分工具图标以用户提供的 Photoshop 工具栏截图为参考，部分经过重绘。保留目录内来源说明。
- PySide6、shiboken6 和 PyInstaller 通过依赖文件安装，其许可证以对应依赖随附内容为准。

完整文件清单为 `source-manifest.json`。`check_source.py` 检查文件、内置资源与运行依赖；`--strict` 同时核对导出时的哈希。
