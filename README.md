# Minecraft PackStudio

Minecraft PackStudio 是面向 Minecraft Java 版资源包的桌面编辑器，集素材管理、像素编辑、物品预览、图集组件处理、项目合成和跨版本导出于一体。

正式版名称为 **Minecraft PackStudio**，发行程序名为 **MCPS**。应用名称统一维护在 `packstudio/release.py`。

## 仓库交付范围

本仓库用于私有源码托管。应用代码、版本映射、界面文本、检查脚本和构建入口随仓库保存；原版资源库、模型、游戏中文文本及待核实图标保留在原工程中，逐项清单见 `docs/private-resources.json`。

**启动和完整打包前，需要按清单补齐本地运行资源。** 原版资源库由 `builtin_assets.py` 在运行时读取。补齐后的文件受 `.gitignore` 管理，授权审查后再决定其仓库分发方式。检查命令为：

```powershell
py -3.13 analysis/check_distribution.py
```

资源来源与分发事项见 `THIRD_PARTY_NOTICES.md`，审查结论见 `docs/distribution-audit.md`。

## 启动

源码运行环境：Windows、Python 3.13、PySide6 6.12.0。

双击 `start.cmd` 启动。首次运行时，脚本创建 `.venv` 虚拟环境并安装 `requirements.txt` 中的依赖。

也可以在本目录执行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

发行版通过 `MCPS.exe` 启动，运行依赖随程序分发。解压时保留完整目录结构，包括 `_internal`。

## 构建

补齐运行资源后，在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe analysis/build_mcps.py
```

构建脚本先核对运行资源，再使用 PyInstaller 生成 `output/McPackStudio/MCPS.exe` 和配套 `_internal`。已有同名输出目录时停止构建，保留现有成品。运行依赖锁定在 `requirements.lock.txt`，构建依赖列于 `requirements-build.txt`。

## 基本流程

1. 导入材质包 ZIP、文件夹、PNG 或 OGG 音效。
2. 在素材库中浏览、筛选和编辑资源。
3. 将整包、单项资源或图集组件加入项目。
4. 调整项目内容、图层顺序和启用状态。
5. 保存 `.MCPSD` 工程文件。
6. 设置包名、描述和目标版本，导出 ZIP 资源包，并查看导出记录。

## 素材库与选择器

素材库保存导入资源的本地副本，支持通过菜单导入，以及拖入 ZIP、文件夹和 PNG。识别结果用于资源命名、分类、版本标记和关联展示；未知素材可通过文件树查看。

素材库提供两种浏览方式：

| 视图 | 用途 |
| --- | --- |
| 文件树 | 按资源路径浏览文件，查看配置、音效、未知资源及图集组件。 |
| 选择器 | 按游戏物品、方块及其他资源类别浏览，结合族类和状态组织内容。 |

选择器围绕物品组织贴图。例如选中铁砧后，编辑区底部展示本体和损坏状态等关联素材；交通工具可以关联对应的实体贴图。分类内容根据当前资源集合建立。

内置原版资源用于浏览、预览、版本识别和转换参考。需要编辑时，将对应资源加入项目建立编辑副本。

## 图集与组件

图集中的语义区域可以作为小素材浏览、编辑、提取和加入项目。例如，粒子图集中的单个粒子，以及界面图集中的爱心、饥饿值图标和经验条。

编辑组件时，修改写回其所属图集的对应区域。组件加入项目后，合成时按区域覆盖承载图；其他区域由项目中的底层内容提供。组件关联信息用于跨版本定位和图集合成。

## 编辑区域

画板提供画笔、橡皮擦、魔术橡皮擦、油漆桶、填充、吸管、矩形选区、魔棒、加深、减淡、变明和变暗等工具。工具菜单提供粗细、容差、作用范围或明暗幅度等设置。

右键色块打开颜色编辑，支持 RGBA、HSVA 和色板。常用色保存在调色盘中。画板支持缩放、平移、撤销、重做、图片替换和 PNG 导出。

### 选区

- 矩形工具通过框选建立选区，魔棒工具通过点击按颜色条件建立选区。默认每次操作都建立新选区，替换原有选区。
- 按住 Shift 操作，在现有选区上加选；按住 Alt 操作，从现有选区中减选。两种工具均采用此规则。
- 存在选区时，像素编辑作用于选区内部。
- 切换移动工具可拖动选区，按回车确认放置并结束选中。
- 切换编辑素材时清除当前选区。

### 调色与渐变

调色面板提供颜色、明暗渐变、透明度和空间渐变处理，可调整饱和度、对比度、亮度及渐变参数。处理范围可使用当前选区、全图或非透明像素。

先预览效果，再通过“应用”提交编辑；取消预览后恢复提交前的画面。批量调色入口用于成组处理素材。材质派生结合部件范围、参考材质和明暗关系生成变体，操作时先确认目标区域。

### 动画

动画编辑器读取贴图及对应动画元数据，提供帧预览和单帧编辑。整体调色可分析各帧范围，并逐帧确认处理区域。动画分析按界面显示的帧数和像素额度执行，较大的动画可逐帧处理。

### 渲染与其他资源

渲染预览根据选中对象和关联资源展示物品或方块模型。天空资源提供天空预览，超大图片进入浏览模式，工具状态随当前资源类型调整。

音效资源提供 OGG 导入、试听和替换入口。关联资源及规则窗口用于查看配置、引用关系和缺失引用。中英文界面通过菜单栏地球图标切换；窗口菜单管理各面板，支持恢复默认工作区。

## 项目与保存

素材库与项目分别保存资源。导入后，素材进入素材库；加入项目时建立独立副本。素材库编辑自动写入本地素材库，项目编辑保存在工程文件中。

项目可组合整包、单张贴图、音效和图集组件。启用状态决定资源是否参与合成，图层顺序决定覆盖优先级：

- 上层整张资源覆盖下层同路径资源。
- 图集组件覆盖对应区域。
- 多个组件按区域和项目顺序参与合成。

使用 `Ctrl+S` 保存工程，`Ctrl+Shift+S` 另存为，`Ctrl+O` 打开工程。工程保存项目图层、资源数据、来源关联和工作版本，打开后继续编辑。

项目采用 `.MCPSD` 文件，同时支持项目文件夹中的 `project.packstudio`。编辑期间，程序在 `projects/` 中写入 `Recovery-*.MCPSD` 恢复副本。操作历史提供像素编辑和资源操作的回看与撤销入口，具体操作范围由历史条目及当前编辑状态决定。

工程文件用于继续制作，导出的 ZIP 用于游戏加载。

## 跨版本与导出

当前代码配置了以下 17 个 Java 版版本节点：

```text
1.7.10   1.8.9    1.9.4    1.12.2   1.13.2   1.14.4
1.15.2   1.16.5   1.18.2   1.19.2   1.20.1   1.20.4
1.20.6   1.21.1   1.21.11  26.2     26.3
```

版本识别结合包元数据、资源路径、原版记录和图集布局信息。资源保留各自的来源信息，同一项目可以组合多个版本的素材。

选择目标版本后，程序按已有映射处理路径重命名、图集切分与重组、语义区域迁移及相关元数据，再按项目顺序合成。需要确认的来源、布局和补全方式在转换流程中交由用户选择。

选择“保留原始格式”时，以可识别的底包版本作为适配依据；底包来源待定时，按素材来源组织导出。

目标版本的资源规则决定保留、迁移和排除结果。自定义物品、特殊天空及扩展配置结合引用关系处理，相关问题记录在导出报告中。扩展资源的游戏效果由目标客户端及其扩展环境共同决定。

导出窗口设置包名、描述、封面和版本，生成包含启用项目内容的 ZIP。导出记录保存在 `.tmp/export-history/`，记录目标路径、来源、转换说明和合成情况，可通过软件中的导出记录界面查看。

## 源码结构

| 位置 | 职责 |
| --- | --- |
| `main.py` | 应用入口、运行日志、安装检查入口。 |
| `packstudio/release.py` | 应用标题和发行程序名。 |
| `packstudio/studio.py`、`ui.py` | 主窗口、交互连接和编辑工作流。 |
| `packstudio/core.py`、`library.py` | 资源数据、工程读写、素材库持久化。 |
| `packstudio/library_browser.py`、`selector.py`、`selector_taxonomy.py` | 文件浏览、物品选择器和分类。 |
| `packstudio/canvas.py`、`selection_state.py`、`pointer_input.py` | 像素画板、选区和鼠标交互。 |
| `packstudio/recolor.py`、`recolor_panel.py`、`gradient_controls.py` | 调色计算、预览面板和渐变设置。 |
| `packstudio/animation_editor.py`、`texture_animation.py` | 动画帧编辑与播放。 |
| `packstudio/material_derivation.py`、`part_derivation.py` | 材质与部件派生。 |
| `packstudio/models.py`、`preview.py`、`sky_view.py` | 模型解析、渲染和天空浏览。 |
| `packstudio/versions.py`、`layouts.py`、`semantics.py` | 版本识别、图集布局和语义映射。 |
| `packstudio/conversion.py`、`adaptation.py` | 跨版本资源转换。 |
| `packstudio/export_priority.py`、`original_export.py`、`export_dialog.py` | 合成优先级、原始格式处理和导出。 |
| `packstudio/resource_graph.py`、`export_integrity.py` | 资源引用与导出完整性处理。 |
| `packstudio/history_window.py`、`resource_history.py` | 操作历史和资源撤销。 |
| `packstudio/localization.py`、`resource_names.py` | 界面语言与资源名称。 |
| `packstudio/data/`、`packstudio/assets/` | 版本数据、原版资源、规则、模型与界面资源。 |
| `analysis/` | 开发分析、专项检查与数据处理脚本。 |
| `docs/` | 设计说明、转换规则、审计与阶段记录。 |

## 本地数据

源码运行时，以下目录位于本源码目录；发行版运行时，位于程序所在目录：

| 位置 | 内容 |
| --- | --- |
| `library/` | 导入素材的本地持久化副本。 |
| `projects/` | 项目恢复副本及默认工程相关内容。 |
| `.tmp/export-history/` | 导出记录。 |
| `.tmp/editor-errors.log` | 应用异常日志。 |
| `.tmp/native-crash.log` | 底层异常日志。 |

备份工作成果时，保存工程文件，并根据需要一并保存素材库与原始资源包。运行资源与源码分发事项见 `THIRD_PARTY_NOTICES.md` 和 `docs/distribution-audit.md`。`analysis/verify_*.py` 为检查源码，其中部分脚本使用本地 `test/` 或 `reference/` 输入；相应素材与历史报告留在原工程中。
