"""
Risk Engine Module
Calculates risk metrics: NSFs, negative days, DTI, cash activity flags,
gambling detection, and overall risk scoring.
"""

import pandas as pd
import re
from typing import List, Dict, Optional
from datetime import datetime
from collections import defaultdict


NSF_PATTERNS = [
    r'nsf\s*fee',
    r'insufficient\s*funds',
    r'overdraft\s*fee',
    r'returned\s*item',
    r'od\s*fee',
    r'non-sufficient',
    r'overdraft\s*charge',
    r'overdraft\s*transfer',
]

GAMBLING_PATTERNS = [
    r'draftkings',
    r'fanduel',
    r'betmgm',
    r'caesars\s*sports',
    r'barstool',
    r'pointsbet',
    r'wynn\s*bet',
    r'bet365',
    r'bovada',
    r'casino',
    r'poker',
    r'slot',
    r'gambling',
    r'gaming\s*commission',
    r'lottery',
    r'lotto',
    r'powerball',
    r'mega\s*millions',
]

CASH_PATTERNS = [
    r'cash\s*deposit',
    r'counter\s*deposit',
    r'branch\s*deposit',
    r'atm\s*deposit',
]

ATM_PATTERNS = [
    r'atm\s*withdrawal',
    r'atm\s*cash',
    r'cash\s*withdrawal',
]

MCA_LENDER_PATTERNS = [
    r'capify',
    r'credibly',
    r'ondeck',
    r'on\s*deck',
    r'kabbage',
    r'fundbox',
    r'bluevine',
    r'lendio',
    r'rapid\s*advance',
    r'swift\s*capital',
    r'merchant\s*cash',
    r'daily\s*ach',
    r'world\s*business',
    r'can\s*capital',
    r'national\s*funding',
    r'forward\s*financing',
    r'fora\s*financial',
    r'expansion\s*capital',
    r'clear\s*balance',
    r'slice\s*capital',
    r'everest\s*business',
    r'reliant\s*funding',
    r'yellowstone',
    r'bizfi',
    r'newtek',
]


def matches_patterns(text: str, patterns: List[str]) -> bool:
    """Check if text matches any pattern."""
    text_lower = text.lower()
    for pattern in patterns:
        if re.search(pattern, text_lower):
            return True
    return False


def count_nsf_occurrences(transactions: List[Dict]) -> Dict:
    """
    Count NSF (Non-Sufficient Funds) occurrences and fees.
    """
    nsf_transactions = []
    nsf_total = 0
    
    for txn in transactions:
        description = txn.get('description', '').lower()
        
        if matches_patterns(description, NSF_PATTERNS):
            nsf_transactions.append({
                'date': txn.get('date'),
                'description': description,
                'amount': txn.get('debit', 0) or txn.get('amount', 0)
            })
            nsf_total += txn.get('debit', 0) or txn.get('amount', 0)
    
    return {
        'nsf_count': len(nsf_transactions),
        'nsf_total_fees': nsf_total,
        'nsf_transactions': nsf_transactions,
        'nsf_dates': [t['date'] for t in nsf_transactions],
        'nsf_flag': len(nsf_transactions) >= 3,
    }


def count_negative_balance_days(daily_balances: pd.DataFrame) -> Dict:
    """
    Count days with negative ending balance.
    """
    if daily_balances is None or daily_balances.empty:
        return {
            'negative_days_count': 0,
            'negative_dates': [],
            'max_negative': 0,
            'negative_percentage': 0,
            'negative_flag': False,
        }
    
    if 'ending_balance' not in daily_balances.columns:
        return {
            'negative_days_count': 0,
            'negative_dates': [],
            'max_negative': 0,
            'negative_percentage': 0,
            'negative_flag': False,
        }
    
    negative_days = daily_balances[daily_balances['ending_balance'] < 0]
    
    total_days = len(daily_balances)
    negative_count = len(negative_days)
    
    if negative_count > 0:
        max_negative = negative_days['ending_balance'].min()
        negative_dates = negative_days['date'].dt.strftime('%Y-%m-%d').tolist() if 'date' in negative_days.columns else []
    else:
        max_negative = 0
        negative_dates = []
    
    return {
        'negative_days_count': negative_count,
        'negative_dates': negative_dates[:10],
        'max_negative': max_negative,
        'negative_percentage': round((negative_count / total_days * 100) if total_days > 0 else 0, 2),
        'negative_flag': negative_count >= 5 or (negative_count / total_days > 0.1 if total_days > 0 else False),
        'total_days_analyzed': total_days,
    }


def calculate_average_daily_balance(daily_balances: pd.DataFrame) -> float:
    """
    Calculate average daily balance across statement period.
    """
    if daily_balances is None or daily_balances.empty:
        return 0
    
    if 'ending_balance' not in daily_balances.columns:
        return 0
    
    return round(daily_balances['ending_balance'].mean(), 2)


def detect_gambling_activity(transactions: List[Dict]) -> Dict:
    """
    Detect gambling-related transactions.
    """
    gambling_transactions = []
    gambling_total = 0
    
    for txn in transactions:
        description = txn.get('description', '').lower()
        
        if matches_patterns(description, GAMBLING_PATTERNS):
            amount = txn.get('debit', 0) or txn.get('credit', 0) or txn.get('amount', 0)
            gambling_transactions.append({
                'date': txn.get('date'),
                'description': description[:50],
                'amount': amount
            })
            gambling_total += amount
    
    return {
        'gambling_count': len(gambling_transactions),
        'gambling_total': gambling_total,
        'gambling_transactions': gambling_transactions[:10],
        'gambling_flag': len(gambling_transactions) >= 3 or gambling_total >= 1000,
    }


def detect_existing_mca_payments(transactions: List[Dict]) -> List[Dict]:
    """
    Detect existing MCA/loan payments in transaction history.
    """
    mca_payments = []
    payment_patterns = defaultdict(list)
    
    for txn in transactions:
        description = txn.get('description', '').lower()
        debit = txn.get('debit', 0)
        
        if debit <= 0:
            continue
        
        if matches_patterns(description, MCA_LENDER_PATTERNS):
            mca_payments.append({
                'date': txn.get('date'),
                'description': description[:50],
                'amount': debit,
                'lender_match': 'known_mca'
            })
            payment_patterns[description[:20]].append(debit)
            continue
        
        if re.search(r'ach\s*debit|daily\s*payment|weekly\s*payment', description):
            if 100 <= debit <= 5000:
                mca_payments.append({
                    'date': txn.get('date'),
                    'description': description[:50],
                    'amount': debit,
                    'lender_match': 'suspected_mca'
                })
                payment_patterns[description[:20]].append(debit)
    
    total_mca = sum(p['amount'] for p in mca_payments)
    unique_lenders = len(set(p['description'][:20] for p in mca_payments))
    
    stacking_detected = unique_lenders >= 2
    
    return {
        'mca_payments': mca_payments[:20],
        'mca_payment_count': len(mca_payments),
        'mca_total_payments': total_mca,
        'unique_mca_lenders': unique_lenders,
        'stacking_detected': stacking_detected,
        'stacking_flag': stacking_detected,
    }


def flag_cash_atm_activity(transactions: List[Dict]) -> Dict:
    """
    Flag suspicious cash/ATM activity.
    """
    cash_deposits = []
    atm_withdrawals = []
    
    for txn in transactions:
        description = txn.get('description', '').lower()
        
        if matches_patterns(description, CASH_PATTERNS):
            cash_deposits.append({
                'date': txn.get('date'),
                'amount': txn.get('credit', 0) or txn.get('amount', 0)
            })
        
        if matches_patterns(description, ATM_PATTERNS):
            atm_withdrawals.append({
                'date': txn.get('date'),
                'amount': txn.get('debit', 0) or txn.get('amount', 0)
            })
    
    total_cash = sum(c['amount'] for c in cash_deposits)
    total_atm = sum(a['amount'] for a in atm_withdrawals)
    
    total_deposits = sum(t.get('credit', 0) for t in transactions if t.get('credit', 0) > 0)
    
    cash_percentage = (total_cash / total_deposits * 100) if total_deposits > 0 else 0
    
    return {
        'cash_deposit_count': len(cash_deposits),
        'cash_deposit_total': total_cash,
        'atm_withdrawal_count': len(atm_withdrawals),
        'atm_withdrawal_total': total_atm,
        'cash_percentage': round(cash_percentage, 2),
        'high_cash_flag': cash_percentage > 20,
    }


def calculate_risk_score(
    nsf_data: Dict,
    negative_days_data: Dict,
    gambling_data: Dict,
    mca_data: Dict,
    cash_data: Dict,
    revenue_metrics: Dict = None
) -> Dict:
    """
    Calculate overall risk score (0-100, lower is better).
    """
    score = 0
    risk_factors = []
    
    nsf_count = nsf_data.get('nsf_count', 0)
    if nsf_count >= 5:
        score += 25
        risk_factors.append(f"High NSF count: {nsf_count}")
    elif nsf_count >= 3:
        score += 15
        risk_factors.append(f"Moderate NSF count: {nsf_count}")
    elif nsf_count >= 1:
        score += 5
        risk_factors.append(f"Some NSFs: {nsf_count}")
    
    neg_pct = negative_days_data.get('negative_percentage', 0)
    if neg_pct >= 20:
        score += 20
        risk_factors.append(f"High negative balance days: {neg_pct}%")
    elif neg_pct >= 10:
        score += 10
        risk_factors.append(f"Some negative balance days: {neg_pct}%")
    elif neg_pct >= 5:
        score += 5
    
    if gambling_data.get('gambling_flag'):
        score += 15
        risk_factors.append("Gambling activity detected")
    
    if mca_data.get('stacking_detected'):
        score += 25
        risk_factors.append(f"MCA stacking detected: {mca_data.get('unique_mca_lenders')} lenders")
    elif mca_data.get('mca_payment_count', 0) > 0:
        score += 10
        risk_factors.append("Existing MCA position")
    
    if cash_data.get('high_cash_flag'):
        score += 10
        risk_factors.append(f"High cash deposits: {cash_data.get('cash_percentage')}%")
    
    if revenue_metrics:
        monthly_rev = revenue_metrics.get('monthly_average_deposits', 0)
        if monthly_rev < 10000:
            score += 10
            risk_factors.append(f"Low monthly revenue: ${monthly_rev:,.0f}")
    
    score = min(100, score)
    
    if score <= 20:
        tier = 'A'
    elif score <= 35:
        tier = 'B'
    elif score <= 50:
        tier = 'C'
    elif score <= 70:
        tier = 'D'
    else:
        tier = 'Decline'
    
    return {
        'risk_score': score,
        'risk_tier': tier,
        'risk_factors': risk_factors,
        'approved': tier != 'Decline',
    }


def generate_risk_profile(transactions: List[Dict], daily_balances: pd.DataFrame = None) -> Dict:
    """
    Generate comprehensive risk profile for the applicant.
    """
    if not transactions:
        return {
            'nsf_analysis': {'nsf_count': 0, 'nsf_total_fees': 0, 'nsf_flag': False},
            'negative_days': {'negative_days_count': 0, 'negative_percentage': 0, 'negative_flag': False},
            'gambling': {'gambling_count': 0, 'gambling_flag': False},
            'mca_positions': {'mca_payment_count': 0, 'stacking_detected': False},
            'cash_activity': {'cash_percentage': 0, 'high_cash_flag': False},
            'risk_score': {'risk_score': 50, 'risk_tier': 'C', 'risk_factors': ['No transaction data']},
            'average_daily_balance': 0,
        }
    
    nsf_data = count_nsf_occurrences(transactions)
    
    negative_days_data = count_negative_balance_days(daily_balances)
    
    avg_balance = calculate_average_daily_balance(daily_balances)
    
    gambling_data = detect_gambling_activity(transactions)
    
    mca_data = detect_existing_mca_payments(transactions)
    
    cash_data = flag_cash_atm_activity(transactions)
    
    risk_score = calculate_risk_score(
        nsf_data, negative_days_data, gambling_data, mca_data, cash_data
    )
    
    return {
        'nsf_analysis': nsf_data,
        'negative_days': negative_days_data,
        'gambling': gambling_data,
        'mca_positions': mca_data,
        'cash_activity': cash_data,
        'risk_score': risk_score,
        'average_daily_balance': avg_balance,
    }
