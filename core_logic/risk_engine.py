"""
Risk Engine Module
Calculates risk metrics: NSFs, negative days, DTI, cash activity flags,
gambling detection, MCA detection, revenue velocity, expense categorization,
red flag detection, and overall risk scoring.
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

NSF_WAIVER_PATTERNS = [
    r'not\s*charged',
    r'waived',
    r'reversed',
    r'fee\s*reversal',
    r'fee\s*refund',
    r'credit\s*back',
    r'overdraft\s*transfer',
    r'od\s*transfer',
    r'overdraft\s*protection\s*transfer',
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
    r'capify', r'credibly', r'ondeck', r'on\s*deck', r'kabbage', r'fundbox',
    r'bluevine', r'lendio', r'rapid\s*advance', r'swift\s*capital',
    r'merchant\s*cash', r'daily\s*ach', r'world\s*business', r'can\s*capital',
    r'national\s*funding', r'forward\s*financing', r'fora\s*financial',
    r'expansion\s*capital', r'clear\s*balance', r'slice\s*capital',
    r'everest\s*business', r'reliant\s*funding', r'yellowstone', r'bizfi', r'newtek',
    r'efinancialtree', r'e\s*financial\s*tree', r'capybara', r'ivy\s*receivables',
    r'rauch.*milliken', r'doordash\s*capital', r'sl\s*recovery', r'slrecovery',
    r'spoton', r'spot\s*on', r'libertas', r'clearview', r'quickbridge',
    r'fox\s*capital', r'rapid\s*finance', r'payability', r'behalf',
    r'square\s*capital', r'shopify\s*capital', r'amazon\s*lending', r'paypal\s*working',
    r'stripe\s*capital', r'brex', r'divvy', r'clearco', r'pipe',
]

MCA_ACH_IDENTIFIERS = {
    '9144978400': 'eFinancialTree',
    '5612081085': 'CAPYBARA',
    '7183166893': 'Ivy Receivables/Fox',
    'D002': 'Rauch-Milliken',
    'doordash': 'DoorDash Capital',
    'slrecovery': 'SL Recovery',
    'minpmt': 'SpotOn',
    'libertas': 'Libertas Funding',
    'clearview': 'Clearview Funding',
    'quickbridge': 'Quick Bridge',
    'credibly': 'Credibly',
    'ondeck': 'OnDeck',
    'kabbage': 'Kabbage',
    'fundbox': 'Fundbox',
    'bluevine': 'BlueVine',
    'payability': 'Payability',
    'behalf': 'Behalf',
}

FUNDING_PATTERNS = [
    r'wire\s*(transfer|in|credit)',
    r'incoming\s*wire',
    r'fed\s*wire',
    r'ach\s*credit',
    r'external\s*deposit',
    r'same\s*day\s*credit',
]

REVENUE_SOURCE_PATTERNS = {
    'shift4': {'pattern': r'shift4|harbortouch', 'type': 'cc_processing'},
    'spoton_revenue': {'pattern': r'spoton.*deposit|spoton.*settlement', 'type': 'cc_processing'},
    'square': {'pattern': r'square.*deposit|sq\s*\*', 'type': 'cc_processing'},
    'stripe': {'pattern': r'stripe', 'type': 'cc_processing'},
    'clover': {'pattern': r'clover', 'type': 'cc_processing'},
    'toast': {'pattern': r'toast', 'type': 'cc_processing'},
    'doordash_revenue': {'pattern': r'doordash(?!.*capital).*deposit|dd\s*doordash', 'type': 'delivery'},
    'grubhub': {'pattern': r'grubhub|seamless', 'type': 'delivery'},
    'ubereats': {'pattern': r'uber\s*eats|ubereats', 'type': 'delivery'},
    'postmates': {'pattern': r'postmates', 'type': 'delivery'},
    'counter_deposit': {'pattern': r'counter\s*deposit|branch\s*deposit|cash\s*deposit', 'type': 'cash'},
}

RECURRING_EXPENSE_PATTERNS = {
    'adp_payroll': {'pattern': r'adp|paychex|gusto', 'type': 'payroll'},
    'cheney_brothers': {'pattern': r'cheney\s*brothers?|sysco|us\s*foods', 'type': 'food_supplier'},
    'paper_supplier': {'pattern': r'paper|janitorial|cleaning\s*supply', 'type': 'supplies'},
    'electric': {'pattern': r'fpl|florida\s*power|duke\s*energy|pge|electric', 'type': 'utilities'},
    'comcast': {'pattern': r'comcast|spectrum|att|verizon|tmobile', 'type': 'telecom'},
    'rent': {'pattern': r'rent|lease\s*payment|landlord', 'type': 'rent'},
    'insurance': {'pattern': r'insurance|geico|progressive|state\s*farm', 'type': 'insurance'},
}


def matches_patterns(text: str, patterns: List[str]) -> bool:
    text_lower = text.lower()
    for pattern in patterns:
        if re.search(pattern, text_lower):
            return True
    return False


def count_nsf_occurrences(transactions: List[Dict]) -> Dict:
    nsf_transactions = []
    nsf_total = 0

    for txn in transactions:
        description = txn.get('description', '').lower()

        if matches_patterns(description, NSF_PATTERNS):
            if matches_patterns(description, NSF_WAIVER_PATTERNS):
                continue
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
    if daily_balances is None or daily_balances.empty:
        return 0

    if 'ending_balance' not in daily_balances.columns:
        return 0

    return round(daily_balances['ending_balance'].mean(), 2)


def detect_gambling_activity(transactions: List[Dict]) -> Dict:
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


def identify_mca_lender(description: str) -> Optional[str]:
    desc_lower = description.lower()

    if 'minpmt' in desc_lower and 'spoton' in desc_lower:
        return 'SpotOn (MINPMT)'

    if re.search(r'spoton\s*-\s*[a-z0-9]|fbo spoton|spoton transact', desc_lower):
        return None

    for ach_id, lender_name in MCA_ACH_IDENTIFIERS.items():
        if ach_id.lower() in desc_lower:
            return lender_name

    for pattern in MCA_LENDER_PATTERNS:
        if re.search(pattern, desc_lower):
            match = re.search(pattern, desc_lower)
            if match:
                return match.group(0).title()

    return None


def parse_date_flexible(date_val) -> Optional[datetime]:
    if isinstance(date_val, datetime):
        return date_val
    if not isinstance(date_val, str) or not date_val:
        return None

    formats = ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%d/%m/%Y', '%m/%d/%y', '%Y%m%d']
    for fmt in formats:
        try:
            return datetime.strptime(date_val.strip(), fmt)
        except ValueError:
            continue
    return None


def detect_payment_frequency(dates: List[str]) -> str:
    if len(dates) < 2:
        return 'unknown'

    try:
        date_objs = []
        for d in dates:
            parsed = parse_date_flexible(d)
            if parsed:
                date_objs.append(parsed)

        if len(date_objs) < 2:
            return 'unknown'

        date_objs.sort()

        monthly_counts = defaultdict(int)
        for d in date_objs:
            month_key = f"{d.year}-{d.month:02d}"
            monthly_counts[month_key] += 1

        if not monthly_counts:
            return 'unknown'

        avg_per_month = sum(monthly_counts.values()) / len(monthly_counts)

        if avg_per_month >= 10:
            return 'daily'
        elif avg_per_month >= 3.5:
            return 'weekly'
        elif avg_per_month >= 1.8:
            return 'bi-weekly'
        elif avg_per_month >= 0.8:
            return 'monthly'
        else:
            return 'irregular'
    except:
        return 'unknown'


def reverse_engineer_mca_position(payments: List[Dict], frequency: str) -> Dict:
    if not payments:
        return {}

    amounts = [p['amount'] for p in payments]
    avg_payment = sum(amounts) / len(amounts)

    frequency_multipliers = {
        'daily': 22,
        'weekly': 4.33,
        'bi-weekly': 2.17,
        'monthly': 1,
    }

    multiplier = frequency_multipliers.get(frequency, 4)
    monthly_cost = avg_payment * multiplier

    est_factor = 1.35
    est_term_months = 6
    est_funding = (monthly_cost * est_term_months) / est_factor

    payments_made = len(payments)
    if frequency == 'daily':
        months_paid = payments_made / 22
    elif frequency == 'weekly':
        months_paid = payments_made / 4.33
    elif frequency == 'bi-weekly':
        months_paid = payments_made / 2.17
    else:
        months_paid = payments_made

    pct_paid = min(months_paid / est_term_months, 0.9)
    est_remaining = est_funding * (1 - pct_paid) * est_factor

    return {
        'avg_payment': round(avg_payment, 2),
        'monthly_cost': round(monthly_cost, 2),
        'est_funding': round(est_funding, 2),
        'est_remaining': round(est_remaining, 2),
        'payments_made': payments_made,
        'frequency': frequency,
    }


def track_payment_changes(lender_payments: Dict[str, List[Dict]]) -> Dict:
    changes = {}

    for lender, payments in lender_payments.items():
        if len(payments) < 2:
            continue

        sorted_payments = sorted(payments, key=lambda x: x.get('date', ''))

        first_half = sorted_payments[:len(sorted_payments)//2]
        second_half = sorted_payments[len(sorted_payments)//2:]

        if first_half and second_half:
            first_avg = sum(p['amount'] for p in first_half) / len(first_half)
            second_avg = sum(p['amount'] for p in second_half) / len(second_half)

            if first_avg > 0:
                pct_change = ((second_avg - first_avg) / first_avg) * 100
            else:
                pct_change = 0

            last_payment_date = sorted_payments[-1].get('date', '')

            try:
                last_date = datetime.strptime(last_payment_date, '%Y-%m-%d') if isinstance(last_payment_date, str) else last_payment_date
                days_since_last = (datetime.now() - last_date).days if last_date else 999
            except:
                days_since_last = 999

            if days_since_last > 30:
                status = 'STOPPED'
            elif pct_change < -30:
                status = 'REDUCED'
            elif pct_change > 30:
                status = 'INCREASED'
            else:
                status = 'ACTIVE'

            changes[lender] = {
                'first_avg': round(first_avg, 2),
                'second_avg': round(second_avg, 2),
                'pct_change': round(pct_change, 1),
                'status': status,
                'last_payment': last_payment_date,
                'days_since_last': days_since_last,
            }

    return changes


def detect_existing_mca_payments(transactions: List[Dict]) -> Dict:
    mca_payments = []
    lender_payments = defaultdict(list)

    for txn in transactions:
        description = txn.get('description', '')
        desc_lower = description.lower()
        debit = txn.get('debit', 0)

        if debit <= 0:
            continue

        lender = identify_mca_lender(description)

        if lender:
            payment = {
                'date': txn.get('date'),
                'description': description[:100],
                'amount': debit,
                'lender': lender,
                'match_type': 'confirmed'
            }
            mca_payments.append(payment)
            lender_payments[lender].append(payment)
            continue

        if re.search(r'ach\s*debit|ach\s*withdrawal|ach\s*pmt', desc_lower):
            if 100 <= debit <= 2000:
                numbers = re.findall(r'\d{8,12}', description)
                if numbers:
                    ach_id = numbers[0]
                    suspected_lender = f"ACH-{ach_id[:8]}"
                    payment = {
                        'date': txn.get('date'),
                        'description': description[:100],
                        'amount': debit,
                        'lender': suspected_lender,
                        'ach_id': ach_id,
                        'match_type': 'suspected'
                    }
                    mca_payments.append(payment)
                    lender_payments[suspected_lender].append(payment)

    mca_positions = []
    for lender, payments in lender_payments.items():
        dates = [p['date'] for p in payments if p.get('date')]
        frequency = detect_payment_frequency(dates)
        position = reverse_engineer_mca_position(payments, frequency)

        mca_positions.append({
            'lender': lender,
            'frequency': frequency,
            'payment_count': len(payments),
            'total_paid': sum(p['amount'] for p in payments),
            'avg_payment': position.get('avg_payment', 0),
            'monthly_cost': position.get('monthly_cost', 0),
            'est_funding': position.get('est_funding', 0),
            'est_remaining': position.get('est_remaining', 0),
            'match_type': payments[0].get('match_type', 'unknown') if payments else 'unknown',
            'first_payment': min(dates) if dates else None,
            'last_payment': max(dates) if dates else None,
        })

    mca_positions.sort(key=lambda x: x['monthly_cost'], reverse=True)

    payment_changes = track_payment_changes(lender_payments)

    total_monthly_debt = sum(p['monthly_cost'] for p in mca_positions)
    total_outstanding = sum(p['est_remaining'] for p in mca_positions)
    unique_lenders = len(mca_positions)
    stacking_detected = unique_lenders >= 2

    return {
        'mca_payments': mca_payments[:50],
        'mca_payment_count': len(mca_payments),
        'mca_total_payments': sum(p['amount'] for p in mca_payments),
        'unique_mca_lenders': unique_lenders,
        'stacking_detected': stacking_detected,
        'stacking_flag': stacking_detected,
        'mca_positions': mca_positions,
        'total_monthly_debt': round(total_monthly_debt, 2),
        'total_outstanding': round(total_outstanding, 2),
        'payment_changes': payment_changes,
    }


def detect_funding_events(transactions: List[Dict]) -> Dict:
    funding_events = []

    for txn in transactions:
        description = txn.get('description', '')
        desc_lower = description.lower()
        credit = txn.get('credit', 0)

        if credit < 3000:
            continue

        is_funding = False
        funding_type = 'unknown'

        if matches_patterns(desc_lower, FUNDING_PATTERNS):
            is_funding = True
            funding_type = 'wire'

        if re.search(r'wire|fed\s*ref|incoming', desc_lower) and credit >= 5000:
            is_funding = True
            funding_type = 'wire'

        if credit >= 10000 and not is_funding:
            if not re.search(r'shift4|square|stripe|clover|toast|doordash|grubhub|uber', desc_lower):
                is_funding = True
                funding_type = 'large_deposit'

        if is_funding:
            is_likely_mca = credit >= 10000 and credit <= 150000

            funding_events.append({
                'date': txn.get('date'),
                'description': description[:100],
                'amount': credit,
                'funding_type': funding_type,
                'likely_mca': is_likely_mca,
            })

    funding_events.sort(key=lambda x: x.get('date', ''), reverse=True)

    most_recent = funding_events[0] if funding_events else None
    if most_recent:
        parsed_date = parse_date_flexible(most_recent['date'])
        if parsed_date:
            days_since = (datetime.now() - parsed_date).days
        else:
            days_since = 999
    else:
        days_since = 999

    return {
        'funding_events': funding_events[:20],
        'funding_count': len(funding_events),
        'total_funding': sum(f['amount'] for f in funding_events),
        'likely_mca_fundings': [f for f in funding_events if f.get('likely_mca')],
        'most_recent_funding': most_recent,
        'days_since_last_funding': days_since,
        'recent_funding_flag': days_since <= 30,
    }


def analyze_revenue_sources(transactions: List[Dict]) -> Dict:
    sources = defaultdict(lambda: {'amount': 0, 'count': 0, 'transactions': []})

    for txn in transactions:
        description = txn.get('description', '')
        desc_lower = description.lower()
        credit = txn.get('credit', 0)

        if credit <= 0:
            continue

        matched = False
        for source_name, config in REVENUE_SOURCE_PATTERNS.items():
            if re.search(config['pattern'], desc_lower):
                sources[source_name]['amount'] += credit
                sources[source_name]['count'] += 1
                sources[source_name]['type'] = config['type']
                sources[source_name]['transactions'].append({
                    'date': txn.get('date'),
                    'amount': credit,
                })
                matched = True
                break

        if not matched:
            sources['other']['amount'] += credit
            sources['other']['count'] += 1
            sources['other']['type'] = 'other'

    total_revenue = sum(s['amount'] for s in sources.values())

    source_summary = []
    for name, data in sources.items():
        if data['amount'] > 0:
            monthly_avg = data['amount'] / 3
            source_summary.append({
                'source': name,
                'type': data.get('type', 'other'),
                'total': round(data['amount'], 2),
                'monthly_avg': round(monthly_avg, 2),
                'count': data['count'],
                'pct_of_revenue': round((data['amount'] / total_revenue * 100) if total_revenue > 0 else 0, 1),
            })

    source_summary.sort(key=lambda x: x['total'], reverse=True)

    return {
        'sources': source_summary[:15],
        'total_revenue': round(total_revenue, 2),
        'cc_processing_total': sum(s['total'] for s in source_summary if s['type'] == 'cc_processing'),
        'delivery_total': sum(s['total'] for s in source_summary if s['type'] == 'delivery'),
        'cash_total': sum(s['total'] for s in source_summary if s['type'] == 'cash'),
    }


def analyze_recurring_expenses(transactions: List[Dict]) -> Dict:
    expenses = defaultdict(lambda: {'amount': 0, 'count': 0, 'transactions': []})

    for txn in transactions:
        description = txn.get('description', '')
        desc_lower = description.lower()
        debit = txn.get('debit', 0)

        if debit <= 0:
            continue

        for expense_name, config in RECURRING_EXPENSE_PATTERNS.items():
            if re.search(config['pattern'], desc_lower):
                expenses[expense_name]['amount'] += debit
                expenses[expense_name]['count'] += 1
                expenses[expense_name]['type'] = config['type']
                expenses[expense_name]['transactions'].append({
                    'date': txn.get('date'),
                    'amount': debit,
                    'description': description[:50],
                })
                break

    expense_summary = []
    for name, data in expenses.items():
        if data['amount'] > 0:
            avg_payment = data['amount'] / data['count'] if data['count'] > 0 else 0
            monthly_est = data['amount'] / 3
            expense_summary.append({
                'expense': name,
                'type': data.get('type', 'other'),
                'total': round(data['amount'], 2),
                'monthly_est': round(monthly_est, 2),
                'count': data['count'],
                'avg_payment': round(avg_payment, 2),
            })

    expense_summary.sort(key=lambda x: x['total'], reverse=True)

    return {
        'expenses': expense_summary,
        'payroll_monthly': sum(e['monthly_est'] for e in expense_summary if e['type'] == 'payroll'),
        'rent_monthly': sum(e['monthly_est'] for e in expense_summary if e['type'] == 'rent'),
        'utilities_monthly': sum(e['monthly_est'] for e in expense_summary if e['type'] == 'utilities'),
        'supplies_monthly': sum(e['monthly_est'] for e in expense_summary if e['type'] in ['food_supplier', 'supplies']),
    }


def detect_underwriting_red_flags(transactions: List[Dict], mca_data: Dict, funding_data: Dict) -> Dict:
    red_flags = []

    mca_positions = mca_data.get('mca_positions', [])
    if len(mca_positions) >= 5:
        red_flags.append({
            'flag': 'HEAVY_STACKING',
            'severity': 'critical',
            'detail': f'{len(mca_positions)} active MCA positions detected',
        })
    elif len(mca_positions) >= 3:
        red_flags.append({
            'flag': 'MODERATE_STACKING',
            'severity': 'high',
            'detail': f'{len(mca_positions)} active MCA positions detected',
        })

    days_since_funding = funding_data.get('days_since_last_funding', 999)
    if 0 <= days_since_funding <= 14:
        red_flags.append({
            'flag': 'VERY_RECENT_FUNDING',
            'severity': 'critical',
            'detail': f'Most recent funding only {days_since_funding} days ago',
        })
    elif 0 <= days_since_funding <= 30:
        red_flags.append({
            'flag': 'RECENT_FUNDING',
            'severity': 'high',
            'detail': f'Funding received {days_since_funding} days ago',
        })

    total_monthly_debt = mca_data.get('total_monthly_debt', 0)
    if total_monthly_debt >= 25000:
        red_flags.append({
            'flag': 'HIGH_MONTHLY_DEBT',
            'severity': 'critical',
            'detail': f'Monthly MCA payments: ${total_monthly_debt:,.0f}',
        })
    elif total_monthly_debt >= 15000:
        red_flags.append({
            'flag': 'ELEVATED_MONTHLY_DEBT',
            'severity': 'high',
            'detail': f'Monthly MCA payments: ${total_monthly_debt:,.0f}',
        })

    returned_deposits = []
    returned_total = 0
    return_item_count = 0
    for txn in transactions:
        desc = txn.get('description', '').lower()
        debit = txn.get('debit', 0)
        if 'return deposit item' in desc or 'returned item' in desc:
            return_item_count += 1
            if debit > 0:
                returned_deposits.append(txn)
                returned_total += debit
        elif ('returned' in desc or 'reversal' in desc or 'chargeback' in desc) and debit > 0:
            returned_deposits.append(txn)
            returned_total += debit

    if return_item_count >= 3 or returned_total >= 10000:
        red_flags.append({
            'flag': 'RETURNED_DEPOSITS',
            'severity': 'high',
            'detail': f'{return_item_count} returned items, ${returned_total:,.0f} total',
        })

    payment_changes = mca_data.get('payment_changes', {})
    stopped_count = sum(1 for c in payment_changes.values() if c.get('status') == 'STOPPED')
    if stopped_count >= 2:
        red_flags.append({
            'flag': 'STOPPED_PAYMENTS',
            'severity': 'high',
            'detail': f'{stopped_count} MCA positions show stopped payments',
        })

    dates = [txn.get('date') for txn in transactions if txn.get('date')]
    if dates:
        try:
            parsed_dates = [parse_date_flexible(d) for d in dates if d]
            parsed_dates = [d for d in parsed_dates if d]
            if parsed_dates:
                earliest = min(parsed_dates)
                latest = max(parsed_dates)
                statement_span = (latest - earliest).days
                if statement_span <= 60:
                    red_flags.append({
                        'flag': 'NEW_BANK_ACCOUNT',
                        'severity': 'high',
                        'detail': f'Only {statement_span} days of history available',
                    })
        except:
            pass

    return {
        'red_flags': red_flags,
        'critical_count': sum(1 for f in red_flags if f['severity'] == 'critical'),
        'high_count': sum(1 for f in red_flags if f['severity'] == 'high'),
        'has_critical': any(f['severity'] == 'critical' for f in red_flags),
        'returned_total': returned_total,
        'return_item_count': return_item_count,
    }


detect_red_flags = detect_underwriting_red_flags


def flag_cash_atm_activity(transactions: List[Dict]) -> Dict:
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


# ── ENGINE Keyword-Based Helper Functions ────────────────────────────

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


def _categorize_expenses(transactions: list, keywords: dict) -> dict:
    categories = keywords.get("expense_categories", {})
    totals = defaultdict(float)
    other_total = 0.0

    for txn in transactions:
        debit = txn.get('debit', 0) or 0
        amount = txn.get('amount', 0) or 0
        if debit > 0:
            expense_amt = debit
        elif amount < 0:
            expense_amt = abs(amount)
        else:
            continue

        desc = txn.get("description", "").upper()
        matched = False

        for cat_name, cat_keywords in categories.items():
            for kw in cat_keywords:
                if kw.upper() in desc:
                    totals[cat_name] += expense_amt
                    matched = True
                    break
            if matched:
                break

        if not matched:
            other_total += expense_amt

    result = {k: round(v, 2) for k, v in totals.items()}
    result["other"] = round(other_total, 2)
    return result


def _detect_keyword_red_flags(transactions: list, keywords: dict) -> list:
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


def _analyze_cash_deposits(transactions: list, keywords: dict, net_revenue: float) -> dict:
    cash_kws = [kw.upper() for kw in keywords.get("cash_deposit_keywords", [])]
    total = 0.0

    for txn in transactions:
        credit = txn.get('credit', 0) or 0
        amount = txn.get('amount', 0) or 0
        if credit > 0:
            deposit_amt = credit
        elif amount > 0:
            deposit_amt = amount
        else:
            continue

        desc = txn.get("description", "").upper()
        for kw in cash_kws:
            if kw in desc:
                total += deposit_amt
                break

    pct = (total / net_revenue * 100) if net_revenue > 0 else 0.0

    return {
        "cash_deposit_total": round(total, 2),
        "cash_deposit_percent": round(pct, 2),
        "cash_risk_flag": pct > 20,
    }


def _detect_keyword_gambling(transactions: list, keywords: dict) -> dict:
    gamble_kws = [kw.upper() for kw in keywords.get("gambling_keywords", [])]
    gamble_patterns = [re.compile(r'\b' + re.escape(kw) + r'\b') for kw in gamble_kws]
    total = 0.0
    found = []

    for txn in transactions:
        desc = txn.get("description", "").upper()
        for pat in gamble_patterns:
            if pat.search(desc):
                amt = abs(txn.get('debit', 0) or txn.get('amount', 0) or 0)
                total += amt
                found.append({
                    "date": txn.get("date", ""),
                    "description": txn.get("description", ""),
                    "amount": amt,
                })
                break

    return {
        "gambling_total": round(total, 2),
        "gambling_flag": len(found) > 0,
        "gambling_transactions": found,
    }


def _count_nsf_events(transactions: list, keywords: dict) -> dict:
    nsf_kws = [kw.upper() for kw in keywords.get("nsf_keywords", [])]
    nsf_patterns = [re.compile(r'\b' + re.escape(kw) + r'\b') for kw in nsf_kws]
    waiver_compiled = [re.compile(p, re.IGNORECASE) for p in NSF_WAIVER_PATTERNS]
    count = 0
    total_fees = 0.0
    by_month = defaultdict(int)

    for txn in transactions:
        desc = txn.get("description", "").upper()
        for pat in nsf_patterns:
            if pat.search(desc):
                if any(wp.search(desc) for wp in waiver_compiled):
                    break
                count += 1
                fee = abs(txn.get('debit', 0) or txn.get("amount", 0) or 0)
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


def _calc_avg_daily_balance(transactions: list) -> float:
    balances = [t["running_balance"] for t in transactions if t.get("running_balance") is not None]
    if not balances:
        return 0.0
    return round(sum(balances) / len(balances), 2)


# ── Enhanced Risk Score (combines ROOT + ENGINE factors) ─────────────

def _calculate_enhanced_risk_score(
    nsf_count: int,
    negative_days_count: int,
    negative_percentage: float,
    gambling_flag: bool,
    mca_data: Dict,
    cash_risk_flag: bool,
    high_severity_flags: int,
    medium_severity_flags: int,
    velocity_flag: str,
    has_critical_underwriting: bool,
    revenue_metrics: Dict = None,
) -> Dict:
    score = 100
    risk_factors = []

    nsf_deduction = min(nsf_count * 5, 25)
    if nsf_deduction > 0:
        score -= nsf_deduction
        risk_factors.append(f"NSF count: {nsf_count} (-{nsf_deduction})")

    neg_deduction = min(int(negative_percentage * 1.5), 20) if negative_percentage > 0 else 0
    if negative_days_count >= 5:
        neg_deduction = max(neg_deduction, 10)
    if neg_deduction > 0:
        score -= neg_deduction
        risk_factors.append(f"Negative balance days: {negative_days_count} ({negative_percentage}%) (-{neg_deduction})")

    if mca_data.get('stacking_detected'):
        stacking_deduction = min(mca_data.get('unique_mca_lenders', 2) * 8, 25)
        score -= stacking_deduction
        risk_factors.append(f"MCA stacking: {mca_data.get('unique_mca_lenders')} lenders (-{stacking_deduction})")
    elif mca_data.get('mca_payment_count', 0) > 0:
        score -= 10
        risk_factors.append("Existing MCA position (-10)")

    if cash_risk_flag:
        score -= 10
        risk_factors.append("High cash deposits >20% (-10)")

    if gambling_flag:
        score -= 15
        risk_factors.append("Gambling activity detected (-15)")

    high_deduction = min(high_severity_flags * 10, 30)
    if high_deduction > 0:
        score -= high_deduction
        risk_factors.append(f"High severity red flags: {high_severity_flags} (-{high_deduction})")

    medium_deduction = min(medium_severity_flags * 5, 15)
    if medium_deduction > 0:
        score -= medium_deduction
        risk_factors.append(f"Medium severity red flags: {medium_severity_flags} (-{medium_deduction})")

    if velocity_flag == "accelerating_decline":
        score -= 15
        risk_factors.append("Revenue accelerating decline (-15)")
    elif velocity_flag == "declining":
        score -= 10
        risk_factors.append("Revenue declining (-10)")

    if has_critical_underwriting:
        score -= 20
        risk_factors.append("Critical underwriting red flags (-20)")

    if revenue_metrics:
        monthly_rev = revenue_metrics.get('monthly_average_deposits', 0)
        if monthly_rev > 0 and monthly_rev < 10000:
            score -= 10
            risk_factors.append(f"Low monthly revenue: ${monthly_rev:,.0f} (-10)")

    score = max(0, min(100, score))

    if score >= 80:
        tier = 'A'
    elif score >= 60:
        tier = 'B'
    elif score >= 40:
        tier = 'C'
    elif score >= 20:
        tier = 'D'
    else:
        tier = 'Decline'

    return {
        'risk_score': score,
        'risk_tier': tier,
        'risk_factors': risk_factors,
        'approved': tier != 'Decline',
    }


# ── Main Entry Points ───────────────────────────────────────────────

def analyze_risk(
    transactions: List[Dict],
    daily_balances: Optional[pd.DataFrame] = None,
    keywords: Optional[Dict] = None,
    net_revenue: float = 0.0,
    revenue_metrics: Optional[Dict] = None,
) -> Dict:
    if not transactions:
        return {
            'nsf_analysis': {'nsf_count': 0, 'nsf_total_fees': 0, 'nsf_flag': False},
            'negative_days': {'negative_days_count': 0, 'negative_percentage': 0, 'negative_flag': False},
            'gambling': {'gambling_count': 0, 'gambling_flag': False},
            'mca_positions': {'mca_payment_count': 0, 'stacking_detected': False, 'mca_positions': []},
            'cash_activity': {'cash_percentage': 0, 'high_cash_flag': False},
            'risk_score': {'risk_score': 50, 'risk_tier': 'C', 'risk_factors': ['No transaction data'], 'approved': True},
            'average_daily_balance': 0,
            'funding_analysis': {'funding_events': [], 'funding_count': 0},
            'revenue_sources': {'sources': []},
            'recurring_expenses': {'expenses': []},
            'underwriting_flags': {'red_flags': [], 'critical_count': 0},
            'revenue_velocity': 0.0,
            'revenue_acceleration': 0.0,
            'velocity_flag': 'stable',
            'expenses_by_category': {},
            'red_flags': [],
            'cash_deposit_total': 0.0,
            'cash_deposit_percent': 0.0,
            'cash_risk_flag': False,
            'gambling_total': 0.0,
            'gambling_flag': False,
            'gambling_transactions': [],
            'avg_daily_balance': 0.0,
        }

    nsf_data = count_nsf_occurrences(transactions)
    negative_days_data = count_negative_balance_days(daily_balances)
    avg_balance = calculate_average_daily_balance(daily_balances)
    gambling_data = detect_gambling_activity(transactions)
    mca_data = detect_existing_mca_payments(transactions)
    cash_data = flag_cash_atm_activity(transactions)
    funding_data = detect_funding_events(transactions)
    revenue_sources = analyze_revenue_sources(transactions)
    recurring_expenses = analyze_recurring_expenses(transactions)
    underwriting_flag_data = detect_underwriting_red_flags(transactions, mca_data, funding_data)

    if keywords:
        kw_nsf = _count_nsf_events(transactions, keywords)
        kw_gambling = _detect_keyword_gambling(transactions, keywords)
        kw_red_flags = _detect_keyword_red_flags(transactions, keywords)
        kw_expenses = _categorize_expenses(transactions, keywords)
        kw_cash = _analyze_cash_deposits(transactions, keywords, net_revenue)

        nsf_data['nsf_count'] = max(nsf_data['nsf_count'], kw_nsf['nsf_count'])
        nsf_data['nsf_total_fees'] = max(nsf_data['nsf_total_fees'], kw_nsf['nsf_total_fees'])
        nsf_data['nsf_by_month'] = kw_nsf.get('nsf_by_month', {})

        final_gambling_total = kw_gambling['gambling_total']
        final_gambling_flag = kw_gambling['gambling_flag']
        final_gambling_transactions = kw_gambling['gambling_transactions']
        final_red_flags = kw_red_flags
        final_expenses_by_category = kw_expenses
        final_cash_deposit_total = kw_cash['cash_deposit_total']
        final_cash_deposit_percent = kw_cash['cash_deposit_percent']
        final_cash_risk_flag = kw_cash['cash_risk_flag']
    else:
        final_gambling_total = gambling_data.get('gambling_total', 0)
        final_gambling_flag = gambling_data.get('gambling_flag', False)
        final_gambling_transactions = gambling_data.get('gambling_transactions', [])
        final_red_flags = []
        final_expenses_by_category = {}
        final_cash_deposit_total = cash_data.get('cash_deposit_total', 0)
        final_cash_deposit_percent = cash_data.get('cash_percentage', 0)
        final_cash_risk_flag = cash_data.get('high_cash_flag', False)

    monthly_deposits = defaultdict(float)
    for txn in transactions:
        credit = txn.get('credit', 0) or 0
        amount = txn.get('amount', 0) or 0
        deposit = credit if credit > 0 else (amount if amount > 0 else 0)
        if deposit > 0:
            mk = str(txn.get('date', ''))[:7]
            if mk:
                monthly_deposits[mk] += deposit
    velocity_data = _calculate_revenue_velocity(dict(monthly_deposits))

    avg_daily_balance = _calc_avg_daily_balance(transactions)

    high_severity_flags = sum(1 for f in final_red_flags if f.get("severity") == "HIGH")
    medium_severity_flags = sum(1 for f in final_red_flags if f.get("severity") == "MEDIUM")

    risk_score_data = _calculate_enhanced_risk_score(
        nsf_count=nsf_data.get('nsf_count', 0),
        negative_days_count=negative_days_data.get('negative_days_count', 0),
        negative_percentage=negative_days_data.get('negative_percentage', 0),
        gambling_flag=final_gambling_flag,
        mca_data=mca_data,
        cash_risk_flag=final_cash_risk_flag,
        high_severity_flags=high_severity_flags,
        medium_severity_flags=medium_severity_flags,
        velocity_flag=velocity_data['velocity_flag'],
        has_critical_underwriting=underwriting_flag_data.get('has_critical', False),
        revenue_metrics=revenue_metrics,
    )

    return {
        'nsf_analysis': nsf_data,
        'negative_days': negative_days_data,
        'gambling': gambling_data,
        'mca_positions': mca_data,
        'cash_activity': cash_data,
        'risk_score': risk_score_data,
        'average_daily_balance': avg_balance,
        'funding_analysis': funding_data,
        'revenue_sources': revenue_sources,
        'recurring_expenses': recurring_expenses,
        'underwriting_flags': underwriting_flag_data,
        'revenue_velocity': velocity_data['revenue_velocity'],
        'revenue_acceleration': velocity_data['revenue_acceleration'],
        'velocity_flag': velocity_data['velocity_flag'],
        'expenses_by_category': final_expenses_by_category,
        'red_flags': final_red_flags,
        'cash_deposit_total': final_cash_deposit_total,
        'cash_deposit_percent': final_cash_deposit_percent,
        'cash_risk_flag': final_cash_risk_flag,
        'gambling_total': final_gambling_total,
        'gambling_flag': final_gambling_flag,
        'gambling_transactions': final_gambling_transactions,
        'avg_daily_balance': avg_daily_balance,
    }


def generate_risk_profile(transactions: List[Dict], daily_balances: Optional[pd.DataFrame] = None) -> Dict:
    result = analyze_risk(transactions, daily_balances)
    if 'underwriting_flags' in result:
        result['red_flags'] = result.pop('underwriting_flags')
    return result
