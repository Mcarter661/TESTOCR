"""
Lender Matcher - Enhanced matching engine for 73-column lender template.
Checks deal profiles against lender eligibility criteria with:
  1. Hard disqualifications (instant NO)
  2. Soft preferences (affects ranking but not eligibility)
  3. Match scoring (0-100 based on fit)
  4. Lender appetite weighting
"""

import csv
import os
from typing import List, Dict


def match_lenders(deal_data: dict, lenders_csv_path: str) -> dict:
    """
    Main entry point. Check deal against all lenders in the CSV.

    Enhanced matching with:
    1. Hard disqualifications (instant NO)
    2. Soft preferences (affects ranking but not eligibility)
    3. Match scoring (0-100 based on how well deal fits lender's sweet spot)
    4. Lender appetite weighting (HOT lenders ranked higher)
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
        reasons = _check_hard_disqualifications(deal_data, lender)
        if not reasons:
            score = _calculate_match_score(deal_data, lender)
            eligible.append({
                "lender_name": lender["lender_name"],
                "display_name": lender.get("display_name", lender["lender_name"]),
                "product_types": lender.get("product_types", []),
                "positions_accepted": lender.get("positions_accepted", []),
                "payment_types": lender.get("payment_types", []),
                "match_score": score,
                "current_appetite": lender.get("current_appetite", "NORMAL"),
                "tier": lender.get("tier", ""),
                "is_preferred": lender.get("is_preferred", False),
                # Contact info for immediate outreach
                "rep_contact_name": lender.get("rep_contact_name", ""),
                "rep_contact_email": lender.get("rep_contact_email", ""),
                "rep_phone": lender.get("rep_phone", ""),
                "submission_email": lender.get("submission_email", ""),
                # Funding limits
                "min_funding_amount": lender.get("min_funding_amount", 0),
                "max_funding_amount": lender.get("max_funding_amount", 0),
                "max_daily_ach": lender.get("max_daily_ach", 0),
                # Terms
                "term_range": lender.get("term_range", ""),
                "buy_rates": lender.get("buy_rates", ""),
                "commission_structure": lender.get("commission_structure", ""),
                # Operations
                "credit_pull_type": lender.get("credit_pull_type", ""),
                "funding_cutoff": lender.get("funding_cutoff", ""),
                "bank_login_methods": lender.get("bank_login_methods", []),
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


# ── CSV Loading (73-column template) ────────────────────────────────

def _load_lender_criteria(csv_path: str) -> list:
    """Parse the full 73-column lender criteria CSV into a list of dicts."""
    lenders = []
    with open(csv_path, 'r', newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            lender = {
                # ── Basic Info ──
                "lender_name": row.get("Lender Name", "").strip(),
                "display_name": row.get("Display Name", "").strip() or row.get("Lender Name", "").strip(),
                "submission_email": row.get("Submission Email", "").strip(),
                "cc_email": row.get("CC Email", "").strip(),
                "website": row.get("Website", "").strip(),
                "rating": _safe_float(row.get("Rating", "0")),
                "rep_contact_name": row.get("Rep Contact Name", "").strip(),
                "rep_contact_email": row.get("Rep Contact Email", "").strip(),
                "rep_phone": row.get("Rep Phone", "").strip(),

                # ── Product Info ──
                "product_types": _parse_list(row.get("Product Types", ""), sep="|"),
                "positions_accepted": _parse_list(row.get("Positions Accepted", "")),
                "favorite_positions": _parse_list(row.get("Favorite Positions", "")),
                "payment_types": _parse_list(row.get("Payment Types", ""), sep="|"),

                # ── Underwriting Criteria ──
                "min_fico": _safe_int(row.get("Min FICO", "0")),
                "min_monthly_revenue": _safe_float(row.get("Min Monthly Revenue", "0")),
                "min_time_in_business": _safe_int(row.get("Min Time in Business", "0")),
                "max_monthly_nsfs": _safe_int(row.get("Max Monthly NSFs", "999")),
                "max_negative_days": _safe_int(row.get("Max Negative Days", "999")),
                "min_days_since_last_funding": _safe_int(row.get("Min Days Since Last Funding", "0")),
                "max_positions_allowed": _safe_int(row.get("Max Positions Allowed", "99")),
                "min_ownership_percent": _safe_float(row.get("Min Ownership %", "0")),
                "min_monthly_deposits": _safe_float(row.get("Min Monthly Deposits", "0")),
                "min_avg_ledger_balance": _safe_float(row.get("Min Avg Ledger Balance", "0")),
                # Backwards compat: also check legacy column name
                "min_avg_daily_balance": _safe_float(
                    row.get("Min Avg Ledger Balance", "") or row.get("Min Avg Daily Balance", "0")
                ),
                "max_holdback_percent": _safe_float(row.get("Max Remit Holdback %", "")
                                                     or row.get("Max Holdback %", "100")),

                # ── Funding Limits ──
                "min_funding_amount": _safe_float(row.get("Min Funding Amount", "0")),
                "max_funding_amount": _safe_float(row.get("Max Funding Amount", "0")),
                "max_daily_ach": _safe_float(row.get("Max Daily ACH", "0")),

                # ── Restrictions ──
                "restricted_states": _parse_list(row.get("Restricted States", "")),
                "restricted_industries": _parse_list(row.get("Restricted Industries", "")),
                "preferred_industries": _parse_list(row.get("Preferred Industries", "")),

                # ── Policies ──
                "funds_defaults": row.get("Funds Defaults", "").strip(),
                "non_usa_citizen_policy": row.get("Non-USA Citizen Policy", "").strip(),
                "tax_liens_accepted": row.get("Tax Liens Accepted", "").strip(),
                "tax_liens_notes": row.get("Tax Liens Notes", "").strip(),

                # ── Terms ──
                "term_range": row.get("Term Range", "").strip(),
                "buy_rates": row.get("Buy Rates", "").strip(),
                "buyout_net_rule": row.get("Buyout/Net Rule", "").strip(),
                "commission_structure": row.get("Commission Structure", "").strip(),
                "renewal_terms": row.get("Renewal Terms", "").strip(),

                # ── Operations ──
                "credit_pull_type": row.get("Credit Pull Type", "").strip(),
                "uw_fees": row.get("UW Fees", "").strip(),
                "ach_wire": row.get("ACH/Wire", "").strip(),
                "funding_cutoff": row.get("Funding Cutoff", "").strip(),
                "bank_login_methods": _parse_list(row.get("Bank Login Methods", ""), sep="|"),
                "ucc_filing": row.get("UCC Filing", "").strip(),
                "financials_threshold": row.get("Financials Threshold", "").strip(),

                # ── Business Rules ──
                "exclusivity_days": _safe_int(row.get("Exclusivity Days", "0")),
                "commission_payout_timeframe": row.get("Commission Payout Timeframe", "").strip(),
                "has_renewal_program": _parse_bool(row.get("Has Renewal Program", "")),
                "renewal_eligible_at_percent": _safe_float(row.get("Renewal Eligible at %", "0")),
                "has_stacking_program": _parse_bool(row.get("Has Stacking Program", "")),
                "current_appetite": row.get("Current Appetite", "NORMAL").strip().upper(),
                "tier": row.get("Tier", "").strip().upper(),
                "is_active": _parse_bool(row.get("Is Active", "True")),
                "is_preferred": _parse_bool(row.get("Is Preferred", "")),
            }
            lenders.append(lender)
    return lenders


# ── Hard Disqualifications ──────────────────────────────────────────

def _check_hard_disqualifications(deal: dict, lender: dict) -> list:
    """
    Check all hard disqualification criteria.
    Returns list of failure reasons (empty = eligible).
    If ANY criterion fails, the lender is OUT.
    """
    reasons = []

    # Is Active check
    if not lender.get("is_active", True):
        reasons.append("Lender is not currently active")
        return reasons  # No need to check further

    # Current Appetite = PAUSED
    appetite = lender.get("current_appetite", "NORMAL")
    if appetite == "PAUSED":
        reasons.append("Lender appetite is PAUSED")
        return reasons

    # FICO
    fico = deal.get("fico_score", 0)
    if fico > 0 and lender["min_fico"] > 0 and fico < lender["min_fico"]:
        reasons.append(f"FICO {fico} below minimum {lender['min_fico']}")

    # Monthly Revenue
    rev = deal.get("monthly_revenue", 0)
    if lender["min_monthly_revenue"] > 0 and rev < lender["min_monthly_revenue"]:
        reasons.append(f"Monthly revenue ${rev:,.0f} below minimum ${lender['min_monthly_revenue']:,.0f}")

    # Time in Business
    tib = deal.get("time_in_business_months", 0)
    if tib > 0 and lender["min_time_in_business"] > 0 and tib < lender["min_time_in_business"]:
        reasons.append(f"Time in business {tib}mo below minimum {lender['min_time_in_business']}mo")

    # NSF Count
    nsf = deal.get("nsf_count", 0)
    if lender["max_monthly_nsfs"] < 999 and nsf > lender["max_monthly_nsfs"]:
        reasons.append(f"NSF count {nsf} exceeds maximum {lender['max_monthly_nsfs']}")

    # Negative Days
    neg_days = deal.get("negative_days", 0)
    if lender["max_negative_days"] < 999 and neg_days > lender["max_negative_days"]:
        reasons.append(f"Negative days {neg_days} exceeds maximum {lender['max_negative_days']}")

    # Position Count
    positions = deal.get("position_count", 0)
    if lender["max_positions_allowed"] < 99 and positions > lender["max_positions_allowed"]:
        reasons.append(f"Position count {positions} exceeds maximum {lender['max_positions_allowed']}")

    # Days Since Last Funding
    days_since = deal.get("days_since_last_funding", 0)
    if lender["min_days_since_last_funding"] > 0 and days_since < lender["min_days_since_last_funding"]:
        reasons.append(
            f"Days since last funding {days_since} below minimum {lender['min_days_since_last_funding']}"
        )

    # Ownership Percent
    ownership = deal.get("ownership_percent", 100)
    if lender["min_ownership_percent"] > 0 and ownership < lender["min_ownership_percent"]:
        reasons.append(f"Ownership {ownership}% below minimum {lender['min_ownership_percent']}%")

    # Avg Ledger Balance (ADB)
    adb = deal.get("avg_daily_balance", 0)
    min_adb = max(lender.get("min_avg_ledger_balance", 0), lender.get("min_avg_daily_balance", 0))
    if min_adb > 0 and adb < min_adb:
        reasons.append(f"Avg ledger balance ${adb:,.0f} below minimum ${min_adb:,.0f}")

    # Holdback %
    holdback = deal.get("current_holdback_percent", 0)
    if lender["max_holdback_percent"] < 100 and holdback > lender["max_holdback_percent"]:
        reasons.append(f"Current holdback {holdback:.1f}% exceeds maximum {lender['max_holdback_percent']}%")

    # Monthly Deposits
    monthly_deposits = deal.get("monthly_deposits", 0)
    if lender["min_monthly_deposits"] > 0 and monthly_deposits > 0 and monthly_deposits < lender["min_monthly_deposits"]:
        reasons.append(
            f"Monthly deposits {monthly_deposits} below minimum {lender['min_monthly_deposits']:.0f}"
        )

    # Restricted States
    state = deal.get("state", "").upper().strip()
    if state and lender["restricted_states"]:
        restricted_upper = [s.upper().strip() for s in lender["restricted_states"]]
        if state in restricted_upper:
            reasons.append(f"State '{state}' is restricted")

    # Restricted Industries
    industry = deal.get("industry", "").upper().strip()
    if industry and lender["restricted_industries"]:
        for ri in lender["restricted_industries"]:
            if ri.upper().strip() in industry or industry in ri.upper().strip():
                reasons.append(f"Industry '{deal.get('industry', '')}' is restricted")
                break

    return reasons


# ── Match Scoring ───────────────────────────────────────────────────

def _calculate_match_score(deal: dict, lender: dict) -> float:
    """
    Score 0-100 for how well the deal fits the lender.
    Starts at 50, adds/subtracts based on soft preferences, caps at 100.

    Soft Preferences:
    - Industry in Preferred Industries: +10
    - Position matches Favorite Positions: +10
    - Current Appetite = HOT: +15
    - Current Appetite = NORMAL: +5
    - Is Preferred = True: +10
    - Tier A: +10
    - FICO significantly above minimum: +5
    - Revenue significantly above minimum: +5
    """
    score = 50.0

    # ── Appetite weighting ──
    appetite = lender.get("current_appetite", "NORMAL").upper()
    if appetite == "HOT":
        score += 15
    elif appetite == "NORMAL":
        score += 5
    elif appetite == "SLOW":
        score -= 5

    # ── Preferred lender bonus ──
    if lender.get("is_preferred", False):
        score += 10

    # ── Tier bonus ──
    tier = lender.get("tier", "").upper()
    if tier == "A":
        score += 10
    elif tier == "B":
        score += 5
    elif tier == "C":
        score += 0
    elif tier == "D":
        score -= 5

    # ── Preferred Industry match ──
    industry = deal.get("industry", "").upper().strip()
    if industry and lender.get("preferred_industries"):
        for pi in lender["preferred_industries"]:
            if pi.upper().strip() in industry or industry in pi.upper().strip():
                score += 10
                break

    # ── Favorite Position match ──
    position_count = deal.get("position_count", 0)
    fav_positions = lender.get("favorite_positions", [])
    if fav_positions:
        pos_label = _position_to_label(position_count + 1)  # next position
        for fp in fav_positions:
            if fp.strip().upper() == pos_label.upper():
                score += 10
                break

    # ── FICO headroom ──
    fico = deal.get("fico_score", 0)
    min_fico = lender.get("min_fico", 0)
    if min_fico > 0 and fico > 0:
        diff = fico - min_fico
        if diff >= 100:
            score += 5
        elif diff >= 50:
            score += 3

    # ── Revenue headroom ──
    rev = deal.get("monthly_revenue", 0)
    min_rev = lender.get("min_monthly_revenue", 0)
    if min_rev > 0 and rev > 0:
        ratio = rev / min_rev
        if ratio >= 2.0:
            score += 5
        elif ratio >= 1.5:
            score += 3

    # ── NSF headroom (low NSFs relative to max allowed) ──
    nsf = deal.get("nsf_count", 0)
    max_nsf = lender.get("max_monthly_nsfs", 999)
    if max_nsf < 999 and max_nsf > 0:
        remaining = max_nsf - nsf
        score += min(5, remaining * 1.5)
    elif nsf == 0:
        score += 5

    # ── Negative day headroom ──
    neg = deal.get("negative_days", 0)
    max_neg = lender.get("max_negative_days", 999)
    if max_neg < 999 and max_neg > 0:
        remaining = max_neg - neg
        score += min(5, remaining)
    elif neg == 0:
        score += 5

    return round(max(0, min(100, score)), 1)


# ── Parsing helpers ──────────────────────────────────────────────────

def _safe_int(val: str) -> int:
    try:
        return int(str(val).strip().replace(",", ""))
    except (ValueError, TypeError):
        return 0


def _safe_float(val: str) -> float:
    try:
        return float(str(val).strip().replace(",", "").replace("%", "").replace("$", ""))
    except (ValueError, TypeError):
        return 0.0


def _parse_list(val: str, sep: str = ",") -> list:
    if not val or not val.strip():
        return []
    return [item.strip() for item in val.split(sep) if item.strip()]


def _parse_bool(val: str) -> bool:
    if not val:
        return False
    return str(val).strip().upper() in ("TRUE", "YES", "1", "Y")


def _position_to_label(pos_num: int) -> str:
    """Convert numeric position to label (1 -> '1st', 2 -> '2nd', etc.)"""
    labels = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th+"}
    if pos_num >= 5:
        return "5th+"
    return labels.get(pos_num, f"{pos_num}th")


# ── Default Lenders & Backward-Compatible Wrapper ────────────────────

def _get_default_lenders():
    """Return the 5 hardcoded default lenders used when no CSV is available."""
    return [
        {
            'name': 'Premier Capital',
            'max_funding': 250000,
            'min_monthly_revenue': 15000,
            'max_nsf': 3,
            'max_positions': 3,
            'min_credit_score': 550,
            'max_negative_days': 5,
        },
        {
            'name': 'Velocity Funding',
            'max_funding': 150000,
            'min_monthly_revenue': 10000,
            'max_nsf': 5,
            'max_positions': 4,
            'min_credit_score': 500,
            'max_negative_days': 8,
        },
        {
            'name': 'Summit Business Capital',
            'max_funding': 500000,
            'min_monthly_revenue': 25000,
            'max_nsf': 1,
            'max_positions': 2,
            'min_credit_score': 650,
            'max_negative_days': 2,
        },
        {
            'name': 'Quick Bridge Capital',
            'max_funding': 75000,
            'min_monthly_revenue': 8000,
            'max_nsf': 6,
            'max_positions': 5,
            'min_credit_score': 480,
            'max_negative_days': 10,
        },
        {
            'name': 'Titan Merchant Services',
            'max_funding': 350000,
            'min_monthly_revenue': 18000,
            'max_nsf': 3,
            'max_positions': 3,
            'min_credit_score': 550,
            'max_negative_days': 5,
        },
    ]


def _score_applicant(applicant: dict, lender: dict) -> int:
    """Score an applicant against a default lender. Returns 0 (disqualified) or 1-100."""
    revenue = applicant.get('monthly_revenue', 0)
    nsf_count = applicant.get('nsf_count', 0)
    positions = applicant.get('existing_positions', applicant.get('position_count', 0))
    credit_score = applicant.get('credit_score', applicant.get('fico_score', 0))
    negative_days = applicant.get('negative_days', 0)

    if revenue < lender['min_monthly_revenue']:
        return 0
    if nsf_count > lender['max_nsf']:
        return 0
    if positions > lender['max_positions']:
        return 0
    if credit_score > 0 and credit_score < lender['min_credit_score']:
        return 0
    if negative_days > lender['max_negative_days']:
        return 0

    score = 50

    if lender['min_monthly_revenue'] > 0:
        rev_ratio = revenue / lender['min_monthly_revenue']
        if rev_ratio >= 2.0:
            score += 15
        elif rev_ratio >= 1.5:
            score += 10
        elif rev_ratio >= 1.2:
            score += 5

    if lender['max_nsf'] > 0:
        nsf_remaining = lender['max_nsf'] - nsf_count
        score += min(10, nsf_remaining * 3)

    if credit_score > 0 and lender['min_credit_score'] > 0:
        credit_diff = credit_score - lender['min_credit_score']
        if credit_diff >= 100:
            score += 10
        elif credit_diff >= 50:
            score += 5

    if negative_days == 0:
        score += 5
    if positions == 0:
        score += 5

    return max(0, min(100, score))


def find_matching_lenders(applicant_profile):
    """Backward-compatible wrapper. Uses default lender criteria when no CSV path provided."""
    import os
    csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'input_config', 'lender_template.csv')
    if not os.path.exists(csv_path):
        lenders = _get_default_lenders()
        eligible = []
        disqualified = []
        for lender in lenders:
            score = _score_applicant(applicant_profile, lender)
            entry = {
                'lender_name': lender['name'],
                'display_name': lender['name'],
                'match_score': score,
                'eligible': score > 0,
            }
            if score > 0:
                eligible.append(entry)
            else:
                disqualified.append(entry)
        eligible.sort(key=lambda x: x['match_score'], reverse=True)
        return {
            'matches': eligible,
            'disqualified': disqualified,
            'summary': {
                'eligible_count': len(eligible),
                'total_lenders_checked': len(lenders),
            }
        }
    return match_lenders(applicant_profile, csv_path)
