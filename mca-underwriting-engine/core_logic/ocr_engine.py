"""
OCR Engine - PDF text extraction and bank statement parsing.
Extracts transactions, account info, and checks for fraud indicators.

Strategy:
1. Try pdfplumber first (fast, works on digital PDFs)
2. If no text found, fall back to pytesseract OCR (slower, works on scanned PDFs)
"""

import pdfplumber
import re
import os
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from typing import List, Dict, Optional, Tuple

try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


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


def extract_from_pdf(pdf_path: str) -> dict:
    """
    Main entry point. Extract all data from a bank statement PDF.

    Strategy:
    1. Try pdfplumber first (fast, works on digital PDFs)
    2. If no text found, fall back to pytesseract OCR (slower, works on scanned PDFs)
    """
    result = {
        "success": False,
        "extraction_method": None,
        "bank_name": "Unknown",
        "account_number": "",
        "account_type": "operating",
        "statement_period": {"start": None, "end": None},
        "opening_balance": 0.0,
        "closing_balance": 0.0,
        "transactions": [],
        "address_extracted": None,
        "fraud_flags": [],
        "errors": [],
        "warnings": [],
    }

    if not os.path.exists(pdf_path):
        result["errors"].append(f"File not found: {pdf_path}")
        return result

    try:
        with pdfplumber.open(pdf_path) as pdf:
            result["fraud_flags"] = check_pdf_metadata(pdf)

            all_text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                all_text += page_text + "\n"

            # If pdfplumber got text, use it
            if all_text.strip() and len(all_text.strip()) > 100:
                result["extraction_method"] = "pdfplumber"
            else:
                # Fall back to pytesseract OCR
                result["warnings"].append("pdfplumber found no text, falling back to OCR")
                ocr_text = extract_text_ocr(pdf_path)
                if ocr_text and len(ocr_text.strip()) > 100:
                    all_text = ocr_text
                    result["extraction_method"] = "pytesseract_ocr"
                else:
                    result["errors"].append(
                        "Both pdfplumber and OCR failed to extract text"
                        if OCR_AVAILABLE else
                        "No text extracted (pytesseract not installed for OCR fallback)"
                    )
                    return result

            bank_info = identify_bank(all_text)
            result["bank_name"] = bank_info["bank_name"]
            result["account_number"] = bank_info["account_number"]
            result["account_type"] = bank_info["account_type"]
            result["statement_period"] = bank_info["statement_period"]
            result["opening_balance"] = bank_info["opening_balance"]
            result["closing_balance"] = bank_info["closing_balance"]
            result["address_extracted"] = bank_info["address"]

            # Try table extraction first (only works with pdfplumber method)
            transactions = []
            if result["extraction_method"] == "pdfplumber":
                transactions = extract_transactions(pdf)

            # Fall back to text-based extraction
            if not transactions:
                transactions = extract_transactions_from_text(all_text)

            if transactions:
                transactions = _infer_transaction_signs(
                    transactions,
                    result["opening_balance"],
                    all_text
                )
                transactions = _assign_running_balances(
                    transactions,
                    result["opening_balance"]
                )

            result["transactions"] = transactions
            result["errors"].extend(
                validate_extraction(transactions, result["opening_balance"], result["closing_balance"])
            )
            result["success"] = len(transactions) > 0

    except Exception as e:
        result["errors"].append(f"PDF extraction error: {str(e)}")

    return result


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


def identify_bank(text: str) -> dict:
    """Detect bank name, account info, and statement period from text."""
    text_upper = text.upper()

    bank_patterns = {
        "JPMorgan Chase": ["JPMORGAN CHASE", "CHASE BANK", "CHASE BUSINESS", "J.P. MORGAN"],
        "Wells Fargo": ["WELLS FARGO"],
        "Bank of America": ["BANK OF AMERICA", "BANKOFAMERICA"],
        "Truist": ["TRUIST BANK", "TRUIST"],
        "PNC Bank": ["PNC BANK", "PNC FINANCIAL"],
        "US Bank": ["U.S. BANK", "US BANK", "U.S. BANCORP"],
        "TD Bank": ["TD BANK"],
        "Capital One": ["CAPITAL ONE"],
        "Citizens Bank": ["CITIZENS BANK", "CITIZENS FINANCIAL"],
        "Huntington": ["HUNTINGTON NATIONAL", "HUNTINGTON BANK"],
        "Regions Bank": ["REGIONS BANK", "REGIONS FINANCIAL"],
        "Fifth Third Bank": ["FIFTH THIRD"],
        "M&T Bank": ["M&T BANK", "M & T BANK"],
        "KeyBank": ["KEYBANK", "KEY BANK"],
        "BMO": ["BMO HARRIS", "BMO BANK"],
        "Santander": ["SANTANDER"],
        "Citibank": ["CITIBANK", "CITI BANK", "CITIGROUP"],
        "Mercury": ["MERCURY BANK", "MERCURY"],
        "Relay Financial": ["RELAY FINANCIAL", "RELAY"],
        "BlueVine": ["BLUEVINE BUSINESS"],
        "Novo": ["NOVO BANK", "NOVO PLATFORM"],
        "Axos Bank": ["AXOS BANK", "AXOS"],
    }

    bank_name = "Unknown"
    for name, patterns in bank_patterns.items():
        for pattern in patterns:
            if pattern in text_upper:
                bank_name = name
                break
        if bank_name != "Unknown":
            break

    account_number = ""
    acct_patterns = [
        r'(?:Account|Acct)[\s.]*(?:#|Number|No\.?)[\s:]*(?:\*+|x+|X+)?(\d{4})',
        r'(?:Account|Acct)\s+(?:ending\s+(?:in\s+)?)(\d{4})',
        r'(?:\*{3,}|x{3,}|X{3,})(\d{4})',
    ]
    for pat in acct_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            account_number = match.group(1)
            break

    period = {"start": None, "end": None}
    period_patterns = [
        r'[Ss]tatement\s+[Pp]eriod[:\s]+(\w+\.?\s+\d{1,2},?\s+\d{4})\s*(?:to|through|thru|-|–)\s*(\w+\.?\s+\d{1,2},?\s+\d{4})',
        r'[Ss]tatement\s+[Pp]eriod[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:to|through|thru|-|–)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'[Ff]or\s+[Pp]eriod[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:to|through|thru|-|–)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:to|through|thru|-|–)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(\w+\.?\s+\d{1,2},?\s+\d{4})\s*(?:to|through|thru|-|–)\s*(\w+\.?\s+\d{1,2},?\s+\d{4})',
    ]
    for pat in period_patterns:
        match = re.search(pat, text)
        if match:
            period["start"] = _safe_parse_date(match.group(1))
            period["end"] = _safe_parse_date(match.group(2))
            if period["start"] and period["end"]:
                break

    opening = 0.0
    closing = 0.0
    open_pats = [
        r'(?:Beginning|Opening|Previous|Starting)\s+[Bb]alance[:\s]*\$?([\d,]+\.\d{2})',
        r'[Bb]alance\s+[Ff]orward[:\s]*\$?([\d,]+\.\d{2})',
    ]
    close_pats = [
        r'(?:Ending|Closing|New|Final)\s+[Bb]alance[:\s]*\$?([\d,]+\.\d{2})',
        r'[Ss]tatement\s+[Bb]alance[:\s]*\$?([\d,]+\.\d{2})',
    ]
    for pat in open_pats:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            opening = _parse_amount(match.group(1))
            break
    for pat in close_pats:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            closing = _parse_amount(match.group(1))
            break

    account_type = "operating"
    type_upper = text_upper
    if any(k in type_upper for k in ["PAYROLL", "PAYROLL ACCOUNT"]):
        account_type = "payroll"
    elif any(k in type_upper for k in ["SAVINGS", "SAVE", "MONEY MARKET"]):
        account_type = "savings"

    address = _extract_address(text)

    return {
        "bank_name": bank_name,
        "account_number": account_number,
        "account_type": account_type,
        "statement_period": period,
        "opening_balance": opening,
        "closing_balance": closing,
        "address": address,
    }


def extract_transactions(pdf) -> list:
    """Try pdfplumber table extraction across all pages."""
    all_txns = []
    for page in pdf.pages:
        tables = page.extract_tables()
        if not tables:
            continue
        for table in tables:
            txns = _parse_table(table)
            all_txns.extend(txns)
    return all_txns


def extract_transactions_from_text(text: str) -> list:
    """Fall back to regex-based line-by-line transaction extraction."""
    transactions = []
    lines = text.split('\n')

    date_pattern = re.compile(
        r'^(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s+'
    )
    amount_pattern = re.compile(r'-?\$?[\d,]+\.\d{2}')

    pending_description = None
    pending_date = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        date_match = date_pattern.match(line)
        if not date_match:
            if pending_description is not None:
                amounts = amount_pattern.findall(line)
                if amounts:
                    amount_val = _parse_amount(amounts[0])
                    balance_val = _parse_amount(amounts[-1]) if len(amounts) > 1 else None
                    transactions.append({
                        "date": pending_date,
                        "description": pending_description,
                        "amount": amount_val,
                        "running_balance": balance_val,
                    })
                    pending_description = None
                    pending_date = None
                else:
                    pending_description += " " + line
            continue

        date_str = date_match.group(1)
        rest = line[date_match.end():].strip()

        amounts_in_rest = amount_pattern.findall(rest)
        if not amounts_in_rest:
            parsed_d = _safe_parse_date(date_str)
            if parsed_d:
                pending_date = parsed_d
                pending_description = rest
            continue

        first_amt_idx = rest.find(amounts_in_rest[0])
        description = rest[:first_amt_idx].strip()

        parsed_date = _safe_parse_date(date_str)
        if not parsed_date:
            continue

        if not description:
            description = "UNKNOWN"

        parsed_amounts = [_parse_amount(a) for a in amounts_in_rest]

        if len(parsed_amounts) == 1:
            amount = parsed_amounts[0]
            balance = None
        elif len(parsed_amounts) == 2:
            amount = parsed_amounts[0]
            balance = parsed_amounts[1]
        else:
            amount = parsed_amounts[0]
            balance = parsed_amounts[-1]

        transactions.append({
            "date": parsed_date,
            "description": description,
            "amount": amount,
            "running_balance": balance,
        })
        pending_description = None
        pending_date = None

    return transactions


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


# ── Private helpers ───────────────────────────────────────────────────

def _parse_table(table: list) -> list:
    """Parse a pdfplumber-extracted table into transaction dicts."""
    if not table or len(table) < 2:
        return []

    header_row = table[0]
    if header_row is None:
        return []

    headers = [str(h).strip().upper() if h else "" for h in header_row]

    date_col = _find_col(headers, ["DATE", "POSTED", "POST DATE", "TRANS DATE"])
    desc_col = _find_col(headers, ["DESCRIPTION", "DETAILS", "TRANSACTION", "MEMO"])
    debit_col = _find_col(headers, ["DEBIT", "DEBITS", "WITHDRAWALS", "WITHDRAWAL", "CHARGES"])
    credit_col = _find_col(headers, ["CREDIT", "CREDITS", "DEPOSITS", "DEPOSIT", "ADDITIONS"])
    amount_col = _find_col(headers, ["AMOUNT"])
    balance_col = _find_col(headers, ["BALANCE", "RUNNING BALANCE", "ENDING BALANCE"])

    if date_col is None:
        return []

    transactions = []
    for row in table[1:]:
        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        date_val = str(row[date_col]).strip() if date_col < len(row) and row[date_col] else ""
        parsed_date = _safe_parse_date(date_val)
        if not parsed_date:
            continue

        desc = ""
        if desc_col is not None and desc_col < len(row) and row[desc_col]:
            desc = str(row[desc_col]).strip()

        amount = 0.0
        if amount_col is not None and amount_col < len(row) and row[amount_col]:
            amount = _parse_amount(str(row[amount_col]))
        elif debit_col is not None or credit_col is not None:
            debit_val = 0.0
            credit_val = 0.0
            if debit_col is not None and debit_col < len(row) and row[debit_col]:
                debit_val = abs(_parse_amount(str(row[debit_col])))
            if credit_col is not None and credit_col < len(row) and row[credit_col]:
                credit_val = abs(_parse_amount(str(row[credit_col])))
            if credit_val > 0:
                amount = credit_val
            elif debit_val > 0:
                amount = -debit_val

        balance = None
        if balance_col is not None and balance_col < len(row) and row[balance_col]:
            balance = _parse_amount(str(row[balance_col]))

        if desc or amount != 0:
            transactions.append({
                "date": parsed_date,
                "description": desc if desc else "UNKNOWN",
                "amount": amount,
                "running_balance": balance,
            })

    return transactions


def _find_col(headers: list, candidates: list) -> Optional[int]:
    """Find a column index by matching header names."""
    for i, h in enumerate(headers):
        for c in candidates:
            if c in h:
                return i
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
