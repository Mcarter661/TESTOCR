"""
OCR Engine Module
Handles PDF text extraction and bank statement parsing using pdfplumber.
"""

import pdfplumber
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import os


BANK_PATTERNS = {
    'chase': [r'JPMorgan Chase', r'CHASE', r'chase\.com'],
    'bofa': [r'Bank of America', r'BANK OF AMERICA', r'bankofamerica\.com'],
    'wells_fargo': [r'Wells Fargo', r'WELLS FARGO', r'wellsfargo\.com'],
    'td_bank': [r'TD Bank', r'TD BANK'],
    'pnc': [r'PNC Bank', r'PNC BANK'],
    'us_bank': [r'U\.S\. Bank', r'US BANK', r'usbank\.com'],
    'capital_one': [r'Capital One', r'CAPITAL ONE'],
    'regions': [r'Regions Bank', r'REGIONS'],
    'truist': [r'Truist', r'TRUIST', r'BB&T', r'SunTrust'],
    'citizens': [r'Citizens Bank', r'CITIZENS'],
    'fifth_third': [r'Fifth Third', r'FIFTH THIRD'],
    'huntington': [r'Huntington', r'HUNTINGTON'],
    'key_bank': [r'KeyBank', r'KEY BANK'],
    'santander': [r'Santander', r'SANTANDER'],
    'bmo': [r'BMO Harris', r'BMO HARRIS'],
}

DATE_PATTERNS = [
    r'(\d{1,2}/\d{1,2}/\d{2,4})',
    r'(\d{1,2}-\d{1,2}-\d{2,4})',
    r'(\d{4}-\d{2}-\d{2})',
    r'([A-Za-z]{3}\s+\d{1,2},?\s+\d{4})',
    r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})',
]

AMOUNT_PATTERN = r'[\$]?\s*[\-\(]?\s*[\d,]+\.?\d{0,2}\s*[\)]?'


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract raw text from a PDF bank statement using pdfplumber.
    """
    full_text = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text.append(text)
                    
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if row:
                            row_text = ' | '.join([str(cell) if cell else '' for cell in row])
                            full_text.append(row_text)
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
        return ""
    
    return '\n'.join(full_text)


def detect_bank_format(text: str) -> str:
    """
    Detect which bank format the statement belongs to.
    """
    text_upper = text.upper()
    
    for bank, patterns in BANK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return bank
    
    return 'unknown'


def parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse various date formats into datetime object.
    """
    date_formats = [
        '%m/%d/%Y', '%m/%d/%y',
        '%m-%d-%Y', '%m-%d-%y',
        '%Y-%m-%d',
        '%b %d, %Y', '%b %d %Y',
        '%d %b %Y',
        '%B %d, %Y',
    ]
    
    date_str = date_str.strip()
    
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def parse_amount(amount_str: str) -> Optional[float]:
    """
    Parse amount string to float, handling various formats.
    """
    if not amount_str:
        return None
    
    amount_str = amount_str.strip()
    
    is_negative = bool(re.search(r'[\-\(]', amount_str))
    
    cleaned = re.sub(r'[\$,\s\(\)\-]', '', amount_str)
    
    try:
        amount = float(cleaned)
        if is_negative:
            amount = -amount
        return amount
    except ValueError:
        return None


def extract_transactions_generic(text: str) -> List[Dict]:
    """
    Generic transaction extraction for unknown bank formats.
    """
    transactions = []
    lines = text.split('\n')
    
    transaction_pattern = re.compile(
        r'(\d{1,2}[/\-]\d{1,2}[/\-]?\d{0,4})?\s*'
        r'(.+?)\s+'
        r'([\$\-\(]?\s*[\d,]+\.?\d{0,2}\s*[\)]?)\s*'
        r'([\$\-\(]?\s*[\d,]+\.?\d{0,2}\s*[\)]?)?'
    )
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 10:
            continue
        
        for date_pattern in DATE_PATTERNS:
            date_match = re.search(date_pattern, line)
            if date_match:
                date_str = date_match.group(1)
                parsed_date = parse_date(date_str)
                
                if parsed_date:
                    remaining = line[date_match.end():].strip()
                    
                    amounts = re.findall(r'[\$]?\s*[\-\(]?\s*[\d,]+\.\d{2}\s*[\)]?', remaining)
                    
                    if amounts:
                        last_amount_match = None
                        for amt in amounts:
                            match = re.search(re.escape(amt), remaining)
                            if match:
                                last_amount_match = match
                        
                        if last_amount_match:
                            description = remaining[:remaining.find(amounts[0])].strip()
                            amount_val = parse_amount(amounts[-1])
                            
                            if description and amount_val is not None:
                                debit = amount_val if amount_val < 0 else 0
                                credit = amount_val if amount_val > 0 else 0
                                
                                transactions.append({
                                    'date': parsed_date.strftime('%Y-%m-%d'),
                                    'description': description[:100],
                                    'amount': abs(amount_val),
                                    'debit': abs(debit) if debit else 0,
                                    'credit': credit if credit else 0,
                                    'balance': None,
                                    'raw_line': line[:200]
                                })
                                break
    
    return transactions


def extract_transactions_chase(text: str) -> List[Dict]:
    """
    Chase-specific transaction parsing.
    """
    transactions = []
    lines = text.split('\n')
    
    in_transaction_section = False
    
    for line in lines:
        if any(keyword in line.upper() for keyword in ['TRANSACTION DETAIL', 'CHECKING SUMMARY', 'DEPOSITS AND ADDITIONS', 'WITHDRAWALS']):
            in_transaction_section = True
            continue
        
        if in_transaction_section:
            date_match = re.match(r'^(\d{2}/\d{2})\s+(.+?)\s+([\-]?[\d,]+\.\d{2})(?:\s+([\d,]+\.\d{2}))?', line)
            if date_match:
                date_str = date_match.group(1)
                description = date_match.group(2).strip()
                amount_str = date_match.group(3)
                balance_str = date_match.group(4) if date_match.group(4) else None
                
                amount = parse_amount(amount_str)
                balance = parse_amount(balance_str) if balance_str else None
                
                if amount is not None:
                    current_year = datetime.now().year
                    full_date = f"{date_str}/{current_year}"
                    parsed_date = parse_date(full_date)
                    
                    transactions.append({
                        'date': parsed_date.strftime('%Y-%m-%d') if parsed_date else date_str,
                        'description': description[:100],
                        'amount': abs(amount),
                        'debit': abs(amount) if amount < 0 else 0,
                        'credit': amount if amount > 0 else 0,
                        'balance': balance,
                        'raw_line': line[:200]
                    })
    
    if not transactions:
        transactions = extract_transactions_generic(text)
    
    return transactions


def extract_account_info(text: str, bank_format: str) -> Dict:
    """
    Extract account holder and account information.
    """
    account_info = {
        'account_holder': None,
        'account_number': None,
        'statement_period_start': None,
        'statement_period_end': None,
        'opening_balance': None,
        'closing_balance': None,
        'bank_name': bank_format.replace('_', ' ').title() if bank_format != 'unknown' else 'Unknown Bank'
    }
    
    account_patterns = [
        r'Account\s*(?:Number|#|No\.?)?\s*[:\s]*[\*xX]*(\d{4,})',
        r'(?:Account|Acct)\s*[:\s]*[\*xX]+(\d{4})',
        r'ending\s+in\s+(\d{4})',
    ]
    
    for pattern in account_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            account_info['account_number'] = f"****{match.group(1)[-4:]}"
            break
    
    period_patterns = [
        r'(?:Statement\s+Period|Period)[:\s]*(\w+\s+\d{1,2},?\s+\d{4})\s*(?:to|through|-)\s*(\w+\s+\d{1,2},?\s+\d{4})',
        r'(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:to|through|-)\s*(\d{1,2}/\d{1,2}/\d{2,4})',
    ]
    
    for pattern in period_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start_date = parse_date(match.group(1))
            end_date = parse_date(match.group(2))
            if start_date:
                account_info['statement_period_start'] = start_date.strftime('%Y-%m-%d')
            if end_date:
                account_info['statement_period_end'] = end_date.strftime('%Y-%m-%d')
            break
    
    balance_patterns = [
        (r'(?:Beginning|Opening|Previous)\s+Balance[:\s]*\$?([\d,]+\.\d{2})', 'opening_balance'),
        (r'(?:Ending|Closing|New)\s+Balance[:\s]*\$?([\d,]+\.\d{2})', 'closing_balance'),
    ]
    
    for pattern, key in balance_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            account_info[key] = parse_amount(match.group(1))
    
    return account_info


def parse_transactions(text: str, bank_format: str) -> List[Dict]:
    """
    Parse transaction data from extracted text based on bank format.
    """
    if bank_format == 'chase':
        return extract_transactions_chase(text)
    else:
        return extract_transactions_generic(text)


def calculate_summary_stats(transactions: List[Dict]) -> Dict:
    """
    Calculate summary statistics from transactions.
    """
    if not transactions:
        return {
            'total_deposits': 0,
            'total_withdrawals': 0,
            'transaction_count': 0,
            'average_deposit': 0,
            'average_withdrawal': 0,
        }
    
    deposits = [t['credit'] for t in transactions if t.get('credit', 0) > 0]
    withdrawals = [t['debit'] for t in transactions if t.get('debit', 0) > 0]
    
    return {
        'total_deposits': sum(deposits),
        'total_withdrawals': sum(withdrawals),
        'deposit_count': len(deposits),
        'withdrawal_count': len(withdrawals),
        'transaction_count': len(transactions),
        'average_deposit': sum(deposits) / len(deposits) if deposits else 0,
        'average_withdrawal': sum(withdrawals) / len(withdrawals) if withdrawals else 0,
        'net_cash_flow': sum(deposits) - sum(withdrawals),
    }


def process_bank_statement(pdf_path: str) -> Dict:
    """
    Main function to process a complete bank statement.
    Returns complete parsed data including account info and transactions.
    """
    if not os.path.exists(pdf_path):
        return {
            'error': f'File not found: {pdf_path}',
            'success': False
        }
    
    raw_text = extract_text_from_pdf(pdf_path)
    
    if not raw_text:
        return {
            'error': 'Could not extract text from PDF',
            'success': False
        }
    
    bank_format = detect_bank_format(raw_text)
    
    transactions = parse_transactions(raw_text, bank_format)
    
    account_info = extract_account_info(raw_text, bank_format)
    
    summary_stats = calculate_summary_stats(transactions)
    
    return {
        'success': True,
        'filename': os.path.basename(pdf_path),
        'bank_format': bank_format,
        'account_info': account_info,
        'transactions': transactions,
        'summary': summary_stats,
        'raw_text_length': len(raw_text),
        'page_count': raw_text.count('\f') + 1 if '\f' in raw_text else 1,
    }
