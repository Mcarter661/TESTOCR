"""
Position Detector - Detects existing MCA/loan positions and reverse-engineers terms.
Scans withdrawals for recurring patterns, matches against lender keywords,
and estimates funding amounts, remaining balances, and payoff dates.
"""

import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple


def detect_positions(transactions: list, keywords: dict, factor_rates: dict) -> dict:
    """
    Main entry point. Detect all existing MCA/loan positions.
    """
    withdrawals = [t for t in transactions if t.get("amount", 0) < 0]
    deposits = [t for t in transactions if t.get("amount", 0) > 0]

    recurring_groups = _find_recurring_debits(withdrawals)

    all_lender_kws = _build_lender_lookup(keywords)
    generic_kws = [kw.upper() for kw in keywords.get("generic_mca_keywords", [])]
    default_rate = factor_rates.get("default_rate", 1.35)
    lender_rates = factor_rates.get("lender_rates", {})

    positions = []
    position_num = 0

    for group in recurring_groups:
        payment_amount = abs(group["amount"])
        sample_descs = [t.get("description", "") for t in group["transactions"][:3]]

        lender_name = None
        confidence = "LOW"

        for desc in [t.get("description", "") for t in group["transactions"]]:
            name = _match_lender_name(desc, all_lender_kws)
            if name:
                lender_name = name
                confidence = "HIGH"
                break

        if not lender_name:
            for desc in [t.get("description", "") for t in group["transactions"]]:
                desc_upper = desc.upper()
                for kw in generic_kws:
                    if kw in desc_upper:
                        lender_name = f"Unknown MCA ({kw})"
                        confidence = "MEDIUM"
                        break
                if lender_name:
                    break

        if not lender_name:
            if group["frequency"] in ("daily", "weekly") and group["count"] >= 8:
                lender_name = "Unknown Recurring Debit"
                confidence = "LOW"
            else:
                continue

        position_num += 1
        freq = group["frequency"]
        dates = sorted([t.get("date", "") for t in group["transactions"]])
        first_date = dates[0] if dates else ""
        last_date = dates[-1] if dates else ""

        rate = lender_rates.get(lender_name, default_rate) if lender_name in lender_rates else default_rate

        funding_dep = _find_funding_deposit(
            deposits, first_date, lender_name, all_lender_kws, payment_amount
        )

        if funding_dep:
            est_original = funding_dep["amount"]
            funding_date = funding_dep["date"]
            funding_amount = funding_dep["amount"]
        else:
            if freq == "daily":
                est_original = (payment_amount * 160) / rate
            elif freq == "weekly":
                est_original = (payment_amount * 45) / rate
            else:
                est_original = (payment_amount * 12) / rate
            funding_date = None
            funding_amount = None

        est_total_payback = est_original * rate
        est_payments_made = group["count"] * payment_amount
        est_remaining = max(0, est_total_payback - est_payments_made)
        paid_in_pct = (est_payments_made / est_total_payback * 100) if est_total_payback > 0 else 0

        if freq == "daily":
            payments_per_month = 21.5
        elif freq == "weekly":
            payments_per_month = 4.33
        else:
            payments_per_month = 1.0

        total_payments_expected = est_total_payback / payment_amount if payment_amount > 0 else 0
        est_term_months = total_payments_expected / payments_per_month if payments_per_month > 0 else 0

        remaining_payments = est_remaining / payment_amount if payment_amount > 0 else 0
        if freq == "daily":
            remaining_biz_days = remaining_payments
            remaining_cal_days = remaining_biz_days * (7 / 5)
        elif freq == "weekly":
            remaining_cal_days = remaining_payments * 7
        else:
            remaining_cal_days = remaining_payments * 30

        try:
            last_dt = datetime.strptime(last_date, "%Y-%m-%d")
            payoff_dt = last_dt + timedelta(days=int(remaining_cal_days))
            est_payoff = payoff_dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            est_payoff = "Unknown"

        positions.append({
            "position_number": position_num,
            "lender_name": lender_name,
            "payment_amount": round(payment_amount, 2),
            "payment_frequency": freq,
            "payments_detected": group["count"],
            "first_payment_date": first_date,
            "last_payment_date": last_date,
            "funding_deposit_date": funding_date,
            "funding_deposit_amount": round(funding_amount, 2) if funding_amount else None,
            "estimated_factor_rate": rate,
            "estimated_original_funding": round(est_original, 2),
            "estimated_total_payback": round(est_total_payback, 2),
            "estimated_remaining_balance": round(est_remaining, 2),
            "estimated_term_months": round(est_term_months, 1),
            "estimated_payoff_date": est_payoff,
            "paid_in_percent": round(paid_in_pct, 1),
            "confidence": confidence,
            "sample_transactions": sample_descs,
        })

    total_daily = 0.0
    total_monthly = 0.0
    for p in positions:
        if p["payment_frequency"] == "daily":
            total_daily += p["payment_amount"]
            total_monthly += p["payment_amount"] * 21.5
        elif p["payment_frequency"] == "weekly":
            total_daily += p["payment_amount"] / 5
            total_monthly += p["payment_amount"] * 4.33
        else:
            total_monthly += p["payment_amount"]
            total_daily += p["payment_amount"] / 21.5

    days_since_last = 999
    for p in positions:
        fd = p.get("funding_deposit_date") or p.get("first_payment_date")
        if fd:
            try:
                fdt = datetime.strptime(fd, "%Y-%m-%d")
                delta = (datetime.now() - fdt).days
                days_since_last = min(days_since_last, delta)
            except ValueError:
                pass

    unique_lenders = list(set(
        p["lender_name"] for p in positions
        if not p["lender_name"].startswith("Unknown")
    ))

    return {
        "positions": positions,
        "total_positions": len(positions),
        "total_daily_payment": round(total_daily, 2),
        "total_monthly_payment": round(total_monthly, 2),
        "estimated_total_remaining": round(sum(p["estimated_remaining_balance"] for p in positions), 2),
        "days_since_last_funding": days_since_last if days_since_last < 999 else 0,
        "unique_lenders": unique_lenders,
    }


# ── Private helpers ───────────────────────────────────────────────────

def _find_recurring_debits(withdrawals: list) -> list:
    """
    Cluster withdrawals by similar amount (within $1 tolerance).
    Return groups that appear 4+ times and have regular spacing.
    """
    if not withdrawals:
        return []

    amount_groups = defaultdict(list)
    for txn in withdrawals:
        amt = abs(txn.get("amount", 0))
        rounded = round(amt, 0)
        amount_groups[rounded].append(txn)

    merged_groups = {}
    sorted_keys = sorted(amount_groups.keys())
    used = set()

    for key in sorted_keys:
        if key in used:
            continue
        group_txns = list(amount_groups[key])
        for other_key in sorted_keys:
            if other_key != key and other_key not in used and abs(other_key - key) <= 1:
                group_txns.extend(amount_groups[other_key])
                used.add(other_key)
        used.add(key)
        if len(group_txns) >= 4:
            avg_amt = sum(abs(t.get("amount", 0)) for t in group_txns) / len(group_txns)
            merged_groups[round(avg_amt, 2)] = group_txns

    results = []
    for avg_amt, txns in merged_groups.items():
        txns_sorted = sorted(txns, key=lambda t: t.get("date", ""))
        freq = _detect_frequency(txns_sorted)
        if freq:
            results.append({
                "amount": avg_amt,
                "count": len(txns_sorted),
                "frequency": freq,
                "transactions": txns_sorted,
            })

    return results


def _detect_frequency(txns: list) -> Optional[str]:
    """Detect payment frequency from transaction dates."""
    dates = []
    for t in txns:
        d = t.get("date", "")
        try:
            dates.append(datetime.strptime(d, "%Y-%m-%d"))
        except ValueError:
            continue

    if len(dates) < 4:
        return None

    dates.sort()
    gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    gaps = [g for g in gaps if g > 0]

    if not gaps:
        return None

    avg_gap = sum(gaps) / len(gaps)

    if avg_gap <= 2:
        return "daily"
    elif 5 <= avg_gap <= 9:
        return "weekly"
    elif 12 <= avg_gap <= 18:
        return "biweekly"
    elif 25 <= avg_gap <= 35:
        return "monthly"
    elif avg_gap <= 4:
        return "daily"
    else:
        return None


def _build_lender_lookup(keywords: dict) -> dict:
    """Build a flat lookup: alias_upper -> canonical_name."""
    lookup = {}
    tiers = [
        "mca_lenders_tier1_major", "mca_lenders_tier2_growing",
        "mca_lenders_tier3_fintech", "mca_lenders_tier4_regional",
    ]
    for tier_key in tiers:
        tier = keywords.get(tier_key, {})
        for lender_name, aliases in tier.items():
            for alias in aliases:
                lookup[alias.upper()] = lender_name
    return lookup


def _match_lender_name(description: str, lender_lookup: dict) -> Optional[str]:
    """Match a transaction description against the lender keyword lookup."""
    desc_upper = description.upper()
    for alias, name in sorted(lender_lookup.items(), key=lambda x: -len(x[0])):
        if alias in desc_upper:
            return name
    return None


def _find_funding_deposit(
    deposits: list,
    first_payment_date: str,
    lender_name: str,
    lender_lookup: dict,
    payment_amount: float,
) -> Optional[dict]:
    """
    Look for a large deposit ($5K+) 1-7 days before the first payment date
    that might be the original MCA funding.
    """
    if not first_payment_date:
        return None

    try:
        first_dt = datetime.strptime(first_payment_date, "%Y-%m-%d")
    except ValueError:
        return None

    window_start = first_dt - timedelta(days=7)
    window_end = first_dt - timedelta(days=0)

    min_funding = max(5000, payment_amount * 10)

    candidates = []
    for dep in deposits:
        amt = dep.get("amount", 0)
        if amt < min_funding:
            continue
        d = dep.get("date", "")
        try:
            dep_dt = datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        if window_start <= dep_dt <= window_end:
            desc_upper = dep.get("description", "").upper()
            from_lender = False
            if lender_name and not lender_name.startswith("Unknown"):
                for alias, name in lender_lookup.items():
                    if name == lender_name and alias in desc_upper:
                        from_lender = True
                        break

            candidates.append({
                "date": d,
                "amount": amt,
                "description": dep.get("description", ""),
                "from_lender": from_lender,
            })

    if not candidates:
        return None

    lender_matches = [c for c in candidates if c["from_lender"]]
    if lender_matches:
        return max(lender_matches, key=lambda c: c["amount"])

    return max(candidates, key=lambda c: c["amount"])
