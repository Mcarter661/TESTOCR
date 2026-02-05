#!/usr/bin/env python3
"""Quick test to verify reporter Tab 5 works with enhanced lender data."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core_logic.lender_matcher import match_lenders
from core_logic.reporter import generate_report


def test_report_generation():
    csv_path = os.path.join(os.path.dirname(__file__), "input_config", "lenders.csv")

    deal = {
        "fico_score": 680,
        "monthly_revenue": 45000,
        "time_in_business_months": 24,
        "nsf_count": 2,
        "negative_days": 3,
        "position_count": 1,
        "days_since_last_funding": 60,
        "ownership_percent": 75,
        "avg_daily_balance": 6000,
        "current_holdback_percent": 15,
        "state": "FL",
        "industry": "Retail",
    }

    lender_data = match_lenders(deal, csv_path)

    # Minimal stubs for other tabs
    scrub_data = {"monthly_gross": {}, "monthly_net": {}, "monthly_deposit_count": {},
                  "total_gross": 0, "total_net": 0, "avg_monthly_net": 0,
                  "excluded_transactions": []}
    risk_data = {"risk_score": 72, "risk_tier": "B", "nsf_count": 2, "nsf_total_fees": 70,
                 "negative_day_count": 3, "consecutive_negative_days": 1,
                 "max_negative_balance": -500, "cash_deposit_percent": 5,
                 "cash_risk_flag": False, "cash_deposit_total": 2000,
                 "gambling_flag": False, "gambling_total": 0,
                 "red_flags": [], "revenue_velocity": 2.1,
                 "velocity_flag": "stable", "revenue_acceleration": 0.5,
                 "expenses_by_category": {}}
    position_data = {"positions": [], "total_positions": 1, "total_daily_payment": 200,
                     "total_monthly_payment": 4400, "estimated_total_remaining": 15000,
                     "unique_lenders": ["Unknown"], "days_since_last_funding": 60}
    calc_data = {**deal, "max_recommended_funding": 50000, "net_available_revenue": 30000,
                 "cash_flow_coverage": 1.8, "annualized_revenue": 540000,
                 "advance_cap": {"min_advance": 30000, "max_advance": 70000},
                 "dti_ratio": 0.35, "current_holdback_percent": 15,
                 "monthly_holdback": 4400}

    output_path = os.path.join(os.path.dirname(__file__), "output_reports")
    filepath = generate_report(
        merchant_name="Phase3 Test Merchant",
        scrub_data=scrub_data,
        risk_data=risk_data,
        position_data=position_data,
        calculation_data=calc_data,
        lender_match_data=lender_data,
        output_path=output_path,
    )

    print(f"Report generated: {filepath}")
    print(f"Eligible lenders in report: {lender_data['eligible_count']}")
    print(f"Disqualified lenders in report: {lender_data['disqualified_count']}")
    assert os.path.exists(filepath), "Report file not created"
    print("PASS: Report generation with enhanced lender data works")


if __name__ == "__main__":
    test_report_generation()
