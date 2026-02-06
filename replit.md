# MCA Underwriting Command Center

## Overview
This project is a web-based bank statement analysis system designed for Merchant Cash Advance (MCA) underwriting. Its primary purpose is to automate and streamline the process of assessing risk and eligibility for MCA applicants. The system processes PDF bank statements to extract financial data, calculates various risk metrics, detects and reverse-engineers existing MCA positions, matches applicant profiles against lender criteria, and generates comprehensive reports. The ultimate goal is to provide underwriters with detailed forensic analysis and deal summaries to facilitate informed lending decisions. The project aims to enhance efficiency, accuracy, and consistency in the MCA underwriting process, offering a competitive advantage in a high-volume market.

## User Preferences
I want iterative development. I prefer detailed explanations for complex logic. Please ask for confirmation before implementing major architectural changes.

## System Architecture
The system is built as a Flask web application with a modular design, separating concerns into distinct core processing modules.

**UI/UX Decisions:**
The web interface features a dashboard for overview, a drag-and-drop file upload facility, a processing page to initiate analysis, and a results page to view history and download reports. The design utilizes a base HTML layout with a sidebar and a dedicated stylesheet for dashboard styling.

**Technical Implementations:**
-   **Core Logic Modules:** The system includes `ocr_engine.py` for PDF text extraction and bank format detection, `scrubber.py` for transaction cleaning and revenue calculation, `risk_engine.py` for risk metric calculation (NSF, negative days, gambling, velocity/acceleration, garnishments), `position_detector.py` for advanced MCA position identification and reverse engineering, `calculator.py` for DTI and funding calculations, `lender_matcher.py` for matching applicants to lenders, and `reporter.py` for generating multi-tabbed Excel and JSON reports.
-   **Bank-Specific Parsers:** Dedicated parsers are implemented for PNC, Truist, and Chase banks, along with a generic parser fallback. Bank detection prioritizes specific formats (PNC, Truist) before more general ones (Chase).
-   **Enhanced Pipeline:** The processing flow involves OCR, bank format detection, transaction scrubbing (including keyword-based exclusions), risk analysis (including PDF fraud detection and address extraction), 4-tier MCA position detection and reverse engineering, DTI and funding calculations, and lender matching.
-   **MCA Position Detection:** A 4-tier keyword-based system using 60+ lender patterns identifies MCA positions. It leverages ACH IDs, known lender names, MCA-like payment patterns, and suspicious recurring debits.
-   **Reverse Engineering:** For detected MCA positions, the system calculates average payment, payment frequency (daily, weekly, bi-weekly, monthly based on count-per-month method), monthly cost, estimated original funding, estimated remaining balance, and estimated payoff date.
-   **Red Flags Detection:** The system identifies critical red flags such as heavy/moderate stacking, very recent/recent funding, high monthly debt, returned/reversed deposits, stopped MCA payments, garnishments/tax liens/judgments, and declining revenue.
-   **Extraction Validation:** Post-OCR quality validation with 6 checks (balance reconciliation, transaction count, credit/debit sanity, description quality, duplicate detection, date sanity) producing 0-100 confidence score and GOOD/NEEDS_REVIEW/POOR status.
-   **Claude Auto-Fix:** When extraction quality is POOR (score < 70), the system automatically sends the PDF text and quality report to Claude API (claude-sonnet-4-20250514) for diagnosis. If Claude identifies the issue with high confidence, it re-extracts using the recommended parser and re-validates. Logs all activity to `logs/claude_auto_fix.log`. Requires `ANTHROPIC_API_KEY` environment variable (skips gracefully if not set).
-   **Reporting:** Generates an 11-tab Master Excel report (and JSON output) including Summary, Transactions, Monthly Analysis (per-bank), Risk Analysis, MCA Positions, Funding Analysis, Red Flags, Lender Matches, In-House Forensics (including scrubber exclusions), Deal Summary (with leverage, expenses, and recommendations), and Quality Report (extraction confidence with checks/issues/duplicates).
-   **Risk Tiers:** Applicants are classified into A, B, C, D, and Decline tiers based on an overall risk score (0-100).
-   **Config Driven:** Key parameters like MCA lender patterns, factor rates, funder rates, and lender aliases are managed through JSON configuration files.

## External Dependencies
-   **Flask**: Web framework for the application.
-   **pandas**: Used for data manipulation and analysis.
-   **xlsxwriter**: For generating Excel reports.
-   **pdfplumber**: For extracting text and data from PDF bank statements.
-   **openpyxl**: For handling Excel file operations.
-   **anthropic**: Anthropic Claude API client for the auto-fix system.