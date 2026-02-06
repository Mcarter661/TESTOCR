"""
OCR Engine Module
Handles PDF text extraction and bank statement parsing using pdfplumber.
Extracts transactions, account info, and checks for fraud indicators.

Strategy:
1. Try pdfplumber first (fast, works on digital PDFs)
2. If no text found, fall back to pytesseract OCR (slower, works on scanned PDFs)
"""

import pdfplumber
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dateutil import parser as date_parser
import os

from core_logic.bank_parsers import (
    extract_transactions_chase,
    extract_transactions_bofa,
    extract_transactions_wells_fargo,
    extract_transactions_citibank,
    extract_transactions_us_bank,
    extract_transactions_webster,
    extract_transactions_generic_improved,
)

try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


BANK_PATTERNS = {
    'pnc': [r'PNC Bank', r'PNC BANK', r'pnc\.com'],
    'truist': [r'Truist', r'TRUIST', r'BB&T', r'SunTrust'],
    'bofa': [r'Bank of America', r'BANK OF AMERICA', r'bankofamerica\.com', r'Business Advantage'],
    'wells_fargo': [r'Wells Fargo', r'WELLS FARGO', r'wellsfargo\.com', r'Optimize Business'],
    'citibank': [r'CITIBANK', r'CitiBusiness', r'Citibank,?\s+N\.?A\.?', r'Citi CBO'],
    'us_bank': [r'U\.?S\.?\s+Bank', r'US BANK', r'usbank\.com', r'Silver Business'],
    'webster': [r'Webster\s*Bank', r'websterbank\.com', r'PLATINUM\s+BUSINESS\s+ANALYZED'],
    'td_bank': [r'TD Bank', r'TD BANK'],
    'capital_one': [r'Capital One', r'CAPITAL ONE'],
    'regions': [r'Regions Bank', r'REGIONS'],
    'citizens': [r'Citizens Bank', r'CITIZENS'],
    'fifth_third': [r'Fifth Third', r'FIFTH THIRD'],
    'huntington': [r'Huntington', r'HUNTINGTON'],
    'key_bank': [r'KeyBank', r'KEY BANK'],
    'santander': [r'Santander', r'SANTANDER'],
    'bmo': [r'BMO Harris', r'BMO HARRIS'],
    'chase': [r'JPMorgan Chase', r'chase\.com', r'JPMORGAN', r'CHASE', r'Chase Business'],
}

DATE_PATTERNS = [
    r'(\d{1,2}/\d{1,2}/\d{2,4})',
    r'(\d{1,2}-\d{1,2}-\d{2,4})',
    r'(\d{4}-\d{2}-\d{2})',
    r'([A-Za-z]{3}\s+\d{1,2},?\s+\d{4})',
    r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})',
]

AMOUNT_PATTERN = r'[\$]?\s*[\-\(]?\s*[\d,]+\.?\d{0,2}\s*[\)]?'


def _safe_parse_date(date_str: str) -> Optional[str]:
    """Parse a date string into YYYY-MM-DD format, returning None on failure."""
    if not date_str or not date_str.strip():
        return None
    date_str = date_str.strip()
    formats = [
        "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y",
        "%m/%d", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y",
        "%B %d %Y", "%b %d %Y", "%b. %d, %Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            if fmt == "%m/%d":
                dt = dt.replace(year=datetime.now().year)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        dt = date_parser.parse(date_str, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return None


def _parse_amount(amount_str: str) -> float:
    """Parse a currency string into a float."""
    if not amount_str:
        return 0.0
    s = str(amount_str).strip()
    negative = False
    if s.startswith('(') and s.endswith(')'):
        negative = True
        s = s[1:-1]
    if '-' in s:
        negative = True
    s = s.replace('$', '').replace(',', '').replace('-', '').replace(' ', '')
    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return 0.0


def _extract_address(text: str) -> Optional[str]:
    """Try to extract a business address from the statement header."""
    patterns = [
        r'(?:Address|Mailing)[:\s]*([\w\s]+\n[\w\s,]+\s+\d{5}(?:-\d{4})?)',
        r'(\d+\s+[\w\s]+(?:St|Ave|Blvd|Rd|Dr|Ln|Way|Ct|Pl)\.?[,\s]+[\w\s]+,?\s*[A-Z]{2}\s+\d{5})',
    ]
    for pat in patterns:
        match = re.search(pat, text)
        if match:
            addr = match.group(1).strip()
            addr = re.sub(r'\s+', ' ', addr)
            return addr
    return None


def _infer_transaction_signs(transactions: list, opening_balance: float, text: str) -> list:
    """If amounts lack sign info, try to infer from descriptions and balance."""
    deposit_indicators = [
        "DEPOSIT", "CREDIT", "WIRE IN", "ACH CREDIT", "DIRECT DEP",
        "MOBILE DEP", "INTEREST EARNED", "REFUND",
    ]
    withdrawal_indicators = [
        "DEBIT", "WITHDRAWAL", "CHECK", "FEE", "CHARGE",
        "WIRE OUT", "ACH DEBIT", "PAYMENT", "PURCHASE",
    ]

    all_positive = all(t["amount"] >= 0 for t in transactions if t["amount"] != 0)
    if not all_positive:
        return transactions

    for txn in transactions:
        desc_upper = txn["description"].upper()
        is_deposit = any(ind in desc_upper for ind in deposit_indicators)
        is_withdrawal = any(ind in desc_upper for ind in withdrawal_indicators)

        if is_withdrawal and not is_deposit and txn["amount"] > 0:
            txn["amount"] = -txn["amount"]

    return transactions


def _assign_running_balances(transactions: list, opening_balance: float) -> list:
    """Fill in running balances where missing."""
    has_balances = any(t.get("running_balance") is not None for t in transactions)
    if has_balances:
        return transactions

    if opening_balance == 0.0:
        return transactions

    running = opening_balance
    for txn in transactions:
        running += txn["amount"]
        txn["running_balance"] = round(running, 2)
    return transactions


def extract_text_from_pdf(pdf_path: str) -> Tuple[str, List[List]]:
    """
    Extract raw text and table data from a PDF bank statement using pdfplumber.
    Returns tuple of (full_text, all_tables).
    """
    full_text = []
    all_tables = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text.append(text)
                
                tables = page.extract_tables()
                for table in tables:
                    if table:
                        all_tables.extend([row for row in table if row])
                        for row in table:
                            if row:
                                row_text = ' | '.join([str(cell) if cell else '' for cell in row])
                                full_text.append(row_text)
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
        return "", []
    
    return '\n'.join(full_text), all_tables


def extract_text_ocr(pdf_path: str) -> str:
    """Extract text using pytesseract OCR (for scanned/image-based PDFs)."""
    if not OCR_AVAILABLE:
        return ""
    try:
        images = convert_from_path(pdf_path, dpi=300)
        text_parts = []
        for image in images:
            page_text = pytesseract.image_to_string(image)
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts)
    except Exception:
        return ""


def check_pdf_metadata(pdf) -> list:
    """Check PDF creator/producer fields for editing software."""
    flags = []
    metadata = pdf.metadata or {}
    fraud_tools = ["PHOTOSHOP", "ADOBE PHOTOSHOP", "CANVA", "GIMP", "PIXLR",
                   "ILLUSTRATOR", "INKSCAPE", "AFFINITY"]

    creator = str(metadata.get("Creator", "")).upper()
    producer = str(metadata.get("Producer", "")).upper()

    for tool in fraud_tools:
        if tool in creator:
            flags.append(f"FRAUD WARNING: PDF Creator field contains '{tool}' — possible statement manipulation")
        if tool in producer:
            flags.append(f"FRAUD WARNING: PDF Producer field contains '{tool}' — possible statement manipulation")

    mod_date = metadata.get("ModDate", "")
    create_date = metadata.get("CreationDate", "")
    if mod_date and create_date and mod_date != create_date:
        flags.append(f"NOTICE: PDF was modified after creation (Created: {create_date}, Modified: {mod_date})")

    return flags


def validate_extraction(transactions: list, opening_bal: float, closing_bal: float) -> list:
    """Validate extracted transactions against opening/closing balances."""
    errors = []
    if not transactions:
        errors.append("No transactions extracted")
        return errors

    if opening_bal == 0.0 and closing_bal == 0.0:
        return errors

    total_amount = sum(t.get("amount", 0) for t in transactions)
    expected_closing = opening_bal + total_amount

    if closing_bal > 0 and abs(expected_closing - closing_bal) > 1.00:
        errors.append(
            f"Balance validation warning: Opening({opening_bal:.2f}) + "
            f"Transactions({total_amount:.2f}) = {expected_closing:.2f}, "
            f"but Closing = {closing_bal:.2f} (diff: {abs(expected_closing - closing_bal):.2f})"
        )

    return errors


def detect_bank_format(text: str) -> str:
    """
    Detect which bank format the statement belongs to.
    Uses a two-pass approach:
      1. Check ONLY the header/letterhead area (first ~1500 chars) to avoid
         false matches from transaction descriptions mentioning other banks.
      2. Fall back to full-text scan only if no match found in the header.
    """
    header_text = text[:1500]

    for bank, patterns in BANK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, header_text, re.IGNORECASE):
                return bank

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


def extract_transactions_from_tables(tables: List[List]) -> List[Dict]:
    """
    Extract transactions from structured table data.
    This is more reliable than text parsing for capturing full descriptions.
    """
    transactions = []
    
    for row in tables:
        if not row or len(row) < 2:
            continue
        
        cells = [str(cell).strip() if cell else '' for cell in row]
        
        if any(header in ' '.join(cells).upper() for header in ['DATE', 'DESCRIPTION', 'AMOUNT', 'BALANCE', 'DEBIT', 'CREDIT', 'DEPOSITS', 'WITHDRAWALS']):
            continue
        
        date_val = None
        date_idx = -1
        for i, cell in enumerate(cells):
            for date_pattern in DATE_PATTERNS:
                match = re.search(date_pattern, cell)
                if match:
                    date_val = parse_date(match.group(1))
                    if date_val:
                        date_idx = i
                        break
            if date_val:
                break
        
        if not date_val:
            continue
        
        amounts = []
        amount_indices = []
        for i, cell in enumerate(cells):
            if i == date_idx:
                continue
            amt_match = re.search(r'[\$]?\s*[\-\(]?\s*([\d,]+\.\d{2})\s*[\)]?', cell)
            if amt_match:
                parsed_amt = parse_amount(cell)
                if parsed_amt is not None:
                    amounts.append((i, cell, parsed_amt))
                    amount_indices.append(i)
        
        description_parts = []
        for i, cell in enumerate(cells):
            if i == date_idx or i in amount_indices:
                continue
            if cell and len(cell) > 1 and not re.match(r'^[\d\.\$\-\(\),\s]+$', cell):
                description_parts.append(cell)
        
        description = ' '.join(description_parts).strip()
        
        if not description:
            for i, cell in enumerate(cells):
                if i != date_idx and cell and len(cell) > 3:
                    if not re.match(r'^[\d\.\$\-\(\),\s]+$', cell):
                        description = cell
                        break
        
        if description and amounts:
            amount_val = amounts[-1][2]
            is_debit = '-' in amounts[-1][1] or '(' in amounts[-1][1]
            
            if len(amounts) >= 2:
                debit_amt = abs(amounts[0][2]) if amounts[0][2] else 0
                credit_amt = abs(amounts[1][2]) if len(amounts) > 1 and amounts[1][2] else 0
                if debit_amt > 0 and credit_amt == 0:
                    is_debit = True
                    amount_val = debit_amt
                elif credit_amt > 0 and debit_amt == 0:
                    is_debit = False
                    amount_val = credit_amt
            
            transactions.append({
                'date': date_val.strftime('%Y-%m-%d'),
                'description': description[:200],
                'amount': abs(amount_val),
                'debit': abs(amount_val) if is_debit else 0,
                'credit': abs(amount_val) if not is_debit else 0,
                'balance': None,
                'raw_line': ' | '.join(cells)[:300]
            })
    
    return transactions


def extract_transactions_generic(text: str, tables: List[List] = None) -> List[Dict]:
    """
    Generic transaction extraction for unknown bank formats.
    Uses table data if available, falls back to text parsing.
    """
    if tables:
        table_transactions = extract_transactions_from_tables(tables)
        if table_transactions:
            return table_transactions
    
    transactions = []
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 10:
            continue
        
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            date_val = None
            amounts = []
            description_parts = []
            
            for part in parts:
                if not part:
                    continue
                
                if not date_val:
                    for date_pattern in DATE_PATTERNS:
                        match = re.search(date_pattern, part)
                        if match:
                            date_val = parse_date(match.group(1))
                            break
                    if date_val:
                        continue
                
                amt_match = re.search(r'[\$]?\s*[\-\(]?\s*([\d,]+\.\d{2})\s*[\)]?', part)
                if amt_match and re.match(r'^[\$\d\.\-\(\),\s]+$', part.strip()):
                    parsed_amt = parse_amount(part)
                    if parsed_amt is not None:
                        amounts.append((part, parsed_amt))
                        continue
                
                if len(part) > 2 and not re.match(r'^[\d\.\$\-\(\),\s]+$', part):
                    description_parts.append(part)
            
            description = ' '.join(description_parts).strip()
            
            if date_val and description and amounts:
                amount_val = amounts[-1][1]
                is_debit = '-' in amounts[-1][0] or '(' in amounts[-1][0]
                
                transactions.append({
                    'date': date_val.strftime('%Y-%m-%d'),
                    'description': description[:200],
                    'amount': abs(amount_val),
                    'debit': abs(amount_val) if is_debit else 0,
                    'credit': abs(amount_val) if not is_debit else 0,
                    'balance': None,
                    'raw_line': line[:300]
                })
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
                        last_amount = amounts[-1]
                        last_pos = remaining.rfind(last_amount)
                        
                        description = remaining[:last_pos].strip()
                        
                        for amt in amounts[:-1]:
                            pos = description.rfind(amt)
                            if pos > len(description) * 0.6:
                                description = description[:pos].strip()
                        
                        description = re.sub(r'\s+[\d,]+\.\d{2}\s*$', '', description).strip()
                        description = re.sub(r'^\d+\s+', '', description).strip()
                        
                        amount_val = parse_amount(last_amount)
                        
                        if description and len(description) > 2 and amount_val is not None:
                            is_debit = '-' in last_amount or '(' in last_amount
                            
                            transactions.append({
                                'date': parsed_date.strftime('%Y-%m-%d'),
                                'description': description[:200],
                                'amount': abs(amount_val),
                                'debit': abs(amount_val) if is_debit else 0,
                                'credit': abs(amount_val) if not is_debit else 0,
                                'balance': None,
                                'raw_line': line[:300]
                            })
                            break
    
    return transactions


def extract_transactions_truist(text: str, tables: List[List] = None) -> List[Dict]:
    """
    Truist-specific transaction parsing.
    Truist format: MM/DD (no year), sections for Checks (multi-column),
    Other withdrawals (debits), Deposits/credits.
    """
    transactions = []
    lines = text.split('\n')
    
    current_year = datetime.now().year
    
    period_match = re.search(r'(?:as of|For)\s*(\d{2}/\d{2}/\d{4})', text)
    if period_match:
        try:
            d = datetime.strptime(period_match.group(1), '%m/%d/%Y')
            current_year = d.year
        except:
            pass
    
    end_match = re.search(r'new balance as of\s*(\d{2}/\d{2}/\d{4})', text)
    if end_match:
        try:
            d = datetime.strptime(end_match.group(1), '%m/%d/%Y')
            current_year = d.year
        except:
            pass
    
    section_type = None
    in_checks = False
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        
        upper = line_stripped.upper()
        
        if re.match(r'^CHECKS$', upper) or upper.startswith('CHECKS') and 'CHECK#' not in upper and 'CHECKING' not in upper and 'AMOUNT' not in upper:
            if 'DEDUCTION' not in upper and 'CHARGE' not in upper and 'WITHDRAWAL' not in upper:
                section_type = 'debit'
                in_checks = True
                continue
        
        if 'DATE' in upper and 'CHECK#' in upper and 'AMOUNT' in upper:
            continue
        
        if 'OTHERWITHDRAWALS' in upper.replace(' ', '') or ('OTHER' in upper and 'WITHDRAWAL' in upper) or ('DEBITS' in upper and 'SERVICE' in upper):
            section_type = 'debit'
            in_checks = False
            continue
        
        if upper.startswith('DATE') and 'DESCRIPTION' in upper and 'AMOUNT' in upper:
            continue
        
        if 'DEPOSITS' in upper.replace(' ', '') and ('CREDIT' in upper.replace(' ', '') or 'INTEREST' in upper.replace(' ', '')):
            section_type = 'credit'
            in_checks = False
            continue
        
        if 'TOTALCHECKS' in upper.replace(' ', '') or 'TOTALOTHER' in upper.replace(' ', '') or 'TOTALDEPOSITS' in upper.replace(' ', ''):
            continue
        
        if upper.startswith('ACCOUNTSUMMARY') or upper.startswith('YOUR PREVIOUS') or upper.startswith('YOUR NEW'):
            continue
        
        if 'CONTINUED' in upper or upper.startswith('§') or upper.startswith('PAGE') or 'TRUIST DYNAMIC' in upper:
            continue
        
        if re.match(r'^\d{10,}$', line_stripped) or re.match(r'^\d{3}\d+MAV$', line_stripped.replace(' ', '')):
            continue
        
        if re.match(r'^(FL|Page)\s', line_stripped) or line_stripped.startswith('¡'):
            continue
        
        if '*' == line_stripped.strip():
            continue
        
        if re.match(r'^\*indicates', line_stripped):
            continue
        
        if section_type is None:
            continue
        
        if in_checks:
            check_entries = re.findall(r'(\d{2}/\d{2})\s+(\d+)\s+([\d,]+\.\d{2})', line_stripped)
            for entry in check_entries:
                date_str, check_num, amount_str = entry
                try:
                    amount = float(amount_str.replace(',', ''))
                except:
                    continue
                full_date = f"{date_str}/{current_year}"
                parsed_date = parse_date(full_date)
                if not parsed_date:
                    continue
                transactions.append({
                    'date': parsed_date.strftime('%Y-%m-%d'),
                    'description': f"Check #{check_num}",
                    'amount': amount,
                    'debit': amount,
                    'credit': 0,
                    'balance': None,
                    'raw_line': line_stripped[:300]
                })
            continue
        
        match = re.match(r'^(\d{2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s*$', line_stripped)
        if match:
            date_str = match.group(1)
            description = match.group(2).strip()
            amount_str = match.group(3)
            
            try:
                amount = float(amount_str.replace(',', ''))
            except:
                continue
            
            full_date = f"{date_str}/{current_year}"
            parsed_date = parse_date(full_date)
            if not parsed_date:
                continue
            
            description = re.sub(r'\s+\d+\s*$', '', description).strip()
            
            is_credit = section_type == 'credit'
            is_debit = section_type == 'debit'
            
            transactions.append({
                'date': parsed_date.strftime('%Y-%m-%d'),
                'description': description[:200],
                'amount': amount,
                'debit': amount if is_debit else 0,
                'credit': amount if is_credit else 0,
                'balance': None,
                'raw_line': line_stripped[:300]
            })
    
    return transactions


def extract_transactions_pnc(text: str, tables: List[List] = None) -> List[Dict]:
    """
    PNC Bank-specific transaction parsing.
    PNC format sections: Deposits, ACH Additions (credits), Other Additions (credits),
    Checks (debits, multi-column), Debit Card Purchases, POS Purchases,
    ATM Transactions, ACH Deductions, Service Charges, Other Deductions.
    """
    transactions = []
    lines = text.split('\n')
    
    current_year = datetime.now().year
    
    period_match = re.search(r'Period\s+(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})', text)
    if period_match:
        try:
            end_date = datetime.strptime(period_match.group(2), '%m/%d/%Y')
            current_year = end_date.year
        except:
            pass
    
    section_type = None
    in_checks = False
    
    skip_patterns = [
        r'^Date\s+Transaction\s+Reference',
        r'^posted\s+Amount\s+description',
        r'^Date\s+Check\s+Reference',
        r'^posted\s+number\s+Amount',
        r'continued on next page',
        r'\(cid:\d+\)',
        r'^Business Checking',
        r'^For 24-hour',
        r'^pnc\.com',
        r'^Primary Account Number',
        r'^Page \d+ of \d+',
        r'^Effective \d{2}-\d{2}',
        r'^\d{3}-\d{7}',
        r'^[A-Z]{3}\s+\w.{0,40}Mav$',
        r'^Payoneer\s',
        r'^ADP\s',
        r'Gap in check sequence',
        r'^Detail of Services',
        r'^Note:',
        r'^\*\* Combined',
        r'^Description\s+Volume\s+Amount',
        r'^Monthly',
        r'^Total',
        r'^Member FDIC',
    ]
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        
        upper = line_stripped.upper()
        
        if 'DAILY BALANCE' in upper:
            section_type = 'skip'
            in_checks = False
            continue
        elif upper.startswith('DEPOSITS') and 'OTHER' not in upper and 'DEDUCTION' not in upper:
            section_type = 'credit'
            in_checks = False
            continue
        elif 'ACH ADDITIONS' in upper:
            section_type = 'credit'
            in_checks = False
            continue
        elif 'OTHER ADDITIONS' in upper:
            section_type = 'credit'
            in_checks = False
            continue
        elif 'CHECKS AND' in upper or upper.startswith('CHECKS'):
            section_type = 'debit'
            in_checks = True
            continue
        elif 'DEBIT CARD PURCHASE' in upper:
            section_type = 'debit'
            in_checks = False
            continue
        elif 'POS PURCHASE' in upper:
            section_type = 'debit'
            in_checks = False
            continue
        elif 'ATM' in upper and ('DEBIT CARD' in upper or 'TRANSACTION' in upper or 'MISC' in upper):
            section_type = 'debit'
            in_checks = False
            continue
        elif 'ACH DEDUCTION' in upper:
            section_type = 'debit'
            in_checks = False
            continue
        elif 'SERVICE CHARGE' in upper and 'PERIOD' not in upper:
            section_type = 'debit'
            in_checks = False
            continue
        elif 'OTHER DEDUCTION' in upper:
            section_type = 'debit'
            in_checks = False
            continue
        elif 'ACTIVITY DETAIL' in upper or 'BALANCE SUMMARY' in upper or 'OVERDRAFT' in upper:
            continue
        elif 'DETAIL OF SERVICES' in upper:
            section_type = 'skip'
            in_checks = False
            continue
        
        if section_type == 'skip':
            continue
        
        should_skip = False
        for pat in skip_patterns:
            if re.search(pat, line_stripped, re.IGNORECASE):
                should_skip = True
                break
        if should_skip:
            continue
        
        if in_checks:
            check_entries = re.findall(r'(\d{2}/\d{2})\s+(\d+\s*\*?\s*)\s+([\d,]+\.\d{2})\s+(\d+)', line_stripped)
            for entry in check_entries:
                date_str, check_num, amount_str, ref_num = entry
                try:
                    amount = float(amount_str.replace(',', ''))
                except:
                    continue
                full_date = f"{date_str}/{current_year}"
                parsed_date = parse_date(full_date)
                if not parsed_date:
                    continue
                chk = check_num.strip().replace('*', '').strip()
                desc = f"Check #{chk}" if chk and chk != '000' else f"Check (counter)"
                transactions.append({
                    'date': parsed_date.strftime('%Y-%m-%d'),
                    'description': desc,
                    'amount': amount,
                    'debit': amount,
                    'credit': 0,
                    'balance': None,
                    'raw_line': line_stripped[:300]
                })
            continue
        
        match = re.match(r'^(\d{2}/\d{2})\s+([\d,]+\.\d{2})([-]?)\s+(.+)', line_stripped)
        if match:
            date_str = match.group(1)
            amount_str = match.group(2)
            neg_sign = match.group(3)
            description = match.group(4).strip()
            
            try:
                amount = float(amount_str.replace(',', ''))
            except:
                continue
            
            full_date = f"{date_str}/{current_year}"
            parsed_date = parse_date(full_date)
            if not parsed_date:
                continue
            
            if section_type == 'credit':
                is_credit = True
                is_debit = False
            elif section_type == 'debit':
                is_credit = False
                is_debit = True
            else:
                desc_lower = description.lower()
                if any(kw in desc_lower for kw in ['incoming wire', 'pymt proc', 'deposit',
                                                     'reverse corporate ach debit',
                                                     'reverse check', 'item return']):
                    is_credit = True
                    is_debit = False
                else:
                    is_debit = True
                    is_credit = False
            
            if neg_sign == '-':
                is_debit = True
                is_credit = False
            
            transactions.append({
                'date': parsed_date.strftime('%Y-%m-%d'),
                'description': description[:200],
                'amount': amount,
                'debit': amount if is_debit else 0,
                'credit': amount if is_credit else 0,
                'balance': None,
                'raw_line': line_stripped[:300]
            })
    
    return transactions


def _extract_transactions_chase_legacy(text: str, tables: List[List] = None) -> List[Dict]:
    """
    Legacy Chase parser - kept as fallback. Primary Chase parser is in bank_parsers.py.
    """
    if tables:
        table_transactions = extract_transactions_from_tables(tables)
        if table_transactions:
            return table_transactions
    
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
                        'description': description[:200],
                        'amount': abs(amount),
                        'debit': abs(amount) if amount < 0 else 0,
                        'credit': amount if amount > 0 else 0,
                        'balance': balance,
                        'raw_line': line[:300]
                    })
    
    if not transactions:
        transactions = extract_transactions_generic(text, tables)
    
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


def parse_transactions(text: str, bank_format: str, tables: List[List] = None) -> List[Dict]:
    """
    Parse transaction data from extracted text based on bank format.
    Routes to bank-specific parsers or improved generic fallback.
    """
    if bank_format == 'pnc':
        return extract_transactions_pnc(text, tables)
    elif bank_format == 'truist':
        return extract_transactions_truist(text, tables)
    elif bank_format == 'chase':
        return extract_transactions_chase(text, tables)
    elif bank_format in ['bofa', 'bank_of_america']:
        return extract_transactions_bofa(text, tables)
    elif bank_format in ['wells_fargo', 'wells']:
        return extract_transactions_wells_fargo(text, tables)
    elif bank_format in ['citibank', 'citi']:
        return extract_transactions_citibank(text, tables)
    elif bank_format == 'us_bank':
        return extract_transactions_us_bank(text, tables)
    elif bank_format == 'webster':
        return extract_transactions_webster(text, tables)
    else:
        transactions = extract_transactions_generic_improved(text, tables)
        if not transactions:
            transactions = extract_transactions_generic(text, tables)
        return transactions


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


def _normalize_transactions(transactions: List[Dict]) -> List[Dict]:
    """Convert bank-parser transaction format to normalized format with amount/running_balance."""
    for txn in transactions:
        if 'amount' in txn and 'debit' in txn and 'credit' in txn:
            credit = txn.get('credit', 0) or 0
            debit = txn.get('debit', 0) or 0
            if credit > 0:
                txn['amount'] = credit
            elif debit > 0:
                txn['amount'] = -debit
        if 'running_balance' not in txn:
            txn['running_balance'] = txn.get('balance', None)
    return transactions


def process_bank_statement(pdf_path: str) -> Dict:
    """
    Main function to process a complete bank statement.
    Returns complete parsed data including account info and transactions.
    """
    warnings = []
    errors = []
    fraud_flags = []
    extraction_method = "pdfplumber"

    if not os.path.exists(pdf_path):
        return {
            'error': f'File not found: {pdf_path}',
            'success': False
        }

    raw_text = ""
    tables = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            fraud_flags = check_pdf_metadata(pdf)

            text_parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

                page_tables = page.extract_tables()
                for table in page_tables:
                    if table:
                        tables.extend([row for row in table if row])
                        for row in table:
                            if row:
                                row_text = ' | '.join([str(cell) if cell else '' for cell in row])
                                text_parts.append(row_text)

            raw_text = '\n'.join(text_parts)
    except Exception as e:
        errors.append(f"PDF extraction error: {str(e)}")

    if not raw_text or len(raw_text.strip()) < 100:
        warnings.append("pdfplumber found no text, falling back to OCR")
        ocr_text = extract_text_ocr(pdf_path)
        if ocr_text and len(ocr_text.strip()) > 100:
            raw_text = ocr_text
            extraction_method = "pytesseract_ocr"
        else:
            error_msg = (
                "Both pdfplumber and OCR failed to extract text"
                if OCR_AVAILABLE else
                "No text extracted (pytesseract not installed for OCR fallback)"
            )
            errors.append(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'fraud_flags': fraud_flags,
                'warnings': warnings,
                'errors': errors,
            }

    bank_format = detect_bank_format(raw_text)

    transactions = parse_transactions(raw_text, bank_format, tables)

    transactions = _normalize_transactions(transactions)

    account_info = extract_account_info(raw_text, bank_format)

    opening_balance = account_info.get('opening_balance') or 0.0
    closing_balance = account_info.get('closing_balance') or 0.0

    transactions = _infer_transaction_signs(transactions, opening_balance, raw_text)

    transactions = _assign_running_balances(transactions, opening_balance)

    address_extracted = _extract_address(raw_text)

    summary_stats = calculate_summary_stats(transactions)

    validation_errors = validate_extraction(transactions, opening_balance, closing_balance)
    errors.extend(validation_errors)

    return {
        'success': True,
        'filename': os.path.basename(pdf_path),
        'bank_format': bank_format,
        'account_info': account_info,
        'transactions': transactions,
        'summary': summary_stats,
        'raw_text_length': len(raw_text),
        'page_count': raw_text.count('\f') + 1 if '\f' in raw_text else 1,
        'fraud_flags': fraud_flags,
        'address_extracted': address_extracted,
        'extraction_method': extraction_method,
        'warnings': warnings,
        'errors': errors,
        'opening_balance': opening_balance,
        'closing_balance': closing_balance,
    }
