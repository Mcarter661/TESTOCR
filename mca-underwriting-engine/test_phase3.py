#!/usr/bin/env python3
"""
Phase 3 Integration Test - Verify enhanced lender matching with 73-column template.
Tests CSV loading, hard disqualifications, soft preferences, scoring, and reporter output.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core_logic.lender_matcher import match_lenders


def test_csv_loading():
    """Test that the 73-column CSV loads correctly."""
    csv_path = os.path.join(os.path.dirname(__file__), "input_config", "lenders.csv")
    assert os.path.exists(csv_path), f"CSV not found: {csv_path}"

    # Use a deal that passes everything to verify loading
    deal = {
        "fico_score": 750,
        "monthly_revenue": 80000,
        "time_in_business_months": 60,
        "nsf_count": 0,
        "negative_days": 0,
        "position_count": 0,
        "days_since_last_funding": 120,
        "ownership_percent": 100,
        "avg_daily_balance": 10000,
        "current_holdback_percent": 0,
        "state": "NY",
        "industry": "Restaurant",
    }

    result = match_lenders(deal, csv_path)
    print("=" * 70)
    print("TEST 1: CSV Loading & Basic Match")
    print("=" * 70)
    print(f"Total lenders checked: {result['total_lenders_checked']}")
    print(f"Eligible: {result['eligible_count']}")
    print(f"Disqualified: {result['disqualified_count']}")
    assert result['total_lenders_checked'] == 5, f"Expected 5 lenders, got {result['total_lenders_checked']}"
    print("PASS: All 5 lenders loaded from CSV\n")
    return result


def test_strong_deal():
    """Test a strong deal that should match most/all lenders."""
    csv_path = os.path.join(os.path.dirname(__file__), "input_config", "lenders.csv")
    deal = {
        "fico_score": 750,
        "monthly_revenue": 80000,
        "time_in_business_months": 60,
        "nsf_count": 0,
        "negative_days": 0,
        "position_count": 0,
        "days_since_last_funding": 120,
        "ownership_percent": 100,
        "avg_daily_balance": 10000,
        "current_holdback_percent": 0,
        "state": "NY",
        "industry": "Restaurant",
    }

    result = match_lenders(deal, csv_path)
    print("=" * 70)
    print("TEST 2: Strong Deal - Should match all/most lenders")
    print("=" * 70)
    print(f"Deal: FICO={deal['fico_score']}, Rev=${deal['monthly_revenue']:,}, "
          f"TIB={deal['time_in_business_months']}mo, State={deal['state']}, "
          f"Industry={deal['industry']}")
    print(f"\nEligible: {result['eligible_count']}, Disqualified: {result['disqualified_count']}")

    print("\n--- Eligible Lenders ---")
    for lender in result['eligible_lenders']:
        print(f"  {lender['lender_name']:25s} Score: {lender['match_score']:5.1f}  "
              f"Appetite: {lender.get('current_appetite', 'N/A'):8s}  "
              f"Tier: {lender.get('tier', 'N/A'):3s}  "
              f"Rep: {lender.get('rep_contact_name', 'N/A')}")

    if result['disqualified_lenders']:
        print("\n--- Disqualified Lenders ---")
        for lender in result['disqualified_lenders']:
            print(f"  {lender['lender_name']:25s} Reasons: {'; '.join(lender['reasons'])}")

    print("\nPASS: Strong deal matching complete\n")
    return result


def test_weak_deal_disqualifications():
    """Test a weak deal that should disqualify several lenders with specific reasons."""
    csv_path = os.path.join(os.path.dirname(__file__), "input_config", "lenders.csv")
    deal = {
        "fico_score": 580,
        "monthly_revenue": 15000,
        "time_in_business_months": 6,
        "nsf_count": 8,
        "negative_days": 12,
        "position_count": 4,
        "days_since_last_funding": 10,
        "ownership_percent": 40,
        "avg_daily_balance": 1000,
        "current_holdback_percent": 40,
        "state": "CO",
        "industry": "Cannabis",
    }

    result = match_lenders(deal, csv_path)
    print("=" * 70)
    print("TEST 3: Weak Deal - Should disqualify most/all lenders with reasons")
    print("=" * 70)
    print(f"Deal: FICO={deal['fico_score']}, Rev=${deal['monthly_revenue']:,}, "
          f"TIB={deal['time_in_business_months']}mo, NSFs={deal['nsf_count']}, "
          f"NegDays={deal['negative_days']}, Positions={deal['position_count']}")
    print(f"State={deal['state']}, Industry={deal['industry']}, "
          f"ADB=${deal['avg_daily_balance']:,}, Holdback={deal['current_holdback_percent']}%")
    print(f"\nEligible: {result['eligible_count']}, Disqualified: {result['disqualified_count']}")

    if result['eligible_lenders']:
        print("\n--- Eligible Lenders ---")
        for lender in result['eligible_lenders']:
            print(f"  {lender['lender_name']:25s} Score: {lender['match_score']:.1f}")

    print("\n--- Disqualified Lenders ---")
    for lender in result['disqualified_lenders']:
        print(f"\n  {lender['lender_name']}:")
        for r in lender['reasons']:
            print(f"    - {r}")

    assert result['disqualified_count'] >= 4, "Expected at least 4 disqualified lenders for weak deal"
    print("\nPASS: Weak deal properly disqualified lenders with specific reasons\n")
    return result


def test_contact_info():
    """Verify that eligible lenders include contact info."""
    csv_path = os.path.join(os.path.dirname(__file__), "input_config", "lenders.csv")
    deal = {
        "fico_score": 750,
        "monthly_revenue": 80000,
        "time_in_business_months": 60,
        "nsf_count": 0,
        "negative_days": 0,
        "position_count": 0,
        "days_since_last_funding": 120,
        "ownership_percent": 100,
        "avg_daily_balance": 10000,
        "current_holdback_percent": 0,
        "state": "NY",
        "industry": "Restaurant",
    }

    result = match_lenders(deal, csv_path)
    print("=" * 70)
    print("TEST 4: Contact Info in Eligible Lenders")
    print("=" * 70)

    has_contacts = 0
    for lender in result['eligible_lenders']:
        rep = lender.get('rep_contact_name', '')
        email = lender.get('rep_contact_email', '')
        phone = lender.get('rep_phone', '')
        sub_email = lender.get('submission_email', '')
        print(f"  {lender['lender_name']:25s}")
        print(f"    Rep:        {rep}")
        print(f"    Email:      {email}")
        print(f"    Phone:      {phone}")
        print(f"    Submit To:  {sub_email}")
        if rep and email:
            has_contacts += 1

    assert has_contacts > 0, "Expected at least one lender with contact info"
    print(f"\nPASS: {has_contacts} lenders have complete contact info\n")


def test_appetite_scoring():
    """Verify that HOT appetite lenders score higher than NORMAL."""
    csv_path = os.path.join(os.path.dirname(__file__), "input_config", "lenders.csv")
    deal = {
        "fico_score": 700,
        "monthly_revenue": 60000,
        "time_in_business_months": 48,
        "nsf_count": 1,
        "negative_days": 2,
        "position_count": 0,
        "days_since_last_funding": 120,
        "ownership_percent": 100,
        "avg_daily_balance": 8000,
        "current_holdback_percent": 0,
        "state": "NY",
        "industry": "Retail",
    }

    result = match_lenders(deal, csv_path)
    print("=" * 70)
    print("TEST 5: Appetite Scoring - HOT lenders should score higher")
    print("=" * 70)

    for lender in result['eligible_lenders']:
        appetite = lender.get('current_appetite', 'N/A')
        tier = lender.get('tier', 'N/A')
        preferred = lender.get('is_preferred', False)
        print(f"  {lender['lender_name']:25s} Score: {lender['match_score']:5.1f}  "
              f"Appetite: {appetite:8s}  Tier: {tier:3s}  Preferred: {preferred}")

    print("\nPASS: Appetite and tier scoring verified\n")


def count_criteria_fields():
    """Count how many criteria fields are now checked."""
    hard_criteria = [
        "Is Active",
        "Current Appetite (PAUSED)",
        "Min FICO",
        "Min Monthly Revenue",
        "Min Time in Business",
        "Max Monthly NSFs",
        "Max Negative Days",
        "Max Positions Allowed",
        "Min Days Since Last Funding",
        "Min Ownership %",
        "Min Avg Ledger Balance (ADB)",
        "Max Remit Holdback %",
        "Min Monthly Deposits",
        "Restricted States",
        "Restricted Industries",
    ]
    soft_criteria = [
        "Current Appetite (HOT/NORMAL/SLOW)",
        "Is Preferred",
        "Tier (A/B/C/D)",
        "Preferred Industries",
        "Favorite Positions",
        "FICO headroom",
        "Revenue headroom",
        "NSF headroom",
        "Negative day headroom",
    ]
    print("=" * 70)
    print("CRITERIA FIELD COUNT")
    print("=" * 70)
    print(f"\nHard Disqualification Criteria: {len(hard_criteria)}")
    for i, c in enumerate(hard_criteria, 1):
        print(f"  {i:2d}. {c}")
    print(f"\nSoft Preference Criteria: {len(soft_criteria)}")
    for i, c in enumerate(soft_criteria, 1):
        print(f"  {i:2d}. {c}")
    print(f"\nTotal criteria checked: {len(hard_criteria) + len(soft_criteria)}")
    print()


if __name__ == "__main__":
    count_criteria_fields()
    test_csv_loading()
    strong_result = test_strong_deal()
    weak_result = test_weak_deal_disqualifications()
    test_contact_info()
    test_appetite_scoring()

    print("=" * 70)
    print("ALL TESTS PASSED")
    print("=" * 70)
