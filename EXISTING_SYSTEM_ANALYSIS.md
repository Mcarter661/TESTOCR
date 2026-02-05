# EXISTING SYSTEM ANALYSIS — MCA Underwriting Command Center

**Analysis Date**: 2026-02-05
**Analyst**: Claude (Phase 1 Codebase Audit)
**Repository**: /home/user/TESTOCR
**Verdict**: SHELL BUILD — All core logic is unimplemented (stub functions with `pass`)

---

## CRITICAL FINDING: File Structure Mismatch

The following files referenced in the task specification **DO NOT EXIST** in this repository:

| Referenced Path | Status |
|---|---|
| `mca-command-center/backend/services/ai_analyzer.py` | DOES NOT EXIST |
| `mca-command-center/backend/models/database.py` | DOES NOT EXIST |
| `mca-command-center/main.py` (as described) | EXISTS at `./main.py` but contains NO AI logic, NO Claude prompt, NO database models |
| `mca-command-center/frontend/src/App.jsx` | DOES NOT EXIST — No React frontend exists |

There is no `mca-command-center/` subdirectory. There is no React frontend. There is no database.
There is no Claude AI integration. There are no lender keyword lists. There is no scoring algorithm.

**The actual codebase is a Flask + Jinja2 shell build at the repository root with 100% stub functions.**

---

## Section 1: What The System Already Does (Scaffold Only)

### 1.1 Actual Repository Structure

```
/home/user/TESTOCR/
├── app.py                          # Flask web app (261 lines) — FUNCTIONAL
├── main.py                         # CLI pipeline runner (180 lines) — FUNCTIONAL (prints steps, calls stubs)
├── requirements.txt                # 6 Python dependencies
├── replit.md                       # Project documentation
├── .replit                         # Replit platform config
├── .gitignore                      # Ignores PDFs, reports, processed data
├── generated-icon.png              # App icon
├── core_logic/                     # 5 modules — ALL STUBS (pass)
│   ├── __init__.py
│   ├── ocr_engine.py               # 5 functions, 0 implemented (94 lines)
│   ├── scrubber.py                 # 7 functions, 0 implemented (124 lines)
│   ├── risk_engine.py              # 8 functions, 0 implemented (147 lines)
│   ├── lender_matcher.py           # 7 functions, 0 implemented (133 lines)
│   └── reporter.py                 # 8 functions, 0 implemented (168 lines)
├── templates/                      # 5 HTML templates — FUNCTIONAL
│   ├── base.html                   # Sidebar layout
│   ├── index.html                  # Dashboard with stats + pipeline viz
│   ├── upload.html                 # Drag-and-drop PDF upload
│   ├── process.html                # File selection + pipeline trigger
│   └── results.html                # Processing history + report downloads
├── static/
│   └── style.css                   # Professional dark-sidebar styling (687 lines)
├── input_pdfs/                     # PDF upload directory
├── input_config/                   # Lender template config directory (EMPTY)
├── processed_data/                 # Processing results directory
└── output_reports/                 # Generated report directory
```

### 1.2 What Actually Works

#### Web Application (app.py — 261 lines)
The Flask web interface is the ONE part of the system that is functional:

| Feature | Status | Details |
|---|---|---|
| PDF file upload | WORKING | Multi-file upload, drag-and-drop, 50MB max, PDF-only validation |
| File listing | WORKING | Lists uploaded PDFs with size + timestamp, sorted by date |
| File deletion | WORKING | Deletes individual files with confirmation |
| Processing trigger | WORKING (calls stubs) | Selects files, calls `run_pipeline()`, saves result JSON |
| Results display | WORKING | Shows processing history from saved JSON files |
| Report download | WORKING | Downloads Excel/JSON files with path traversal protection |
| API status | WORKING | `GET /api/status` returns file/report counts |
| Dashboard | WORKING | Stats cards, quick actions, pipeline visualization |

**Endpoints:**

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Dashboard with stats, recent uploads, recent reports |
| `/upload` | GET/POST | Upload page, handles multi-file PDF upload |
| `/process` | GET/POST | File selection page, triggers pipeline on selected files |
| `/results` | GET | Shows processing history + generated reports |
| `/download/<filename>` | GET | Download generated report files |
| `/delete/<filename>` | POST | Delete an uploaded PDF |
| `/api/status` | GET | JSON API: system status + counts |

#### CLI Pipeline (main.py — 180 lines)
A command-line interface that:
- Scans `input_pdfs/` for PDF files
- Runs the 5-step pipeline (calling stub functions that return `None`)
- Prints progress to console
- Saves result JSON to `processed_data/`

### 1.3 What DOES NOT Exist (Referenced Features)

The following features described in the task specification **have not been built**:

| Feature | Status |
|---|---|
| MCA lender keywords (60+ lenders across 4 tiers) | NOT BUILT |
| 11 analysis tasks Claude performs | NOT BUILT — No Claude/AI integration exists |
| Deal scoring algorithm (0-100 with deductions) | NOT BUILT — No scoring logic exists |
| Position reverse-engineering logic | NOT BUILT |
| Flagged transaction workflow | NOT BUILT |
| Net Available Revenue formula | NOT BUILT |
| Recommended Max Funding formula | NOT BUILT |
| Holdback percentage calculation | NOT BUILT |
| Position remaining balance | NOT BUILT |
| Deal model / database | NOT BUILT — No database exists |
| `calculate_positioning_metrics()` method | NOT BUILT |
| React frontend / AnalysisTab component | NOT BUILT — Only Jinja2 templates |
| Any AI/Claude integration | NOT BUILT |

### 1.4 Intended Pipeline (From TODOs)

The stub functions define a clear 5-step pipeline architecture:

**Step 1: OCR Extraction** (`ocr_engine.py`)
- `extract_text_from_pdf(pdf_path)` → raw text string
- `detect_bank_format(text)` → bank identifier ('chase', 'bofa', 'wells_fargo')
- `parse_transactions(text, bank_format)` → list of {date, description, debit, credit, balance}
- `extract_account_info(text, bank_format)` → {account_holder, account_number, statement_period}
- `process_bank_statement(pdf_path)` → orchestrator returning consolidated data

**Step 2: Transaction Scrubbing** (`scrubber.py`)
- `load_transfer_patterns()` → regex patterns for internal transfers
- `identify_internal_transfers(transactions)` → (revenue_txns, transfer_txns)
- `rename_descriptions(transactions, mapping)` → standardized descriptions
- `calculate_daily_balances(transactions)` → DataFrame {date, ending_balance}
- `calculate_net_revenue(transactions)` → {gross_deposits, gross_withdrawals, net_revenue}
- `calculate_monthly_breakdown(transactions)` → DataFrame with monthly summaries
- `scrub_transactions(transactions)` → orchestrator

**Step 3: Risk Analysis** (`risk_engine.py`)
- `count_nsf_occurrences(transactions)` → {nsf_count, nsf_total_fees, nsf_dates}
- `count_negative_balance_days(daily_balances)` → {negative_days_count, negative_dates, max_negative}
- `calculate_average_daily_balance(daily_balances)` → float
- `calculate_dti_ratio(monthly_revenue, existing_debt_payments)` → decimal (e.g., 0.35)
- `detect_existing_mca_payments(transactions)` → list of MCA payment transactions
- `flag_cash_atm_activity(transactions)` → {cash_deposit_total, atm_withdrawal_total, flags}
- `calculate_position_size(monthly_revenue, risk_score)` → {recommended_advance, factor_rate_range, term_range}
- `generate_risk_profile(transactions, daily_balances)` → orchestrator (risk score 1-100, tier A/B/C/D/Decline)

**Step 4: Lender Matching** (`lender_matcher.py`)
- `load_lender_profiles(config_path)` → DataFrame from lender_template.csv
- `parse_lender_criteria(lender_row)` → {min_revenue, max_nsf, etc.}
- `check_lender_match(applicant_profile, lender_criteria)` → {is_match, match_score, disqualifying_factors}
- `filter_eligible_lenders(applicant_profile, all_lenders)` → sorted list of matches
- `rank_lender_matches(matches, preferences)` → ranked by factor rates, terms, speed
- `generate_lender_summary(matches)` → {total_matches, best_match, match_breakdown}
- `find_matching_lenders(applicant_profile)` → orchestrator

**Step 5: Report Generation** (`reporter.py`)
- `create_workbook(output_path)` → XlsxWriter Workbook
- `add_summary_sheet(workbook, summary_data)` → executive summary with key metrics
- `add_transactions_sheet(workbook, transactions)` → all transactions with conditional formatting
- `add_monthly_analysis_sheet(workbook, monthly_data)` → monthly breakdowns + trends
- `add_risk_analysis_sheet(workbook, risk_profile)` → NSF, negative balance, cash flags
- `add_lender_matches_sheet(workbook, matches)` → ranked lender recommendations
- `add_charts(workbook, data)` → revenue trend, monthly comparison, balance trend, risk factor charts
- `generate_json_output(full_data, output_path)` → JSON export
- `generate_master_report(...)` → orchestrator

---

## Section 2: Key Formulas Found

### NONE IMPLEMENTED

There are **zero formulas** in the codebase. Every function body is `pass`. The TODO comments describe WHAT to calculate but provide no formulas.

### Intended Calculations (From TODO Comments)

```
Net Revenue           = gross_deposits - gross_withdrawals (excluding internal transfers)
DTI Ratio             = existing_debt_payments / monthly_revenue
Cash Activity Flag    = triggered if cash deposits > 20% of total deposits
Negative Day %        = negative_balance_days / total_statement_days
Risk Score            = 1-100 scale (algorithm undefined — needs to be designed)
Risk Tier             = A / B / C / D / Decline (thresholds undefined)
Position Size         = function(monthly_revenue, risk_score) — formula undefined
Factor Rate Range     = function(risk_tier) — undefined
```

### Formulas That NEED TO BE DESIGNED From Scratch

These were referenced in the task spec but have zero implementation or even pseudocode:

| Formula | Status |
|---|---|
| Net Available Revenue = Monthly Revenue - Existing MCA Payments - Fixed Expenses | NEEDS DESIGN |
| Recommended Max Funding = Net Available Revenue × Multiplier (by risk tier) | NEEDS DESIGN |
| Deal Quality Score = 100 - Σ(deductions) | NEEDS DESIGN |
| Holdback % = Daily Payment / Daily Revenue | NEEDS DESIGN |
| Position Remaining Balance = Original Amount - Payments Made | NEEDS DESIGN |
| Cash Flow Coverage Ratio = Operating Cash Flow / Debt Service | NEEDS DESIGN |
| Revenue Velocity = (Current Period Revenue - Prior Period Revenue) / Prior Period Revenue | NEEDS DESIGN |
| Concentration Risk = Largest Deposit Source / Total Deposits | NEEDS DESIGN |

---

## Section 3: Gaps To Fill (Everything)

### 3.1 Critical Missing Infrastructure

| Gap | Priority | Description |
|---|---|---|
| **Database** | P0 | No database exists. No models, no ORM, no persistence beyond JSON files |
| **AI/Claude Integration** | P0 | No AI integration whatsoever. No Anthropic SDK, no prompts, no analysis |
| **Authentication** | P1 | No user auth, no API keys, no access control |
| **Background Processing** | P1 | Pipeline runs synchronously in request thread |
| **Error Handling** | P1 | Bare `except: pass` in results loading |

### 3.2 Core Logic To Build From Scratch

Every function in `core_logic/` is a stub. **35 functions need full implementation:**

| Module | Stub Functions | Lines of TODO |
|---|---|---|
| ocr_engine.py | 5 functions | 15 TODOs |
| scrubber.py | 7 functions | 17 TODOs |
| risk_engine.py | 8 functions | 22 TODOs |
| lender_matcher.py | 7 functions | 16 TODOs |
| reporter.py | 8 functions | 18 TODOs |
| **TOTAL** | **35 functions** | **88 TODOs** |

### 3.3 Features Referenced in Task Spec That Need Building

| Feature | Complexity | Description |
|---|---|---|
| MCA Lender Keywords (60+ across 4 tiers) | Medium | Comprehensive keyword list for detecting existing MCA positions in bank statements |
| Claude AI Analysis (11 tasks) | High | Full AI-powered bank statement analysis using Claude API |
| Deal Scoring Algorithm (0-100) | Medium | Weighted scoring with deductions for risk factors |
| Position Reverse-Engineering | High | Determine existing MCA positions, payment amounts, remaining balances from transaction patterns |
| Flagged Transaction Workflow | Medium | Flag suspicious transactions for manual review |
| React Frontend | High | Replace Jinja2 templates with React SPA |
| Deal Model + Database | Medium | SQLAlchemy models, migrations, persistent storage |

### 3.4 Advanced Analytics Features Missing

| Feature | Description |
|---|---|
| **Concentration Risk Analysis** | Measure % of revenue from top 1-3 deposit sources. Flag if >50% from single source |
| **Expense Categorization** | Classify debits: payroll, rent, taxes, utilities, loan payments, supplies, owner draws |
| **Revenue Velocity/Acceleration** | Month-over-month rate of change. Is revenue accelerating or decelerating? |
| **PDF Metadata Fraud Detection** | Check PDF producer/creator for Photoshop, Canva, or other editing tools. Flag modified statements |
| **Cash Flow Coverage Ratio** | Operating cash flow / total debt service obligations. Key underwriting metric |
| **Industry Benchmarking** | Compare applicant metrics to industry averages by SIC/NAICS code |
| **Diversion Account Detection** | Detect if applicant may be diverting revenue to other accounts (sudden drops, new payees) |
| **Statistical Anomaly Detection** | Use z-scores or IQR to identify transactions that are statistical outliers |
| **Seasonality Detection** | Identify seasonal revenue patterns and adjust projections |
| **Bank Statement Completeness** | Verify no pages missing, no gaps in date sequences |
| **Multi-Account Consolidation** | Merge analysis across multiple bank accounts for same applicant |

---

## Section 4: Data Structures

### 4.1 Existing Data Structures (From Function Signatures)

**No actual data flows through the system** since all functions return `None`. But the function signatures and TODOs define the intended structures:

#### OCR Output (process_bank_statement return value — INTENDED)

```json
{
  "account_info": {
    "account_holder": "string",
    "account_number": "string (masked)",
    "statement_period": {
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD"
    }
  },
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "description": "string",
      "debit": 0.00,
      "credit": 0.00,
      "balance": 0.00
    }
  ],
  "bank_format": "chase|bofa|wells_fargo|unknown",
  "raw_text": "string"
}
```

#### Scrubbed Data (scrub_transactions return value — INTENDED)

```json
{
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "description": "string (standardized)",
      "original_description": "string (raw)",
      "debit": 0.00,
      "credit": 0.00,
      "balance": 0.00,
      "category": "revenue|transfer|payroll|rent|utilities|mca_payment|cash|other",
      "is_transfer": false
    }
  ],
  "daily_balances": "DataFrame {date, ending_balance}",
  "monthly_data": "DataFrame {month, deposits, withdrawals, net, growth_rate}",
  "revenue_metrics": {
    "gross_deposits": 0.00,
    "gross_withdrawals": 0.00,
    "net_revenue": 0.00,
    "monthly_average": 0.00
  }
}
```

#### Risk Profile (generate_risk_profile return value — INTENDED)

```json
{
  "risk_score": 75,
  "risk_tier": "B",
  "nsf": {
    "nsf_count": 3,
    "nsf_total_fees": 105.00,
    "nsf_dates": ["2025-01-15", "2025-02-03", "2025-02-28"],
    "exceeds_threshold": false
  },
  "negative_balance": {
    "negative_days_count": 5,
    "negative_dates": [],
    "max_negative": -1250.00,
    "negative_percentage": 5.5
  },
  "average_daily_balance": 12500.00,
  "dti_ratio": 0.35,
  "existing_mca_payments": [
    {
      "description": "ACH DEBIT LENDERNAME",
      "amount": 500.00,
      "frequency": "daily",
      "estimated_monthly": 10000.00
    }
  ],
  "cash_activity": {
    "cash_deposit_total": 5000.00,
    "atm_withdrawal_total": 2000.00,
    "cash_deposit_percentage": 8.5,
    "flags": []
  },
  "position_sizing": {
    "recommended_advance": 50000.00,
    "factor_rate_range": [1.25, 1.45],
    "term_range": [6, 12]
  },
  "flags": ["High NSF count", "Existing MCA detected"]
}
```

#### Lender Matching (find_matching_lenders return value — INTENDED)

```json
{
  "matches": [
    {
      "lender_name": "string",
      "is_match": true,
      "match_score": 85,
      "factor_rate": 1.35,
      "term_months": 9,
      "max_advance": 75000,
      "disqualifying_factors": [],
      "criteria_met": ["min_revenue", "max_nsf", "time_in_business"]
    }
  ],
  "summary": {
    "total_matches": 5,
    "best_match": "LenderName",
    "match_breakdown": {
      "tier_a": 1,
      "tier_b": 2,
      "tier_c": 2,
      "tier_d": 0
    }
  }
}
```

#### Pipeline Result (saved to processed_data/ — ACTUALLY EXISTS)

```json
{
  "filename": "statement.pdf",
  "timestamp": "2026-02-05T10:30:00",
  "steps": [
    {"name": "OCR Extraction", "status": "pending", "message": "TODO: Implement OCR logic"},
    {"name": "Transaction Scrubbing", "status": "pending", "message": "TODO: Implement scrubbing logic"},
    {"name": "Risk Analysis", "status": "pending", "message": "TODO: Implement risk analysis"},
    {"name": "Lender Matching", "status": "pending", "message": "TODO: Implement lender matching"},
    {"name": "Report Generation", "status": "pending", "message": "TODO: Implement report generation"}
  ],
  "report_path": null,
  "status": "pending"
}
```

### 4.2 Data Structures That Need To Be DESIGNED

For the new system described in the task spec, these structures need to be created:

#### Deal Model (referenced but does not exist)

```
Deal:
  - id
  - business_name
  - business_type / industry
  - time_in_business
  - requested_amount
  - status (new, analyzing, reviewed, funded, declined)
  - deal_quality_score (0-100)
  - risk_tier (A/B/C/D/Decline)
  - monthly_revenue
  - net_available_revenue
  - recommended_funding
  - existing_positions[] (detected MCA stacking)
  - flagged_transactions[]
  - analysis_result (full AI analysis JSON)
  - documents[] (uploaded PDFs)
  - created_at / updated_at
```

#### AI Analysis Response (Claude integration — does not exist)

```
Claude should return structured JSON with:
  - bank_info (account holder, bank name, period)
  - monthly_summaries[] (revenue, expenses, net by month)
  - deposit_analysis (total, average, concentration)
  - withdrawal_analysis (total, categories)
  - nsf_analysis (count, dates, fees)
  - negative_balance_analysis (days, max negative)
  - existing_positions[] (detected MCA/loan payments)
  - flagged_transactions[] (suspicious items needing review)
  - cash_activity (deposits, withdrawals, percentage)
  - scoring (deal_quality_score, deductions[], risk_tier)
  - recommendation (max_funding, factor_rate, term, holdback)
```

---

## Section 5: Technology Assessment

### 5.1 Current Stack

| Component | Technology | Version | Status |
|---|---|---|---|
| Backend | Flask | >= 3.0 | Working (web UI only) |
| Templates | Jinja2 | (bundled) | Working |
| PDF Extraction | pdfplumber | >= 0.10 | Imported, not used |
| Data Processing | pandas | >= 2.0 | Imported, not used |
| Excel Reports | xlsxwriter | >= 3.1 | Imported, not used |
| Excel Reading | openpyxl | >= 3.1 | Listed, not used |
| Pattern Matching | regex | >= 2023 | Listed, not used |
| Database | NONE | — | Not designed |
| AI Integration | NONE | — | Not designed |
| Frontend Framework | NONE (Jinja2) | — | No React/SPA |

### 5.2 What Needs To Be Added For Phase 2

| Component | Recommended Technology |
|---|---|
| Database | SQLAlchemy + SQLite/PostgreSQL |
| AI Integration | Anthropic Python SDK (Claude) |
| Background Tasks | Celery or asyncio |
| API Framework | FastAPI or Flask-RESTful |
| Frontend | React (if SPA needed) or enhanced Jinja2 |
| Authentication | Flask-Login or JWT |
| PDF Metadata | PyPDF2 or pikepdf (for fraud detection) |
| Testing | pytest |

---

## Section 6: What Can Be Preserved vs. Rebuilt

### PRESERVE (Solid Foundation)
- `app.py` upload/download/delete flow — clean file management
- `templates/` — professional UI can be enhanced or replaced
- `static/style.css` — professional styling with CSS variables
- Directory structure convention (input_pdfs, processed_data, output_reports)
- `.gitignore` — properly excludes data files

### REBUILD FROM SCRATCH
- All 35 stub functions in `core_logic/`
- Database layer (doesn't exist)
- AI integration (doesn't exist)
- MCA lender keyword lists (doesn't exist)
- Scoring algorithms (doesn't exist)
- Position detection logic (doesn't exist)
- Report generation (doesn't exist)
- API endpoints for deal management (doesn't exist)

---

## Section 7: Summary — Phase 2 Build Scope

The existing system is a **well-structured empty shell**. The Flask web UI works for uploading and managing files, but every piece of underwriting logic is unimplemented.

**Lines of actual working code**: ~500 (app.py + main.py + templates)
**Lines of stub code**: ~666 (core_logic modules — all `pass`)
**Lines of business logic**: 0

For Phase 2, we are not enhancing an existing system — we are **building the entire analysis engine from the ground up** while potentially reusing the file management scaffold.

### Build Priority Order:
1. **Database + Models** — Persistent deal tracking
2. **Claude AI Integration** — Bank statement analysis with structured output
3. **MCA Lender Detection** — 60+ keywords across tiers
4. **Scoring Algorithm** — Deal quality score with deductions
5. **Position Detection** — Reverse-engineer existing MCA obligations
6. **Advanced Analytics** — Concentration risk, velocity, anomaly detection
7. **Report Generation** — Excel + JSON output
8. **Frontend Enhancement** — React SPA or enhanced Jinja2
