#!/usr/bin/env python3
from pathlib import Path
import json
p=Path(__file__).resolve().parents[1]
base={}
for line in (p/'工具/基础词条.tsv').read_text().splitlines():
    if not line.strip():continue
    a,b=line.split('\t',1)
    base[a.replace('\\n','\n')]=b.replace('\\n','\n')
exact={}
for en,zh in base.items():
    for v in {en,en.upper(),en.lower(),en.title(),en[:1].upper()+en[1:]}:
        for key in {v,v.replace(' ','_'),v.replace('_',' ')}:
            exact.setdefault(key,zh)
            if '\n' not in key and len(key)<100:
                exact.setdefault(key+' ',zh+' ')
                exact.setdefault(key+':',zh+'：')
# Explicit spelling and rich text used by menus.
for en,zh in base.items():
    exact[en]=zh
for en in ['Copy','Paste','Paste as child','Delete','Rename']:
    exact['<color=#999>'+en+'</color>']='<color=#999>'+base[en]+'</color>'
exact['Welcome to the\nSquareLine Studio']='欢迎使用\nSquareLine Studio'
exact['ID:\nType:\nDate:']='编号：\n类型：\n日期：'
exact['<size=24>End User License Agreement (EULA)</size>\r\n']='<size=24>最终用户许可协议（EULA）</size>\r\n'
# Limit the render method to observed spellings plus explicit dictionary entries.
observed=set(json.loads((p/'工具/界面原文清单.json').read_text()))
observed.update(base)
observed.update(k.upper() for k in base)
exact={k:v for k,v in exact.items() if k in observed}
for days in range(31):
    exact[f'There are {days} days left\nin the trial version']=f'试用期还剩 {days} 天'
for minutes in range(61):
    exact[f'{minutes} mins']=f'{minutes} 分钟'
exact.update({k.strip():v.strip() for k,v in list(exact.items()) if k.strip()})
# Full legal agreement and version/brand/file strings are intentionally retained.
prefix={
 'Language: <b><color=#fff>':'语言：<b><color=#fff>',
 'Font is missing: ':'缺少字体：',
 'File is missing: ':'缺少文件：',
 'Project export failed':'工程导出失败',
 'Project Export Failed':'工程导出失败',
 'Error: ':'错误：',
 'ERROR: ':'错误：',
 'Warning: ':'警告：',
 'WARNING: ':'警告：',
 'WARNING! ':'警告！',
 'Connection failed: ':'连接失败：',
 'Invalid font size! default is \'16\', but you set: ':'字号无效！默认值为 16，当前值为：',
 'Invalid font name, this font exists already!':'字体名称无效，已存在同名字体！',
 'An asset with the same name [':'已存在同名资源 [',
 'Can\'t load image: ':'无法加载图像：',
 'Can\'t load asset: ':'无法加载资源：',
 'Select image':'选择图像',
 'Select font':'选择字体',
 'Select folder':'选择文件夹',
 'Select project':'选择工程',
 'Select Project':'选择工程',
 'Screen - ':'屏幕 - ',
 ' Screens: ':' 屏幕数：',
 ' Widgets: ':' 控件数：',
 'Screens: ':'屏幕数：',
 'Widgets: ':'控件数：',
 'Style (':'样式（',
 'STYLE (':'样式（',
 'Action (':'动作（',
 'ACTION (':'动作（',
 'EVENT (':'事件（',
 'Event (':'事件（',
 'There are ':'剩余 ',
 'Export in progress':'正在导出',
 'Downloading board list':'正在下载开发板列表',
 'Rebuilding all screens...':'正在重建所有屏幕…',
 'Rebuilding screens [':'正在重建屏幕 [',
 'Collect ':'收集 ',
 'Size: ':'尺寸：',
 'Mouse X: ':'鼠标 X：',
 'Mouse Y: ':'鼠标 Y：',
 '<b>ERROR:</b> ':'<b>错误：</b> ',
 '><b>ERROR:</b> ':'><b>错误：</b> ',
 '<color=#f00>Some files are missing</color>':'<color=#f00>部分文件缺失</color>',
}
# Do not add arbitrary partial word replacements: matching is exact or anchored.
(p/'简体中文词典.json').write_text(json.dumps({'exact':exact,'prefix':prefix},ensure_ascii=False,indent=2)+'\n')
print(len(base),'基础词条，',len(exact),'显示匹配，',len(prefix),'动态前缀')
