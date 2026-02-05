"""
Scrubber Module
Cleans transaction data, identifies transfers, calculates revenue metrics,
and performs concentration analysis.
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


def scrub_transactions(transactions: List[Dict]) -> Dict:
    """
    Main function to clean and analyze transactions.
    Returns scrubbed data with revenue metrics and categorized transactions.
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
        }
    
    fixed_transactions = fix_debit_credit_from_description(transactions)
    
    revenue_txns, transfers = identify_internal_transfers(fixed_transactions)
    
    categorized = rename_descriptions(revenue_txns)
    
    revenue_metrics = calculate_net_revenue(transactions, exclude_transfers=True)
    
    monthly_data = calculate_monthly_breakdown(categorized)
    
    daily_balances = calculate_daily_balances(categorized)
    
    concentration = analyze_deposit_concentration(categorized)
    
    seasonality = detect_seasonality(monthly_data)
    
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
    }
