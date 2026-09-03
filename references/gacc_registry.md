# 在华注册号（GACC 境外生产企业注册编号）核验细则

配合 `scripts/verify_gacc.py` 使用。该文件记录实测得到的接口事实与判定规则，
脚本行为以本文件为准。

## 一、适用范围

| 编号类型 | 是否覆盖 | 说明 |
|---|---|---|
| C 或 Q 开头的境外生产企业在华注册编号 | 覆盖 | 走海关总署境外生产企业注册系统公开查询接口 |
| YA 开头 18 位的进口食品境外出口商备案号 | 不覆盖 | 属另一套备案系统，不得用本脚本结果对其下结论 |

## 二、号码格式

通常为大写字母与数字连续组成，无空格，长度约 17 位。形如 `Q` + 国家码 + 日期段 + 序列号。

**识读警告**：高 DPI 渲染后仍易把字符间隙误读为空格，或把 `0` 与 `O`、`1` 与 `I` 混淆。
号码一律先去除空白再转大写后送检，格式异常不得作为判定依据，必须以系统返回为准。

## 三、核验的六个维度

| 维度 | 判定 | 依据字段 |
|---|---|---|
| 号码存在性 | total ≥ 1 为 ok，total = 0 为 bad | data.total |
| 注册状态 | regState 为 "1" 为 ok，其余值为 bad | rows[0].regState |
| 企业名称一致性 | 与单据 Producer 名称比对，见第五节 | rows[0].corpNameEn |
| 产品范围覆盖 | 登记产品清单包含本次商品为 ok | prodNameCn / prodNameEn |
| 有效期覆盖装船日 | validFrom ≤ 装船日 ≤ validTo 为 ok | validFrom / validTo |
| 原产国一致性 | 与单据原产国指向同一国家为 ok | countryNameEn / countryNameCn |

## 四、为什么不能只验号码有效性

实测案例：号码 `QXXXX...XXXX`（示意，非真实号码）在 GACC 系统中真实存在且状态有效，但登记企业为 EXAMPLE ENTERPRISE PTY LTD，
与单据上的 Producer 完全不同。若只做"号码是否存在 + 状态是否有效"两步核验，该号会被判定为通过，
而实际情况是把 A 企业的注册号抄成了 B 企业的。

因此**企业名称一致性是必做维度，不可省略**。六个维度中任一为 bad，整体即判 FAIL。

## 五、名称相似度阈值

脚本对单据 Producer 名称与官方登记名称做归一化后比对（转小写、去除 PTY/LTD/CO 等公司后缀与标点、压缩空白），
再用序列相似度打分：

| 相似度 | 判定 | 含义 |
|---|---|---|
| ≥ 0.85 | ok | 视为同一主体 |
| 0.60 ~ 0.85 | warn | 可能为母子公司、更名或简称，须人工确认 |
| < 0.60 | bad | 号码与企业名称错配，属重大合规风险 |

该阈值为本技能设定的启发式规则，非官方标准，仅用于缩小人工复核范围。warn 与 bad 均须人工确认后才可放行。

## 六、查不到号码时的兜底

按以下顺序尝试，任一命中即列出候选供人工比对。候选不等于确认。

1. 注册号前缀查（去掉末尾 1 位，再 2 位），用于兜住抄错位数。
2. 企业名称子串查。先取前两个实词，零结果再退到首个实词，避免用 food 这类过宽的词召回大量无关企业。

兜底仍无结果时，判 NOT_FOUND，建议核对号码抄写并改用企业全称在 GACC 官网人工检索。

## 七、接口事实（2026-09-03 实测）

请求：`POST https://scintl.chinaport.gov.cn/aprwebserver/publicity/list`

请求头：`rdtime: 123456`、`Content-Type: application/json`

请求体示例：`{"pageSize": 10, "pageNum": 1, "chinaRegNo": "<编号>"}`

可用的查询参数：`chinaRegNo`（支持精确与前缀）、`corpNameEn`（子串匹配）、`countryCode`、`prodCategoryCode`、`pageSize`、`pageNum`。

实测无效的参数：`corpNameMo`，一律返回 0 条，不要使用。

返回结构：`code` / `message` / `data.rows[]` / `data.total`。`code` 为 200 表示查询成功，
与业务上的"核验通过"无关。

rows 内主要字段：`chinaRegNo`、`corpNameEn`、`corpAddrNameEn`、`countryNameEn`、
`countryNameCn`、`provinceNameEn`、`corpTypeNameCn`、`prodTypeNameCn`、
`prodCategoryNameCn`、`prodNameCn`、`prodNameEn`、`overseasOfficialRegNo`、
`validFrom`、`validTo`、`regState`。

`prodNameCn` 与 `prodNameEn` 为换行分隔的多值文本，比对时须按行拆分后逐项包含匹配。

`regState` 实测见过 "1"（有效）与 "2"。除 "1" 以外的值一律视为非有效，须在报告中如实展示官方值并人工确认，
不得自行推断其具体含义。

`validFrom` 与 `validTo` 格式为 `YYYY-MM-DD HH:MM:SS`，比对时取日期部分即可。

## 八、接口不可用时的处置

网络异常、HTTP 非 200、或返回的 code 非 200 时，脚本判定为 UNKNOWN 而非 FAIL。
此时不得得出"号码无效"的结论，报告中须如实标注核验未完成，并建议稍后重试或改用官网人工查询。
