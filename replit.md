# MCA Underwriting Command Center

## Overview
Web-based bank statement analysis system for MCA (Merchant Cash Advance) underwriting. This project provides a complete pipeline for processing bank statement PDFs, extracting financial data, calculating risk metrics, detecting and reverse-engineering MCA positions, matching with lender criteria, and generating comprehensive reports with forensics and deal summary tabs.

## Current State
**Status**: Fully operational - all core modules implemented with enhanced pipeline including keyword-based analysis, position detection, fraud detection, and forensics reporting.

**Last Updated**: February 5, 2026

## Project Structure

```
/
├── app.py                     # Flask web application with enhanced pipeline integration
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
├── config/                    # Configuration files
│   ├── keywords.json          # 60+ MCA lender patterns across 4 tiers
│   ├── factor_rates.json      # Factor rate tables
│   ├── funder_rates_complete.json  # Complete funder rate data
│   └── lender_aliases.json    # Lender name aliases
├── core_logic/                # Core processing modules (FULLY IMPLEMENTED)
│   ├── __init__.py
│   ├── ocr_engine.py          # PDF text extraction, bank format detection, fraud detection
│   ├── scrubber.py            # Transaction cleaning, revenue calculation, keyword-based exclusions
│   ├── risk_engine.py         # NSF, negative days, MCA detection, velocity/acceleration, garnishments
│   ├── calculator.py          # DTI, holdback, max funding, deal summary calculations
│   ├── lender_matcher.py      # Lender criteria matching (5 default lenders + CSV support)
│   ├── position_detector.py   # 4-tier keyword-based MCA position detection & reverse engineering
│   └── reporter.py            # Excel/JSON report generation (10-tab format with forensics & deal summary)
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

## Bank-Specific Parsers
The system has dedicated parsers for each supported bank format:

### PNC Bank Parser (`extract_transactions_pnc`)
- Handles PNC's section-based format (Deposits, ACH Additions, Checks, Debit Card, ATM, ACH Deductions, etc.)
- Multi-column check parsing (3 checks per row)
- Section headers determine debit/credit classification
- Statement period date extraction for year assignment
- Detects incoming/outgoing wires, Shift4 deposits, ADP payroll

### Truist Parser (`extract_transactions_truist`)
- Handles Truist's MM/DD format (no year) with section-based layout
- Multi-column check parsing (3 per row)
- "Other withdrawals, debits and service charges" section (debits)
- "Deposits, credits and interest" section (credits)
- Continuation line and page break handling
- Year extraction from statement period header

### Chase Parser (`extract_transactions_chase`)
- Standard Chase transaction parsing with table fallback

### Generic Parser (`extract_transactions_generic`)
- Fallback parser for unknown bank formats
- Table-based and text-based extraction

### Bank Detection Priority
Banks are checked in this order to prevent misidentification:
1. PNC, Truist (checked first - specific patterns)
2. BofA, Wells Fargo, TD, US Bank, Capital One, etc.
3. Chase (checked last - generic "JPMORGAN" pattern)

## Enhanced Pipeline Flow (All Implemented)
1. **OCR Engine** (`ocr_engine.py`): 
   - Extract text from PDF bank statements using pdfplumber
   - Auto-detect bank format (PNC, Truist, Chase, BofA, Wells Fargo, TD, US Bank, Capital One, etc.)
   - Route to bank-specific parser for accurate transaction extraction
   - PDF fraud detection (Photoshop, Canva, GIMP metadata flags)
   - Address extraction from statements
   
2. **Scrubber** (`scrubber.py`): 
   - Identify internal transfers (Zelle, Venmo, PayPal, wire transfers)
   - Categorize transactions (payroll, rent, utilities, etc.)
   - Calculate net revenue and monthly breakdowns
   - Analyze deposit concentration
   - Apex Test (inter-account transfer detection)
   - Keyword-based deposit exclusions when keywords.json is loaded
   
3. **Risk Engine** (`risk_engine.py`): 
   - Count NSF/overdraft occurrences and fees
   - Track negative balance days and percentages
   - Detect gambling activity (DraftKings, FanDuel, etc.)
   - Identify existing MCA positions via ACH IDs and transaction patterns
   - Detect stacking (multiple MCA lenders)
   - Calculate overall risk score (0-100) and tier (A, B, C, D, Decline)
   - Revenue velocity and acceleration tracking
   - Expense categorization (payroll, rent, utilities, supplies)
   - Garnishment, tax lien, and judgment detection with severity levels
   
4. **Position Detector** (`position_detector.py`):
   - 4-tier keyword matching against 60+ MCA lender patterns
   - Reverse engineering of each position (funding amount, factor rate, remaining balance, payoff date)
   - Payment frequency detection (daily, weekly, bi-weekly, monthly)
   - Stacking analysis and total monthly holdback calculation
   
5. **Calculator** (`calculator.py`):
   - Calculate DTI (Debt-to-Income) ratio
   - Determine max holdback percentages by risk tier
   - Calculate max funding amounts
   - Generate factor rate ranges
   - Position sizing recommendations
   - Deal summary with proposed impact analysis
   
6. **Lender Matcher** (`lender_matcher.py`): 
   - Match applicant profile against 5 default lenders
   - Score matches with disqualification tracking
   - Rank by eligibility and terms
   - CSV-based lender template support
   
7. **Reporter** (`reporter.py`): 
   - Generate 10-tab Master Excel report
   - Also generates JSON output for programmatic access

## Frequency Detection (Count-per-Month Method)
Payment frequency is determined by counting payments per month:
- **15+ per month** = Daily
- **4-5 per month** = Weekly
- **2 per month** = Bi-weekly
- **1 per month** = Monthly
This replaced the gap-based method for more accurate classification.

## SpotOn Identification
SpotOn transactions are separated into two categories:
- **SpotOn (MINPMT)**: MCA payments identified by "minpmt" keyword - treated as MCA position
- **SpotOn RTP/FBO**: Revenue deposits and processing fees - NOT treated as MCA

## Enhanced MCA Detection
The system uses ACH identifier patterns to identify specific MCA lenders:
- eFinancialTree (9144978400) - Daily payments ~$297.91
- CAPYBARA (5612081085) - Daily payments ~$288
- Ivy Receivables/Fox (7183166893) - Weekly payments ~$400
- Rauch-Milliken (D002) - Weekly payments ~$750
- DoorDash Capital - Bi-weekly
- SL Recovery - Monthly ~$1,300-$1,680
- SpotOn MINPMT - Monthly ~$3,567
- And 50+ additional lender patterns in config/keywords.json

## Position Detection (4-Tier System)
Positions are classified by match confidence:
- **Tier 1**: Exact ACH ID match (highest confidence)
- **Tier 2**: Known lender name pattern match
- **Tier 3**: MCA-like payment pattern match
- **Tier 4**: Suspicious recurring debit pattern

## Reverse Engineering
For each detected MCA position, the system calculates:
- **Average Payment**: Based on transaction history
- **Payment Frequency**: Daily, weekly, bi-weekly, monthly
- **Monthly Cost**: Extrapolated from payment frequency
- **Estimated Funding**: Original funding amount (using factor rates from config)
- **Estimated Remaining**: Balance owed based on payments made
- **Estimated Payoff Date**: Projected payoff based on payment trajectory

## Red Flags Detection
- Heavy Stacking (5+ positions) - CRITICAL
- Moderate Stacking (3+ positions) - HIGH
- Very Recent Funding (<14 days) - CRITICAL
- Recent Funding (14-30 days) - HIGH
- High Monthly Debt (>$25K) - CRITICAL
- Returned/Reversed Deposits - HIGH
- Stopped MCA Payments - HIGH
- Garnishments/Tax Liens/Judgments - HIGH/CRITICAL
- Revenue Declining - MEDIUM
- High Cash Deposit Percentage - MEDIUM

## Excel Report Tabs (10 tabs)
1. **Summary**: Account info, revenue metrics, risk assessment
2. **Transactions**: Full transaction detail with filtering
3. **Monthly Analysis**: Cash flow trends with charts
4. **Risk Analysis**: NSF, negative days, gambling detection
5. **MCA Positions**: Reverse-engineered positions with payment tracking
6. **Funding Analysis**: Wire transfers, revenue sources, recurring expenses
7. **Red Flags**: Critical warnings and alerts
8. **Lender Matches**: Eligibility scores for 5 default lenders
9. **In-House Forensics**: Forensics checklist (NSF, cash deposits, gambling, tax liens, PDF metadata, revenue velocity), red flags with severity, expense breakdown
10. **Deal Summary**: Spec sheet with business info, revenue summary, position table, proposed deal impact, recommendations, monthly breakdown

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

## Config Files (config/)
- **keywords.json**: 60+ MCA lender patterns organized by ACH ID, lender name, and aliases; used by position detector and scrubber for keyword-based analysis
- **factor_rates.json**: Factor rate lookup table by lender
- **funder_rates_complete.json**: Complete funder rate data
- **lender_aliases.json**: Maps variant lender names to canonical names

## Dependencies
- Flask: Web framework
- pandas: Data manipulation
- xlsxwriter: Excel report generation
- pdfplumber: PDF text extraction
- openpyxl: Excel file handling

## How to Run
The web server runs automatically on port 5000.

## Recent Changes
- February 5, 2026: Enhanced pipeline merge
  - Added position_detector.py with 4-tier keyword-based MCA position detection
  - Added config/ directory with keywords.json (60+ lender patterns), factor_rates.json, funder_rates_complete.json, lender_aliases.json
  - Enhanced reporter.py with In-House Forensics tab and Deal Summary spec sheet tab (now 10 tabs total)
  - Enhanced app.py pipeline with keyword-based analysis, position detection, fraud flag tracking, enhanced risk analysis
  - Added backward-compatible wrappers: find_matching_lenders(), calculate_full_deal_metrics(), generate_report()
  - Fixed forensics tab data mapping (nested risk_profile -> flat format)
  - Fixed red_flags handling for both string and dict formats
- February 5, 2026: Bank parser improvements and frequency detection fix
  - Added PNC Bank parser with section-based transaction extraction
  - Added Truist parser with multi-column check and section handling
  - Fixed bank detection ordering (PNC/Truist checked before Chase)
  - Changed frequency detection from gap-based to count-per-month method
  - Separated SpotOn MINPMT (MCA) from SpotOn processing fees (revenue)
  - Chase detection pattern tightened to "JPMorgan Chase" / "JPMORGAN"
- February 5, 2026: Enhanced MCA detection and analysis
  - ACH identifier patterns for 20+ lenders
  - Reverse-engineering of MCA positions (funding, remaining balance)
  - Payment change tracking (increased/decreased/stopped)
  - Funding event detection (wires, large deposits)
  - Revenue source categorization (Shift4, DoorDash, SpotOn, Square)
  - Recurring expense analysis (payroll, suppliers, rent, utilities)
  - Red flag detection (stacking, recent funding, returns)
  - Expanded Excel report to 8 tabs
