# REPLIT MERGE INSTRUCTIONS
## Bank Parser Update - February 6, 2026

---

## ⚠️ CRITICAL: READ BEFORE DOING ANYTHING

**ONLY modify these files:**
1. ADD new file: `core_logic/bank_parsers.py`
2. UPDATE: `core_logic/ocr_engine.py` (specific sections only)

**DO NOT TOUCH:**
- main.py
- reporter.py  
- risk_engine.py
- position_detector.py
- calculator.py
- scrubber.py
- lender_matcher.py
- deal_input.py
- deal_summary.py
- Any config files

---

## STEP 1: Add New File

Create new file: `core_logic/bank_parsers.py`

Copy the ENTIRE contents of the `bank_parsers.py` file provided.

This file contains parsers for:
- Chase
- Bank of America
- Wells Fargo (formal + MTD)
- Citibank
- US Bank
- Webster (formal + MTD)
- Improved Generic Fallback

---

## STEP 2: Update ocr_engine.py

### 2A. Add import at top of file (after existing imports, around line 15):

```python
# Import bank parsers module
from core_logic.bank_parsers import (
    detect_bank,
    parse_bank_statement,
    validate_extraction,
    extract_transactions_chase,
    extract_transactions_bofa,
    extract_transactions_wells_fargo,
    extract_transactions_citibank,
    extract_transactions_us_bank,
    extract_transactions_webster,
    extract_transactions_generic_improved,
)
```

### 2B. Update the `parse_transactions` function (around line 947):

REPLACE this function:

```python
def parse_transactions(text: str, bank_format: str, tables: List[List] = None) -> List[Dict]:
    """
    Parse transaction data from extracted text based on bank format.
    """
    if bank_format == 'pnc':
        return extract_transactions_pnc(text, tables)
    elif bank_format == 'truist':
        return extract_transactions_truist(text, tables)
    elif bank_format == 'chase':
        return extract_transactions_chase(text, tables)
    else:
        return extract_transactions_generic(text, tables)
```

WITH this updated version:

```python
def parse_transactions(text: str, bank_format: str, tables: List[List] = None) -> List[Dict]:
    """
    Parse transaction data from extracted text based on bank format.
    Routes to bank-specific parsers or improved generic fallback.
    """
    # Keep existing PNC and Truist parsers (they work)
    if bank_format == 'pnc':
        return extract_transactions_pnc(text, tables)
    elif bank_format == 'truist':
        return extract_transactions_truist(text, tables)
    
    # Use new bank parsers module for other banks
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
    
    # Improved generic fallback for unknown banks
    else:
        # Try improved generic parser first
        transactions = extract_transactions_generic_improved(text, tables)
        
        # If that fails, fall back to original generic
        if not transactions:
            transactions = extract_transactions_generic(text, tables)
        
        return transactions
```

### 2C. Update the `detect_bank_format` function (around line 251):

FIND this function and ADD these patterns to BANK_PATTERNS dict at the top of the file:

```python
BANK_PATTERNS = {
    'pnc': [r'PNC Bank', r'PNC BANK', r'pnc\.com'],
    'truist': [r'Truist', r'TRUIST', r'BB&T', r'SunTrust'],
    'bofa': [r'Bank of America', r'BANK OF AMERICA', r'bankofamerica\.com', r'Business Advantage'],
    'wells_fargo': [r'Wells Fargo', r'WELLS FARGO', r'wellsfargo\.com', r'Optimize Business'],
    'citibank': [r'CITIBANK', r'CitiBusiness', r'Citibank,?\s+N\.?A\.?', r'Citi CBO'],
    'us_bank': [r'U\.?S\.?\s+Bank', r'US BANK', r'usbank\.com', r'Silver Business'],
    'webster': [r'Webster\s*Bank', r'websterbank\.com', r'PLATINUM BUSINESS'],
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
```

---

## STEP 3: Test

After making changes, test with:

```bash
cd /workspace
python3 -c "
from core_logic.ocr_engine import extract_from_pdf, detect_bank_format

# Test bank detection
test_texts = [
    'BANK OF AMERICA Business Advantage',
    'WELLS FARGO Optimize Business Checking',
    'CITIBANK CitiBusiness Flexible Checking',
    'CHASE Business Complete Checking',
]

for text in test_texts:
    bank = detect_bank_format(text)
    print(f'{text[:30]}... -> {bank}')
"
```

Expected output:
```
BANK OF AMERICA Business Advan... -> bofa
WELLS FARGO Optimize Business ... -> wells_fargo
CITIBANK CitiBusiness Flexible... -> citibank
CHASE Business Complete Checki... -> chase
```

---

## STEP 4: Test with Real PDF

```bash
python3 -c "
from core_logic.ocr_engine import extract_from_pdf

result = extract_from_pdf('input_pdfs/YOUR_TEST_FILE.pdf')
print('Success:', result['success'])
print('Bank:', result.get('bank_name'))
print('Transactions found:', len(result.get('transactions', [])))
if result.get('transactions'):
    print('First 5 transactions:')
    for t in result['transactions'][:5]:
        print(f\"  {t['date']} | {t['description'][:40]} | {t['amount']}\")
"
```

---

## WHAT THIS UPDATE DOES

1. **Adds dedicated parsers for 6 major banks:**
   - Chase (handles multi-line ACH, section-based amounts)
   - Bank of America (handles DES:/ID:/INDN: format, card transactions)
   - Wells Fargo (handles BOTH formal and MTD formats)
   - Citibank (handles separate debit/credit columns)
   - US Bank (handles MMM DD dates, - suffix amounts)
   - Webster (handles BOTH formal and MTD formats)

2. **Improves generic fallback:**
   - Better table extraction
   - Multiple regex patterns
   - Smarter debit/credit inference

3. **Keeps existing parsers:**
   - PNC parser unchanged (working)
   - Truist parser unchanged (working)

4. **Adds validation function:**
   - Checks transaction count
   - Validates dates
   - Balance reconciliation
   - Can flag extraction issues

---

## IF SOMETHING BREAKS

If the update causes issues:

1. The new `bank_parsers.py` file is INDEPENDENT
2. You can remove the import and revert `parse_transactions` to original
3. The original generic parser is still there as fallback

---

## NEXT STEPS (AFTER THIS WORKS)

1. Test with statements from each bank
2. Fix any parsing issues found
3. Add Claude auto-learning system (Phase 2)
