# 第三方资源与分发事项

本文件记录仓库审查时找到的来源证据。当前源码快照用于私有源码托管。整体项目许可证由作者选择后补入；第三方文件按各自授权处理。

## 随源码保留

- `packstudio/data/slice_rules.json`：由 Mojang slicer 的声明式区域规则提取。随附 `packstudio/data/Mojang-slicer-LICENSE`，其中保留 Microsoft 的 MIT 许可证正文。
- `packstudio/data/version_catalog.json`、`texture_aliases.json`、`semantic_index.json`、`atlas_layouts.json` 等：资源路径、哈希、尺寸、布局及转换索引。它们承担版本识别和映射；公开分发前仍需审阅生成来源。
- `packstudio/data/material-evidence.json`：材质分析所得的聚合数值，包含工具部位统计和样本计数。原始样本包保留在本地；公开前需确认这类派生数据的使用依据。
- `packstudio/data/naming_defaults.json`、`search_tags.json`、`docs/resource-identities.tsv`：命名与资源对照数据。公开前需核实其中参考名称和数据来源。
- `packstudio/assets/globe-*.png`、`undo-*.png`、`redo-*.png`：对应本仓库中的像素生成脚本，保留脚本与结果便于审阅。
- PySide6、shiboken6、PyInstaller 及其 hooks 通过依赖清单安装。制作可分发程序时，需要同时审阅安装版本携带的许可证、Qt 组件与打包依赖的分发要求。

## 暂缓加入仓库

逐文件路径、大小和 SHA-256 见 `docs/private-resources.json`。

| 内容 | 审查发现 | 补齐用途 |
| --- | --- | --- |
| `packstudio/data/vanilla-assets.zip` | 包含 Minecraft 原版贴图、模型及其他资源；现有源码包中的 slicer MIT 许可证对应 slicer，不代表原版游戏资源授权。 | 应用启动、原版浏览、预览和转换。 |
| `packstudio/data/models/*.xml` | 构建脚本从 MCSkin3D 参考程序的 Models 目录复制 48 个模型。 | 实体预览。 |
| `packstudio/data/boat_legacy.xml` | 旧船模型，来源与分发许可待核实。 | 旧版本船预览。 |
| `packstudio/data/game_names_zh.json` | 从游戏语言资源及参考转换工具中提取中文名称。 | 中文游戏名称。 |
| `packstudio/assets/tool-*.png` | 旧生成脚本直接从 Photoshop 截图提取部分图标；后续脚本重绘过部分图标，需要逐项建立来源记录。 | 编辑工具图标。 |
| `packstudio/assets/mcps.png`、`mcps.ico` | 在源码目录中找到成品图标，原创或授权证明待补。 | 应用图标和打包。 |

Photoshop 参考截图 `ps-toolbar-reference.png`、私人素材包、参考程序、用户工程、缓存与历史导出产物留在原工程。

## 人工处理事项

1. 确定整体项目许可证及版权署名。
2. 逐项确认原版资源、模型、语言文本和图标的来源及授权，或替换为可分发资源。
3. 确认保留的派生数据、索引和命名数据的分发范围。
4. 准备发行程序时整理实际依赖的许可证文件。
5. 完成资源补齐后，执行安装和构建验收。仓库公开状态由所有者另行决定。
