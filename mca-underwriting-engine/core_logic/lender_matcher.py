"""
Lender Matcher - Matches a deal profile against lender eligibility criteria.
Loads criteria from CSV, checks each criterion, returns eligible and disqualified lists.
"""

import csv
import os
from typing import List, Dict


def match_lenders(deal_data: dict, lenders_csv_path: str) -> dict:
    """
    Main entry point. Check deal against all lenders in the CSV.
    """
    if not os.path.exists(lenders_csv_path):
        return {
            "eligible_lenders": [],
            "disqualified_lenders": [],
            "total_lenders_checked": 0,
            "eligible_count": 0,
            "disqualified_count": 0,
            "error": f"Lender CSV not found: {lenders_csv_path}",
        }

    lenders = _load_lender_criteria(lenders_csv_path)
    eligible = []
    disqualified = []

    for lender in lenders:
        reasons = _check_criteria(deal_data, lender)
        if not reasons:
            score = _calculate_match_score(deal_data, lender)
            eligible.append({
                "lender_name": lender["lender_name"],
                "product_types": lender.get("product_types", []),
                "payment_types": lender.get("payment_types", []),
                "match_score": score,
            })
        else:
            disqualified.append({
                "lender_name": lender["lender_name"],
                "reasons": reasons,
            })

    eligible.sort(key=lambda x: x["match_score"], reverse=True)

    return {
        "eligible_lenders": eligible,
        "disqualified_lenders": disqualified,
        "total_lenders_checked": len(lenders),
        "eligible_count": len(eligible),
        "disqualified_count": len(disqualified),
    }


def _load_lender_criteria(csv_path: str) -> list:
    """Parse the lender criteria CSV into a list of dicts."""
    lenders = []
    with open(csv_path, 'r', newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            lenders.append({
                "lender_name": row.get("Lender Name", "").strip(),
                "min_fico": _safe_int(row.get("Min FICO", "0")),
                "min_monthly_revenue": _safe_float(row.get("Min Monthly Revenue", "0")),
                "min_time_in_business": _safe_int(row.get("Min Time in Business", "0")),
                "max_monthly_nsfs": _safe_int(row.get("Max Monthly NSFs", "999")),
                "max_negative_days": _safe_int(row.get("Max Negative Days", "999")),
                "max_positions_allowed": _safe_int(row.get("Max Positions Allowed", "99")),
                "min_days_since_last_funding": _safe_int(row.get("Min Days Since Last Funding", "0")),
                "min_ownership_percent": _safe_float(row.get("Min Ownership %", "0")),
                "min_avg_daily_balance": _safe_float(row.get("Min Avg Daily Balance", "0")),
                "max_holdback_percent": _safe_float(row.get("Max Holdback %", "100")),
                "restricted_states": _parse_list(row.get("Restricted States", "")),
                "restricted_industries": _parse_list(row.get("Restricted Industries", "")),
                "product_types": _parse_list(row.get("Product Types", ""), sep="|"),
                "payment_types": _parse_list(row.get("Payment Types", ""), sep="|"),
            })
    return lenders


def _check_criteria(deal: dict, lender: dict) -> list:
    """Check all criteria. Returns list of failure reasons (empty = eligible)."""
    reasons = []

    fico = deal.get("fico_score", 0)
    if fico > 0 and fico < lender["min_fico"]:
        reasons.append(f"FICO {fico} below minimum {lender['min_fico']}")

    rev = deal.get("monthly_revenue", 0)
    if rev < lender["min_monthly_revenue"]:
        reasons.append(f"Monthly revenue ${rev:,.0f} below minimum ${lender['min_monthly_revenue']:,.0f}")

    tib = deal.get("time_in_business_months", 0)
    if tib > 0 and tib < lender["min_time_in_business"]:
        reasons.append(f"Time in business {tib}mo below minimum {lender['min_time_in_business']}mo")

    nsf = deal.get("nsf_count", 0)
    if nsf > lender["max_monthly_nsfs"]:
        reasons.append(f"NSF count {nsf} exceeds maximum {lender['max_monthly_nsfs']}")

    neg_days = deal.get("negative_days", 0)
    if neg_days > lender["max_negative_days"]:
        reasons.append(f"Negative days {neg_days} exceeds maximum {lender['max_negative_days']}")

    positions = deal.get("position_count", 0)
    if positions > lender["max_positions_allowed"]:
        reasons.append(f"Position count {positions} exceeds maximum {lender['max_positions_allowed']}")

    days_since = deal.get("days_since_last_funding", 0)
    if days_since < lender["min_days_since_last_funding"]:
        reasons.append(f"Days since last funding {days_since} below minimum {lender['min_days_since_last_funding']}")

    ownership = deal.get("ownership_percent", 100)
    if ownership < lender["min_ownership_percent"]:
        reasons.append(f"Ownership {ownership}% below minimum {lender['min_ownership_percent']}%")

    adb = deal.get("avg_daily_balance", 0)
    if adb < lender["min_avg_daily_balance"]:
        reasons.append(f"Avg daily balance ${adb:,.0f} below minimum ${lender['min_avg_daily_balance']:,.0f}")

    holdback = deal.get("current_holdback_percent", 0)
    if holdback > lender["max_holdback_percent"]:
        reasons.append(f"Current holdback {holdback:.1f}% exceeds maximum {lender['max_holdback_percent']}%")

    state = deal.get("state", "").upper().strip()
    if state and state in [s.upper().strip() for s in lender["restricted_states"]]:
        reasons.append(f"State '{state}' is restricted")

    industry = deal.get("industry", "").upper().strip()
    if industry:
        for ri in lender["restricted_industries"]:
            if ri.upper().strip() in industry or industry in ri.upper().strip():
                reasons.append(f"Industry '{deal.get('industry', '')}' is restricted")
                break

    return reasons


def _calculate_match_score(deal: dict, lender: dict) -> float:
    """
    Score 0-100 for how well the deal fits the lender.
    Higher = better fit (more headroom above minimums).
    """
    score = 50.0

    rev = deal.get("monthly_revenue", 0)
    min_rev = lender["min_monthly_revenue"]
    if min_rev > 0:
        ratio = rev / min_rev
        score += min(15, (ratio - 1) * 10)

    fico = deal.get("fico_score", 0)
    min_fico = lender["min_fico"]
    if min_fico > 0 and fico > 0:
        diff = fico - min_fico
        score += min(10, diff / 10)

    nsf = deal.get("nsf_count", 0)
    max_nsf = lender["max_monthly_nsfs"]
    if max_nsf > 0:
        remaining = max_nsf - nsf
        score += min(10, remaining * 2)
    elif nsf == 0:
        score += 10

    neg = deal.get("negative_days", 0)
    max_neg = lender["max_negative_days"]
    if max_neg > 0:
        remaining = max_neg - neg
        score += min(10, remaining)
    elif neg == 0:
        score += 10

    holdback = deal.get("current_holdback_percent", 0)
    max_hb = lender["max_holdback_percent"]
    if max_hb > 0:
        remaining = max_hb - holdback
        score += min(5, remaining / 2)

    return round(max(0, min(100, score)), 1)


# ── Parsing helpers ──────────────────────────────────────────────────

def _safe_int(val: str) -> int:
    try:
        return int(str(val).strip().replace(",", ""))
    except (ValueError, TypeError):
        return 0


def _safe_float(val: str) -> float:
    try:
        return float(str(val).strip().replace(",", "").replace("%", ""))
    except (ValueError, TypeError):
        return 0.0


def _parse_list(val: str, sep: str = ",") -> list:
    if not val or not val.strip():
        return []
    return [item.strip() for item in val.split(sep) if item.strip()]
