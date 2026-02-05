"""
Risk Engine - Identifies all risk factors in bank statement transactions.
NSFs, negative days, cash activity, gambling, red flags, expense categorization,
revenue velocity, and overall risk scoring.
"""

import re
from collections import defaultdict
from datetime import datetime
from typing import List, Dict


def analyze_risk(transactions: list, net_revenue: float, keywords: dict) -> dict:
    """
    Main entry point. Analyze all risk factors and return a comprehensive profile.
    """
    nsf = _count_nsf_events(transactions, keywords)
    neg = _analyze_negative_days(transactions)
    cash = _analyze_cash_deposits(transactions, keywords, net_revenue)
    gamble = _detect_gambling(transactions, keywords)
    flags = _detect_red_flags(transactions, keywords)
    expenses = _categorize_expenses(transactions, keywords)

    monthly_deposits = defaultdict(float)
    for txn in transactions:
        if txn.get("amount", 0) > 0:
            mk = txn.get("date", "")[:7]
            if mk:
                monthly_deposits[mk] += txn["amount"]

    velocity_data = _calculate_revenue_velocity(dict(monthly_deposits))

    score, tier = _calculate_risk_score(
        nsf_count=nsf["nsf_count"],
        negative_days=neg["negative_day_count"],
        consecutive_neg=neg["consecutive_negative_days"],
        cash_risk=cash["cash_risk_flag"],
        gambling_flag=gamble["gambling_flag"],
        high_flags=sum(1 for f in flags if f["severity"] == "HIGH"),
        medium_flags=sum(1 for f in flags if f["severity"] == "MEDIUM"),
        velocity_flag=velocity_data["velocity_flag"],
    )

    avg_daily_balance = _calc_avg_daily_balance(transactions)

    return {
        "nsf_count": nsf["nsf_count"],
        "nsf_total_fees": nsf["nsf_total_fees"],
        "nsf_by_month": nsf["nsf_by_month"],
        "negative_day_count": neg["negative_day_count"],
        "consecutive_negative_days": neg["consecutive_negative_days"],
        "max_negative_balance": neg["max_negative_balance"],
        "cash_deposit_total": cash["cash_deposit_total"],
        "cash_deposit_percent": cash["cash_deposit_percent"],
        "cash_risk_flag": cash["cash_risk_flag"],
        "gambling_total": gamble["gambling_total"],
        "gambling_flag": gamble["gambling_flag"],
        "gambling_transactions": gamble["gambling_transactions"],
        "red_flags": flags,
        "expenses_by_category": expenses,
        "revenue_velocity": velocity_data["revenue_velocity"],
        "revenue_acceleration": velocity_data["revenue_acceleration"],
        "velocity_flag": velocity_data["velocity_flag"],
        "risk_score": score,
        "risk_tier": tier,
        "avg_daily_balance": avg_daily_balance,
    }


# ── NSF / Overdraft Analysis ─────────────────────────────────────────

def _count_nsf_events(transactions: list, keywords: dict) -> dict:
    nsf_kws = [kw.upper() for kw in keywords.get("nsf_keywords", [])]
    nsf_patterns = [re.compile(r'\b' + re.escape(kw) + r'\b') for kw in nsf_kws]
    count = 0
    total_fees = 0.0
    by_month = defaultdict(int)

    for txn in transactions:
        desc = txn.get("description", "").upper()
        for pat in nsf_patterns:
            if pat.search(desc):
                count += 1
                fee = abs(txn.get("amount", 0))
                total_fees += fee
                mk = txn.get("date", "")[:7]
                if mk:
                    by_month[mk] += 1
                break

    return {
        "nsf_count": count,
        "nsf_total_fees": round(total_fees, 2),
        "nsf_by_month": dict(sorted(by_month.items())),
    }


# ── Negative Balance Analysis ────────────────────────────────────────

def _analyze_negative_days(transactions: list) -> dict:
    negative_dates = set()
    balances_by_date = {}

    for txn in transactions:
        bal = txn.get("running_balance")
        d = txn.get("date", "")
        if bal is not None and d:
            balances_by_date[d] = bal

    max_negative = 0.0
    for d, bal in balances_by_date.items():
        if bal < 0:
            negative_dates.add(d)
            if bal < max_negative:
                max_negative = bal

    sorted_dates = sorted(negative_dates)
    max_consecutive = 0
    current_streak = 0
    prev_date = None

    for ds in sorted_dates:
        try:
            dt = datetime.strptime(ds, "%Y-%m-%d")
        except ValueError:
            continue
        if prev_date and (dt - prev_date).days == 1:
            current_streak += 1
        else:
            current_streak = 1
        max_consecutive = max(max_consecutive, current_streak)
        prev_date = dt

    return {
        "negative_day_count": len(negative_dates),
        "consecutive_negative_days": max_consecutive,
        "max_negative_balance": round(max_negative, 2),
    }


# ── Cash Deposit Analysis ────────────────────────────────────────────

def _analyze_cash_deposits(transactions: list, keywords: dict, net_revenue: float) -> dict:
    cash_kws = [kw.upper() for kw in keywords.get("cash_deposit_keywords", [])]
    total = 0.0

    for txn in transactions:
        if txn.get("amount", 0) <= 0:
            continue
        desc = txn.get("description", "").upper()
        for kw in cash_kws:
            if kw in desc:
                total += txn["amount"]
                break

    pct = (total / net_revenue * 100) if net_revenue > 0 else 0.0

    return {
        "cash_deposit_total": round(total, 2),
        "cash_deposit_percent": round(pct, 2),
        "cash_risk_flag": pct > 20,
    }


# ── Gambling Detection ───────────────────────────────────────────────

def _detect_gambling(transactions: list, keywords: dict) -> dict:
    gamble_kws = [kw.upper() for kw in keywords.get("gambling_keywords", [])]
    gamble_patterns = [re.compile(r'\b' + re.escape(kw) + r'\b') for kw in gamble_kws]
    total = 0.0
    found = []

    for txn in transactions:
        desc = txn.get("description", "").upper()
        for pat in gamble_patterns:
            if pat.search(desc):
                total += abs(txn.get("amount", 0))
                found.append({
                    "date": txn.get("date", ""),
                    "description": txn.get("description", ""),
                    "amount": txn.get("amount", 0),
                })
                break

    return {
        "gambling_total": round(total, 2),
        "gambling_flag": len(found) > 0,
        "gambling_transactions": found,
    }


# ── Red Flag Detection ───────────────────────────────────────────────

def _detect_red_flags(transactions: list, keywords: dict) -> list:
    red_kws = [kw.upper() for kw in keywords.get("red_flag_keywords", [])]
    red_patterns = [(kw, re.compile(r'\b' + re.escape(kw) + r'\b')) for kw in red_kws]
    severity_map = {
        "GARNISHMENT": "HIGH", "WAGE GARNISH": "HIGH", "COURT ORDER": "HIGH",
        "TAX LEVY": "HIGH", "IRS LEVY": "HIGH", "STATE LEVY": "HIGH",
        "TAX LIEN": "HIGH", "JUDGMENT": "HIGH", "LEGAL JUDGMENT": "HIGH",
        "BANKRUPTCY": "HIGH", "BK TRUSTEE": "HIGH",
    }
    flags = []

    for txn in transactions:
        desc = txn.get("description", "").upper()
        for kw, pat in red_patterns:
            if pat.search(desc):
                severity = severity_map.get(kw, "MEDIUM")
                category = _categorize_red_flag(kw)
                flags.append({
                    "severity": severity,
                    "category": category,
                    "description": f"{kw} detected: {txn.get('description', '')}",
                    "date": txn.get("date", ""),
                    "amount": txn.get("amount", 0),
                })
                break

    return flags


def _categorize_red_flag(keyword: str) -> str:
    kw = keyword.upper()
    if any(w in kw for w in ["GARNISH", "COURT ORDER", "JUDGMENT"]):
        return "Legal"
    if any(w in kw for w in ["TAX", "IRS", "LEVY", "LIEN"]):
        return "Tax"
    if any(w in kw for w in ["BANKRUPT", "BK TRUSTEE"]):
        return "Bankruptcy"
    return "Other"


# ── Expense Categorization ───────────────────────────────────────────

def _categorize_expenses(transactions: list, keywords: dict) -> dict:
    categories = keywords.get("expense_categories", {})
    totals = defaultdict(float)
    other_total = 0.0

    for txn in transactions:
        if txn.get("amount", 0) >= 0:
            continue
        desc = txn.get("description", "").upper()
        amt = abs(txn["amount"])
        matched = False

        for cat_name, cat_keywords in categories.items():
            for kw in cat_keywords:
                if kw.upper() in desc:
                    totals[cat_name] += amt
                    matched = True
                    break
            if matched:
                break

        if not matched:
            other_total += amt

    result = {k: round(v, 2) for k, v in totals.items()}
    result["other"] = round(other_total, 2)
    return result


# ── Revenue Velocity ─────────────────────────────────────────────────

def _calculate_revenue_velocity(monthly_deposits: dict) -> dict:
    sorted_months = sorted(monthly_deposits.keys())

    if len(sorted_months) < 2:
        return {
            "revenue_velocity": 0.0,
            "revenue_acceleration": 0.0,
            "velocity_flag": "stable",
        }

    mom_changes = []
    for i in range(1, len(sorted_months)):
        prev = monthly_deposits[sorted_months[i - 1]]
        curr = monthly_deposits[sorted_months[i]]
        if prev > 0:
            change = ((curr - prev) / prev) * 100
            mom_changes.append(change)

    if not mom_changes:
        return {
            "revenue_velocity": 0.0,
            "revenue_acceleration": 0.0,
            "velocity_flag": "stable",
        }

    avg_velocity = sum(mom_changes) / len(mom_changes)

    acceleration = 0.0
    if len(mom_changes) >= 2:
        accel_changes = []
        for i in range(1, len(mom_changes)):
            accel_changes.append(mom_changes[i] - mom_changes[i - 1])
        acceleration = sum(accel_changes) / len(accel_changes) if accel_changes else 0.0

    if avg_velocity < -5 and acceleration < -2:
        flag = "accelerating_decline"
    elif avg_velocity < -5:
        flag = "declining"
    elif avg_velocity > 5:
        flag = "growth"
    else:
        flag = "stable"

    return {
        "revenue_velocity": round(avg_velocity, 2),
        "revenue_acceleration": round(acceleration, 2),
        "velocity_flag": flag,
    }


# ── Risk Scoring ─────────────────────────────────────────────────────

def _calculate_risk_score(
    nsf_count: int,
    negative_days: int,
    consecutive_neg: int,
    cash_risk: bool,
    gambling_flag: bool,
    high_flags: int,
    medium_flags: int,
    velocity_flag: str,
) -> tuple:
    """
    Start at 100, deduct points.
    Returns (score, tier).
    """
    score = 100

    nsf_deduction = min(nsf_count * 5, 25)
    score -= nsf_deduction

    neg_deduction = min(negative_days * 2, 20)
    score -= neg_deduction

    if consecutive_neg >= 3:
        score -= 5

    if cash_risk:
        score -= 10

    if gambling_flag:
        score -= 15

    score -= min(high_flags * 10, 30)
    score -= min(medium_flags * 5, 15)

    if velocity_flag == "accelerating_decline":
        score -= 15
    elif velocity_flag == "declining":
        score -= 10

    score = max(0, min(100, score))

    if score >= 80:
        tier = "A"
    elif score >= 60:
        tier = "B"
    elif score >= 40:
        tier = "C"
    else:
        tier = "D"

    return score, tier


# ── Helper ───────────────────────────────────────────────────────────

def _calc_avg_daily_balance(transactions: list) -> float:
    balances = [t["running_balance"] for t in transactions if t.get("running_balance") is not None]
    if not balances:
        return 0.0
    return round(sum(balances) / len(balances), 2)
