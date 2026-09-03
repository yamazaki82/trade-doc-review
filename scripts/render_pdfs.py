#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
贸易单据审查 - PDF 渲染脚本

将（扫描件 / 图片型，无文本层）PDF 逐页渲染为高清 PNG，供多模态读图审查。
解决了 Read 工具直接读图片型 PDF 报 "Cannot display content of binary file" 的问题。

用法：
  python render_pdfs.py <output_dir> <pdf_path1> [pdf_path2] ...
  python render_pdfs.py <output_dir> --dir <pdf_directory>
  python render_pdfs.py <output_dir> contract.pdf --dpi 300
  python render_pdfs.py <output_dir> coo.pdf --pages 1 --dpi 480 --suffix hi

参数：
  --dpi N      渲染精度，默认 300。小字密集（如 GACC 注册号、小号唛头）建议 400-600
  --pages N N  只渲染指定页码（1 起），用于局部重渲染
  --suffix S   输出文件名附加后缀，避免重渲染覆盖原图
  --dir D      扫描该目录下所有 *.pdf

输出：
  每个 PDF 渲染为 <safe_basename>[_S]_pNN.png
  并打印 JSON manifest（页码、图片路径、像素尺寸），供调用方读取。

依赖：pymupdf。未安装时先跑 bootstrap.py。
"""
import sys
import json
import argparse
from pathlib import Path

try:
    # PyMuPDF 1.28 起推荐 import pymupdf，旧版为 import fitz，两者都兼容
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
except ImportError:
    print(json.dumps({
        'success': False,
        'error': '缺少 pymupdf，请先运行 python bootstrap.py 安装依赖'
    }, ensure_ascii=False))
    sys.exit(1)

DEFAULT_DPI = 300


def sanitize(name):
    """清理文件名中的非法字符，保留中英文、数字与常见符号。"""
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in name)


def render_one(pdf_path, out_dir, dpi, pages, suffix):
    doc = fitz.open(str(pdf_path))
    total = len(doc)
    targets = [p - 1 for p in pages] if pages else list(range(total))
    invalid = [p for p in targets if p < 0 or p >= total]
    if invalid:
        doc.close()
        raise ValueError('页码超出范围，该 PDF 共 %d 页' % total)

    safe = sanitize(pdf_path.stem) + (('_' + sanitize(suffix)) if suffix else '')
    files = []
    for i in targets:
        page = doc[i]
        pix = page.get_pixmap(dpi=dpi)
        out_name = '%s_p%02d.png' % (safe, i + 1)
        out_path = out_dir / out_name
        pix.save(str(out_path))
        files.append({'page': i + 1, 'path': str(out_path),
                      'width': pix.width, 'height': pix.height})
    doc.close()
    return {'pdf': str(pdf_path), 'page_count': total, 'dpi': dpi, 'images': files}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('output_dir')
    ap.add_argument('pdfs', nargs='*')
    ap.add_argument('--dir', help='扫描该目录下的所有 *.pdf')
    ap.add_argument('--dpi', type=int, default=DEFAULT_DPI, help='渲染精度，默认 %d' % DEFAULT_DPI)
    ap.add_argument('--pages', type=int, nargs='+', help='只渲染指定页码（1 起）')
    ap.add_argument('--suffix', default='', help='输出文件名附加后缀')
    args = ap.parse_args()

    if args.dpi < 72 or args.dpi > 1200:
        print(json.dumps({'success': False, 'error': 'dpi 应在 72-1200 之间'},
                         ensure_ascii=False))
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = list(args.pdfs)
    if args.dir:
        d = Path(args.dir)
        if not d.is_dir():
            print(json.dumps({'success': False, 'error': '目录不存在: %s' % args.dir},
                             ensure_ascii=False))
            sys.exit(1)
        pdfs += [str(p) for p in sorted(d.glob('*.pdf'))]

    if not pdfs:
        print(json.dumps({'success': False, 'error': '未提供任何 PDF'}, ensure_ascii=False))
        sys.exit(1)

    manifest = {'success': True, 'output_dir': str(out_dir), 'dpi': args.dpi, 'rendered': []}
    for p in pdfs:
        try:
            manifest['rendered'].append(
                render_one(Path(p), out_dir, args.dpi, args.pages, args.suffix))
        except Exception as e:
            manifest['rendered'].append({'pdf': p, 'error': repr(e)})
            manifest['success'] = False

    max_side = 0
    for r in manifest['rendered']:
        for img in r.get('images', []):
            max_side = max(max_side, img['width'], img['height'])
    manifest['max_side_px'] = max_side
    if max_side > 4096:
        manifest['hint'] = '图片长边 %dpx 偏大，多模态识读成本高。若非小字密集单据，' \
                           '可降到 200-250 dpi 重渲染。' % max_side

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
