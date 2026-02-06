import os
import sys
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional

import pdfplumber

# Anthropic integration - blueprint:python_anthropic
# The newest Anthropic model is "claude-sonnet-4-20250514"
# Do not revert to older 3.x models unless explicitly asked.
DEFAULT_MODEL_STR = "claude-sonnet-4-20250514"

logger = logging.getLogger('claude_auto_fix')

LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'claude_auto_fix.log')

MAX_API_CALLS = 3
RETRY_DELAY_SECONDS = 2

VALID_PARSERS = ['chase', 'bofa', 'wells_fargo', 'citibank', 'pnc', 'truist', 'us_bank', 'webster', 'generic']


def _setup_file_logger():
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = logging.FileHandler(LOG_FILE, mode='a')
    file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.setLevel(logging.INFO)


def _log(message: str):
    _setup_file_logger()
    logger.info(message)


def _extract_pdf_text(pdf_path: str, max_chars: int = 5000) -> str:
    try:
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
                full = '\n'.join(text_parts)
                if len(full) >= max_chars:
                    break
        return '\n'.join(text_parts)[:max_chars]
    except Exception as e:
        _log(f"Error extracting PDF text for auto-fix: {e}")
        return ""


def _should_trigger(quality_report: Dict, transactions: List[Dict]) -> bool:
    score = quality_report.get('confidence_score', 100)
    status = quality_report.get('status', 'GOOD')
    txn_count = len(transactions) if transactions else 0

    credits = sum(1 for t in transactions if t.get('type') == 'credit') if transactions else 0
    debits = sum(1 for t in transactions if t.get('type') == 'debit') if transactions else 0

    if score < 70:
        return True
    if score < 85 and txn_count < 10:
        return True
    if credits == 0 and debits == 0:
        return True

    return False


def _build_prompt(
    bank_name: str,
    score: int,
    status: str,
    issues: List[str],
    transactions: List[Dict],
    pdf_text: str,
    statement_info: Optional[Dict] = None,
) -> str:
    issues_str = '\n'.join(f"  - {i}" for i in issues) if issues else '  (none)'

    sample = transactions[:10] if transactions else []
    txn_lines = []
    for t in sample:
        txn_lines.append(
            f"  Date: {t.get('date','?')} | Desc: {t.get('description','?')} | "
            f"Amount: {t.get('amount','?')} | Type: {t.get('type','?')}"
        )
    txn_str = '\n'.join(txn_lines) if txn_lines else '  (no transactions extracted)'

    si = statement_info or {}
    begin_bal = si.get('beginning_balance', si.get('opening_balance', 'N/A'))
    end_bal = si.get('ending_balance', si.get('closing_balance', 'N/A'))
    stated_count = si.get('stated_transaction_count', 'N/A')
    extracted_count = len(transactions) if transactions else 0

    return f"""Bank statement extraction failed quality checks.

DETECTED BANK: {bank_name}
CONFIDENCE SCORE: {score}/100
STATUS: {status}

ISSUES FOUND:
{issues_str}

EXTRACTED TRANSACTIONS (sample):
{txn_str}

RAW TEXT FROM PDF (first 5000 chars):
{pdf_text}

STATEMENT SUMMARY (if available):
- Beginning Balance: {begin_bal}
- Ending Balance: {end_bal}
- Stated Transaction Count: {stated_count}
- Extracted Transaction Count: {extracted_count}

Please analyze and return JSON with:
{{
  "diagnosis": "What went wrong with the extraction",
  "bank_identified": "The actual bank name if you can tell",
  "recommended_parser": "Which parser should be used (chase/bofa/wells_fargo/citibank/pnc/truist/us_bank/webster/generic)",
  "transaction_pattern": "Description of the transaction format you see in the text",
  "date_format": "The date format used (e.g., MM/DD/YY, MM/DD, MMM DD)",
  "amount_position": "Where amounts appear (end of line, before description, separate columns)",
  "section_headers": ["List of section headers you see like 'DEPOSITS', 'WITHDRAWALS'"],
  "sample_parsed_transactions": [
    {{"date": "YYYY-MM-DD", "description": "...", "amount": 123.45, "type": "credit/debit"}}
  ],
  "confidence": "high/medium/low",
  "can_auto_fix": true,
  "fix_instructions": "Specific instructions if manual fix needed"
}}"""


def _call_claude_api(prompt: str, api_key: str) -> Optional[Dict]:
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)

        response = client.messages.create(
            model=DEFAULT_MODEL_STR,
            max_tokens=4096,
            system="You are a bank statement parsing expert. Analyze why the extraction failed and provide specific fixes. Return JSON only.",
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()

        if raw.startswith('```'):
            lines = raw.split('\n')
            lines = lines[1:] if lines[0].startswith('```') else lines
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            raw = '\n'.join(lines)

        return json.loads(raw)

    except json.JSONDecodeError as e:
        _log(f"Invalid JSON from Claude API: {e}")
        return None
    except Exception as e:
        err_str = str(e).lower()
        if 'rate' in err_str and 'limit' in err_str:
            _log(f"Claude API rate limit hit: {e}")
        elif 'timeout' in err_str or 'timed out' in err_str:
            _log(f"Claude API timeout: {e}")
        else:
            _log(f"Claude API error: {e}")
        return None


def _re_extract_with_parser(pdf_path: str, recommended_parser: str) -> Optional[List[Dict]]:
    try:
        from core_logic.ocr_engine import parse_transactions, extract_account_info

        text_parts = []
        tables = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
                page_tables = page.extract_tables()
                for table in page_tables:
                    if table:
                        tables.extend([row for row in table if row])

        raw_text = '\n'.join(text_parts)
        if not raw_text or len(raw_text.strip()) < 100:
            return None

        transactions = parse_transactions(raw_text, recommended_parser, tables)
        return transactions if transactions else None

    except Exception as e:
        _log(f"Re-extraction failed with parser '{recommended_parser}': {e}")
        return None


def attempt_auto_fix(
    pdf_paths: List[str],
    transactions: List[Dict],
    quality_report: Dict,
    bank_name: str,
    statement_info: Optional[Dict] = None,
) -> Dict:
    result = {
        'auto_fix_attempted': False,
        'api_calls_made': 0,
        'original_score': quality_report.get('confidence_score', 0),
        'new_score': None,
        'improvement': None,
        'claude_diagnosis': None,
        'action_taken': None,
        'status': 'UNCHANGED',
        'new_transactions': None,
    }

    if not _should_trigger(quality_report, transactions):
        result['action_taken'] = 'Auto-fix not triggered (quality above threshold)'
        return result

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        _log("Claude auto-fix skipped: No API key configured")
        result['action_taken'] = 'Skipped - no ANTHROPIC_API_KEY configured'
        return result

    result['auto_fix_attempted'] = True
    pdf_path = pdf_paths[0] if pdf_paths else None

    statement_label = os.path.basename(pdf_path) if pdf_path else 'unknown'
    score = quality_report.get('confidence_score', 0)
    status = quality_report.get('status', 'POOR')
    issues = quality_report.get('issues_found', [])

    _log(f"Statement: {statement_label}")
    _log(f"Original Score: {score}/100 ({status})")

    pdf_text = _extract_pdf_text(pdf_path) if pdf_path else ""

    prompt = _build_prompt(
        bank_name=bank_name,
        score=score,
        status=status,
        issues=issues,
        transactions=transactions,
        pdf_text=pdf_text,
        statement_info=statement_info,
    )

    claude_response = None
    for attempt in range(1, MAX_API_CALLS + 1):
        _log(f"Claude API called (attempt {attempt}/{MAX_API_CALLS})")
        result['api_calls_made'] = attempt

        claude_response = _call_claude_api(prompt, api_key)
        if claude_response is not None:
            break

        if attempt < MAX_API_CALLS:
            _log(f"Retrying in {RETRY_DELAY_SECONDS}s...")
            time.sleep(RETRY_DELAY_SECONDS)

    if claude_response is None:
        _log("All API attempts failed")
        result['status'] = 'MANUAL_REVIEW_NEEDED'
        result['action_taken'] = 'Claude API calls failed - manual review needed'
        _save_manual_review_log(statement_label, quality_report, None)
        return result

    diagnosis = claude_response.get('diagnosis', 'No diagnosis provided')
    result['claude_diagnosis'] = diagnosis
    _log(f"Diagnosis: {diagnosis}")

    can_auto_fix = claude_response.get('can_auto_fix', False)
    confidence = claude_response.get('confidence', 'low')
    recommended_parser = claude_response.get('recommended_parser', 'generic')

    if recommended_parser not in VALID_PARSERS:
        _log(f"Unknown parser '{recommended_parser}', falling back to generic")
        recommended_parser = 'generic'

    if can_auto_fix and confidence == 'high' and pdf_path:
        _log(f"Action: Re-extracting with {recommended_parser} parser")
        result['action_taken'] = f"Re-extracted using {recommended_parser} parser"

        new_transactions = _re_extract_with_parser(pdf_path, recommended_parser)

        claude_sample = claude_response.get('sample_parsed_transactions', [])
        if new_transactions and len(new_transactions) > 0 and claude_sample:
            from core_logic.extraction_validator import validate_extraction
            test_quality = validate_extraction(
                transactions=new_transactions,
                bank_name=recommended_parser,
                beginning_balance=(statement_info or {}).get('opening_balance'),
                ending_balance=(statement_info or {}).get('closing_balance'),
                statement_start=(statement_info or {}).get('statement_period_start'),
                statement_end=(statement_info or {}).get('statement_period_end'),
            )
            test_score = test_quality.get('confidence_score', 0)
            if test_score <= score and len(claude_sample) >= 2:
                _log(f"Parser re-extraction didn't help (score {test_score}), using Claude's parsed transactions")
                claude_txns = []
                for ct in claude_sample:
                    amt = ct.get('amount', 0)
                    txn_type = ct.get('type', 'debit')
                    if txn_type == 'debit' and amt > 0:
                        amt = -amt
                    elif txn_type == 'credit' and amt < 0:
                        amt = abs(amt)
                    claude_txns.append({
                        'date': ct.get('date', ''),
                        'description': ct.get('description', '')[:300],
                        'amount': amt,
                        'debit': abs(amt) if amt < 0 else 0,
                        'credit': amt if amt > 0 else 0,
                        'balance': None,
                        'category': ct.get('category', 'OTHER'),
                        'raw_line': ct.get('description', '')[:300],
                    })
                if claude_txns:
                    new_transactions = claude_txns
                    result['action_taken'] = 'Used Claude-parsed transactions directly'

        if new_transactions and len(new_transactions) > 0:
            from core_logic.extraction_validator import validate_extraction

            new_quality = validate_extraction(
                transactions=new_transactions,
                bank_name=recommended_parser,
                beginning_balance=(statement_info or {}).get('opening_balance'),
                ending_balance=(statement_info or {}).get('closing_balance'),
                statement_start=(statement_info or {}).get('statement_period_start'),
                statement_end=(statement_info or {}).get('statement_period_end'),
            )
            new_score = new_quality.get('confidence_score', 0)
            improvement = new_score - score

            if new_score > score:
                result['new_score'] = new_score
                result['improvement'] = improvement
                result['new_transactions'] = new_transactions

                if improvement >= 15:
                    result['status'] = 'FIXED'
                    _log(f"New Score: {new_score}/100 ({new_quality.get('status', 'UNKNOWN')})")
                    _log(f"Status: FIXED (+{improvement} points)")
                else:
                    result['status'] = 'IMPROVED'
                    _log(f"New Score: {new_score}/100 ({new_quality.get('status', 'UNKNOWN')})")
                    _log(f"Status: IMPROVED (+{improvement} points)")
            else:
                _log(f"Re-extraction did not improve score ({new_score} vs {score})")
                result['status'] = 'UNCHANGED'
                result['action_taken'] += ' - no improvement, keeping original'
        else:
            _log("Re-extraction produced no transactions")
            result['status'] = 'MANUAL_REVIEW_NEEDED'
            result['action_taken'] += ' - re-extraction failed'
            _save_manual_review_log(statement_label, quality_report, claude_response)
    else:
        reason_parts = []
        if not can_auto_fix:
            reason_parts.append("can_auto_fix=false")
        if confidence != 'high':
            reason_parts.append(f"confidence={confidence}")
        reason = ', '.join(reason_parts) if reason_parts else 'no PDF path'

        _log(f"Manual review needed ({reason})")
        result['status'] = 'MANUAL_REVIEW_NEEDED'
        result['action_taken'] = f"Claude analyzed - manual review needed ({reason})"
        result['claude_diagnosis'] = diagnosis
        _save_manual_review_log(statement_label, quality_report, claude_response)

    return result


def _save_manual_review_log(statement_label: str, quality_report: Dict, claude_response: Optional[Dict]):
    os.makedirs(LOG_DIR, exist_ok=True)
    review_path = os.path.join(LOG_DIR, 'needs_manual_review.log')
    try:
        with open(review_path, 'a') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Statement: {statement_label}\n")
            f.write(f"Score: {quality_report.get('confidence_score', '?')}/100\n")
            f.write(f"Status: {quality_report.get('status', '?')}\n")
            issues = quality_report.get('issues_found', [])
            if issues:
                f.write("Issues:\n")
                for i in issues:
                    f.write(f"  - {i}\n")
            if claude_response:
                f.write(f"Claude Diagnosis: {claude_response.get('diagnosis', 'N/A')}\n")
                f.write(f"Recommended Parser: {claude_response.get('recommended_parser', 'N/A')}\n")
                f.write(f"Fix Instructions: {claude_response.get('fix_instructions', 'N/A')}\n")
                sample = claude_response.get('sample_parsed_transactions', [])
                if sample:
                    f.write(f"Claude Sample Transactions ({len(sample)}):\n")
                    for t in sample[:5]:
                        f.write(f"  {t}\n")
            else:
                f.write("Claude Response: API call failed\n")
    except Exception as e:
        _log(f"Error writing manual review log: {e}")
