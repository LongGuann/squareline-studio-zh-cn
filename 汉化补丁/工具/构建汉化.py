#!/usr/bin/env python3
"""SquareLine 1.6.3: translate Unity UI rendering without changing Text.text/data."""
from pathlib import Path
import copy
import hashlib
import io
import os
import json
import struct
import sys

sys.path.append('/usr/lib/python3/dist-packages')
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.cil.body.reader import CilMethodBodyReaderBytes
import UnityPy

PATCH = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('SQUARELINE_APP_DIR', str(PATCH.parent))).expanduser().resolve()
BACKUP = PATCH / '备份'
OUTPUT = PATCH / '中文文件'
FILES = ['SquareLine_Studio_Data/Managed/UnityEngine.UI.dll',
         'SquareLine_Studio_Data/sharedassets0.assets']


def align(n, a=4):
    return (n + a - 1) // a * a


def compressed(n):
    if n < 0x80:
        return bytes([n])
    if n < 0x4000:
        return struct.pack('>H', n | 0x8000)
    return struct.pack('>I', n | 0xc0000000)


class IL:
    def __init__(self):
        self.code = bytearray()
        self.labels = {}
        self.fixups = []
        self.counter = 0

    def label(self, name=None):
        if name is None:
            self.counter += 1
            return 'L' + str(self.counter)
        self.labels[name] = len(self.code)

    def op(self, op, token=None):
        self.code.append(op)
        if token is not None:
            self.code.extend(struct.pack('<I', token))

    def branch(self, op, label):
        self.op(op)
        self.fixups.append((len(self.code), label))
        self.code.extend(b'\0' * 4)

    def finish(self):
        for off, label in self.fixups:
            struct.pack_into('<i', self.code, off, self.labels[label] - off - 4)
        return self.code


def build_ui(mapping, prefixes):
    src = BACKUP / FILES[0]
    p = dnfile.dnPE(str(src))
    data = bytearray(src.read_bytes())
    md = p.get_offset_from_rva(p.net.struct.MetaDataRva)
    streams = {k: bytearray(data[md+s.struct.Offset:md+s.struct.Offset+s.struct.Size])
               for k, s in p.net.metadata.streams.items()}
    old_counts = {tid: len(t.rows) for tid, t in p.net.mdtables.tables.items()}
    additions = {}

    def heap(name, content):
        h = streams[name]
        idx = len(h)
        h.extend(content)
        return idx

    def string(s):
        return heap(b'#Strings', s.encode() + b'\0')

    def blob(b):
        return heap(b'#Blob', compressed(len(b)) + b)

    us_cache = {}
    def us(s):
        if s not in us_cache:
            b = s.encode('utf-16le')
            special = int(any(ord(c) > 0x7f or ord(c) in range(1, 9) or
                              ord(c) in range(14, 32) or c in "'\x7f-" for c in s))
            us_cache[s] = 0x70000000 | heap(b'#US', compressed(len(b)+1) + b + bytes([special]))
        return us_cache[s]

    def addrow(table, row):
        additions.setdefault(table, []).append(row)
        return old_counts.get(table, 0) + len(additions[table])

    typerefs = {str(t.TypeNamespace)+'.'+str(t.TypeName): i+1
                for i, t in enumerate(p.net.mdtables.TypeRef)}
    types = {str(t.TypeName): (i+1, t) for i, t in enumerate(p.net.mdtables.TypeDef)}
    textid, texttype = types['Text']
    inputid, inputtype = types['InputField']
    methods = {str(m.row.Name): m.row_index for m in texttype.MethodList}
    input_getter = next(m.row_index for m in inputtype.MethodList
                        if str(m.row.Name) == 'get_textComponent')
    input_readonly = next(m.row_index for m in inputtype.MethodList
                          if str(m.row.Name) == 'get_readOnly')

    def member(classname, name, signature):
        rid = typerefs[classname]
        for i, m in enumerate(p.net.mdtables.MemberRef):
            if (str(m.Name) == name and m.Class.table.name == 'TypeRef' and
                    m.Class.row_index == rid and m.Signature.value == signature):
                return 0x0a000000 | (i+1)
        idx = addrow(10, struct.pack('<HHH', (rid << 3) | 1, string(name), blob(signature)))
        return 0x0a000000 | idx

    compare = member('System.String', 'CompareOrdinal', b'\x00\x02\x08\x0e\x0e')
    starts = member('System.String', 'StartsWith', b'\x20\x01\x02\x0e')
    substring = member('System.String', 'Substring', b'\x20\x01\x0e\x08')
    concat = member('System.String', 'Concat', b'\x00\x02\x0e\x0e\x0e')
    trim = member('System.String', 'Trim', b'\x20\x00\x0e')
    generic_parent = next(i+1 for i, m in enumerate(p.net.mdtables.MemberRef)
                          if str(m.Name) == 'GetComponentInParent' and
                          m.Class.table.name == 'TypeRef' and
                          str(m.Class.row.TypeName) == 'Component' and
                          m.Signature.value == b'\x30\x01\x00\x1e\x00')
    spec = addrow(43, struct.pack('<HH', (generic_parent << 1) | 1,
                                 blob(b'\x0a\x01\x12' + compressed(inputid << 2))))
    local_sig = addrow(17, struct.pack('<H', blob(b'\x07\x02\x0e\x0e')))

    il = IL()
    # Never translate the editable text of InputFields. Placeholders still translate.
    il.op(0x02)                         # ldarg.0
    il.op(0x28, 0x2b000000 | spec)     # GetComponentInParent<InputField>
    il.op(0x25)                         # dup
    il.branch(0x39, 'no_parent')
    il.op(0x25)
    il.op(0x6f, 0x06000000 | input_readonly)
    il.branch(0x3a, 'no_parent')        # read-only labels can translate
    il.op(0x6f, 0x06000000 | input_getter)
    il.op(0x02)
    il.code.extend(b'\xfe\x01')        # ceq
    il.branch(0x39, 'translate')
    il.op(0x02)
    il.op(0x6f, 0x06000000 | methods['get_text'])
    il.op(0x2a)
    il.label('no_parent')
    il.op(0x26)
    il.label('translate')
    il.op(0x02)
    il.op(0x6f, 0x06000000 | methods['get_text'])
    il.op(0x0a)                         # stloc.0
    il.op(0x06)
    il.branch(0x39, 'original')
    il.op(0x06)
    il.op(0x6f, trim)
    il.op(0x0b)                         # stloc.1 (lookup only, retain original)

    def tree(items):
        if not items:
            il.branch(0x38, 'prefixes')
            return
        mid = len(items)//2
        en, zh = items[mid]
        match, left = il.label(), il.label()
        il.op(0x07)
        il.op(0x72, us(en))
        il.op(0x28, compare)
        il.op(0x25)
        il.branch(0x39, match)
        il.op(0x16)
        il.branch(0x3f, left)
        tree(items[mid+1:])
        il.label(left)
        tree(items[:mid])
        il.label(match)
        il.op(0x26)
        il.op(0x72, us(zh))
        il.op(0x2a)

    tree(sorted(mapping.items()))
    il.label('prefixes')
    # Null is a legitimate Text value; StartsWith must not run on null.
    il.op(0x06)
    il.branch(0x39, 'original')
    for en, zh in sorted(prefixes.items(), key=lambda x: -len(x[0])):
        nxt = il.label()
        il.op(0x06)
        il.op(0x72, us(en))
        il.op(0x6f, starts)
        il.branch(0x39, nxt)
        il.op(0x72, us(zh))
        il.op(0x06)
        il.op(0x20, len(en))
        il.op(0x6f, substring)
        il.op(0x28, concat)
        il.op(0x2a)
        il.label(nxt)
    il.label('original')
    il.op(0x06)
    il.op(0x2a)
    code = il.finish()
    body = struct.pack('<HHII', 0x3013, 4, len(code), 0x11000000 | local_sig) + code
    last = max(p.sections, key=lambda s: s.PointerToRawData)
    method_off = align(len(data))
    method_rva = last.VirtualAddress + method_off - last.PointerToRawData
    helper_id = old_counts[6] + 1
    helper_sig = blob(b'\x00\x01\x0e\x12' + compressed(textid << 2))
    # Give the helper its own accessible type; a compiler-generated private
    # nested value type cannot be called from UnityEngine.UI.Text under Mono.
    addrow(2, struct.pack('<IHHHHH', 0x00100181,
                          string('SquareLineZhCN'), string('SquareLine.Localization'),
                          (typerefs['System.Object'] << 2) | 1,
                          old_counts[4]+1, helper_id))
    addrow(6, struct.pack('<IHHHHH', method_rva, 0, 0x96,
                          string('SquareLine_ZhCN_RenderText'), helper_sig,
                          old_counts[8]+1))
    # All existing indices must retain their original widths.
    assert len(streams[b'#Strings']) < 65536
    assert len(streams[b'#Blob']) < 65536
    assert old_counts[6]+1 < 8192   # MethodDefOrRef coded indices remain 2 bytes.
    assert old_counts[10]+len(additions.get(10, [])) < 8192

    changed = []
    textfield = next(f.row_index for f in texttype.FieldList if str(f.row.Name) == 'm_Text')
    for mi in texttype.MethodList:
        m = mi.row
        if str(m.Name) not in ['OnPopulateMesh', 'get_preferredWidth', 'get_preferredHeight']:
            continue
        b = CilMethodBody(CilMethodBodyReaderBytes(p.get_data(m.Rva, 10000)))
        for ins in b.instructions:
            op = ins.operand
            get_text = (ins.opcode.name in ['call', 'callvirt'] and
                        getattr(op, 'value', 0) == (0x06000000 | methods['get_text']))
            get_field = (ins.opcode.name == 'ldfld' and
                         getattr(op, 'value', 0) == (0x04000000 | textfield))
            if get_text or get_field:
                off = p.get_offset_from_rva(m.Rva) + ins.offset
                data[off:off+5] = b'\x28' + struct.pack('<I', 0x06000000 | helper_id)
                changed.append(str(m.Name))
    assert sorted(changed) == sorted(['OnPopulateMesh', 'get_preferredWidth', 'get_preferredHeight'])

    # Rebuild the table stream, appending rows without renumbering existing tokens.
    old = streams[b'#~']
    valid = struct.unpack_from('<Q', old, 8)[0]
    present = [i for i in range(64) if valid >> i & 1]
    all_ids = sorted(set(present) | set(additions))
    header = bytearray(old[:24])
    struct.pack_into('<Q', header, 8, sum(1 << i for i in all_ids))
    sorted_mask = struct.unpack_from('<Q', header, 16)[0]
    for i in additions:
        sorted_mask &= ~(1 << i)
    struct.pack_into('<Q', header, 16, sorted_mask)
    for i in all_ids:
        header.extend(struct.pack('<I', old_counts.get(i, 0)+len(additions.get(i, []))))
    for i in all_ids:
        table = p.net.mdtables.tables.get(i)
        if table is not None and table.rows:
            start = table.rows[0].struct.get_file_offset()
            end = table.rows[-1].struct.get_file_offset()+table.row_size
            header.extend(p.__data__[start:end])
        header.extend(b''.join(additions.get(i, [])))
    streams[b'#~'] = header

    # Retain the metadata signature, version, flags, and stream ordering.
    first = min(s.struct.get_file_offset() for s in p.net.metadata.streams.values())-md
    root_header = bytearray(p.__data__[md:md+first])
    header_size = first + sum(8+align(len(k)+1) for k in streams)
    stream_data = bytearray()
    for k, value in streams.items():
        root_header.extend(struct.pack('<II', header_size+len(stream_data), len(value)))
        name = k+b'\0'
        root_header.extend(name+b'\0'*(align(len(name))-len(name)))
        stream_data.extend(value)
        stream_data.extend(b'\0'*(align(len(stream_data))-len(stream_data)))
    metadata = root_header+stream_data
    data.extend(b'\0'*(method_off-len(data)))
    data.extend(body)
    meta_off = align(len(data))
    data.extend(b'\0'*(meta_off-len(data)))
    data.extend(metadata)
    meta_rva = last.VirtualAddress+meta_off-last.PointerToRawData
    virtual_size = len(data)-last.PointerToRawData
    raw_size = align(virtual_size, p.OPTIONAL_HEADER.FileAlignment)
    data.extend(b'\0'*(last.PointerToRawData+raw_size-len(data)))
    struct.pack_into('<I', data, last.get_field_absolute_offset('Misc_VirtualSize'), virtual_size)
    struct.pack_into('<I', data, last.get_field_absolute_offset('SizeOfRawData'), raw_size)
    struct.pack_into('<I', data, last.get_field_absolute_offset('Characteristics'),
                     (last.Characteristics | 0x40000040) & ~0x02000000)
    struct.pack_into('<I', data, p.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),
                     align(last.VirtualAddress+virtual_size, p.OPTIONAL_HEADER.SectionAlignment))
    struct.pack_into('<II', data, p.net.struct.get_field_absolute_offset('MetaDataRva'),
                     meta_rva, len(metadata))
    target = OUTPUT / FILES[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    # Reparse every original token and the newly generated IL before installation.
    q = dnfile.dnPE(str(target))
    assert len(q.net.mdtables.MethodDef) == old_counts[6]+1
    m = q.net.mdtables.MethodDef[-1]
    parsed = CilMethodBody(CilMethodBodyReaderBytes(q.get_data(m.Rva, len(body))))
    boundaries = {i.offset for i in parsed.instructions}
    for ins in parsed.instructions:
        if ins.opcode.name.startswith(('br', 'blt')):
            assert ins.operand in boundaries, (ins, ins.operand)
    return {'exact_entries': len(mapping), 'prefix_entries': len(prefixes),
            'method_bytes': len(code), 'render_methods': changed}


def build_fonts():
    src = BACKUP / FILES[1]
    env = UnityPy.load(str(src))
    assets = env.file
    font = next(o for o in env.objects if o.type.name == 'Font' and
                o.read_typetree()['m_Name'] == 'OpenSans-Regular')
    fd = font.read_typetree()
    old_material = assets.objects[fd['m_DefaultMaterial']['m_PathID']]
    old_texture = assets.objects[fd['m_Texture']['m_PathID']]
    next_id = max(assets.objects)+1
    new_font, new_material, new_texture = (copy.copy(x) for x in [font, old_material, old_texture])
    for i, obj in enumerate([new_font, new_material, new_texture]):
        obj.path_id = next_id+i
        assets.objects[obj.path_id] = obj
    fd['m_Name'] = 'SquareLine_ZhCN_DroidSansFallback'
    fd['m_FontNames'] = ['Droid Sans Fallback']
    fd['m_FontData'] = list(Path(os.environ.get('SQUARELINE_CJK_FONT', '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf')).expanduser().read_bytes())
    fd['m_FallbackFonts'] = []
    fd['m_CharacterRects'] = []
    fd['m_KerningValues'] = []
    fd['m_DefaultMaterial']['m_PathID'] = new_material.path_id
    fd['m_Texture']['m_PathID'] = new_texture.path_id
    new_font.save_typetree(fd)
    mat = old_material.read_typetree()
    mat['m_Name'] = 'SquareLine_ZhCN_FontMaterial'
    for prop in mat.get('m_SavedProperties', {}).get('m_TexEnvs', []):
        if prop[1]['m_Texture']['m_PathID'] == old_texture.path_id:
            prop[1]['m_Texture']['m_PathID'] = new_texture.path_id
    new_material.save_typetree(mat)
    tex = old_texture.read_typetree()
    tex['m_Name'] = 'SquareLine_ZhCN_FontTexture'
    new_texture.save_typetree(tex)
    for o in list(assets.objects.values()):
        if o.type.name == 'Font' and o.path_id != new_font.path_id:
            d = o.read_typetree()
            d['m_FallbackFonts'].append({'m_FileID': 0, 'm_PathID': new_font.path_id})
            o.save_typetree(d)
    target = OUTPUT / FILES[1]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(assets.save())
    check = UnityPy.load(str(target)).file
    assert len(check.objects) == len(assets.objects)
    for pid, obj in check.objects.items():
        if obj.type.name == 'Font':
            d = obj.read_typetree()
            assert (pid == new_font.path_id or
                    any(p['m_PathID'] == new_font.path_id for p in d['m_FallbackFonts']))
    return {'cjk_font_path_id': new_font.path_id, 'new_objects': 3}


def main():
    supported = json.loads((PATCH / '支持构建指纹.json').read_text())
    for rel in FILES:
        source = BACKUP / rel if (BACKUP / rel).exists() else ROOT / rel
        if not source.is_file():
            raise SystemExit(f'未找到原版应用文件：{source}；请设置 SQUARELINE_APP_DIR')
        if hashlib.sha256(source.read_bytes()).hexdigest() != supported['files'][rel]:
            raise SystemExit(f'应用文件不匹配已验证的 1.6.3 构建：{source}；请使用原始文件或原版备份')
    for rel in FILES:
        dest = BACKUP / rel
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / rel).read_bytes())
    raw = json.loads((PATCH / '简体中文词典.json').read_text())
    mapping = raw['exact']
    stats = build_ui(mapping, raw['prefix'])
    stats.update(build_fonts())
    protected = 'SquareLine_Studio_Data/Managed/Assembly-CSharp.dll'
    manifest = {'app_version': '1.6.3', 'stats': stats, 'files': {},
                'protected_files': {protected: hashlib.sha256((ROOT/protected).read_bytes()).hexdigest()}}
    for rel in FILES:
        manifest['files'][rel] = {
            'original_sha256': hashlib.sha256((BACKUP/rel).read_bytes()).hexdigest(),
            'chinese_sha256': hashlib.sha256((OUTPUT/rel).read_bytes()).hexdigest()}
    (PATCH / '校验清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
