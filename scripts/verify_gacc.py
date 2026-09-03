#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在华注册号（GACC 境外生产企业注册编号）真实性核验

对接中国海关总署境外生产企业注册系统公开查询接口，对 COO / 中文标签上的
"CHINESE REGISTRATION NUMBER" 做六个维度的真实性核验，输出 JSON 结果。

适用范围：
  C 或 Q 开头的境外生产企业在华注册编号（格式示意 QZZZ2501010001234，非真实号码），走 scintl 系统。
  不在范围内：YA 开头 18 位的进口食品境外出口商备案号，属另一套系统，本脚本不覆盖，
  请勿用本脚本结果对 YA 号下任何结论。

用法：
  python verify_gacc.py --reg-no QZZZ2501010001234
  python verify_gacc.py --reg-no <号> --producer "PRODUCER NAME" --product "小麦" \
                        --ship-date 2026-08-16 --country Australia --json-out gacc.json

参数：
  --reg-no      在华注册号（必需）
  --producer    COO/标签上的生产企业英文名，用于名称一致性核验
  --product     本次商品名称（中英文均可），用于产品范围核验
  --ship-date   装船日 YYYY-MM-DD，用于有效期覆盖核验
  --country     COO/标签上的原产国英文名，用于国别一致性核验
  --json-out    结果写入指定 JSON 文件（同时始终打印到 stdout）

核验维度：
  1 号码存在性   2 注册状态   3 企业名称一致性
  4 产品范围     5 有效期覆盖装船日   6 原产国一致性

依赖：requests。未安装时先跑 bootstrap.py。
"""
import sys
import json
import argparse
import re
from datetime import datetime

try:
    import requests
except ImportError:
    print(json.dumps({
        'success': False,
        'error': '缺少 requests，请先运行 python bootstrap.py 安装依赖'
    }, ensure_ascii=False))
    sys.exit(1)

URL = 'https://scintl.chinaport.gov.cn/aprwebserver/publicity/list'
HEADERS = {'rdtime': '123456', 'Content-Type': 'application/json'}
TIMEOUT = 30

NAME_NOISE = re.compile(
    r'\b(pty|ltd|limited|co|company|corp|corporation|inc|gmbh|s\.?a\.?|bv|nv|llc|plc)\b',
    re.IGNORECASE)


def query(payload):
    """调用 GACC 接口。网络或协议异常统一转为结构化错误。"""
    try:
        r = requests.post(URL, headers=HEADERS, json=payload, timeout=TIMEOUT)
    except Exception as e:
        return {'ok': False, 'error': '网络请求失败: %r' % e}
    if r.status_code != 200:
        return {'ok': False, 'error': 'HTTP %s' % r.status_code}
    try:
        j = r.json()
    except Exception:
        return {'ok': False, 'error': '返回非 JSON'}
    if j.get('code') != 200:
        return {'ok': False, 'error': '接口返回 code=%s message=%s' % (j.get('code'), j.get('message'))}
    return {'ok': True, 'data': j.get('data') or {}}


def normalize_name(s):
    """企业名称归一化：转小写、去公司后缀与标点、压缩空白。"""
    if not s:
        return ''
    s = s.lower()
    s = NAME_NOISE.sub(' ', s)
    s = re.sub(r'[^a-z0-9\u4e00-\u9fff]+', ' ', s)
    return ' '.join(s.split()).strip()


def similarity(a, b):
    from difflib import SequenceMatcher
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb or na in nb or nb in na:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def split_products(val):
    """产品字段是多行文本（\\n 分隔），拆成列表。"""
    if not val:
        return []
    parts = re.split(r'[\n;；,，]', str(val))
    return [p.strip().lower() for p in parts if p.strip()]


def check_existence(reg_no):
    res = query({'pageSize': 10, 'pageNum': 1, 'chinaRegNo': reg_no})
    if not res['ok']:
        return {'level': 'pending', 'detail': '核验未完成：%s' % res['error'],
                'rows': [], 'raw': None, 'query_error': res['error']}
    data = res['data']
    rows = data.get('rows') or []
    if not rows:
        return {'level': 'bad',
                'detail': 'GACC 系统中查无此号（total=0），注册号可能抄错或已注销。',
                'rows': [], 'raw': data, 'query_error': None}
    return {'level': 'ok', 'detail': '系统中命中 %s 条记录。' % data.get('total'),
            'rows': rows, 'raw': data, 'query_error': None}


def fallback_search(reg_no, producer):
    """精确查不到时的兜底：注册号前缀查 + 企业名称子串查。"""
    out = {'attempts': [], 'candidates': []}
    seen = set()

    if reg_no and len(reg_no) >= 8:
        for cut in (1, 2):
            prefix = reg_no[:-cut]
            if len(prefix) < 6:
                continue
            res = query({'pageSize': 20, 'pageNum': 1, 'chinaRegNo': prefix})
            tag = '注册号前缀 %s（去尾 %d 位）' % (prefix, cut)
            if res['ok']:
                rows = res['data'].get('rows') or []
                out['attempts'].append({'method': tag, 'total': res['data'].get('total')})
                for r in rows:
                    key = r.get('chinaRegNo')
                    if key and key not in seen:
                        seen.add(key)
                        out['candidates'].append({
                            'chinaRegNo': key, 'corpNameEn': r.get('corpNameEn'),
                            'regState': r.get('regState'), 'similarity': None})
            else:
                out['attempts'].append({'method': tag, 'error': res['error']})

    if producer:
        words = normalize_name(producer).split()
        # 先用前两个实词检索（更精准），零结果再退到首个实词，避免 "food" 这类
        # 过宽的词召回一堆无关企业
        trials = []
        if len(words) >= 2:
            trials.append(' '.join(words[:2]))
        if words:
            trials.append(words[0])
        for token in trials:
            if len(token) < 4:
                continue
            res = query({'pageSize': 20, 'pageNum': 1, 'corpNameEn': token})
            tag = '企业名称子串 "%s"' % token
            if not res['ok']:
                out['attempts'].append({'method': tag, 'error': res['error']})
                continue
            rows = res['data'].get('rows') or []
            out['attempts'].append({'method': tag, 'total': res['data'].get('total')})
            for r in rows:
                k = r.get('chinaRegNo')
                if k and k not in seen:
                    seen.add(k)
                    sim = round(similarity(producer, r.get('corpNameEn')), 3)
                    out['candidates'].append({
                        'chinaRegNo': k, 'corpNameEn': r.get('corpNameEn'),
                        'regState': r.get('regState'), 'similarity': sim})
            if rows:
                break

    out['candidates'].sort(key=lambda x: (x.get('similarity') or 0), reverse=True)
    return out


def check_reg_state(row):
    state = str(row.get('regState', '')).strip()
    if state == '1':
        return {'level': 'ok', 'detail': 'regState=1，注册状态为有效。', 'regState': state}
    if not state:
        return {'level': 'pending', 'detail': '接口未返回 regState，无法判定。', 'regState': state}
    return {'level': 'bad',
            'detail': 'regState=%s，非有效状态（官方登记中 1 为有效，其余值须视为无效并人工确认）。' % state,
            'regState': state}


def check_name(row, producer):
    if not producer:
        return {'level': 'pending', 'detail': '未提供单据上的生产企业名称，跳过名称比对。'}
    official = row.get('corpNameEn') or ''
    sim = round(similarity(producer, official), 3)
    if sim >= 0.85:
        return {'level': 'ok', 'similarity': sim,
                'detail': '单据名称与官方登记一致（相似度 %.2f）。' % sim}
    if sim >= 0.60:
        return {'level': 'warn', 'similarity': sim,
                'detail': '单据名称「%s」与官方登记「%s」接近但不等同（相似度 %.2f），'
                          '可能为母子公司/更名/简称，须人工确认。' % (producer, official, sim)}
    return {'level': 'bad', 'similarity': sim,
            'detail': '单据名称「%s」与官方登记「%s」不符（相似度 %.2f）。'
                      '注册号与企业名称错配属重大合规风险，须立即与对方确认。'
                      % (producer, official, sim)}


def check_product(row, product):
    if not product:
        return {'level': 'pending', 'detail': '未提供本次商品名称，跳过产品范围比对。'}
    cn = split_products(row.get('prodNameCn'))
    en = split_products(row.get('prodNameEn'))
    pool = cn + en
    kw = str(product).strip().lower()
    hit = [p for p in pool if kw in p or p in kw]
    if hit:
        return {'level': 'ok',
                'detail': '产品范围含本次商品，命中：%s。' % '、'.join(hit[:5]),
                'matched': hit}
    if not pool:
        return {'level': 'pending', 'detail': '官方登记未列出产品明细，无法比对。'}
    return {'level': 'bad',
            'detail': '登记产品范围【%s】中未见「%s」，该号可能不涵盖本次商品。'
                      % ('、'.join(pool[:8]), product),
            'registered_products': pool[:12]}


def check_validity(row, ship_date):
    if not ship_date:
        return {'level': 'pending', 'detail': '未提供装船日，跳过有效期覆盖比对。'}
    try:
        datetime.strptime(ship_date, '%Y-%m-%d')
    except ValueError:
        return {'level': 'pending', 'detail': '装船日格式应为 YYYY-MM-DD，跳过比对。'}
    vf = str(row.get('validFrom') or '').split(' ')[0]
    vt = str(row.get('validTo') or '').split(' ')[0]
    if not vf or not vt:
        return {'level': 'pending', 'detail': '接口未返回有效期，无法比对。'}
    if ship_date < vf:
        return {'level': 'bad', 'detail': '装船日 %s 早于注册生效日 %s。' % (ship_date, vf),
                'validFrom': vf, 'validTo': vt}
    if ship_date > vt:
        return {'level': 'bad', 'detail': '装船日 %s 晚于注册失效日 %s，注册号已过期。'
                                          % (ship_date, vt), 'validFrom': vf, 'validTo': vt}
    return {'level': 'ok', 'detail': '有效期 %s ~ %s 覆盖装船日 %s。' % (vf, vt, ship_date),
            'validFrom': vf, 'validTo': vt}


def check_country(row, country):
    if not country:
        return {'level': 'pending', 'detail': '未提供单据原产国，跳过国别比对。'}
    official_en = (row.get('countryNameEn') or '').strip().lower()
    official_cn = (row.get('countryNameCn') or '').strip()
    given = str(country).strip().lower()
    if given and (given == official_en or given in official_en or official_en in given
                  or given == official_cn):
        return {'level': 'ok', 'detail': '原产国与官方登记一致（%s）。' % official_en}
    return {'level': 'warn',
            'detail': '单据原产国「%s」与官方登记「%s / %s」不一致，须人工确认。'
                      % (country, row.get('countryNameEn'), row.get('countryNameCn'))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reg-no', required=True, help='在华注册号')
    ap.add_argument('--producer', default='', help='单据上的生产企业英文名')
    ap.add_argument('--product', default='', help='本次商品名称')
    ap.add_argument('--ship-date', default='', help='装船日 YYYY-MM-DD')
    ap.add_argument('--country', default='', help='单据原产国')
    ap.add_argument('--json-out', default='', help='结果写入 JSON 文件')
    args = ap.parse_args()

    reg_no = ''.join(str(args.reg_no).split()).upper()
    result = {
        'success': True,
        'input': {'reg_no_raw': args.reg_no, 'reg_no_normalized': reg_no,
                  'producer': args.producer, 'product': args.product,
                  'ship_date': args.ship_date, 'country': args.country},
        'scope_note': '本脚本仅覆盖 C/Q 开头的境外生产企业在华注册编号，'
                      'YA 开头的进口食品境外出口商备案号不在核验范围内。',
        'checks': {},
    }

    exist = check_existence(reg_no)
    result['checks']['existence'] = {
        'level': exist['level'], 'detail': exist['detail'],
        'total': (exist['raw'] or {}).get('total')}

    if exist['query_error']:
        result['success'] = False
        result['verdict'] = 'UNKNOWN'
        result['conclusion'] = '接口不可用，本次核验未完成，不得据此判定号码无效。'
    elif exist['level'] == 'ok':
        row = exist['rows'][0]
        if len(exist['rows']) > 1:
            result['checks']['existence']['detail'] += '（命中多条，取首条；' \
                                                       '同一企业可能持多个注册号，须核对产品范围）'
        result['official_record'] = {
            'chinaRegNo': row.get('chinaRegNo'),
            'corpNameEn': row.get('corpNameEn'),
            'corpAddrNameEn': row.get('corpAddrNameEn'),
            'countryNameEn': row.get('countryNameEn'),
            'countryNameCn': row.get('countryNameCn'),
            'provinceNameEn': row.get('provinceNameEn'),
            'corpTypeNameCn': row.get('corpTypeNameCn'),
            'prodTypeNameCn': row.get('prodTypeNameCn'),
            'prodCategoryNameCn': row.get('prodCategoryNameCn'),
            'prodNameCn': row.get('prodNameCn'),
            'prodNameEn': row.get('prodNameEn'),
            'overseasOfficialRegNo': row.get('overseasOfficialRegNo'),
            'validFrom': row.get('validFrom'),
            'validTo': row.get('validTo'),
            'regState': row.get('regState'),
        }
        result['checks']['reg_state'] = check_reg_state(row)
        result['checks']['name_match'] = check_name(row, args.producer)
        result['checks']['product_scope'] = check_product(row, args.product)
        result['checks']['validity_window'] = check_validity(row, args.ship_date)
        result['checks']['country_match'] = check_country(row, args.country)

        levels = [v['level'] for k, v in result['checks'].items()]
        if 'bad' in levels:
            result['verdict'] = 'FAIL'
            result['conclusion'] = '该在华注册号存在实质性不符，不得据此放行。'
        elif 'warn' in levels:
            result['verdict'] = 'PASS_WITH_WARNING'
            result['conclusion'] = '号码本身真实有效，但存在需人工确认的差异项。'
        else:
            result['verdict'] = 'PASS'
            result['conclusion'] = '号码真实有效，各核验项与单据一致。'
    else:
        fb = fallback_search(reg_no, args.producer)
        result['fallback'] = fb
        result['verdict'] = 'NOT_FOUND'
        result['conclusion'] = ('系统中查无此号。已尝试兜底查询，'
                                '请核对号码抄写是否正确，或改用企业全称在 GACC 官网人工检索。')

    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            f.write(text)
    sys.exit(0 if result['success'] else 1)


if __name__ == '__main__':
    main()
