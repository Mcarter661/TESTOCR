"""
MCA Underwriting Command Center
Main execution script for automated bank statement analysis.
"""

import os
import sys
from datetime import datetime
from typing import List

from core_logic.ocr_engine import process_bank_statement
from core_logic.scrubber import scrub_transactions
from core_logic.risk_engine import generate_risk_profile
from core_logic.lender_matcher import find_matching_lenders
from core_logic.reporter import generate_master_report


INPUT_PDF_DIR = "input_pdfs"
INPUT_CONFIG_DIR = "input_config"
PROCESSED_DATA_DIR = "processed_data"
OUTPUT_REPORTS_DIR = "output_reports"


def check_for_new_files(directory: str) -> List[str]:
    """
    Check input directory for new PDF files to process.
    
    Args:
        directory: Path to input directory.
        
    Returns:
        List of PDF file paths.
    """
    # TODO: Scan directory for PDF files
    # TODO: Filter out already-processed files (check processed_data)
    # TODO: Return list of new files to process
    pdf_files = []
    if os.path.exists(directory):
        for filename in os.listdir(directory):
            if filename.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(directory, filename))
    return pdf_files


def save_processed_data(data: dict, filename: str) -> None:
    """
    Save processed OCR data to processed_data directory.
    
    Args:
        data: Processed data dictionary.
        filename: Original filename for reference.
    """
    # TODO: Serialize data to JSON
    # TODO: Save to processed_data directory with timestamp
    pass


def run_pipeline(pdf_path: str) -> str:
    """
    Run the complete underwriting pipeline on a single PDF.
    
    Args:
        pdf_path: Path to the bank statement PDF.
        
    Returns:
        Path to generated report.
    """
    print(f"\n{'='*60}")
    print(f"Processing: {os.path.basename(pdf_path)}")
    print(f"{'='*60}\n")
    
    # Step 1: OCR - Extract data from PDF
    print("Step 1: OCR Started...")
    print("  - Extracting text from PDF")
    print("  - Detecting bank format")
    print("  - Parsing transactions")
    ocr_data = process_bank_statement(pdf_path)
    print("  [COMPLETE] OCR extraction finished\n")
    
    # Step 2: Scrubbing - Clean and categorize transactions
    print("Step 2: Scrubbing Started...")
    print("  - Identifying internal transfers")
    print("  - Categorizing transactions")
    print("  - Calculating net revenue")
    scrubbed_data = scrub_transactions(ocr_data.get('transactions', []) if ocr_data else [])
    print("  [COMPLETE] Transaction scrubbing finished\n")
    
    # Step 3: Risk Analysis
    print("Step 3: Risk Analysis Started...")
    print("  - Counting NSF occurrences")
    print("  - Analyzing negative balance days")
    print("  - Calculating DTI ratio")
    print("  - Flagging cash/ATM activity")
    print("  - Detecting existing MCA positions")
    risk_profile = generate_risk_profile(
        scrubbed_data.get('transactions', []) if scrubbed_data else [],
        scrubbed_data.get('daily_balances', None) if scrubbed_data else None
    )
    print("  [COMPLETE] Risk analysis finished\n")
    
    # Step 4: Lender Matching
    print("Step 4: Lender Matching Started...")
    print("  - Loading lender profiles")
    print("  - Filtering eligible lenders")
    print("  - Ranking matches")
    lender_matches = find_matching_lenders(risk_profile if risk_profile else {})
    print("  [COMPLETE] Lender matching finished\n")
    
    # Step 5: Report Generation
    print("Step 5: Report Generation Started...")
    print("  - Creating Master Excel workbook")
    print("  - Adding summary sheet")
    print("  - Adding transaction details")
    print("  - Adding risk analysis")
    print("  - Adding lender recommendations")
    print("  - Generating charts")
    
    report_path = generate_master_report(
        summary_data=ocr_data.get('account_info', {}) if ocr_data else {},
        transactions=scrubbed_data.get('transactions', []) if scrubbed_data else [],
        monthly_data=scrubbed_data.get('monthly_data', None) if scrubbed_data else None,
        risk_profile=risk_profile if risk_profile else {},
        lender_matches=lender_matches.get('matches', []) if lender_matches else [],
        output_dir=OUTPUT_REPORTS_DIR
    )
    print("  [COMPLETE] Report generation finished\n")
    
    return report_path


def main():
    """
    Main entry point for the MCA Underwriting Command Center.
    """
    print("\n" + "="*60)
    print("   MCA UNDERWRITING COMMAND CENTER")
    print("   Automated Bank Statement Analysis")
    print("="*60)
    print(f"\nStarted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check for new files
    print(f"\nChecking {INPUT_PDF_DIR}/ for new bank statements...")
    pdf_files = check_for_new_files(INPUT_PDF_DIR)
    
    if not pdf_files:
        print("No new PDF files found in input_pdfs/")
        print("Place bank statement PDFs in the input_pdfs/ folder and run again.")
        return
    
    print(f"Found {len(pdf_files)} file(s) to process:")
    for pdf in pdf_files:
        print(f"  - {os.path.basename(pdf)}")
    
    # Process each file
    reports_generated = []
    for pdf_path in pdf_files:
        try:
            report_path = run_pipeline(pdf_path)
            if report_path:
                reports_generated.append(report_path)
        except Exception as e:
            print(f"ERROR processing {pdf_path}: {str(e)}")
            continue
    
    # Summary
    print("\n" + "="*60)
    print("   PROCESSING COMPLETE")
    print("="*60)
    print(f"\nFiles processed: {len(pdf_files)}")
    print(f"Reports generated: {len(reports_generated)}")
    if reports_generated:
        print("\nGenerated reports:")
        for report in reports_generated:
            print(f"  - {report}")
    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
