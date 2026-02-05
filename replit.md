# MCA Underwriting Command Center

## Overview
Automated bank statement analysis system for MCA (Merchant Cash Advance) underwriting. This project provides a complete pipeline for processing bank statement PDFs, extracting financial data, calculating risk metrics, matching with lender criteria, and generating comprehensive reports.

## Current State
**Status**: Empty shell with stub functions - all core modules have `pass` implementations with detailed TODO comments marking where AI logic will be added.

## Project Structure

```
/
├── main.py                    # Main execution script
├── requirements.txt           # Python dependencies
├── core_logic/                # Core processing modules
│   ├── __init__.py
│   ├── ocr_engine.py          # PDF text extraction & bank format detection
│   ├── scrubber.py            # Transaction cleaning & revenue calculation
│   ├── risk_engine.py         # NSF, negative days, DTI, cash flagging
│   ├── lender_matcher.py      # Lender criteria matching
│   └── reporter.py            # Excel/JSON report generation
├── input_pdfs/                # Drop bank statement PDFs here
├── input_config/              # Lender templates and rules
├── processed_data/            # OCR raw text output
└── output_reports/            # Generated reports
```

## Pipeline Flow
1. **OCR Engine**: Extract text from PDF bank statements, detect bank format, parse transactions
2. **Scrubber**: Identify internal transfers, categorize transactions, calculate net revenue
3. **Risk Engine**: Count NSFs, negative days, calculate DTI, flag cash/ATM activity
4. **Lender Matcher**: Load lender profiles, filter eligible lenders, rank matches
5. **Reporter**: Generate Master Excel report with all analysis

## Dependencies
- pandas: Data manipulation
- xlsxwriter: Excel report generation
- pdfplumber: PDF text extraction
- openpyxl: Excel file handling
- regex: Pattern matching

## How to Run
```bash
python main.py
```

## Next Steps (TODO)
- Implement OCR extraction logic in ocr_engine.py
- Build transaction parsing for major banks
- Implement transfer identification in scrubber.py
- Build risk calculation formulas in risk_engine.py
- Create lender matching logic in lender_matcher.py
- Build Excel report templates in reporter.py
