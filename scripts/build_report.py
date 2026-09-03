#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
贸易单据审查 - HTML 报告生成器

读取 JSON 规格文件，生成带颜色分级、内联 CSS 的 HTML 审查报告。
报告默认 UTF-8 BOM 编码，双击浏览器即可打开，不依赖任何外部资源。

用法：
  python build_report.py <input.json> <output.html>
  python build_report.py <input.json> <output.html> --gacc-json gacc_result.json
  python build_report.py <input.json> <output.html> --downloads-dir ~/Downloads

参数：
  --gacc-json      引入 verify_gacc.py 的输出，自动渲染"在华注册号核验"章节
  --downloads-dir  生成后同时复制一份到该目录（跨平台，不写死路径）

校验：生成前对 spec 做结构校验。任何错误都会中断并列出问题，
      不会产出缺章节的半成品报告。

JSON 规格结构见本文件底部注释。
"""
import sys
import json
import shutil
import argparse
from pathlib import Path

CSS = """
  body { font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif; margin: 24px; color: #2c3e50; background: #fafbfc; }
  h1 { color: #1a3d6e; border-bottom: 3px solid #1a3d6e; padding-bottom: 8px; }
  h2 { color: #1a3d6e; margin-top: 32px; border-left: 5px solid #1a3d6e; padding-left: 10px; }
  .meta { background: #eef3f8; padding: 10px 14px; border-radius: 6px; margin-bottom: 18px; font-size: 14px; }
  .meta div { margin: 3px 0; }
  .verdict { padding: 14px 18px; border-radius: 8px; margin: 18px 0 24px 0; font-size: 16px; border-left: 6px solid #888; background: #f4f4f4; }
  .verdict .vlabel { font-weight: 600; margin-right: 10px; }
  .verdict.ok { background: #e7f6ec; border-left-color: #1e6b3a; color: #1e6b3a; }
  .verdict.warn { background: #fff4e0; border-left-color: #b9770e; color: #8a5a00; }
  .verdict.bad { background: #fde6e3; border-left-color: #a02c2c; color: #a02c2c; }
  .verdict .vbasis { display: block; margin-top: 8px; font-size: 14px; color: #2c3e50; font-weight: 400; line-height: 1.6; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0 24px 0; font-size: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); background: #fff; }
  th { background: #1a3d6e; color: #fff; padding: 10px 8px; text-align: left; border: 1px solid #1a3d6e; }
  td { padding: 8px 10px; border: 1px solid #d6dbe0; vertical-align: top; }
  tr:nth-child(even) td { background: #f7f9fc; }
  td.ok { background: #e7f6ec; color: #1e6b3a; }
  td.warn { background: #fff4e0; color: #8a5a00; }
  td.bad { background: #fde6e3; color: #a02c2c; font-weight: 600; }
  td.note { background: #eef3f8; color: #2c3e50; font-style: italic; }
  td.pending { background: #f0f0f0; color: #666; }
  .risk-card { border-left: 5px solid #e74c3c; background: #fff5f3; padding: 10px 14px; margin: 8px 0; border-radius: 4px; }
  .risk-card.medium { border-left-color: #f39c12; background: #fff8ed; }
  .risk-card.low { border-left-color: #f1c40f; background: #fffaea; }
  .risk-card strong { color: #c0392b; }
  .risk-card.medium strong { color: #d68910; }
  .risk-card.low strong { color: #b7950b; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 600; }
  .pill-red { background: #e74c3c; color: #fff; }
  .pill-orange { background: #f39c12; color: #fff; }
  .pill-yellow { background: #f1c40f; color: #2c3e50; }
  .pill-green { background: #27ae60; color: #fff; }
  .pill-gray { background: #b4b2a9; color: #fff; }
  .legend { font-size: 13px; color: #555; margin: 10px 0; }
  .legend span { margin-right: 16px; }
  .kv td:first-child { font-weight: 600; background: #f0f3f7; width: 26%; }
  ol li { margin: 6px 0; }
  ul li { margin: 5px 0; }
  .empty { color: #7a8896; font-style: italic; padding: 8px 0; }
  .footer { margin-top: 36px; font-size: 12px; color: #7a8896; border-top: 1px solid #d6dbe0; padding-top: 10px; }
"""

STATUS_CLASS = {'ok': 'ok', 'warn': 'warn', 'bad': 'bad', 'note': 'note', 'pending': 'pending'}
SEV_PILL = {'P0': ('pill-red', 'P0 重大'), 'P1': ('pill-orange', 'P1 中度'),
            'P2': ('pill-yellow', 'P2 提示')}
GACC_VERDICT = {
    'PASS': ('ok', 'pill-green', '核验通过'),
    'PASS_WITH_WARNING': ('warn', 'pill-yellow', '通过但有差异项'),
    'FAIL': ('bad', 'pill-red', '核验不通过'),
    'NOT_FOUND': ('bad', 'pill-red', '查无此号'),
    'UNKNOWN': ('pending', 'pill-gray', '未完成核验'),
}
CHECK_LABEL = {
    'existence': '号码存在性', 'reg_state': '注册状态有效性',
    'name_match': '企业名称一致性', 'product_scope': '产品范围覆盖',
    'validity_window': '有效期覆盖装船日', 'country_match': '原产国一致性',
}


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def validate(spec):
    """生成前校验。返回错误列表，空列表表示通过。"""
    errs = []
    if not spec.get('title'):
        errs.append('缺少 title')
    for i, r in enumerate(spec.get('risks', [])):
        if r.get('severity') not in SEV_PILL:
            errs.append('risks[%d].severity 非法：%r（应为 P0/P1/P2）' % (i, r.get('severity')))
        if not r.get('title'):
            errs.append('risks[%d] 缺少 title' % i)
    for key in ('contract_vs_draft', 'bilingual', 'cross_contract'):
        t = spec.get(key)
        if not t:
            continue
        cols = t.get('columns')
        if not cols:
            errs.append('%s 缺少 columns' % key)
            continue
        for j, row in enumerate(t.get('rows', [])):
            cells = row.get('cells')
            if cells is None:
                errs.append('%s.rows[%d] 缺少 cells' % (key, j))
                continue
            if len(cells) != len(cols):
                errs.append('%s.rows[%d] cells 有 %d 项，columns 有 %d 项，数量不匹配'
                            % (key, j, len(cells), len(cols)))
            st = row.get('status')
            if st is not None:
                if 'index' not in st or 'level' not in st:
                    errs.append('%s.rows[%d].status 需含 index 与 level' % (key, j))
                elif not (0 <= st['index'] < len(cols)):
                    errs.append('%s.rows[%d].status.index=%s 越界（columns 共 %d 列）'
                                % (key, j, st['index'], len(cols)))
                elif st['level'] not in STATUS_CLASS:
                    errs.append('%s.rows[%d].status.level=%r 非法（应为 ok/warn/bad/note/pending）'
                                % (key, j, st['level']))
    v = spec.get('verdict')
    if v and not v.get('decision'):
        errs.append('verdict 缺少 decision')
    return errs


def build_table(t):
    cols = t.get('columns', [])
    head = ''.join('<th>%s</th>' % esc(c) for c in cols)
    body = ''
    for r in t.get('rows', []):
        st = r.get('status')
        cells = []
        for i, c in enumerate(r.get('cells', [])):
            cls = ''
            if st and st.get('index') == i:
                cls = ' class="%s"' % STATUS_CLASS.get(st.get('level'), '')
            cells.append('<td%s>%s</td>' % (cls, esc(c)))
        body += '<tr>%s</tr>' % ''.join(cells)
    return '<table><tr>%s</tr>%s</table>' % (head, body)


def risk_cards(risks):
    out = ''
    for r in risks:
        sev = r.get('severity', 'P2')
        pill_cls, pill_txt = SEV_PILL.get(sev, ('pill-yellow', sev))
        level_cls = {'P0': '', 'P1': ' medium', 'P2': ' low'}.get(sev, ' low')
        out += ('<div class="risk-card%s"><span class="pill %s">%s</span> '
                '<strong>%s</strong><br>%s</div>'
                % (level_cls, pill_cls, pill_txt, esc(r.get('title', '')),
                   esc(r.get('detail', ''))))
    return out


def build_verdict(v):
    if not v:
        return ''
    level = v.get('level', 'warn')
    if level not in ('ok', 'warn', 'bad'):
        level = 'warn'
    basis = v.get('basis', '')
    basis_html = '<span class="vbasis">%s</span>' % esc(basis) if basis else ''
    return ('<div class="verdict %s"><span class="vlabel">审单结论：%s</span>%s</div>'
            % (level, esc(v.get('decision', '')), basis_html))


def build_gacc(g):
    if not g:
        return ''
    verdict = g.get('verdict', 'UNKNOWN')
    vcls, vpill, vtxt = GACC_VERDICT.get(verdict, ('pending', 'pill-gray', verdict))
    out = ['<div class="verdict %s"><span class="pill %s">%s</span> '
           '<span class="vlabel" style="margin-left:8px">%s</span></div>'
           % (vcls, vpill, vtxt, esc(g.get('conclusion', '')))]

    inp = g.get('input', {})
    if inp:
        out.append('<table class="kv">')
        out.append('<tr><td>单据上的注册号</td><td>%s</td></tr>' % esc(inp.get('reg_no_raw', '')))
        out.append('<tr><td>归一化后号码</td><td>%s</td></tr>' % esc(inp.get('reg_no_normalized', '')))
        if inp.get('producer'):
            out.append('<tr><td>单据生产企业</td><td>%s</td></tr>' % esc(inp['producer']))
        if inp.get('product'):
            out.append('<tr><td>本次商品</td><td>%s</td></tr>' % esc(inp['product']))
        if inp.get('ship_date'):
            out.append('<tr><td>装船日</td><td>%s</td></tr>' % esc(inp['ship_date']))
        out.append('</table>')

    checks = g.get('checks', {})
    if checks:
        out.append('<table><tr><th>核验维度</th><th>判定</th><th>说明</th></tr>')
        for key in ('existence', 'reg_state', 'name_match', 'product_scope',
                    'validity_window', 'country_match'):
            c = checks.get(key)
            if not c:
                continue
            lvl = c.get('level', 'pending')
            label = {'ok': '通过', 'warn': '待人工确认', 'bad': '不符', 'pending': '未核验'}.get(lvl, lvl)
            out.append('<tr><td>%s</td><td class="%s">%s</td><td>%s</td></tr>'
                       % (esc(CHECK_LABEL.get(key, key)), STATUS_CLASS.get(lvl, ''),
                          label, esc(c.get('detail', ''))))
        out.append('</table>')

    rec = g.get('official_record')
    if rec:
        out.append('<table class="kv"><tr><th>官方登记字段</th><th>海关总署系统登记值</th></tr>')
        for k, label in (('chinaRegNo', '在华注册号'), ('corpNameEn', '境外生产企业（英）'),
                         ('corpAddrNameEn', '企业地址（英）'),
                         ('countryNameCn', '国家（中）'), ('countryNameEn', '国家（英）'),
                         ('provinceNameEn', '省/州（英）'), ('corpTypeNameCn', '企业类型'),
                         ('prodTypeNameCn', '产品大类'), ('prodCategoryNameCn', '产品类别'),
                         ('prodNameCn', '产品范围（中）'), ('prodNameEn', '产品范围（英）'),
                         ('overseasOfficialRegNo', '境外官方注册号'),
                         ('validFrom', '有效期自'), ('validTo', '有效期至'),
                         ('regState', '注册状态')):
            val = rec.get(k)
            if val in (None, ''):
                continue
            out.append('<tr><td>%s</td><td>%s</td></tr>'
                       % (esc(label), esc(str(val)).replace('\n', '<br>')))
        out.append('</table>')

    fb = g.get('fallback')
    if fb and fb.get('candidates'):
        out.append('<p style="font-size:14px;margin-bottom:4px">兜底查询候选（供人工比对，不代表已确认）：</p>')
        out.append('<table><tr><th>候选注册号</th><th>企业名称</th><th>状态</th><th>名称相似度</th></tr>')
        for c in fb['candidates'][:10]:
            st = '有效' if str(c.get('regState')) == '1' else 'regState=%s' % c.get('regState')
            cls = 'ok' if str(c.get('regState')) == '1' else 'bad'
            sim = c.get('similarity')
            out.append('<tr><td>%s</td><td>%s</td><td class="%s">%s</td><td>%s</td></tr>'
                       % (esc(c.get('chinaRegNo', '')), esc(c.get('corpNameEn', '')),
                          cls, st, '' if sim is None else '%.2f' % sim))
        out.append('</table>')

    if g.get('scope_note'):
        out.append('<p class="empty">%s</p>' % esc(g['scope_note']))
    return ''.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('spec')
    ap.add_argument('output')
    ap.add_argument('--gacc-json', default='', help='verify_gacc.py 的输出 JSON')
    ap.add_argument('--downloads-dir', default='', help='生成后复制一份到该目录')
    args = ap.parse_args()

    spec_path = Path(args.spec)
    out_path = Path(args.output)
    if not spec_path.is_file():
        print(json.dumps({'success': False, 'error': 'spec 文件不存在: %s' % spec_path},
                         ensure_ascii=False))
        sys.exit(1)

    with open(spec_path, 'r', encoding='utf-8') as f:
        try:
            spec = json.load(f)
        except Exception as e:
            print(json.dumps({'success': False, 'error': 'spec 不是合法 JSON: %r' % e},
                             ensure_ascii=False))
            sys.exit(1)

    gacc = None
    if args.gacc_json:
        gp = Path(args.gacc_json)
        if not gp.is_file():
            print(json.dumps({'success': False, 'error': 'gacc json 不存在: %s' % gp},
                             ensure_ascii=False))
            sys.exit(1)
        with open(gp, 'r', encoding='utf-8') as f:
            gacc = json.load(f)

    errs = validate(spec)
    if errs:
        print(json.dumps({'success': False, 'error': 'spec 校验未通过，未生成报告',
                          'details': errs}, ensure_ascii=False, indent=2))
        sys.exit(1)

    meta = spec.get('meta', {})
    meta_html = ''.join('<div><b>%s：</b>%s</div>' % (esc(k), esc(v)) for k, v in meta.items())

    html = ['<!DOCTYPE html>', '<html lang="zh-CN">', '<head>', '<meta charset="UTF-8">',
            '<title>%s</title>' % esc(spec.get('title', '单据审查报告')),
            '<style>%s</style>' % CSS, '</head>', '<body>']
    html.append('<h1>%s</h1>' % esc(spec.get('title', '单据审查报告')))
    if meta_html:
        html.append('<div class="meta">%s</div>' % meta_html)

    if spec.get('verdict'):
        html.append(build_verdict(spec['verdict']))

    sec = 0
    if spec.get('risks'):
        sec += 1
        html.append('<h2>%d、风险摘要（按严重程度）</h2>' % sec)
        html.append(risk_cards(spec['risks']))

    if spec.get('contract_vs_draft'):
        sec += 1
        html.append('<h2>%d、%s</h2>' % (sec, esc(spec.get('cvd_title', '合同 vs 草稿件 字段对照'))))
        html.append(build_table(spec['contract_vs_draft']))
        html.append('<div class="legend">'
                    '<span><span class="pill pill-green">一致</span> 字段匹配</span>'
                    '<span><span class="pill pill-yellow">待核</span> 需进一步确认</span>'
                    '<span><span class="pill pill-orange">中度</span> 风险需关注</span>'
                    '<span><span class="pill pill-red">重大</span> 需立即处理</span>'
                    '<span><span class="pill pill-gray">未核验</span> 条件不足跳过</span></div>')

    if spec.get('bilingual'):
        sec += 1
        html.append('<h2>%d、%s</h2>' % (sec, esc(spec.get('bil_title', '中英文标签核对'))))
        html.append(build_table(spec['bilingual']))

    if gacc:
        sec += 1
        html.append('<h2>%d、在华注册号（GACC）真实性核验</h2>' % sec)
        html.append(build_gacc(gacc))

    if spec.get('cross_contract'):
        sec += 1
        html.append('<h2>%d、%s</h2>' % (sec, esc(spec.get('cc_title', '横向对比（抓串单 / 抄错）'))))
        html.append(build_table(spec['cross_contract']))

    if spec.get('conclusion'):
        sec += 1
        html.append('<h2>%d、审查说明</h2>' % sec)
        html.append('<p>%s</p>' % esc(spec['conclusion']))

    if spec.get('suggestions'):
        sec += 1
        html.append('<h2>%d、建议（按优先级）</h2>' % sec)
        html.append('<ol>%s</ol>' % ''.join('<li>%s</li>' % esc(s) for s in spec['suggestions']))

    if spec.get('references'):
        sec += 1
        html.append('<h2>%d、附：审查依据与资料清单</h2>' % sec)
        html.append('<ul>%s</ul>' % ''.join('<li>%s</li>' % esc(s) for s in spec['references']))

    html.append('<div class="footer">本报告由 WorkBuddy 基于视觉识读生成，'
                'P0/P1 项及标注"待人工确认"的差异项须由业务负责人逐项复核并与对方书面确认。'
                '存档：%s</div>' % esc(out_path))
    html.append('</body></html>')

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8-sig') as f:
        f.write('\n'.join(html))

    result = {'success': True, 'output': str(out_path), 'sections': sec}
    if args.downloads_dir:
        d = Path(args.downloads_dir).expanduser()
        if not d.is_dir():
            result['copy_error'] = '目标目录不存在，已跳过复制：%s' % d
        else:
            target = d / out_path.name
            try:
                if target.resolve() == out_path.resolve():
                    result['copy_error'] = '目标与源文件同路径，已跳过复制'
                else:
                    shutil.copy2(str(out_path), str(target))
                    result['copied_to'] = str(target)
            except Exception as e:
                result['copy_error'] = '复制失败：%r' % e
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

"""
JSON 规格示例（全部字段均为可选，但提供时须符合结构，否则校验不通过）：

{
  "title": "XXX 单据审查报告",
  "meta": {"审核对象": "...", "参照基准": "...", "审查日期": "YYYY-MM-DD"},
  "verdict": {"decision": "暂不放行", "level": "bad",
              "basis": "存在 P0 项 1 项、P1 项 2 项，须先与对方书面确认。"},
  "risks": [
    {"severity": "P0", "title": "数量超出合同容差",
     "detail": "合同 100MT ±5% → 允许 95-105MT；实际 92MT，低于下限 3MT。"}
  ],
  "cvd_title": "合同 vs 草稿件 字段对照",
  "contract_vs_draft": {
    "columns": ["字段", "合同值", "草稿件值", "状态", "说明"],
    "rows": [
      {"cells": ["合同号", "SC-001", "SC-001", "一致", "各单据一致"],
       "status": {"index": 3, "level": "ok"}},
      {"cells": ["数量", "100MT ±5%", "92MT", "超标", "低于下限 3MT"],
       "status": {"index": 3, "level": "bad"}}
    ]
  },
  "bil_title": "中英文标签核对",
  "bilingual": {
    "columns": ["字段", "单据英文", "对应中文", "状态", "说明"],
    "rows": [
      {"cells": ["品名", "WHEAT", "小麦", "一致", "与 HS 中文品名相符"],
       "status": {"index": 3, "level": "ok"}}
    ]
  },
  "cross_contract": {
    "columns": ["字段", "本单草稿件", "参考合同", "串单风险", "结论"],
    "rows": [
      {"cells": ["提单号", "ABCD1234567", "EFGH7654321", "无", "未抄错"],
       "status": {"index": 3, "level": "ok"}}
    ]
  },
  "conclusion": "未发现串单。",
  "suggestions": ["P0：与卖方确认短装补货或书面同意按实结算。"],
  "references": ["已读单据：合同 3 页、发票 1 页、提单 2 页、COO 1 页"]
}
"""
