"""
Bank Statement Parsers Module
Comprehensive parsers for major US banks

Supported Banks:
- Chase (formal statement)
- Bank of America (formal statement)
- Wells Fargo (formal + MTD)
- Citibank (CitiBusiness)
- US Bank (formal statement)
- Webster Bank (formal + MTD)
- PNC Bank (already in ocr_engine.py - imported for reference)
- Truist (already in ocr_engine.py - imported for reference)
- Generic fallback (improved)

Each parser returns standardized format:
{
    'date': 'YYYY-MM-DD',
    'description': str,
    'amount': float,  # positive for credits, negative for debits
    'debit': float,   # absolute value if debit, else 0
    'credit': float,  # absolute value if credit, else 0
    'balance': float or None,
    'category': str,  # ACH, CHECK, WIRE, DEBIT_CARD, FEE, TRANSFER, etc.
    'raw_line': str
}
"""

import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dateutil import parser as date_parser


# =============================================================================
# BANK DETECTION PATTERNS
# =============================================================================

BANK_DETECTION_PATTERNS = {
    'chase': [
        r'CHASE\s*[✓®™]?',
        r'JPMorgan\s+Chase',
        r'chase\.com',
        r'CHECKING\s+SUMMARY',
        r'JPMORGAN\s+CHASE\s+BANK',
    ],
    'bofa': [
        r'BANK\s+OF\s+AMERICA',
        r'bankofamerica\.com',
        r'Bank\s+of\s+America,?\s+N\.?A\.?',
        r'Business\s+Advantage',
    ],
    'wells_fargo': [
        r'WELLS\s+FARGO',
        r'wellsfargo\.com',
        r'Wells\s+Fargo\s+Bank',
        r'Optimize\s+Business\s+Checking',
    ],
    'citibank': [
        r'CITIBANK',
        r'CitiBusiness',
        r'Citibank,?\s+N\.?A\.?',
        r'Citi\s+CBO\s+Services',
    ],
    'us_bank': [
        r'U\.?S\.?\s+Bank',
        r'usbank\.com',
        r'US\s+Bank\s+National\s+Association',
        r'Silver\s+Business\s+Checking',
    ],
    'webster': [
        r'Webster\s*Bank',
        r'websterbank\.com',
        r'PLATINUM\s+BUSINESS\s+ANALYZED',
    ],
    'pnc': [
        r'PNC\s+Bank',
        r'pnc\.com',
        r'PNC\s+BANK',
    ],
    'truist': [
        r'Truist',
        r'TRUIST',
        r'BB&T',
        r'SunTrust',
        r'truist\.com',
    ],
    'bank_of_bartlett': [
        r'Bank\s+of\s+Bartlett',
        r'bankofbartlett\.com',
    ],
    'city_bank_tx': [
        r'City\s+Bank',
        r'P\.?O\.?\s+Box\s+5060\s+Lubbock',
        r'Lubbock,?\s+Texas',
    ],
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_date_safe(date_str: str, year_hint: int = None) -> Optional[str]:
    """
    Parse various date formats into YYYY-MM-DD.
    
    Handles:
    - MM/DD/YY, MM/DD/YYYY
    - MM/DD (adds year)
    - MMM DD (adds year)
    - MM-DD-YYYY
    """
    if not date_str or not date_str.strip():
        return None
    
    date_str = date_str.strip()
    current_year = year_hint or datetime.now().year
    
    # Direct format attempts
    formats = [
        ("%m/%d/%Y", False),
        ("%m/%d/%y", False),
        ("%m/%d", True),  # needs year
        ("%m-%d-%Y", False),
        ("%m-%d-%y", False),
        ("%b %d", True),  # needs year (e.g., "Feb 1")
        ("%b %d, %Y", False),
        ("%B %d", True),
        ("%B %d, %Y", False),
        ("%Y-%m-%d", False),
    ]
    
    for fmt, needs_year in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if needs_year:
                dt = dt.replace(year=current_year)
            elif dt.year < 100:
                dt = dt.replace(year=2000 + dt.year)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    # Fuzzy parse as last resort
    try:
        dt = date_parser.parse(date_str, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except:
        return None


def parse_amount_safe(amount_str: str) -> Optional[float]:
    """
    Parse currency string to float.
    
    Handles:
    - $1,234.56
    - (1,234.56) - negative
    - 1234.56-  - negative suffix
    - -1,234.56
    """
    if not amount_str:
        return None
    
    s = str(amount_str).strip()
    if not s:
        return None
    
    # Detect negative indicators
    negative = False
    if s.startswith('(') and s.endswith(')'):
        negative = True
        s = s[1:-1]
    if s.endswith('-'):
        negative = True
        s = s[:-1]
    if s.startswith('-'):
        negative = True
        s = s[1:]
    if '<' in s:  # Wells Fargo ACH debit indicator
        negative = True
        s = s.replace('<', '')
    
    # Clean and parse
    s = s.replace('$', '').replace(',', '').replace(' ', '').strip()
    
    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return None


def detect_bank(text: str) -> str:
    """
    Detect which bank the statement is from.
    Returns bank key or 'unknown'.
    """
    text_upper = text.upper()
    
    for bank, patterns in BANK_DETECTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return bank
    
    return 'unknown'


def extract_year_from_text(text: str) -> int:
    """Extract statement year from text for date parsing."""
    patterns = [
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(\d{4})\s+through\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(\d{4})',
        r'(?:for|period|from)\s+\w+\s+\d{1,2},?\s+(\d{4})',
        r'(\d{4})\s+to\s+\w+\s+\d{1,2}',
        r'Statement\s+Period[:\s]+.*?(\d{4})',
        r'(\d{1,2}/\d{1,2}/(\d{4}))',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()
            if len(groups) == 2 and all(g and g.isdigit() and 2000 <= int(g) <= 2100 for g in groups):
                return int(groups[1])
            year_str = groups[-1] if len(groups) > 1 else groups[0]
            try:
                year = int(year_str)
                if 2000 <= year <= 2100:
                    return year
            except:
                pass
    
    return datetime.now().year


def categorize_transaction(description: str) -> str:
    """Categorize transaction based on description."""
    desc_upper = description.upper()
    
    if any(kw in desc_upper for kw in ['ACH', 'ELECTRONIC', 'DIRECT DEP', 'DIRECT DEPOSIT']):
        return 'ACH'
    if any(kw in desc_upper for kw in ['WIRE', 'WIRE TRANSFER', 'WIRE IN', 'WIRE OUT', 'FEDWIRE']):
        return 'WIRE'
    if any(kw in desc_upper for kw in ['CHECK', 'CHK', 'CHECK NO']):
        return 'CHECK'
    if any(kw in desc_upper for kw in ['DEBIT CARD', 'CHECKCARD', 'PURCHASE', 'POS']):
        return 'DEBIT_CARD'
    if any(kw in desc_upper for kw in ['FEE', 'SERVICE CHARGE', 'MONTHLY FEE']):
        return 'FEE'
    if any(kw in desc_upper for kw in ['TRANSFER', 'XFER', 'TFR']):
        return 'TRANSFER'
    if any(kw in desc_upper for kw in ['DEPOSIT', 'DEP']):
        return 'DEPOSIT'
    if any(kw in desc_upper for kw in ['ATM']):
        return 'ATM'
    if any(kw in desc_upper for kw in ['ZELLE']):
        return 'ZELLE'
    
    return 'OTHER'


# =============================================================================
# CHASE PARSER
# =============================================================================

def extract_transactions_chase(text: str, tables: List[List] = None) -> List[Dict]:
    """
    Chase Business Complete Checking parser.
    
    Format characteristics:
    - Date: MM/DD (year from header)
    - Sections: DEPOSITS AND ADDITIONS, CHECKS PAID, ELECTRONIC WITHDRAWALS, ATM & DEBIT CARD WITHDRAWALS
    - Amount AFTER description (may have $ prefix)
    - Multi-line ACH entries (continuation lines with Descr:, Ind Name:, Trn: etc.)
    - Checks format: CHECK_NO ^ MM/DD AMOUNT
    - All amounts positive, section determines debit/credit
    """
    transactions = []
    year = extract_year_from_text(text)
    
    cleaned_text = re.sub(r'\*(?:start|end)\*.*?(?=\d{2}/\d{2}\s)', '', text)
    cleaned_text = re.sub(r'\*(?:start|end)\*[^\n]*', '', cleaned_text)
    lines = cleaned_text.split('\n')
    
    current_section = None
    section_is_credit = False
    
    credit_headers = ['DEPOSITS AND ADDITIONS', 'DEPOSITS AND CREDITS']
    debit_headers = ['CHECKS PAID', 'ELECTRONIC WITHDRAWALS', 'ATM & DEBIT CARD WITHDRAWALS',
                     'OTHER WITHDRAWALS', 'WITHDRAWALS AND DEBITS', 'FEES', 'SERVICE CHARGES']
    stop_headers = ['DAILY ENDING BALANCE', 'DAILY LEDGER BALANCE', 'DAILY BALANCE',
                    'SERVICE CHARGE SUMMARY', 'TRANSACTION DETAIL', 'OVERDRAFT PROTECTION']
    
    skip_patterns = re.compile(
        r'^(Total |DATE$|CHECK NO|If you see|not the original|\*|•|Page |\d+ items|Ledger |Number |Opening |Ending |Summary|Commercial |Account Number|Please examine)',
        re.IGNORECASE
    )
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        line_upper = line.upper()
        
        is_stop = False
        for header in stop_headers:
            if header in line_upper:
                current_section = None
                is_stop = True
                break
        if is_stop:
            continue
        
        matched_section = False
        is_summary_line = bool(re.search(r'\d+\s+\$[\d,]+\.\d{2}', line))
        for header in debit_headers:
            if header in line_upper and not line_upper.startswith('TOTAL') and not is_summary_line:
                current_section = 'debit'
                section_is_credit = False
                matched_section = True
                break
        if not matched_section:
            for header in credit_headers:
                if header in line_upper and not line_upper.startswith('TOTAL') and not is_summary_line:
                    current_section = 'credit'
                    section_is_credit = True
                    matched_section = True
                    break
        
        if matched_section:
            continue
        
        if current_section is None:
            continue
        
        if skip_patterns.match(line):
            continue
        
        match = re.match(r'^(\d{2}/\d{2})\s+(.+?)\s+\$?([\d,]+\.\d{2})\s*$', line)
        
        if match:
            date_str = match.group(1)
            description = match.group(2).strip()
            amount = parse_amount_safe(match.group(3))
            
            if amount is not None:
                parsed_date = parse_date_safe(f"{date_str}/{year}")
                
                if not section_is_credit:
                    amount = -abs(amount)
                else:
                    amount = abs(amount)
                
                transactions.append({
                    'date': parsed_date or date_str,
                    'description': description[:300],
                    'amount': amount,
                    'debit': abs(amount) if amount < 0 else 0,
                    'credit': amount if amount > 0 else 0,
                    'balance': None,
                    'category': categorize_transaction(description),
                    'raw_line': line[:300]
                })
            continue
        
        check_match = re.match(r'^(\d+)\s*\*?\^?\s*(\d{2}/\d{2})\s+\$?([\d,]+\.\d{2})\s*$', line)
        if check_match and current_section == 'debit':
            check_num = check_match.group(1)
            date_str = check_match.group(2)
            amount = parse_amount_safe(check_match.group(3))
            
            if amount is not None:
                parsed_date = parse_date_safe(f"{date_str}/{year}")
                amount = -abs(amount)
                
                transactions.append({
                    'date': parsed_date or date_str,
                    'description': f"CHECK #{check_num}",
                    'amount': amount,
                    'debit': abs(amount),
                    'credit': 0,
                    'balance': None,
                    'category': 'CHECK',
                    'raw_line': line[:300]
                })
            continue
        
        if current_section and not re.match(r'^\d{2}/\d{2}', line):
            if transactions and len(line) > 5:
                jpm_continuation = any(kw in line.upper() for kw in [
                    'ENTRY DESCR:', 'IND ID:', 'IND NAME:', 'TRN:', 'TRACE#',
                    'IMAD:', 'YOUR REF:', 'ORIG CO', 'ORIG ID:', 'EED:',
                    'SEC:', 'DIRECT DEPOSIT', 'CO ENTRY'
                ])
                if jpm_continuation or not re.search(r'[\d,]+\.\d{2}', line):
                    prev_desc = transactions[-1]['description']
                    if len(prev_desc) < 250:
                        transactions[-1]['description'] = f"{prev_desc} {line}"[:300]
    
    return transactions


# =============================================================================
# BANK OF AMERICA PARSER
# =============================================================================

def extract_transactions_bofa(text: str, tables: List[List] = None) -> List[Dict]:
    """
    Bank of America Business Advantage parser.
    
    Format characteristics:
    - Date: MM/DD/YY (05/01/23)
    - Multi-line descriptions with DES:, ID:, INDN:, CO ID: fields
    - Sections: Deposits and other credits, Withdrawals and other debits, Checks
    - Amount at far right
    - Withdrawals shown with '-' prefix
    - Card transactions listed under Withdrawals with card account header
    """
    transactions = []
    year = extract_year_from_text(text)
    lines = text.split('\n')
    
    current_section = None
    section_is_credit = False
    
    credit_sections = ['DEPOSITS AND OTHER CREDITS', 'DEPOSITS']
    debit_sections = ['WITHDRAWALS AND OTHER DEBITS', 'WITHDRAWALS', 'CHECKS', 'SERVICE FEES']
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        
        # Detect section headers
        line_upper = line.upper()
        for section in credit_sections:
            if section in line_upper:
                current_section = 'credit'
                section_is_credit = True
        for section in debit_sections:
            if section in line_upper:
                current_section = 'debit'
                section_is_credit = False
        
        # BOA format: MM/DD/YY Description Amount
        # Amount may have - prefix for debits
        match = re.match(r'^(\d{2}/\d{2}/\d{2})\s+(.+?)\s+([\-]?[\d,]+\.\d{2})\s*$', line)
        
        if match:
            date_str = match.group(1)
            description = match.group(2).strip()
            amount_str = match.group(3)
            amount = parse_amount_safe(amount_str)
            
            # Look ahead for continuation lines (DES:, ID:, INDN:, CO ID:)
            full_description = description
            j = i + 1
            while j < len(lines) and j < i + 4:
                next_line = lines[j].strip()
                # Continuation line doesn't start with date
                if next_line and not re.match(r'^\d{2}/\d{2}', next_line):
                    # Check if it looks like ACH detail
                    if any(kw in next_line.upper() for kw in ['DES:', 'ID:', 'INDN:', 'CO ID:', 'CCD', 'PPD', 'WEB']):
                        full_description = f"{full_description} {next_line}"
                        j += 1
                    else:
                        break
                else:
                    break
            
            if amount is not None:
                parsed_date = parse_date_safe(date_str)
                
                # BOA uses - prefix for debits, but also section context
                if amount > 0 and not section_is_credit:
                    amount = -amount
                
                transactions.append({
                    'date': parsed_date or date_str,
                    'description': full_description[:300],
                    'amount': amount,
                    'debit': abs(amount) if amount < 0 else 0,
                    'credit': amount if amount > 0 else 0,
                    'balance': None,
                    'category': categorize_transaction(full_description),
                    'raw_line': line[:300]
                })
        
        # Also check for CHECKCARD/PURCHASE format (card transactions)
        card_match = re.match(r'^(\d{2}/\d{2}/\d{2})\s+(CHECKCARD|PURCHASE)\s+(\d{4})\s+(.+?)\s+([\-]?[\d,]+\.\d{2})\s*$', line)
        if card_match:
            date_str = card_match.group(1)
            txn_type = card_match.group(2)
            card_date = card_match.group(3)  # MMDD of actual purchase
            description = card_match.group(4).strip()
            amount = parse_amount_safe(card_match.group(5))
            
            if amount is not None:
                parsed_date = parse_date_safe(date_str)
                amount = -abs(amount)  # Card purchases are always debits
                
                transactions.append({
                    'date': parsed_date or date_str,
                    'description': f"{txn_type} {description}"[:300],
                    'amount': amount,
                    'debit': abs(amount),
                    'credit': 0,
                    'balance': None,
                    'category': 'DEBIT_CARD',
                    'raw_line': line[:300]
                })
        
        i += 1
    
    # Handle Checks section separately (Date | Check # | Amount format)
    check_pattern = re.compile(r'(\d{2}/\d{2}/\d{2})\s+(\d+)\s+([\-]?[\d,]+\.\d{2})')
    in_checks_section = False
    
    for line in lines:
        if 'CHECKS' in line.upper() and 'PAID' not in line.upper():
            in_checks_section = True
            continue
        if in_checks_section:
            check_match = check_pattern.search(line)
            if check_match:
                date_str = check_match.group(1)
                check_num = check_match.group(2)
                amount = parse_amount_safe(check_match.group(3))
                
                if amount is not None:
                    parsed_date = parse_date_safe(date_str)
                    amount = -abs(amount)  # Checks are always debits
                    
                    transactions.append({
                        'date': parsed_date or date_str,
                        'description': f"CHECK #{check_num}",
                        'amount': amount,
                        'debit': abs(amount),
                        'credit': 0,
                        'balance': None,
                        'category': 'CHECK',
                        'raw_line': line[:300]
                    })
    
    return transactions


# =============================================================================
# WELLS FARGO PARSER
# =============================================================================

def extract_transactions_wells_fargo(text: str, tables: List[List] = None) -> List[Dict]:
    """
    Wells Fargo Business Checking parser.
    
    Handles BOTH formats:
    1. Formal Statement: Amount BEFORE description, < for ACH debits
    2. Online/MTD: Separate Deposits/Credits and Withdrawals/Debits columns
    
    Format detection:
    - If "Deposits/Credits" and "Withdrawals/Debits" columns → MTD format
    - Otherwise → Formal statement format
    """
    # Detect format
    is_mtd_format = bool(re.search(r'Deposits/Credits.*Withdrawals/Debits', text, re.IGNORECASE))
    
    if is_mtd_format:
        return _parse_wells_fargo_mtd(text)
    else:
        return _parse_wells_fargo_formal(text)


def _parse_wells_fargo_formal(text: str) -> List[Dict]:
    """
    Wells Fargo formal statement format.
    Amount BEFORE description, < symbol for ACH debits.
    """
    transactions = []
    year = extract_year_from_text(text)
    lines = text.split('\n')
    
    current_section = None
    section_is_credit = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Detect sections
        line_upper = line.upper()
        if 'CREDITS' in line_upper or 'DEPOSITS' in line_upper:
            current_section = 'credit'
            section_is_credit = True
        elif 'DEBITS' in line_upper or 'WITHDRAWALS' in line_upper or 'CHECKS' in line_upper:
            current_section = 'debit'
            section_is_credit = False
        
        # Wells Fargo formal: $Amount < Description (< indicates ACH debit)
        # Or: $Amount Description
        match = re.match(r'^\$?([\d,]+\.\d{2})\s*(<)?\s+(.+)$', line)
        
        if match:
            amount = parse_amount_safe(match.group(1))
            is_ach_debit = match.group(2) == '<'
            description = match.group(3).strip()
            
            # Extract date from description if present
            date_match = re.search(r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)', description)
            date_str = date_match.group(1) if date_match else None
            
            if amount is not None:
                parsed_date = parse_date_safe(date_str, year) if date_str else None
                
                # Determine sign
                if is_ach_debit or not section_is_credit:
                    amount = -abs(amount)
                else:
                    amount = abs(amount)
                
                transactions.append({
                    'date': parsed_date,
                    'description': description[:300],
                    'amount': amount,
                    'debit': abs(amount) if amount < 0 else 0,
                    'credit': amount if amount > 0 else 0,
                    'balance': None,
                    'category': categorize_transaction(description),
                    'raw_line': line[:300]
                })
    
    return transactions


def _parse_wells_fargo_mtd(text: str) -> List[Dict]:
    """
    Wells Fargo online/MTD format.
    Separate columns for Deposits/Credits and Withdrawals/Debits.
    Date format: MM/DD/YY
    """
    transactions = []
    year = extract_year_from_text(text)
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # MTD format: Date | Description | Deposit Amount | Withdrawal Amount
        # One of the amount columns will be empty
        
        # Pattern for line with deposit (credit)
        credit_match = re.match(r'^(\d{1,2}/\d{1,2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s*$', line)
        
        # Pattern for line with withdrawal (debit) - usually has empty deposit column
        # This is harder to detect, so we also look for description patterns
        
        if credit_match:
            date_str = credit_match.group(1)
            description = credit_match.group(2).strip()
            amount = parse_amount_safe(credit_match.group(3))
            
            if amount is not None:
                parsed_date = parse_date_safe(date_str)
                
                # Determine if debit or credit based on description
                is_debit = any(kw in description.upper() for kw in 
                    ['DEBIT', 'PAYMENT', 'PURCHASE', 'WITHDRAWAL', 'FEE', 'CHECK'])
                
                if is_debit:
                    amount = -abs(amount)
                
                transactions.append({
                    'date': parsed_date or date_str,
                    'description': description[:300],
                    'amount': amount,
                    'debit': abs(amount) if amount < 0 else 0,
                    'credit': amount if amount > 0 else 0,
                    'balance': None,
                    'category': categorize_transaction(description),
                    'raw_line': line[:300]
                })
    
    return transactions


# =============================================================================
# CITIBANK PARSER
# =============================================================================

def extract_transactions_citibank(text: str, tables: List[List] = None) -> List[Dict]:
    """
    Citibank CitiBusiness parser.
    
    Format characteristics:
    - BEST FORMAT: Separate Debits and Credits columns WITH running balance
    - Date: MM/DD
    - Multi-line descriptions
    - All transactions in one chronological CHECKING ACTIVITY section
    - Format: Date | Description | Debits | Credits | Balance
    """
    transactions = []
    year = extract_year_from_text(text)
    lines = text.split('\n')
    
    in_activity_section = False
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        # Detect CHECKING ACTIVITY section
        if 'CHECKING ACTIVITY' in line.upper():
            in_activity_section = True
            continue
        
        if not in_activity_section:
            continue
        
        # Citi format has separate debit/credit columns
        # Pattern: MM/DD Description Debit Credit Balance
        
        # Debit transaction (has amount in debit column)
        debit_match = re.match(r'^(\d{2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$', line)
        # Credit transaction (has amount in credit column, then balance)
        credit_match = re.match(r'^(\d{2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s*$', line)
        
        # Try to parse as debit first (has 2 amounts: debit and balance)
        if debit_match:
            date_str = debit_match.group(1)
            description = debit_match.group(2).strip()
            amount1 = parse_amount_safe(debit_match.group(3))
            balance = parse_amount_safe(debit_match.group(4))
            
            # Check next line for description continuation
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not re.match(r'^\d{2}/\d{2}', next_line):
                    description = f"{description} {next_line}"
            
            if amount1 is not None:
                parsed_date = parse_date_safe(f"{date_str}/{year}")
                
                # Determine if debit or credit from description
                is_credit = any(kw in description.upper() for kw in 
                    ['CREDIT', 'DEPOSIT', 'WIRE FROM', 'TRANSFER CREDIT', 'WIRE TRANSFER'])
                
                amount = amount1 if is_credit else -amount1
                
                transactions.append({
                    'date': parsed_date or date_str,
                    'description': description[:300],
                    'amount': amount,
                    'debit': abs(amount) if amount < 0 else 0,
                    'credit': amount if amount > 0 else 0,
                    'balance': balance,
                    'category': categorize_transaction(description),
                    'raw_line': line[:300]
                })
        
        # Also try simpler pattern for CHECK NO: lines
        check_match = re.match(r'^(\d{2}/\d{2})\s+CHECK\s+NO:\s*(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', line)
        if check_match:
            date_str = check_match.group(1)
            check_num = check_match.group(2)
            amount = parse_amount_safe(check_match.group(3))
            balance = parse_amount_safe(check_match.group(4))
            
            if amount is not None:
                parsed_date = parse_date_safe(f"{date_str}/{year}")
                amount = -abs(amount)  # Checks are debits
                
                transactions.append({
                    'date': parsed_date or date_str,
                    'description': f"CHECK NO: {check_num}",
                    'amount': amount,
                    'debit': abs(amount),
                    'credit': 0,
                    'balance': balance,
                    'category': 'CHECK',
                    'raw_line': line[:300]
                })
    
    return transactions


# =============================================================================
# US BANK PARSER
# =============================================================================

def extract_transactions_us_bank(text: str, tables: List[List] = None) -> List[Dict]:
    """
    US Bank Silver Business Checking parser.
    
    Format characteristics:
    - Date: MMM DD (Feb 1, Feb 3)
    - Multi-line format with REF number on second line
    - Amount at far right
    - Withdrawals shown with '-' suffix (e.g., 1,194.31-)
    - Sections: Other Deposits, Other Withdrawals, Checks Presented
    """
    transactions = []
    year = extract_year_from_text(text)
    lines = text.split('\n')
    
    current_section = None
    section_is_credit = False
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        # Detect sections
        line_upper = line.upper()
        if 'OTHER DEPOSITS' in line_upper or 'DEPOSITS' in line_upper:
            current_section = 'credit'
            section_is_credit = True
        elif 'OTHER WITHDRAWALS' in line_upper or 'WITHDRAWALS' in line_upper:
            current_section = 'debit'
            section_is_credit = False
        elif 'CHECKS PRESENTED' in line_upper:
            current_section = 'checks'
            section_is_credit = False
        
        # US Bank format: MMM DD Description $ Amount
        # Amount may have - suffix for debits
        match = re.match(r'^([A-Za-z]{3}\s+\d{1,2})\s+(.+?)\s+\$?\s*([\d,]+\.\d{2})([\-]?)\s*$', line)
        
        if match:
            date_str = match.group(1)
            description = match.group(2).strip()
            amount = parse_amount_safe(match.group(3))
            is_negative = match.group(4) == '-'
            
            # Look for REF line
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith('REF='):
                    description = f"{description} {next_line}"
            
            if amount is not None:
                parsed_date = parse_date_safe(date_str, year)
                
                # Apply negative suffix or section context
                if is_negative or not section_is_credit:
                    amount = -abs(amount)
                
                transactions.append({
                    'date': parsed_date or date_str,
                    'description': description[:300],
                    'amount': amount,
                    'debit': abs(amount) if amount < 0 else 0,
                    'credit': amount if amount > 0 else 0,
                    'balance': None,
                    'category': categorize_transaction(description),
                    'raw_line': line[:300]
                })
    
    return transactions


# =============================================================================
# WEBSTER BANK PARSER
# =============================================================================

def extract_transactions_webster(text: str, tables: List[List] = None) -> List[Dict]:
    """
    Webster Bank parser.
    
    Handles BOTH formats:
    1. Formal Statement: MM/DD/YYYY with separate Debits/Credits columns
    2. Online/MTD: MMM DD with +/- single amount column
    """
    # Detect format by date pattern
    has_full_date = bool(re.search(r'\d{2}/\d{2}/\d{4}', text))
    
    if has_full_date:
        return _parse_webster_formal(text)
    else:
        return _parse_webster_mtd(text)


def _parse_webster_formal(text: str) -> List[Dict]:
    """
    Webster Bank formal statement.
    Date: MM/DD/YYYY
    Columns: Date | Description | Debits | Credits | Balance
    """
    transactions = []
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Webster formal: MM/DD/YYYY | Description | Debits | Credits | Balance
        # Debits have -$ prefix
        
        # Pattern with debit
        debit_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+\-?\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})\s*$', line)
        
        # Pattern with credit (debit column empty)
        credit_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})\s*$', line)
        
        if debit_match or credit_match:
            match = debit_match or credit_match
            date_str = match.group(1)
            description = match.group(2).strip()
            amount1 = parse_amount_safe(match.group(3))
            balance = parse_amount_safe(match.group(4))
            
            if amount1 is not None:
                parsed_date = parse_date_safe(date_str)
                
                # Determine debit/credit from description or -$ prefix
                is_debit = '-$' in line or any(kw in description.upper() for kw in 
                    ['DEBIT', 'PAYMENT', 'WITHDRAWAL', 'CHECK', 'FEE'])
                
                amount = -abs(amount1) if is_debit else abs(amount1)
                
                transactions.append({
                    'date': parsed_date or date_str,
                    'description': description[:300],
                    'amount': amount,
                    'debit': abs(amount) if amount < 0 else 0,
                    'credit': amount if amount > 0 else 0,
                    'balance': balance,
                    'category': categorize_transaction(description),
                    'raw_line': line[:300]
                })
    
    return transactions


def _parse_webster_mtd(text: str) -> List[Dict]:
    """
    Webster Bank online/MTD format.
    Date: MMM DD (Jun 20)
    Single Amount column with +/-
    """
    transactions = []
    year = extract_year_from_text(text)
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Webster MTD: MMM DD | Description | Amount | Balance
        match = re.match(r'^([A-Za-z]{3}\s+\d{1,2})\s+(.+?)\s+([\-\+]?\$?[\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})\s*$', line)
        
        if match:
            date_str = match.group(1)
            description = match.group(2).strip()
            amount = parse_amount_safe(match.group(3))
            balance = parse_amount_safe(match.group(4))
            
            if amount is not None:
                parsed_date = parse_date_safe(date_str, year)
                
                transactions.append({
                    'date': parsed_date or date_str,
                    'description': description[:300],
                    'amount': amount,
                    'debit': abs(amount) if amount < 0 else 0,
                    'credit': amount if amount > 0 else 0,
                    'balance': balance,
                    'category': categorize_transaction(description),
                    'raw_line': line[:300]
                })
    
    return transactions


# =============================================================================
# GENERIC FALLBACK PARSER (IMPROVED)
# =============================================================================

def extract_transactions_generic_improved(text: str, tables: List[List] = None) -> List[Dict]:
    """
    Improved generic parser for unknown bank formats.
    
    Strategy:
    1. Try table extraction first
    2. Look for common transaction patterns
    3. Use multiple regex patterns
    4. Infer debits/credits from description keywords
    """
    transactions = []
    year = extract_year_from_text(text)
    
    # Strategy 1: Try tables first
    if tables:
        for row in tables:
            if not row or len(row) < 3:
                continue
            
            # Look for date in first few columns
            date_str = None
            description = None
            amount = None
            
            for i, cell in enumerate(row[:3]):
                if cell:
                    cell_str = str(cell).strip()
                    # Check if date
                    if re.match(r'\d{1,2}[/\-]\d{1,2}', cell_str):
                        date_str = cell_str
                    # Check if amount
                    elif re.match(r'[\$\-\(]?[\d,]+\.\d{2}', cell_str):
                        amount = parse_amount_safe(cell_str)
                    # Otherwise description
                    elif len(cell_str) > 3:
                        description = cell_str
            
            # Look for amount in remaining columns
            for cell in row[3:]:
                if cell and amount is None:
                    cell_str = str(cell).strip()
                    if re.match(r'[\$\-\(]?[\d,]+\.\d{2}', cell_str):
                        amount = parse_amount_safe(cell_str)
            
            if date_str and amount is not None:
                parsed_date = parse_date_safe(date_str, year)
                
                # Infer sign from description
                if description:
                    is_debit = any(kw in description.upper() for kw in 
                        ['DEBIT', 'WITHDRAWAL', 'CHECK', 'FEE', 'PAYMENT', 'PURCHASE'])
                    if is_debit and amount > 0:
                        amount = -amount
                
                transactions.append({
                    'date': parsed_date or date_str,
                    'description': (description or 'Unknown')[:300],
                    'amount': amount,
                    'debit': abs(amount) if amount < 0 else 0,
                    'credit': amount if amount > 0 else 0,
                    'balance': None,
                    'category': categorize_transaction(description or ''),
                    'raw_line': ' | '.join(str(c) for c in row if c)[:300]
                })
    
    # Strategy 2: Line-by-line pattern matching
    if not transactions:
        lines = text.split('\n')
        
        # Multiple transaction patterns to try
        patterns = [
            # MM/DD/YYYY Description Amount
            r'^(\d{1,2}/\d{1,2}/\d{2,4})\s+(.+?)\s+([\-\$\(]?[\d,]+\.\d{2}[\)\-]?)\s*$',
            # MM/DD Description Amount
            r'^(\d{1,2}/\d{1,2})\s+(.+?)\s+([\-\$\(]?[\d,]+\.\d{2}[\)\-]?)\s*$',
            # Date Amount Description
            r'^(\d{1,2}/\d{1,2}/?\d{0,4})\s+([\-\$\(]?[\d,]+\.\d{2}[\)\-]?)\s+(.+)$',
            # MMM DD Description Amount
            r'^([A-Za-z]{3}\s+\d{1,2})\s+(.+?)\s+([\-\$\(]?[\d,]+\.\d{2}[\)\-]?)\s*$',
        ]
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 10:
                continue
            
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    groups = match.groups()
                    
                    # Determine which group is which
                    date_str = groups[0]
                    if len(groups) == 3:
                        # Check if group 2 is amount or description
                        if re.match(r'[\-\$\(]?[\d,]+\.\d{2}', groups[1]):
                            amount = parse_amount_safe(groups[1])
                            description = groups[2]
                        else:
                            description = groups[1]
                            amount = parse_amount_safe(groups[2])
                    
                    if amount is not None:
                        parsed_date = parse_date_safe(date_str, year)
                        
                        # Infer sign
                        if description:
                            is_debit = any(kw in description.upper() for kw in 
                                ['DEBIT', 'WITHDRAWAL', 'CHECK', 'FEE', 'PAYMENT', 'PURCHASE', 'ACH DEBIT'])
                            is_credit = any(kw in description.upper() for kw in 
                                ['DEPOSIT', 'CREDIT', 'WIRE IN', 'ACH CREDIT', 'TRANSFER IN'])
                            
                            if is_debit and amount > 0:
                                amount = -amount
                            elif is_credit and amount < 0:
                                amount = abs(amount)
                        
                        transactions.append({
                            'date': parsed_date or date_str,
                            'description': (description or 'Unknown')[:300],
                            'amount': amount,
                            'debit': abs(amount) if amount < 0 else 0,
                            'credit': amount if amount > 0 else 0,
                            'balance': None,
                            'category': categorize_transaction(description or ''),
                            'raw_line': line[:300]
                        })
                    break  # Found a match, move to next line
    
    return transactions


# =============================================================================
# MAIN ROUTER FUNCTION
# =============================================================================

def parse_bank_statement(text: str, tables: List[List] = None, bank_hint: str = None) -> Tuple[str, List[Dict]]:
    """
    Main entry point for parsing bank statements.
    
    Args:
        text: Extracted text from PDF
        tables: Extracted tables from PDF
        bank_hint: Optional hint for bank type
    
    Returns:
        Tuple of (bank_name, transactions)
    """
    # Detect bank
    bank = bank_hint or detect_bank(text)
    
    # Route to appropriate parser
    if bank == 'chase':
        transactions = extract_transactions_chase(text, tables)
    elif bank == 'bofa':
        transactions = extract_transactions_bofa(text, tables)
    elif bank in ['wells_fargo', 'wells']:
        transactions = extract_transactions_wells_fargo(text, tables)
    elif bank == 'citibank':
        transactions = extract_transactions_citibank(text, tables)
    elif bank == 'us_bank':
        transactions = extract_transactions_us_bank(text, tables)
    elif bank == 'webster':
        transactions = extract_transactions_webster(text, tables)
    else:
        # Use improved generic parser
        transactions = extract_transactions_generic_improved(text, tables)
        bank = 'generic' if bank == 'unknown' else bank
    
    return bank, transactions


# =============================================================================
# VALIDATION FUNCTION
# =============================================================================

def validate_extraction(transactions: List[Dict], 
                       expected_count: int = None,
                       beginning_balance: float = None,
                       ending_balance: float = None) -> Tuple[bool, List[str]]:
    """
    Validate extraction quality.
    
    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues = []
    
    # Check 1: Transaction count
    if len(transactions) == 0:
        issues.append("NO_TRANSACTIONS: Zero transactions extracted")
    
    # Check 2: Dates
    dates_valid = sum(1 for t in transactions if t.get('date'))
    if transactions and dates_valid < len(transactions) * 0.8:
        issues.append(f"MISSING_DATES: Only {dates_valid}/{len(transactions)} have dates")
    
    # Check 3: Amounts
    amounts_valid = sum(1 for t in transactions 
                       if isinstance(t.get('amount'), (int, float)) and t['amount'] != 0)
    if transactions and amounts_valid < len(transactions) * 0.8:
        issues.append(f"MISSING_AMOUNTS: Only {amounts_valid}/{len(transactions)} have valid amounts")
    
    # Check 4: Balance reconciliation
    if beginning_balance is not None and ending_balance is not None and transactions:
        total_credits = sum(t.get('credit', 0) or 0 for t in transactions)
        total_debits = sum(t.get('debit', 0) or 0 for t in transactions)
        calculated_ending = beginning_balance + total_credits - total_debits
        
        tolerance = abs(ending_balance) * 0.02 + 10  # 2% + $10 tolerance
        if abs(calculated_ending - ending_balance) > tolerance:
            issues.append(f"BALANCE_MISMATCH: Calculated {calculated_ending:.2f} vs stated {ending_balance:.2f}")
    
    # Check 5: Expected count
    if expected_count and transactions:
        if len(transactions) < expected_count * 0.7:
            issues.append(f"TRANSACTION_COUNT_LOW: Got {len(transactions)}, expected ~{expected_count}")
    
    is_valid = len(issues) == 0
    return is_valid, issues
