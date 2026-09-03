#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
贸易单据审查 - 环境自检与依赖安装

审查开始前先跑一次，确认 Python 解释器与依赖可用。任何一项缺失会自动尝试安装，
安装失败则给出明确提示而不是让后续步骤静默崩溃。

用法：
  python bootstrap.py            检查并按需安装
  python bootstrap.py --check    只检查，不安装

依赖：
  pymupdf  （渲染 PDF 为 PNG，必需）
  requests （调用 GACC 在华注册号核验接口，仅在需要核验时必需）

输出：JSON，含 python 路径、各依赖状态、下载目录探测结果。
"""
import sys
import json
import shutil
import subprocess
from pathlib import Path

REQUIRED = {
    # PyMuPDF 1.28 起模块名为 pymupdf，旧版为 fitz，任一存在即视为已装
    'pymupdf': {'import': ('pymupdf', 'fitz'), 'pip': 'pymupdf',
                'desc': 'PDF 渲染为 PNG（步骤 A 必需）'},
    'requests': {'import': ('requests',), 'pip': 'requests',
                 'desc': 'GACC 在华注册号核验（步骤 B-3 需要）'},
}


def check_import(import_names):
    """按优先级尝试导入，任一成功即视为已安装。"""
    if isinstance(import_names, str):
        import_names = (import_names,)
    for name in import_names:
        try:
            mod = __import__(name)
            return {'installed': True, 'version': getattr(mod, '__version__', None),
                    'import_as': name}
        except Exception:
            continue
    return {'installed': False, 'version': None, 'import_as': None}


def try_install(pip_name):
    """用当前解释器自带的 pip 安装。失败返回错误信息。"""
    try:
        proc = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', pip_name, '--disable-pip-version-check'],
            capture_output=True, text=True, timeout=300
        )
        if proc.returncode == 0:
            return {'ok': True, 'output': (proc.stdout or '').strip()[-500:]}
        return {'ok': False, 'error': (proc.stderr or proc.stdout or '').strip()[-500:]}
    except Exception as e:
        return {'ok': False, 'error': repr(e)}


def detect_downloads():
    """跨平台探测下载目录。找不到返回 None，由调用方询问用户。"""
    home = Path.home()
    candidates = [home / 'Downloads', home / '下载', home / 'Desktop']
    for c in candidates:
        if c.is_dir():
            return str(c)
    return None


def main():
    check_only = '--check' in sys.argv
    result = {
        'success': True,
        'python': sys.executable,
        'python_version': sys.version.split()[0],
        'platform': sys.platform,
        'check_only': check_only,
        'deps': {},
    }

    for key, cfg in REQUIRED.items():
        st = check_import(cfg['import'])
        entry = {'desc': cfg['desc'], **st, 'action': 'none'}
        if not st['installed'] and not check_only:
            inst = try_install(cfg['pip'])
            entry['action'] = 'installed' if inst['ok'] else 'install_failed'
            if not inst['ok']:
                entry['install_error'] = inst.get('error')
                result['success'] = False
            else:
                after = check_import(cfg['import'])
                entry['installed'] = after['installed']
                entry['version'] = after['version']
                if not after['installed']:
                    entry['action'] = 'install_failed'
                    result['success'] = False
        elif not st['installed'] and check_only:
            entry['action'] = 'missing'
            result['success'] = False
        result['deps'][key] = entry

    result['downloads_dir'] = detect_downloads()
    if not result['downloads_dir']:
        result['note'] = '未能自动定位下载目录，请向用户确认报告存放位置。'

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['success'] else 1)


if __name__ == '__main__':
    main()
