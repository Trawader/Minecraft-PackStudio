"""Render the completed ten-run test report without re-exporting any packs."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
folder=Path(sys.argv[1]) if len(sys.argv)>1 else sorted((ROOT/'test').glob('bidirectional-results-*'))[-1]
data=json.loads((folder/'report.json').read_text('utf8'))
lines=['# 十组高低版本混搭测试及补测','',
 '直接调用内部 API，未打开编辑器窗口，未进行 Minecraft 游戏内测试。',
 f"固定随机种子：{data['seed']}。原始输入 ZIP 数：{len(data['inputs'])}。",'',
 '## 输入版本说明','',
 '新加入的两个 ZIP 均声明 pack_format=15，即 1.20.1；没有新版拆分的 HUD 目录。测试没有把其中任何一个强行改标为原生 1.21.11。',
 '额外生成 derived-source-1.21.11.zip，作为明确转换后的 1.21.11 中间包，用于高版本拆分素材向低版本图集重组测试。它不是第六个原始上传包，也不算入目标导出数量。','',
 '## 组成和核验','',
 '每组：12 种小素材（6 个 GUI、6 个粒子）+ 1 个同类下层重复项 + 2 张完整图集 + 12 张独立 PNG + 1 个底包。每个原始上传包及中间包均贡献小素材和独立图片。',
 '不同类型小素材同时生效，同类上层优先；逐项核验目标槽位像素、保留高清尺寸、独立 PNG 覆盖、目标版本元数据、全部 PNG 解码、ZIP CRC 和文件名不重复。',
 '透明度逐像素严格一致，颜色按预乘 alpha 比较，允许 1/255 舍入；不比较全透明像素的隐藏 RGB。本次使用 keep 策略，不把全透明部件视为缺失主动补原版。','',
 '|组|底包版本|目标版本|叠加检查|PNG 数|省略记录|未验证记录|',
 '|---|---|---|---|---:|---:|---:|']
for i,run in enumerate(data['runs'],1):
 actions=run.get('conversion_actions',{})
 lines.append(f"|{i}|{run.get('base_version','?')}|[{run['target']}]({run.get('zip','')})|{run['status']}|{run.get('png_decoded','—')}|{actions.get('omitted','—')}|{actions.get('unresolved','—')}|")
lines+=['',f"通过 {sum(r['status']=='PASS' for r in data['runs'])}/{len(data['runs'])}；原始 ZIP 哈希未改变：{data.get('original_zip_hashes_unchanged',False)}。",'',
 '首轮十组中 1.13.2 导出超限失败，其余九组通过；追加 26.2 一组通过，共获得十个不同版本的成功导出。',
 '失败原因：Crystal 中 generic_0.png 为 256×256，合入 1.13.2 粒子图集的 8×8/256×256 槽位需要 8192×8192（约 6711 万像素），超过 3200 万像素安全上限。没有降低素材清晰度，也没有放宽上限。已修复先放大再检测的分配顺序，改为分配前拦截并报告来源与目标文件。','',
 '## 限制','',
 'PASS 表示上述自动核验通过，不代表所有资源跨版本无损兼容。无可靠映射的旧模型、实体布局或不存在的物品会被省略；MCPatcher、OptiFine、自定义资源可能保留但不保证可用。每个 ZIP 内的 packstudio-conversion-report.json 有完整记录，表中计数是记录数。',
 '此前 GUI 升级审计发现的酿造台、创造栏、村民交易等布局适配风险未在本次测试中修复；不能从随机部件像素检查通过推断所有界面在游戏里都正确。',
 'report.json 保存逐组从上到下的素材来源、来源版本、区域、目标路径和核验结果。']
(folder/'测试结果.md').write_text('\n'.join(lines),'utf8')
print(folder)
print([(r['target'],r['status']) for r in data['runs']])
