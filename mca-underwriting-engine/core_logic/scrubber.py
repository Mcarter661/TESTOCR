"""
Scrubber - Separates gross deposits from true net revenue.
Excludes internal transfers, loan proceeds, owner deposits, refunds, etc.
"""

import re
from collections import defaultdict
from typing import List, Dict, Tuple


def scrub_statement(transactions: list, keywords: dict) -> dict:
    """
    Main entry point. Classify every deposit as revenue or excluded.
    Returns monthly breakdowns of gross vs net revenue.
    """
    excluded = []
    clean = []

    for txn in transactions:
        amount = txn.get("amount", 0)
        if amount <= 0:
            clean.append(txn)
            continue

        exclusion_reason = _classify_deposit(txn, keywords)
        if exclusion_reason:
            excluded.append({
                "date": txn.get("date", ""),
                "description": txn.get("description", ""),
                "amount": amount,
                "reason": exclusion_reason,
            })
        else:
            clean.append(txn)

    monthly_gross = defaultdict(float)
    monthly_net = defaultdict(float)
    monthly_deposit_count = defaultdict(int)

    for txn in transactions:
        amount = txn.get("amount", 0)
        if amount <= 0:
            continue
        month_key = _month_key(txn.get("date", ""))
        if not month_key:
            continue
        monthly_gross[month_key] += amount
        monthly_deposit_count[month_key] += 1

    for txn in clean:
        amount = txn.get("amount", 0)
        if amount <= 0:
            continue
        month_key = _month_key(txn.get("date", ""))
        if not month_key:
            continue
        monthly_net[month_key] += amount

    total_gross = sum(monthly_gross.values())
    total_net = sum(monthly_net.values())
    num_months = max(len(monthly_net), 1)
    avg_monthly_net = total_net / num_months

    mg = {k: round(v, 2) for k, v in sorted(monthly_gross.items())}
    mn = {k: round(v, 2) for k, v in sorted(monthly_net.items())}
    mc = dict(sorted(monthly_deposit_count.items()))

    return {
        "monthly_gross": mg,
        "monthly_net": mn,
        "monthly_deposit_count": mc,
        "total_gross": round(total_gross, 2),
        "total_net": round(total_net, 2),
        "avg_monthly_net": round(avg_monthly_net, 2),
        "excluded_transactions": excluded,
        "clean_transactions": clean,
    }


def detect_inter_account_transfers(statements: list) -> list:
    """
    Find matching deposit/withdrawal amounts within +/- 1 day across statements.
    Each element in `statements` is a list of transactions from a different account.
    Returns list of (deposit_txn, withdrawal_txn) pairs that are inter-account transfers.
    """
    if len(statements) < 2:
        return []

    transfers = []

    for i in range(len(statements)):
        deposits_i = [t for t in statements[i] if t.get("amount", 0) > 0]
        for j in range(len(statements)):
            if i == j:
                continue
            withdrawals_j = [t for t in statements[j] if t.get("amount", 0) < 0]

            for dep in deposits_i:
                dep_date = dep.get("date", "")
                dep_amt = abs(dep["amount"])
                for wth in withdrawals_j:
                    wth_date = wth.get("date", "")
                    wth_amt = abs(wth["amount"])
                    if abs(dep_amt - wth_amt) < 0.01 and _dates_within_days(dep_date, wth_date, 1):
                        transfers.append({
                            "deposit_account": i,
                            "withdrawal_account": j,
                            "amount": dep_amt,
                            "deposit_date": dep_date,
                            "withdrawal_date": wth_date,
                            "deposit_description": dep.get("description", ""),
                            "withdrawal_description": wth.get("description", ""),
                        })

    return transfers


def analyze_concentration(clean_transactions: list, total_net: float) -> dict:
    """
    Analyze deposit source concentration.
    Returns top depositors and whether concentration risk is triggered.
    """
    if total_net <= 0:
        return {
            "top_depositors": [],
            "concentration_risk": False,
        }

    source_totals = defaultdict(float)
    for txn in clean_transactions:
        if txn.get("amount", 0) <= 0:
            continue
        desc = _normalize_description(txn.get("description", "UNKNOWN"))
        source_totals[desc] += txn["amount"]

    sorted_sources = sorted(source_totals.items(), key=lambda x: x[1], reverse=True)
    top_depositors = []
    for name, amount in sorted_sources[:10]:
        pct = (amount / total_net) * 100 if total_net > 0 else 0
        top_depositors.append({
            "name": name,
            "amount": round(amount, 2),
            "percent": round(pct, 2),
        })

    concentration_risk = False
    if top_depositors and top_depositors[0]["percent"] > 30:
        concentration_risk = True

    return {
        "top_depositors": top_depositors,
        "concentration_risk": concentration_risk,
    }


# ── Private helpers ───────────────────────────────────────────────────

def _classify_deposit(txn: dict, keywords: dict) -> str:
    """Check if a deposit should be excluded from revenue. Returns reason or empty string."""
    desc = txn.get("description", "").upper()
    amount = txn.get("amount", 0)

    for kw in keywords.get("internal_transfer_keywords", []):
        if kw.upper() in desc:
            return f"Internal transfer ({kw})"

    for kw in keywords.get("loan_proceed_keywords", []):
        if kw.upper() in desc:
            return f"Loan/MCA proceeds ({kw})"

    all_lender_tiers = [
        "mca_lenders_tier1_major", "mca_lenders_tier2_growing",
        "mca_lenders_tier3_fintech", "mca_lenders_tier4_regional",
    ]
    for tier_key in all_lender_tiers:
        tier = keywords.get(tier_key, {})
        for lender_name, aliases in tier.items():
            for alias in aliases:
                if alias.upper() in desc:
                    if amount >= 5000:
                        return f"Suspected MCA funding deposit from {lender_name}"
                    break

    if amount >= 10000:
        round_check = amount % 1000
        if round_check == 0:
            generic_kws = keywords.get("generic_mca_keywords", [])
            for kw in generic_kws:
                if kw.upper() in desc:
                    return f"Large round-sum suspected loan deposit ({kw})"

    for kw in keywords.get("owner_deposit_keywords", []):
        if kw.upper() in desc:
            return f"Owner/shareholder deposit ({kw})"

    for kw in keywords.get("exclude_from_revenue", []):
        if kw.upper() in desc:
            return f"Non-revenue item ({kw})"

    return ""


def _month_key(date_str: str) -> str:
    """Convert YYYY-MM-DD to YYYY-MM key."""
    if not date_str or len(date_str) < 7:
        return ""
    return date_str[:7]


def _dates_within_days(date1: str, date2: str, max_days: int) -> bool:
    """Check if two YYYY-MM-DD date strings are within max_days of each other."""
    from datetime import datetime
    try:
        d1 = datetime.strptime(date1, "%Y-%m-%d")
        d2 = datetime.strptime(date2, "%Y-%m-%d")
        return abs((d1 - d2).days) <= max_days
    except (ValueError, TypeError):
        return False


def _normalize_description(desc: str) -> str:
    """Normalize a transaction description for grouping deposit sources."""
    desc = desc.upper().strip()
    desc = re.sub(r'\d{4,}', 'XXXX', desc)
    desc = re.sub(r'\s+', ' ', desc)
    prefixes_to_strip = [
        "ACH CREDIT ", "ACH DEPOSIT ", "WIRE TRANSFER ", "DIRECT DEP ",
        "ONLINE PAYMENT ", "MOBILE DEPOSIT ",
    ]
    for prefix in prefixes_to_strip:
        if desc.startswith(prefix):
            desc = desc[len(prefix):]
            break
    return desc.strip()[:50]
