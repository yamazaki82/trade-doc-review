# trade-doc-review 进出口贸易单据审查

**发货前把合同和草稿件交给 AI，它自动逐字段对账、核中英文标签、联网验真在华注册号，出一份彩色分级的审查报告。**

---

## 一、它能帮你解决什么问题

做进口业务的人，审单这活儿有四个绕不开的痛点：

**第一，单据读不出来。** 合同、发票、装箱单、提单、COO、植检证、中文标签，绝大多数是扫描件或图片型 PDF，没有文本层。直接读取会报错，全文检索也搜不到任何字。

**第二，人工对账容易漏。** 一份合同的草稿件少则五六份、多则十几份，字段几十项，靠眼睛比容易漏，尤其是数量容差、金额大写、唛头这类细节。

**第三，在华注册号真假难辨。** 这是本技能的重点能力，见下一节。

**第四，抄错串单防不胜防。** 一批货和上一批的草稿件混用同一个模板，合同号、船名航次、数量、注册号抄错，等到港才发现，代价已经产生。

本技能的做法：把每页渲染成 300 DPI 高清 PNG，多模态模型逐页识读字段，再以合同为基准逐字段对账，最后生成 HTML 审查报告。注册号、唛头、金额大写这类小字读不清时，可单独对该页做 480 DPI 重渲染，不必整份重来。

---

## 二、为什么在华注册号必须单独核一遍

### 这个号码是什么

进口食品、农产品以及部分饲料原料的境外生产企业，需要在中国海关总署完成注册，取得**在华注册编号**（C 或 Q 开头的一串号码）。这个号码会印在 **COO 原产地证书**和**中文标签**上，是货物入境时海关核对的关键信息之一。

### 不核或者核错，会发生什么

下面这些情况在口岸环节都可能被拦下，后果由收货方承担：

| 问题情形 | 口岸后果 | 代价 |
|---|---|---|
| 号码在海关总署系统查不到（未注册 / 已注销 / 过期） | 无法清关 | 退运或销毁，损失货值加来回运费 |
| 号码真实有效，但**属于另一家企业** | 单证不符，同样无法通关 | 责任在己方，还可能影响后续通关信用 |
| 注册产品范围不含本批货物 | 海关认定该号不适用于本批 | 重新出证或退运，延误交货 |
| 有效期未覆盖装船日 | 装船时该号已失效 | 同上 |
| 中文标签上的注册号、生产企业、原产国与 COO 不一致 | 标签整改 | 整改费用加上架延误 |

这里最容易被忽略的是第二种：**号码本身是真的，但抄成了别家企业的号**。只查"这个号码存不存在"是查不出来的，必须比对企业名称。本技能把企业名称一致性设为**必做维度**，就是专门抓这一类。

### 本技能怎么核（六维度）

对 COO 或中文标签上的 CHINESE REGISTRATION NUMBER，联网查询海关总署公开系统，逐项核对：

1. **号码存在性** —— 系统里能不能查到
2. **注册状态** —— 是否有效（含注销、过期判定）
3. **企业名称一致性（必做）** —— 系统登记的企业名与单据上的生产商是否对得上，专抓串号抄错
4. **产品范围** —— 登记的品类是否包含本批货物
5. **有效期覆盖装船日** —— 有效期区间是否涵盖实际装船日期
6. **原产国一致性** —— 登记国别与单据原产国是否一致

两条硬规矩：

- 查不到号码时自动做兜底检索（换企业名称模糊查），不会一查不到就直接判无效
- 接口不通时一律判**未完成核验**，绝不据此得出"号码无效"的结论

需要说明的是，相似度阈值属于启发式规则，不是官方标准，核验结论仅供业务判断参考，最终以海关总署系统返回为准。

---

## 三、它能做什么（功能清单）

| 功能 | 说明 |
|---|---|
| 逐字段对账 | 25+ 字段逐项比对，五级色标（一致 / 待核 / 重大 / 注释 / 未核验）；默认 ±5% 数量容差，定金逾期、非正本提单自动预警 |
| 中英文标签核对 | 单据内 10 个中英对照点 + 中文标签 10 项合规要素交叉核对，附常见错配陷阱清单 |
| **在华注册号六维度核验** | 联网查海关总署公开系统，见上一节 |
| 横向串单核查 | 与另一份已签合同比对 20+ 字段，专抓抄错串单 |
| 彩色 HTML 审查报告 | P0 / P1 / P2 风险卡 + 色标字段表 + 放行建议，双击浏览器即开 |
| 缺件不中断 | 植检证未出、提单还是草本等 6 种缺件场景都有降级处理，先出可审部分 |

---

## 四、怎么用

### 第一步：安装

把 `trade-doc-review` 整个文件夹复制到技能目录：

- 用户级（个人长期使用）：`~/.workbuddy/skills/`
- 项目级（团队共用）：`{项目目录}/.workbuddy/skills/`

新开一个会话即可自动加载。

### 第二步：准备环境

需要 Python 3，以及 pymupdf、requests 两个库。首次使用先跑一次环境自检，缺什么会自动装：

```bash
python scripts/bootstrap.py
```

脚本会输出解释器路径、两个库的安装状态和探测到的下载目录。

### 第三步：准备单据

- 基准：**合同 PDF**（双方签署版）
- 草稿件：发票、装箱单、重量质量证、提单、COO、植检证、中文标签，有几份给几份
- 可选：另一份已签合同 PDF（用于串单核查）

### 第四步：对 AI 说一句话

按场景直接复制下面这些话：

| 场景 | 说法 |
|---|---|
| 常规审单 | 帮我审单，合同和草稿件都在这个文件夹里，按合同逐字段对一遍，出审查报告。 |
| 只验注册号 | 核一下这张 COO 上的在华注册号是不是真实有效，企业名称也要比对。 |
| 中英文标签 | 核对一下这票货的中英文标签和单据是否一致，重点是注册号、生产企业和原产国。 |
| 串单排查 | 把这一票的草稿件和上一份已签合同横向比对，看有没有串单抄错。 |
| 缺件降级审 | 植检证还没出、提单还是 PROFORMA，能审的先审，把出证后要补核的列出来。 |
| 图片看不清 | COO 上的注册号太小看不清，提高精度重渲染那一页再读一遍。 |

点名启动（最稳妥，不会漏触发）：

```
用 trade-doc-review 技能审查这票单据：基准是合同《XX》，草稿件有发票、装箱单、重量质量证、提单和
COO，装船日 2026-XX-XX，重点做在华注册号六维度核验，最后出 HTML 审查报告。
```

### 第五步：看报告

报告生成在指定目录并同步到下载目录，双击用浏览器打开就是彩色分级表。上半部分是风险卡（P0 最严重、P2 提示级），中间是字段对照表，最后是放行建议。

**P0 / P1 项以及标注"待人工确认"的差异项，必须业务负责人复核并与对方书面确认后，才能放行。**

---

## 五、适合谁用

- 进口商、外贸公司的单证与跟单人员
- 粮油、杂粮、食品原料、饲料添加剂的采购与品控
- 需要频繁核对境外生产企业在华注册资质的进口业务

用到在华注册号的品类尤其适合：进口农产品、食品原料、饲料添加剂等需要境外生产企业注册的货物。

---

## 六、目录结构

```
trade-doc-review/
├── SKILL.md                        # 技能定义与执行流程（核心）
├── references/
│   ├── field_checklist.md          # 字段清单、容差与风险判定、输出规范、缺件处理
│   ├── bilingual_labels.md         # 中英文核对点、中文标签合规要素、常见错配陷阱
│   └── gacc_registry.md            # 在华注册号格式、六维度判定、相似度阈值、兜底策略
├── scripts/
│   ├── bootstrap.py                # 环境检测与依赖自动安装
│   ├── render_pdfs.py              # PDF 渲染为 PNG，支持 --dpi / --pages / --suffix
│   ├── verify_gacc.py              # 在华注册号六维度核验，输出 JSON
│   └── build_report.py             # HTML 报告生成，含 spec 校验与放行建议
└── docs/
    └── 在华注册号核验要点.md          # 面向进口商的注册号核验科普与常见问题
```

---

## 七、注意事项

- 数量容差、相似度阈值等属于启发式规则，不是官方标准，合同另有约定的以合同为准。
- 所有"待人工确认"项须业务负责人复核并与对方书面确认后放行。
- 在华注册号是否真实有效，一律以中国海关总署系统返回为准，不得以号码格式肉眼判定。
- 脚本目前覆盖 C 或 Q 开头的境外生产企业在华注册编号；YA 开头 18 位的进口食品境外出口商备案号不在核验范围内，会如实提示。

---

## 八、环境与依赖

Python 3 + pymupdf + requests，跨平台，不依赖任何 MCP 服务或外部技能。

## 九、开源协议

MIT，见 [LICENSE](LICENSE)。

---

## English

An AI agent skill for import/export trade document review.

Scanned trade documents (contracts, invoices, packing lists, B/L, Certificates of Origin) are image-based PDFs with no text layer, so both text extraction and AI reading usually fail. This skill solves it: it renders every page to a high-resolution PNG (300+ DPI, per-page re-render up to 480 DPI for fine print), lets a multimodal model extract fields from the images, then audits every field against the sales contract as the baseline.

### Key capabilities

- **Field-by-field audit**: 25+ fields (quantity with ±5% tolerance, deposit terms, Incoterms, ports, packing, marks, B/L status, HS code consistency), each rated ok / warn / bad / note / pending.
- **Bilingual (EN/CN) label check**: 10 in-document cross-check points plus 10 compliance elements on Chinese import labels, with a trap list (synonym drift, MT unit ambiguity, day/month order, figures vs. words in amounts, and more).
- **Six-dimension GACC verification**: queries the China Customs public registry for the CHINESE REGISTRATION NUMBER on the COO, covering existence, registration state, company-name match (mandatory: catches numbers copied from another company), product scope, validity window vs. shipment date, and country consistency. Includes fallback searches and a strict UNKNOWN (never FAIL) rule when the API is unreachable.
- **Cross-contract audit**: compares documents against a second signed contract to catch copy-paste errors across 20+ fields.
- **Color-coded HTML report**: severity-ranked risk cards (P0/P1/P2), status-colored tables, and a release recommendation.

### Requirements

Python 3 with pymupdf and requests (bootstrap.py detects and auto-installs). No MCP servers, no external skill dependencies, cross-platform.

### Disclaimer

Similarity thresholds are heuristics, not official standards. All warn/bad items must be confirmed by a human before any release decision. GACC verification results are only authoritative when returned by the official China Customs system; an unreachable API always means UNKNOWN, never FAIL.
