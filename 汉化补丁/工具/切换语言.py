#!/usr/bin/env python3
"""Install the already-built, checksum-verified Chinese or original files."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile

patch = Path(__file__).resolve().parents[1]
root = Path(os.environ.get('SQUARELINE_APP_DIR', str(patch.parent))).expanduser().resolve()
mode = sys.argv[1] if len(sys.argv) == 2 else ''
if mode not in ['中文', '英文']:
    raise SystemExit('用法：切换语言.py 中文|英文')
exe = root / 'SquareLine_Studio.x86_64'
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        if (proc/'exe').resolve() == exe:
            raise SystemExit('请先正常退出 SquareLine Studio，再切换语言；未修改任何文件。')
    except (PermissionError, FileNotFoundError, ProcessLookupError):
        pass
manifest = json.loads((patch/'校验清单.json').read_text())
plans = []
for rel, hashes in manifest['files'].items():
    target = root/rel
    source = patch/('中文文件' if mode == '中文' else '备份')/rel
    current = hashlib.sha256(target.read_bytes()).hexdigest()
    if current not in hashes.values():
        raise SystemExit(f'文件与已记录版本不符，已停止，避免覆盖其他修改：{target}')
    content = source.read_bytes()
    expected = hashes['chinese_sha256' if mode == '中文' else 'original_sha256']
    if hashlib.sha256(content).hexdigest() != expected:
        raise SystemExit(f'补丁校验失败，已停止：{source}')
    plans.append((target, content))
for target, content in plans:
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        name = tmp.name
    os.chmod(name, target.stat().st_mode & 0o777)
    os.replace(name, target)
print(f'已切换为{mode}界面，重新启动 SquareLine Studio 后生效。')
