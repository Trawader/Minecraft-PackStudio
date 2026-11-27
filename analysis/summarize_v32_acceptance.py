import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'analysis/v32-acceptance-20261118'
suite=json.loads((out/'results.json').read_text(encoding='utf-8'))
real=json.loads((out/'real-workflows.json').read_text(encoding='utf-8'))
assert real['results'][-1].get('step')=='complete','Workflows still running'
exports=[r for r in real['results'] if r.get('step')=='reopen-export-reimport']
assert len(exports)==14 and len(suite)==46 and all(r['exit_code']==0 for r in suite)
lines=['# V3.2 两轮离屏测试记录','',
'日期：2026-11-18 至 2026-11-19。范围为当前主目录源码；未重新打包发布版。',
'', '## 结果', '',
'- 23 个专项脚本各执行两遍，46 次通过。日志位于本目录。',
'- V3.2 的 7 个实际 ZIP 各完成两轮导入、加入项目、保存、关闭重开、导出和回读，共 14 次导出检查通过。',
'- 第二轮倒序导入，并使用不同的亮度参数，避免仅复用第一轮结果。',
'- 有普通 PNG 的包执行预览取消、应用、撤销、重做和批量修改／整体回滚；纯音效和动画包由对应专项脚本补充编辑测试，两遍均通过。',
'- 实际天空包括 486 万、629 万及 354 万像素图片，保持原尺寸编辑、撤销、重做和持久化。',
'- 项目编辑没有污染素材库副本；7 个输入 ZIP 的 SHA-256 未改变。',
'- 导出 ZIP CRC、重复路径、安全路径、回读字节一致性通过，没有新插入内部转换报告、测试目录或工程文件。',
'- 音效和 properties 配置保持原字节；动画配置存在下述已报告的转换省略，不能概括为全部完整保留。',
'', '## 未解决的兼容性问题', '',
'Blue 128x 声明 pack_format=1，但含铁粒、知识之书等较新物品。“保留原始格式”根据最新资源推断为 1.12.2，随后将旧 clock.png、compass.png 及其动画配置省略。两轮均复现，省略写入软件转换报告。不能把 ZIP 结构通过视为资源完整性通过。',
'',
'已验证临时处理：明确选择 1.8.9 导出，clock.png 及其 .mcmeta 均按原字节保留，证据见 blue-explicit-legacy-export.json。此处理不代表较新物品在旧版游戏中可用。',
'',
'其他包也存在有报告的旧资源省略（如旧不透明树叶贴图），详见各包报告；本次未把所有省略认定为软件缺陷，也未将它们视为游戏内已验收。未修改版本推断或新增旧时钟动画拆分规则。',
'', '## 测试边界', '',
'主要验证为 Qt 离屏事件模拟和真实数据调用，包含进度心跳、取消、冲突保护和回滚。用户要求后停止所有桌面操作；未完成原生鼠标全流程验收，未启动 Minecraft。音效检查不代表实际听感验收。',
'', '测试工作目录：`'+real['workspace']+'`。包含每轮工程、导出 ZIP 及独立报告。',
'', '| 轮次 | 材质包 | 导出文件数 | 被省略的动画配置数 |', '|---|---|---:|---:|']
for r in exports:
    lines.append(f"| {r['round']} | {r['pack'].split(' (from ')[0]} | {r['files']} | {len(r['configuration_omissions'])} |")
(out/'测试结果.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('46 regression executions; 14 real-pack round trips; compatibility caveat recorded.')
