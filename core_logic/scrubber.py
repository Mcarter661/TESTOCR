"""
Scrubber Module
Cleans transaction data, identifies transfers, calculates revenue metrics,
and performs concentration analysis.

Supports two modes:
- Inline pattern mode (backward compatible): Uses regex patterns for classification
- Keyword mode: Uses config/keywords.json for keyword-based classification
"""

import pandas as pd
import re
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from collections import defaultdict


TRANSFER_PATTERNS = [
    r'transfer\s*(from|to)',
    r'xfer\s*(from|to)?',
    r'online\s*transfer',
    r'internal\s*transfer',
    r'move\s*money',
    r'zelle\s*(from|to)',
    r'venmo\s*(from|to)',
    r'paypal\s*(from|to)',
    r'cash\s*app',
    r'wire\s*(in|out)',
    r'ach\s*transfer',
]

LOAN_DEPOSIT_PATTERNS = [
    r'loan\s*(?:deposit|funding|proceeds)',
    r'sba\s*(?:loan|deposit)',
    r'ppp\s*(?:loan|deposit)',
    r'eidl\s*(?:loan|deposit)',
    r'business\s*loan',
    r'credit\s*line\s*advance',
    r'line\s*of\s*credit',
    r'merchant\s*cash',
    r'mca\s*funding',
    r'working\s*capital',
]

OWNER_DRAW_PATTERNS = [
    r'owner\s*(draw|withdrawal)',
    r'member\s*distribution',
    r'shareholder\s*dist',
    r'dividend',
    r'personal\s*transfer',
]

CATEGORY_PATTERNS = {
    'payroll': [r'payroll', r'adp', r'paychex', r'gusto', r'employee', r'wages', r'salary'],
    'rent': [r'rent', r'lease', r'landlord', r'property\s*mgmt'],
    'utilities': [r'electric', r'gas\s*bill', r'water\s*bill', r'utility', r'power\s*company', r'pge', r'edison'],
    'insurance': [r'insurance', r'geico', r'progressive', r'state\s*farm', r'allstate'],
    'supplies': [r'office\s*depot', r'staples', r'amazon', r'supplies'],
    'equipment': [r'equipment', r'machinery', r'tools'],
    'marketing': [r'google\s*ads', r'facebook\s*ads', r'marketing', r'advertising', r'meta'],
    'professional': [r'attorney', r'lawyer', r'accountant', r'cpa', r'legal', r'consulting'],
    'taxes': [r'irs', r'tax\s*payment', r'federal\s*tax', r'state\s*tax', r'eftps'],
    'credit_card': [r'credit\s*card\s*payment', r'visa', r'mastercard', r'amex', r'discover'],
    'loan_payment': [r'loan\s*payment', r'note\s*payment', r'sba\s*payment'],
    'merchant_services': [r'square', r'stripe', r'clover', r'toast', r'merchant\s*service'],
    'bank_fees': [r'service\s*charge', r'monthly\s*fee', r'overdraft', r'nsf\s*fee', r'wire\s*fee'],
}


def load_transfer_patterns() -> List[str]:
    """
    Load patterns that identify internal transfers.
    """
    return TRANSFER_PATTERNS


def matches_patterns(text: str, patterns: List[str]) -> bool:
    """
    Check if text matches any of the given patterns.
    """
    text_lower = text.lower()
    for pattern in patterns:
        if re.search(pattern, text_lower):
            return True
    return False


def identify_internal_transfers(transactions: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    Separate internal transfers from actual revenue transactions.
    """
    revenue_transactions = []
    transfer_transactions = []
    
    for txn in transactions:
        description = txn.get('description', '').lower()
        
        is_transfer = matches_patterns(description, TRANSFER_PATTERNS)
        is_loan = matches_patterns(description, LOAN_DEPOSIT_PATTERNS)
        is_owner_draw = matches_patterns(description, OWNER_DRAW_PATTERNS)
        
        txn_copy = txn.copy()
        
        if is_transfer:
            txn_copy['transfer_type'] = 'internal_transfer'
            transfer_transactions.append(txn_copy)
        elif is_loan:
            txn_copy['transfer_type'] = 'loan_deposit'
            transfer_transactions.append(txn_copy)
        elif is_owner_draw:
            txn_copy['transfer_type'] = 'owner_draw'
            transfer_transactions.append(txn_copy)
        else:
            txn_copy['transfer_type'] = None
            revenue_transactions.append(txn_copy)
    
    return revenue_transactions, transfer_transactions


def identify_internal_transfers_keyword(transactions: List[Dict], keywords: Dict) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Separate internal transfers from actual revenue transactions using keyword-based classification.
    Returns (revenue_transactions, transfer_transactions, excluded_deposits_with_reasons).
    """
    revenue_transactions = []
    transfer_transactions = []
    excluded_deposits = []

    for txn in transactions:
        txn_copy = txn.copy()
        credit = txn_copy.get('credit', 0)

        if credit > 0:
            exclusion_reason = _classify_deposit(txn_copy, keywords)
            if exclusion_reason:
                txn_copy['transfer_type'] = exclusion_reason.split('(')[0].strip().lower().replace(' ', '_')
                transfer_transactions.append(txn_copy)
                excluded_deposits.append({
                    'date': txn_copy.get('date', ''),
                    'description': txn_copy.get('description', ''),
                    'amount': credit,
                    'reason': exclusion_reason,
                })
                continue

        description = txn_copy.get('description', '').lower()
        is_transfer = matches_patterns(description, TRANSFER_PATTERNS)
        is_loan = matches_patterns(description, LOAN_DEPOSIT_PATTERNS)
        is_owner_draw = matches_patterns(description, OWNER_DRAW_PATTERNS)

        if is_transfer:
            txn_copy['transfer_type'] = 'internal_transfer'
            transfer_transactions.append(txn_copy)
        elif is_loan:
            txn_copy['transfer_type'] = 'loan_deposit'
            transfer_transactions.append(txn_copy)
        elif is_owner_draw:
            txn_copy['transfer_type'] = 'owner_draw'
            transfer_transactions.append(txn_copy)
        else:
            txn_copy['transfer_type'] = None
            revenue_transactions.append(txn_copy)

    return revenue_transactions, transfer_transactions, excluded_deposits


def categorize_transaction(description: str) -> str:
    """
    Categorize a transaction based on its description.
    """
    description_lower = description.lower()
    
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, description_lower):
                return category
    
    return 'other'


def rename_descriptions(transactions: List[Dict], mapping: Dict[str, str] = None) -> List[Dict]:
    """
    Standardize transaction descriptions and add categories.
    """
    result = []
    
    for txn in transactions:
        txn_copy = txn.copy()
        original_desc = txn.get('description', '')
        
        txn_copy['original_description'] = original_desc
        txn_copy['category'] = categorize_transaction(original_desc)
        
        cleaned = re.sub(r'\s+', ' ', original_desc)
        cleaned = re.sub(r'[#*]+\d+', '', cleaned)
        cleaned = cleaned.strip()[:50]
        txn_copy['cleaned_description'] = cleaned
        
        if mapping:
            for pattern, replacement in mapping.items():
                if re.search(pattern, original_desc, re.IGNORECASE):
                    txn_copy['cleaned_description'] = replacement
                    break
        
        result.append(txn_copy)
    
    return result


def calculate_daily_balances(transactions: List[Dict], opening_balance: float = 0) -> pd.DataFrame:
    """
    Calculate daily ending balances from transactions.
    """
    if not transactions:
        return pd.DataFrame(columns=['date', 'ending_balance', 'daily_deposits', 'daily_withdrawals'])
    
    df = pd.DataFrame(transactions)
    
    if 'date' not in df.columns:
        return pd.DataFrame(columns=['date', 'ending_balance', 'daily_deposits', 'daily_withdrawals'])
    
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    
    if df.empty:
        return pd.DataFrame(columns=['date', 'ending_balance', 'daily_deposits', 'daily_withdrawals'])
    
    daily = df.groupby('date').agg({
        'credit': 'sum',
        'debit': 'sum'
    }).reset_index()
    
    daily.columns = ['date', 'daily_deposits', 'daily_withdrawals']
    
    date_range = pd.date_range(start=daily['date'].min(), end=daily['date'].max(), freq='D')
    full_range = pd.DataFrame({'date': date_range})
    
    daily = full_range.merge(daily, on='date', how='left').fillna(0)
    
    daily['net_change'] = daily['daily_deposits'] - daily['daily_withdrawals']
    daily['ending_balance'] = opening_balance + daily['net_change'].cumsum()
    
    return daily


def calculate_net_revenue(transactions: List[Dict], exclude_transfers: bool = True) -> Dict:
    """
    Calculate net revenue metrics from transactions.
    """
    if exclude_transfers:
        revenue_txns, _ = identify_internal_transfers(transactions)
    else:
        revenue_txns = transactions
    
    deposits = sum(t.get('credit', 0) for t in revenue_txns)
    withdrawals = sum(t.get('debit', 0) for t in revenue_txns)
    
    deposit_count = len([t for t in revenue_txns if t.get('credit', 0) > 0])
    
    dates = [t.get('date') for t in revenue_txns if t.get('date')]
    if dates:
        try:
            date_objs = [datetime.strptime(d, '%Y-%m-%d') if isinstance(d, str) else d for d in dates]
            date_range = (max(date_objs) - min(date_objs)).days + 1
            months = max(date_range / 30, 1)
        except:
            months = 1
    else:
        months = 1
    
    return {
        'gross_deposits': deposits,
        'gross_withdrawals': withdrawals,
        'net_revenue': deposits - withdrawals,
        'monthly_average_deposits': deposits / months,
        'monthly_average_withdrawals': withdrawals / months,
        'average_deposit_size': deposits / deposit_count if deposit_count > 0 else 0,
        'deposit_count': deposit_count,
        'statement_months': round(months, 1),
    }


def calculate_monthly_breakdown(transactions: List[Dict]) -> pd.DataFrame:
    """
    Break down transactions by month for trending analysis.
    """
    if not transactions:
        return pd.DataFrame()
    
    df = pd.DataFrame(transactions)
    
    if 'date' not in df.columns:
        return pd.DataFrame()
    
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    
    if df.empty:
        return pd.DataFrame()
    
    df['month'] = df['date'].dt.to_period('M')
    
    monthly = df.groupby('month').agg({
        'credit': 'sum',
        'debit': 'sum',
    }).reset_index()
    
    monthly.columns = ['month', 'deposits', 'withdrawals']
    monthly['net'] = monthly['deposits'] - monthly['withdrawals']
    monthly['month'] = monthly['month'].astype(str)
    
    if len(monthly) > 1:
        monthly['deposit_change'] = monthly['deposits'].pct_change() * 100
        monthly['deposit_change'] = monthly['deposit_change'].fillna(0)
    else:
        monthly['deposit_change'] = 0
    
    return monthly


def analyze_deposit_concentration(transactions: List[Dict], top_n: int = 5) -> Dict:
    """
    Analyze deposit concentration by source.
    """
    deposits = [t for t in transactions if t.get('credit', 0) > 0]
    
    if not deposits:
        return {
            'top_depositors': [],
            'concentration_ratio': 0,
            'unique_sources': 0,
        }
    
    source_totals = defaultdict(float)
    for txn in deposits:
        desc = txn.get('cleaned_description', txn.get('description', 'Unknown'))[:30]
        source_totals[desc] += txn.get('credit', 0)
    
    sorted_sources = sorted(source_totals.items(), key=lambda x: x[1], reverse=True)
    total_deposits = sum(source_totals.values())
    
    top_depositors = []
    for source, amount in sorted_sources[:top_n]:
        top_depositors.append({
            'source': source,
            'amount': amount,
            'percentage': (amount / total_deposits * 100) if total_deposits > 0 else 0
        })
    
    top_concentration = sum(d['percentage'] for d in top_depositors[:3])
    
    return {
        'top_depositors': top_depositors,
        'concentration_ratio': top_concentration,
        'unique_sources': len(source_totals),
        'total_deposits': total_deposits,
    }


def detect_seasonality(monthly_data: pd.DataFrame) -> Dict:
    """
    Detect seasonal patterns in revenue.
    """
    if monthly_data.empty or len(monthly_data) < 3:
        return {
            'is_seasonal': False,
            'trend': 'insufficient_data',
            'volatility': 0,
        }
    
    deposits = monthly_data['deposits'].values
    mean_deposit = deposits.mean()
    std_deposit = deposits.std()
    
    volatility = (std_deposit / mean_deposit * 100) if mean_deposit > 0 else 0
    
    if len(deposits) >= 3:
        first_half = deposits[:len(deposits)//2].mean()
        second_half = deposits[len(deposits)//2:].mean()
        
        if second_half > first_half * 1.1:
            trend = 'increasing'
        elif second_half < first_half * 0.9:
            trend = 'decreasing'
        else:
            trend = 'stable'
    else:
        trend = 'insufficient_data'
    
    return {
        'is_seasonal': volatility > 30,
        'trend': trend,
        'volatility': round(volatility, 2),
        'average_monthly': round(mean_deposit, 2),
        'std_deviation': round(std_deposit, 2),
    }


def fix_debit_credit_from_description(transactions: List[Dict]) -> List[Dict]:
    """
    Fix debit/credit classification based on transaction description.
    Some parsers incorrectly classify debits as credits if the description contains DEBIT keywords.
    """
    debit_keywords = ['ach debit', 'ach corp debit', 'debit card', 'withdrawal', 'wire out', 'outgoing wire']
    credit_keywords = ['ach credit', 'deposit', 'wire in', 'incoming wire', 'rtp credit']
    
    fixed = []
    for txn in transactions:
        txn = txn.copy()
        desc = txn.get('description', '').lower()
        debit = txn.get('debit', 0)
        credit = txn.get('credit', 0)
        
        if credit > 0 and debit == 0 and any(kw in desc for kw in debit_keywords):
            if not any(kw in desc for kw in credit_keywords):
                txn['debit'] = credit
                txn['credit'] = 0
        
        if debit > 0 and credit == 0 and any(kw in desc for kw in credit_keywords):
            if not any(kw in desc for kw in debit_keywords):
                txn['credit'] = debit
                txn['debit'] = 0
        
        fixed.append(txn)
    
    return fixed


# ── Engine functions: keyword-based classification & analysis ─────────


def scrub_statement(transactions: list, keywords: dict) -> dict:
    """
    Keyword-based deposit classification entry point.
    Classify every deposit as revenue or excluded using keywords dict.
    Returns monthly breakdowns of gross vs net revenue.
    """
    excluded = []
    clean = []

    for txn in transactions:
        amount = txn.get("amount", txn.get("credit", 0))
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
        amount = txn.get("amount", txn.get("credit", 0))
        if amount <= 0:
            continue
        month_key = _month_key(txn.get("date", ""))
        if not month_key:
            continue
        monthly_gross[month_key] += amount
        monthly_deposit_count[month_key] += 1

    for txn in clean:
        amount = txn.get("amount", txn.get("credit", 0))
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
    Apex Test: Find matching deposit/withdrawal amounts within +/- 1 day across statements.
    Each element in `statements` is a list of transactions from a different account.
    Returns list of inter-account transfer matches.
    """
    if len(statements) < 2:
        return []

    transfers = []

    for i in range(len(statements)):
        deposits_i = [t for t in statements[i] if t.get("amount", t.get("credit", 0)) > 0]
        for j in range(len(statements)):
            if i == j:
                continue
            withdrawals_j = [t for t in statements[j] if t.get("amount", t.get("debit", 0)) < 0 or t.get("debit", 0) > 0]

            for dep in deposits_i:
                dep_date = dep.get("date", "")
                dep_amt = abs(dep.get("amount", dep.get("credit", 0)))
                for wth in withdrawals_j:
                    wth_date = wth.get("date", "")
                    wth_amt = abs(wth.get("amount", wth.get("debit", 0)))
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
    Analyze deposit source concentration risk.
    Returns top depositors and whether concentration risk is triggered (>30% from single source).
    """
    if total_net <= 0:
        return {
            "top_depositors": [],
            "concentration_risk": False,
        }

    source_totals = defaultdict(float)
    for txn in clean_transactions:
        amount = txn.get("amount", txn.get("credit", 0))
        if amount <= 0:
            continue
        desc = _normalize_description(txn.get("description", "UNKNOWN"))
        source_totals[desc] += amount

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
    """Check if a deposit should be excluded from revenue using keywords. Returns reason or empty string."""
    desc = txn.get("description", "").upper()
    amount = txn.get("amount", txn.get("credit", 0))

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
    if not date_str or len(str(date_str)) < 7:
        return ""
    return str(date_str)[:7]


def _dates_within_days(date1: str, date2: str, max_days: int) -> bool:
    """Check if two YYYY-MM-DD date strings are within max_days of each other."""
    try:
        d1 = datetime.strptime(str(date1), "%Y-%m-%d")
        d2 = datetime.strptime(str(date2), "%Y-%m-%d")
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


# ── Main entry point ──────────────────────────────────────────────────


def scrub_transactions(transactions: List[Dict], keywords: Optional[Dict] = None) -> Dict:
    """
    Main function to clean and analyze transactions.
    Returns scrubbed data with revenue metrics and categorized transactions.

    Args:
        transactions: List of transaction dicts with date, description, credit, debit fields.
        keywords: Optional keywords dict from config/keywords.json. When provided,
                  uses keyword-based classification for better accuracy. When None,
                  falls back to inline regex patterns (backward compatible).
    """
    if not transactions:
        return {
            'cleaned_transactions': [],
            'transactions': [],
            'transfers': [],
            'revenue_metrics': calculate_net_revenue([]),
            'monthly_data': pd.DataFrame(),
            'daily_balances': pd.DataFrame(),
            'concentration': {'top_depositors': [], 'concentration_ratio': 0, 'unique_sources': 0},
            'seasonality': {'is_seasonal': False, 'trend': 'insufficient_data', 'volatility': 0},
            'concentration_analysis': {'top_depositors': [], 'concentration_risk': False},
            'excluded_transactions': [],
        }
    
    fixed_transactions = fix_debit_credit_from_description(transactions)

    excluded_deposits = []

    if keywords:
        revenue_txns, transfers, excluded_deposits = identify_internal_transfers_keyword(fixed_transactions, keywords)
    else:
        revenue_txns, transfers = identify_internal_transfers(fixed_transactions)
    
    categorized = rename_descriptions(revenue_txns)
    
    revenue_metrics = calculate_net_revenue(transactions, exclude_transfers=True)
    
    monthly_data = calculate_monthly_breakdown(categorized)
    
    daily_balances = calculate_daily_balances(categorized)
    
    concentration = analyze_deposit_concentration(categorized)
    
    seasonality = detect_seasonality(monthly_data)

    total_net_deposits = sum(t.get('credit', 0) for t in categorized)
    concentration_analysis = analyze_concentration(categorized, total_net_deposits)

    if keywords:
        statement_results = scrub_statement(fixed_transactions, keywords)
        if not excluded_deposits:
            excluded_deposits = statement_results.get('excluded_transactions', [])
    
    return {
        'cleaned_transactions': categorized,
        'transactions': categorized,
        'transfers': transfers,
        'revenue_metrics': revenue_metrics,
        'monthly_data': monthly_data,
        'daily_balances': daily_balances,
        'concentration': concentration,
        'seasonality': seasonality,
        'transfer_count': len(transfers),
        'revenue_transaction_count': len(categorized),
        'concentration_analysis': concentration_analysis,
        'excluded_transactions': excluded_deposits,
    }
