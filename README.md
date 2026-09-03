# trade-doc-review

AI skill that reviews trade documents: renders scanned PDFs, cross-checks every field against the contract, verifies China GACC registration numbers, and outputs a color-coded HTML audit report.

trade-doc-review is an AI agent skill for import/export trade document review.

Scanned trade documents (contracts, invoices, packing lists, B/L, Certificates of Origin) are image-based PDFs with no text layer, so both text extraction and AI reading usually fail. This skill solves it: it renders every page to a high-resolution PNG (300+ DPI, per-page re-render up to 480 DPI for fine print), lets a multimodal model extract fields from the images, then audits every field against the sales contract as the baseline.

## Key capabilities

- **Field-by-field audit**: 25+ fields (quantity with ±5% tolerance, deposit terms, Incoterms, ports, packing, marks, B/L status, HS code consistency), each rated ok / warn / bad / note / pending.
- **Bilingual (EN/CN) label check**: 10 in-document cross-check points plus 10 compliance elements on Chinese import labels, with a trap list (synonym drift, MT unit ambiguity, day/month order, figures vs. words in amounts, and more).
- **Six-dimension GACC verification**: queries the China Customs public registry for the CHINESE REGISTRATION NUMBER on the COO — existence, registration state, company-name match (mandatory: catches numbers copied from another company), product scope, validity window vs. shipment date, and country consistency. Includes fallback searches and a strict UNKNOWN (never FAIL) rule when the API is unreachable.
- **Cross-contract audit**: compares documents against a second signed contract to catch copy-paste errors ("wrong shipment" mix-ups) across 20+ fields.
- **Color-coded HTML report**: severity-ranked risk cards (P0/P1/P2), status-colored tables, and a release recommendation. UTF-8 BOM, opens by double-click, zero external resources.

## Repository layout

```
trade-doc-review/
├── SKILL.md                        # skill definition and workflow (required)
├── references/
│   ├── field_checklist.md          # field list, tolerances, risk rules, output spec
│   ├── bilingual_labels.md         # EN/CN label check points and trap list
│   └── gacc_registry.md            # GACC registration number rules, 6 dimensions
└── scripts/
    ├── bootstrap.py                # environment check, auto-install pymupdf/requests
    ├── render_pdfs.py              # PDF -> PNG renderer (--dpi --pages --suffix)
    ├── verify_gacc.py              # 6-dimension GACC registry verification
    └── build_report.py             # HTML audit report generator with spec validation
```

## Requirements

Python 3 with pymupdf and requests (bootstrap.py detects and auto-installs). No MCP servers, no external skill dependencies, cross-platform.

## Installation (WorkBuddy)

Copy the `trade-doc-review` folder into your skills directory:

- User-level: `~/.workbuddy/skills/`
- Project-level: `{workspace}/.workbuddy/skills/`

Then start a new session — the skill loads automatically when your request matches its trigger phrases.

## Usage

Trigger the skill by asking your AI agent, for example:

- "Review these trade documents against the contract and give me an audit report."
- "Check whether the CHINESE REGISTRATION NUMBER on this COO is genuine and valid."
- "Cross-check this shipment's drafts against our previous signed contract for copy-paste errors."
- "Verify the Chinese label matches the English documents (product, producer, registration number)."
- "The B/L is still a proforma — audit what we can now and list what to re-check once originals arrive."

English command examples:

- "Review these shipping documents against the sales contract field by field and generate the audit report."
- "Verify the GACC registration number on this Certificate of Origin — six dimensions, including the company name match."
- "Cross-check this shipment against our last signed contract to catch any copy-paste errors."

## Disclaimer

Similarity thresholds are heuristics, not official standards. All warn/bad items must be confirmed by a human before any release decision. GACC verification results are only authoritative when returned by the official China Customs system; an unreachable API always means UNKNOWN, never FAIL.

## License

MIT — see [LICENSE](LICENSE).
