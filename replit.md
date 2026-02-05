# MCA Underwriting Command Center

## Overview
Web-based bank statement analysis system for MCA (Merchant Cash Advance) underwriting. This project provides a complete pipeline for processing bank statement PDFs, extracting financial data, calculating risk metrics, matching with lender criteria, and generating comprehensive reports.

## Current State
**Status**: Fully operational - all core modules are implemented with complete processing logic.

**Last Updated**: February 5, 2026

## Project Structure

```
/
├── app.py                     # Flask web application with full pipeline integration
├── main.py                    # CLI execution script (alternative)
├── requirements.txt           # Python dependencies
├── templates/                 # HTML templates
│   ├── base.html              # Base layout with sidebar
│   ├── index.html             # Dashboard overview
│   ├── upload.html            # File upload page
│   ├── process.html           # Processing page
│   └── results.html           # Results & reports page
├── static/
│   └── style.css              # Dashboard styling
├── core_logic/                # Core processing modules (FULLY IMPLEMENTED)
│   ├── __init__.py
│   ├── ocr_engine.py          # PDF text extraction & bank format detection
│   ├── scrubber.py            # Transaction cleaning & revenue calculation
│   ├── risk_engine.py         # NSF, negative days, MCA detection, risk scoring
│   ├── calculator.py          # DTI, holdback, max funding calculations
│   ├── lender_matcher.py      # Lender criteria matching (5 default lenders)
│   └── reporter.py            # Excel/JSON report generation (5-tab format)
├── input_pdfs/                # Uploaded bank statement PDFs
├── input_config/              # Lender templates and rules
├── processed_data/            # Processing results (JSON)
└── output_reports/            # Generated Excel and JSON reports
```

## Web Interface
- **Dashboard**: Overview of uploaded files, generated reports, pipeline status showing all steps as READY
- **Upload**: Drag-and-drop PDF upload with file management
- **Process**: Select files and run through the complete underwriting pipeline
- **Results**: View processing history and download generated Excel/JSON reports

## Pipeline Flow (All Implemented)
1. **OCR Engine** (`ocr_engine.py`): 
   - Extract text from PDF bank statements using pdfplumber
   - Auto-detect bank format (Chase, BofA, Wells Fargo, TD, PNC, US Bank, Capital One, etc.)
   - Parse transactions with date/amount recognition
   
2. **Scrubber** (`scrubber.py`): 
   - Identify internal transfers (Zelle, Venmo, PayPal, wire transfers)
   - Categorize transactions (payroll, rent, utilities, etc.)
   - Calculate net revenue and monthly breakdowns
   - Analyze deposit concentration
   
3. **Risk Engine** (`risk_engine.py`): 
   - Count NSF/overdraft occurrences and fees
   - Track negative balance days and percentages
   - Detect gambling activity (DraftKings, FanDuel, etc.)
   - Identify existing MCA positions (Kabbage, OnDeck, Credibly, etc.)
   - Detect stacking (multiple MCA lenders)
   - Calculate overall risk score (0-100) and tier (A, B, C, D, Decline)
   
4. **Calculator** (`calculator.py`):
   - Calculate DTI (Debt-to-Income) ratio
   - Determine max holdback percentages by risk tier
   - Calculate max funding amounts
   - Generate factor rate ranges
   - Position sizing recommendations
   
5. **Lender Matcher** (`lender_matcher.py`): 
   - Match applicant profile against 5 default lenders
   - Score matches with disqualification tracking
   - Rank by eligibility and terms
   
6. **Reporter** (`reporter.py`): 
   - Generate 5-tab Master Excel report:
     - Summary (account info, revenue, risk assessment)
     - Transactions (full detail with filtering)
     - Monthly Analysis (with charts)
     - Risk Analysis (NSFs, negative days, MCA positions)
     - Lender Matches (eligibility and scores)
   - Also generates JSON output for programmatic access

## Default Lenders
1. Premier Capital - Standard underwriting, max $250K
2. Velocity Funding - Higher risk tolerance, max $150K
3. Summit Business Capital - Premium terms, lower risk only, max $500K
4. Quick Bridge Capital - Fast funding, higher rates, max $75K
5. Titan Merchant Services - Balanced terms, max $350K

## Risk Tiers
- **A**: Score 0-20, best rates, longest terms
- **B**: Score 21-35, good rates
- **C**: Score 36-50, standard rates
- **D**: Score 51-70, higher rates, shorter terms
- **Decline**: Score 71+, not recommended

## Dependencies
- Flask: Web framework
- pandas: Data manipulation
- xlsxwriter: Excel report generation
- pdfplumber: PDF text extraction
- openpyxl: Excel file handling

## How to Run
The web server runs automatically on port 5000.

## Recent Changes
- February 5, 2026: Implemented all core processing modules with full logic
  - Complete OCR extraction with multi-bank support
  - Transaction scrubbing with transfer detection
  - Risk analysis with NSF, negative days, MCA detection
  - Lender matching against 5 default profiles
  - Multi-tab Excel report generation
