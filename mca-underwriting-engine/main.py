"""
MCA Underwriting Command Center - CLI Entry Point
Run analysis pipeline from the command line.
"""

import os
import sys
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core_logic.ocr_engine import extract_from_pdf
from core_logic.scrubber import scrub_statement, analyze_concentration
from core_logic.risk_engine import analyze_risk
from core_logic.position_detector import detect_positions
from core_logic.calculator import calculate_deal_summary
from core_logic.lender_matcher import match_lenders
from core_logic.reporter import generate_report


INPUT_DIR = os.path.join(BASE_DIR, 'input_pdfs')
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
INPUT_CONFIG = os.path.join(BASE_DIR, 'input_config')
PROCESSED_DIR = os.path.join(BASE_DIR, 'processed_data')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output_reports')


def load_json(filename):
    path = os.path.join(CONFIG_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {}


def find_lender_csv():
    if os.path.exists(INPUT_CONFIG):
        for fn in os.listdir(INPUT_CONFIG):
            if fn.endswith('.csv'):
                return os.path.join(INPUT_CONFIG, fn)
    test_csv = os.path.join(BASE_DIR, 'test_data', 'test_lenders.csv')
    if os.path.exists(test_csv):
        return test_csv
    return None


def run_pipeline(pdf_files, merchant_name="Unknown Merchant", fico=0,
                 tib_months=0, ownership=100, state="", industry=""):
    """Run the full analysis pipeline on one or more bank statement PDFs."""
    keywords = load_json('keywords.json')
    factor_rates = load_json('factor_rates.json')

    print(f"\n{'='*70}")
    print(f"  MCA UNDERWRITING COMMAND CENTER")
    print(f"  Merchant: {merchant_name}")
    print(f"  Files: {len(pdf_files)}")
    print(f"{'='*70}\n")

    # Step 1: OCR Extraction
    print("[1/7] OCR Extraction...")
    all_transactions = []
    all_fraud_flags = []
    all_statements = []

    for pdf_path in pdf_files:
        print(f"  Extracting: {os.path.basename(pdf_path)}")
        result = extract_from_pdf(pdf_path)
        txns = result.get('transactions', [])
        print(f"    Bank: {result.get('bank_name', 'Unknown')}")
        print(f"    Transactions: {len(txns)}")
        print(f"    Period: {result.get('statement_period', {}).get('start', '?')} to {result.get('statement_period', {}).get('end', '?')}")

        if result.get('fraud_flags'):
            for flag in result['fraud_flags']:
                print(f"    *** {flag}")

        if result.get('errors'):
            for err in result['errors']:
                print(f"    WARNING: {err}")

        all_transactions.extend(txns)
        all_statements.append(txns)
        all_fraud_flags.extend(result.get('fraud_flags', []))

    if not all_transactions:
        print("\n  ERROR: No transactions extracted. Aborting.")
        return None

    print(f"  Total transactions: {len(all_transactions)}\n")

    # Step 2: Revenue Scrubbing
    print("[2/7] Revenue Scrubbing...")
    scrub_data = scrub_statement(all_transactions, keywords)
    print(f"  Gross deposits: ${scrub_data.get('total_gross', 0):,.2f}")
    print(f"  Excluded: ${scrub_data.get('total_gross', 0) - scrub_data.get('total_net', 0):,.2f}")
    print(f"  Net revenue: ${scrub_data.get('total_net', 0):,.2f}")
    print(f"  Avg monthly net: ${scrub_data.get('avg_monthly_net', 0):,.2f}")
    print(f"  Excluded transactions: {len(scrub_data.get('excluded_transactions', []))}\n")

    # Step 3: Concentration Analysis
    print("[3/7] Concentration Analysis...")
    concentration = analyze_concentration(
        scrub_data.get('clean_transactions', []),
        scrub_data.get('total_net', 0)
    )
    if concentration.get('top_depositors'):
        top = concentration['top_depositors'][0]
        print(f"  Top depositor: {top['name']} ({top['percent']:.1f}%)")
    print(f"  Concentration risk: {'YES' if concentration.get('concentration_risk') else 'No'}\n")

    # Step 4: Risk Analysis
    print("[4/7] Risk Analysis...")
    risk_data = analyze_risk(all_transactions, scrub_data.get('total_net', 0), keywords)
    print(f"  Risk Score: {risk_data.get('risk_score', 0)}/100 (Tier {risk_data.get('risk_tier', 'D')})")
    print(f"  NSFs: {risk_data.get('nsf_count', 0)} (${risk_data.get('nsf_total_fees', 0):,.2f} in fees)")
    print(f"  Negative days: {risk_data.get('negative_day_count', 0)}")
    print(f"  Cash deposits: {risk_data.get('cash_deposit_percent', 0):.1f}% {'(FLAGGED)' if risk_data.get('cash_risk_flag') else ''}")
    print(f"  Gambling: {'DETECTED' if risk_data.get('gambling_flag') else 'None'}")
    print(f"  Red flags: {len(risk_data.get('red_flags', []))}")
    print(f"  Revenue trend: {risk_data.get('velocity_flag', 'stable')} ({risk_data.get('revenue_velocity', 0):+.1f}% MoM)\n")

    # Step 5: Position Detection
    print("[5/7] Position Detection...")
    position_data = detect_positions(all_transactions, keywords, factor_rates)
    print(f"  Positions found: {position_data.get('total_positions', 0)}")
    for p in position_data.get('positions', []):
        print(f"    #{p['position_number']} {p['lender_name']}: ${p['payment_amount']:,.2f} "
              f"{p['payment_frequency']} | Est. remaining: ${p['estimated_remaining_balance']:,.2f} "
              f"| Confidence: {p['confidence']}")
    print(f"  Total daily payment: ${position_data.get('total_daily_payment', 0):,.2f}")
    print(f"  Total monthly payment: ${position_data.get('total_monthly_payment', 0):,.2f}\n")

    # Step 6: Financial Calculations
    print("[6/7] Financial Calculations...")
    calc_data = calculate_deal_summary(
        scrub_data=scrub_data,
        risk_data=risk_data,
        position_data=position_data,
        fico_score=fico,
        time_in_business_months=tib_months,
        ownership_percent=ownership,
        state=state,
        industry=industry,
    )
    print(f"  DTI: {calc_data.get('dti_ratio', 0):.1%}")
    print(f"  Holdback: {calc_data.get('current_holdback_percent', 0):.1f}%")
    print(f"  Net available: ${calc_data.get('net_available_revenue', 0):,.2f}/mo")
    print(f"  Max recommended funding: ${calc_data.get('max_recommended_funding', 0):,.2f}")
    cap = calc_data.get('advance_cap', {})
    print(f"  Advance cap: ${cap.get('min_advance', 0):,.0f} - ${cap.get('max_advance', 0):,.0f}\n")

    # Step 7: Lender Matching & Report
    print("[7/7] Lender Matching & Report Generation...")
    lender_csv = find_lender_csv()
    if lender_csv:
        lender_data = match_lenders(calc_data, lender_csv)
        print(f"  Checked {lender_data.get('total_lenders_checked', 0)} lenders")
        print(f"  Eligible: {lender_data.get('eligible_count', 0)}")
        print(f"  Disqualified: {lender_data.get('disqualified_count', 0)}")
        for el in lender_data.get('eligible_lenders', []):
            print(f"    + {el['lender_name']} (score: {el['match_score']:.1f})")
        for dq in lender_data.get('disqualified_lenders', []):
            print(f"    - {dq['lender_name']}: {'; '.join(dq['reasons'][:2])}")
    else:
        lender_data = {
            "eligible_lenders": [], "disqualified_lenders": [],
            "total_lenders_checked": 0, "eligible_count": 0, "disqualified_count": 0,
        }
        print("  No lender CSV found. Skipping lender matching.")

    report_path = generate_report(
        merchant_name=merchant_name,
        scrub_data=scrub_data,
        risk_data=risk_data,
        position_data=position_data,
        calculation_data=calc_data,
        lender_match_data=lender_data,
        output_path=OUTPUT_DIR,
        fraud_flags=all_fraud_flags,
    )
    print(f"\n  Report: {report_path}")

    print(f"\n{'='*70}")
    print(f"  ANALYSIS COMPLETE")
    print(f"  Risk: Tier {risk_data['risk_tier']} ({risk_data['risk_score']}/100)")
    print(f"  Max Funding: ${calc_data['max_recommended_funding']:,.2f}")
    print(f"  Positions: {position_data['total_positions']}")
    print(f"{'='*70}\n")

    return report_path


def main():
    print("\n" + "="*70)
    print("  MCA UNDERWRITING COMMAND CENTER v2.0")
    print("  Automated Bank Statement Analysis")
    print("="*70)
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    for d in [INPUT_DIR, PROCESSED_DIR, OUTPUT_DIR]:
        os.makedirs(d, exist_ok=True)

    pdf_files = []
    if os.path.exists(INPUT_DIR):
        for fn in os.listdir(INPUT_DIR):
            if fn.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(INPUT_DIR, fn))

    if not pdf_files:
        print(f"  No PDF files found in {INPUT_DIR}/")
        print(f"  Place bank statement PDFs in the input_pdfs/ folder and run again.\n")
        return

    print(f"  Found {len(pdf_files)} file(s):")
    for pdf in pdf_files:
        print(f"    - {os.path.basename(pdf)}")

    merchant = input("\n  Merchant name [Unknown Merchant]: ").strip() or "Unknown Merchant"
    fico_str = input("  FICO score [0]: ").strip() or "0"
    tib_str = input("  Time in business (months) [0]: ").strip() or "0"

    report = run_pipeline(
        pdf_files,
        merchant_name=merchant,
        fico=int(fico_str),
        tib_months=int(tib_str),
    )

    if report:
        print(f"\n  Report saved to: {report}")
    else:
        print("\n  Pipeline failed. Check errors above.")


if __name__ == '__main__':
    main()
