#!/usr/bin/env python3
"""Verify generated IL, data isolation, font coverage and exported sample strings."""
from pathlib import Path
import collections
import hashlib
import io
import os
import json
import sys
sys.path.append('/usr/lib/python3/dist-packages')
import dnfile
import UnityPy
from dncil.cil.body import CilMethodBody
from dncil.cil.body.reader import CilMethodBodyReaderBytes
from fontTools.ttLib import TTFont

patch=Path(__file__).resolve().parents[1]
root=Path(os.environ.get('SQUARELINE_APP_DIR', str(patch.parent))).expanduser().resolve()
targets=patch/'中文文件' if '--built-files' in sys.argv else root
rel='SquareLine_Studio_Data/Managed/UnityEngine.UI.dll'
original=dnfile.dnPE(str(patch/'备份'/rel))
current=dnfile.dnPE(str(targets/rel))
changed=[]
for a,b in zip(original.net.mdtables.MethodDef,current.net.mdtables.MethodDef):
    assert a.Rva==b.Rva
    if not a.Rva:continue
    ba=CilMethodBody(CilMethodBodyReaderBytes(original.get_data(a.Rva,200000)))
    bb=CilMethodBody(CilMethodBodyReaderBytes(current.get_data(b.Rva,200000)))
    if original.get_data(a.Rva,ba.size)!=current.get_data(b.Rva,bb.size):
        changed.append(str(a.Name))
assert sorted(changed)==sorted(['OnPopulateMesh','get_preferredWidth','get_preferredHeight'])
assert str(current.net.mdtables.TypeDef[-1].TypeName)=='SquareLineZhCN'
method=current.net.mdtables.MethodDef[-1]
body=CilMethodBody(CilMethodBodyReaderBytes(current.get_data(method.Rva,200000)))
instructions={i.offset:i for i in body.instructions}
next_ins={a.offset:b.offset for a,b in zip(body.instructions,body.instructions[1:])}

def render(value,editable=False,placeholder=False):
    text=object()
    parent=object() if editable or placeholder else None
    stack=[];loc=[None,None];pc=body.instructions[0].offset
    for _ in range(10000):
        ins=instructions[pc];op=ins.opcode.name;arg=ins.operand
        following=next_ins.get(pc)
        if op=='ldarg.0':stack.append(text)
        elif op=='dup':stack.append(stack[-1])
        elif op=='pop':stack.pop()
        elif op.startswith('ldloc.') and op[-1].isdigit():stack.append(loc[int(op[-1])])
        elif op.startswith('stloc.') and op[-1].isdigit():loc[int(op[-1])]=stack.pop()
        elif op=='ldstr':stack.append(current.net.user_strings.get(arg.rid).value)
        elif op=='ldc.i4.0':stack.append(0)
        elif op=='ldc.i4':stack.append(arg)
        elif op=='ceq':stack.append(stack.pop()==stack.pop())
        elif op=='br':following=arg
        elif op=='brfalse':
            if not stack.pop():following=arg
        elif op=='brtrue':
            if stack.pop():following=arg
        elif op=='blt':
            b,a=stack.pop(),stack.pop()
            if a<b:following=arg
        elif op in ['call','callvirt']:
            if arg.table==43:
                stack.pop();stack.append(parent)
            else:
                row=(current.net.mdtables.MethodDef if arg.table==6 else
                     current.net.mdtables.MemberRef)[arg.rid-1]
                name=str(row.Name)
                if name=='get_text':stack.pop();stack.append(value)
                elif name=='get_textComponent':stack.pop();stack.append(text if editable else object())
                elif name=='get_readOnly':stack.pop();stack.append(False)
                elif name=='Trim':stack.append(stack.pop().strip())
                elif name=='CompareOrdinal':
                    b,a=stack.pop(),stack.pop()
                    stack.append((a>b)-(a<b))
                elif name=='StartsWith':
                    b,a=stack.pop(),stack.pop();stack.append(a.startswith(b))
                elif name=='Substring':
                    b,a=stack.pop(),stack.pop();stack.append(a[b:])
                elif name=='Concat':
                    b,a=stack.pop(),stack.pop();stack.append(a+b)
                else:raise AssertionError(name)
        elif op=='ret':
            assert len(stack)==1
            return stack[0]
        else:raise AssertionError(op)
        pc=following
    raise AssertionError('IL execution did not terminate')

dictionary=json.loads((patch/'简体中文词典.json').read_text())
for en,zh in dictionary['exact'].items():
    assert render(en)==dictionary['exact'].get(en.strip(),zh),(en,render(en),zh)
for value in [None,'', 'user_file.spj','Screen1', 'CONTINUE', 'Save', '中文工程名称']:
    assert render(value,editable=True)==value
assert render('Save',placeholder=True)=='保存'
assert render('  Pad Right  ')=='右内边距'
assert render(' Font ')=='字体'
assert render('File is missing: my-file.png')=='缺少文件：my-file.png'
assert render('  an unknown label  ')=='  an unknown label  '
assert render(None) is None

asset_rel='SquareLine_Studio_Data/sharedassets0.assets'
a=UnityPy.load(str(patch/'备份'/asset_rel)).file
b=UnityPy.load(str(targets/asset_rel)).file
assert len(b.objects)==len(a.objects)+3
retained=0
for pid,obj in a.objects.items():
    if obj.type.name!='Font':
        assert obj.get_raw_data()==b.objects[pid].get_raw_data(),(pid,obj.type.name)
        retained+=1
glyphs=set()
for obj in b.objects.values():
    if obj.type.name=='Font':
        font=TTFont(io.BytesIO(bytes(obj.read_typetree()['m_FontData'])))
        glyphs.update(font.getBestCmap())
required={ord(c) for s in dictionary['exact'].values() for c in s if not c.isspace()}
assert not required-glyphs, sorted(required-glyphs)
code_sha=hashlib.sha256((root/'SquareLine_Studio_Data/Managed/Assembly-CSharp.dll').read_bytes()).hexdigest()
manifest=json.loads((patch/'校验清单.json').read_text())
assert code_sha==manifest['protected_files']['SquareLine_Studio_Data/Managed/Assembly-CSharp.dll']

def user_values(data):
    result=[]
    def walk(x):
        if isinstance(x,dict):
            if 'strtype' in x and 'strval' in x and not x['strtype'].split('/')[-1].startswith('Style_'):
                result.append((x['strtype'],x['strval']))
            for v in x.values():walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(data)
    return collections.Counter(result)
files=[]
sample_checked=False
if Path('/tmp/squareline-zh-check/export/ui/screens/ui_POS_S2.c').is_file() and (root/'examples/POS_272x480/POS.spj').is_file():
    export=Path('/tmp/squareline-zh-check/export/ui')
    files=[p for p in export.rglob('*') if p.is_file()]
    assert len(files)==30
    assert 'lv_label_set_text(ui_Label_Continue, "CONTINUE");' in (export/'screens/ui_POS_S2.c').read_text()
    sample=json.loads((root/'examples/POS_272x480/POS.spj').read_text())
    saved=json.loads(Path('/tmp/squareline-zh-check/POS/POS.spj').read_text())
    assert user_values(sample)==user_values(saved)
    sample_checked=True
report={
    'result':'通过',
    'dictionary_entries':len(dictionary['exact']),
    'prefix_entries':len(dictionary['prefix']),
    'existing_methods_changed':changed,
    'text_getter_and_setter':'字节保持原样',
    'editable_input_and_placeholder':'用户输入保持原样，占位文字可翻译',
    'original_asset_objects_retained':retained,
    'all_translation_glyphs_present':True,
    'assembly_csharp_sha256':code_sha,
    'sample_export_files':len(files),
    'sample_saved_names_texts_enums':'保持原样（旧示例样式定义由应用正常升级）' if sample_checked else '未执行：本机未提供临时示例夹具',
    'sample_exported_CONTINUE':'保持原样' if sample_checked else '未执行：本机未提供临时示例夹具',
    'verification_target':'构建产物' if '--built-files' in sys.argv else '安装文件',
}
(patch/'验证').mkdir(exist_ok=True)
(patch/'验证/验证结果.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
