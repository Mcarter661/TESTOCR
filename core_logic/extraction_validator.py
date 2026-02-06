from typing import Dict, List, Optional
from datetime import datetime, timedelta
from difflib import SequenceMatcher


def validate_extraction(
    transactions: List[Dict],
    bank_name: str = 'unknown',
    beginning_balance: Optional[float] = None,
    ending_balance: Optional[float] = None,
    stated_deposit_count: Optional[int] = None,
    stated_withdrawal_count: Optional[int] = None,
    stated_total_count: Optional[int] = None,
    statement_start: Optional[str] = None,
    statement_end: Optional[str] = None,
) -> Dict:
    confidence_score = 100
    checks_passed = []
    issues_found = []
    potential_duplicates = []

    credits = [t for t in transactions if t.get('credit', 0) > 0]
    debits = [t for t in transactions if t.get('debit', 0) > 0]
    total_credits = sum(t.get('credit', 0) for t in credits)
    total_debits = sum(t.get('debit', 0) for t in debits)

    checks_passed.append(f"Bank detected: {bank_name.upper()}")
    checks_passed.append(f"Credits found: {len(credits)} (${total_credits:,.0f})")
    checks_passed.append(f"Debits found: {len(debits)} (${total_debits:,.0f})")
    checks_passed.append(f"Total transactions extracted: {len(transactions)}")

    confidence_score, checks_passed, issues_found = _check_balance_reconciliation(
        confidence_score, checks_passed, issues_found,
        beginning_balance, ending_balance, total_credits, total_debits
    )

    confidence_score, checks_passed, issues_found = _check_transaction_count(
        confidence_score, checks_passed, issues_found,
        transactions, credits, debits,
        stated_deposit_count, stated_withdrawal_count, stated_total_count
    )

    confidence_score, checks_passed, issues_found = _check_credit_debit_sanity(
        confidence_score, checks_passed, issues_found,
        transactions, credits, debits
    )

    confidence_score, checks_passed, issues_found = _check_description_quality(
        confidence_score, checks_passed, issues_found, transactions
    )

    confidence_score, potential_duplicates, checks_passed, issues_found = _check_duplicates(
        confidence_score, checks_passed, issues_found, transactions
    )

    confidence_score, checks_passed, issues_found = _check_date_sanity(
        confidence_score, checks_passed, issues_found,
        transactions, statement_start, statement_end
    )

    confidence_score = max(0, confidence_score)

    if confidence_score >= 85:
        status = 'GOOD'
    elif confidence_score >= 70:
        status = 'NEEDS_REVIEW'
    else:
        status = 'POOR'

    if status == 'GOOD':
        recommendation = 'Extraction quality is high. Data is ready for underwriting review.'
    elif status == 'NEEDS_REVIEW':
        recommendation = 'Review flagged items before submitting to lenders.'
    else:
        recommendation = 'Extraction quality is low. Manual review of source documents is strongly recommended.'

    return {
        'confidence_score': confidence_score,
        'status': status,
        'checks_passed': checks_passed,
        'issues_found': issues_found,
        'potential_duplicates': potential_duplicates,
        'recommendation': recommendation,
    }


def _check_balance_reconciliation(
    score, passed, issues,
    beginning_balance, ending_balance, total_credits, total_debits
):
    if beginning_balance is not None and ending_balance is not None:
        calculated_ending = beginning_balance + total_credits - total_debits
        diff = abs(calculated_ending - ending_balance)
        threshold = abs(ending_balance) * 0.02 + 1.0
        if diff <= threshold:
            passed.append(
                f"Balance reconciliation PASSED: Beginning ${beginning_balance:,.2f} "
                f"+ Credits ${total_credits:,.2f} - Debits ${total_debits:,.2f} "
                f"= ${calculated_ending:,.2f} (stated ending: ${ending_balance:,.2f})"
            )
        else:
            pct = (diff / abs(ending_balance) * 100) if ending_balance != 0 else 100
            issues.append(
                f"Balance mismatch: Calculated ${calculated_ending:,.2f} vs stated ${ending_balance:,.2f} "
                f"(off by ${diff:,.2f}, {pct:.1f}%)"
            )
            score -= 20
    else:
        passed.append("Balance reconciliation: Not available (no beginning/ending balance in statement)")

    return score, passed, issues


def _check_transaction_count(
    score, passed, issues,
    transactions, credits, debits,
    stated_deposit_count, stated_withdrawal_count, stated_total_count
):
    extracted_total = len(transactions)
    extracted_credits = len(credits)
    extracted_debits = len(debits)

    stated_combined = None
    if stated_total_count is not None:
        stated_combined = stated_total_count
    elif stated_deposit_count is not None and stated_withdrawal_count is not None:
        stated_combined = stated_deposit_count + stated_withdrawal_count

    if stated_combined is not None:
        missing = stated_combined - extracted_total
        pct_missing = (missing / stated_combined * 100) if stated_combined > 0 else 0

        detail_parts = []
        if stated_deposit_count is not None:
            detail_parts.append(f"Credits: {extracted_credits}/{stated_deposit_count}")
        if stated_withdrawal_count is not None:
            detail_parts.append(f"Debits: {extracted_debits}/{stated_withdrawal_count}")
        detail = " | ".join(detail_parts)

        if pct_missing <= 5:
            passed.append(
                f"Transaction count: {extracted_total}/{stated_combined} extracted ({100 - pct_missing:.1f}% captured). {detail}"
            )
        else:
            issues.append(
                f"Transaction count: {extracted_total} vs {stated_combined} stated "
                f"({missing} missing, {pct_missing:.1f}% gap). {detail}"
            )
            score -= 15
    else:
        passed.append(f"Transaction count: {extracted_total} extracted (no stated count available for comparison)")

    return score, passed, issues


def _check_credit_debit_sanity(score, passed, issues, transactions, credits, debits):
    if not transactions:
        issues.append("No transactions extracted - likely a parser failure")
        score -= 25
        return score, passed, issues

    if len(credits) == 0 and len(debits) > 0:
        issues.append(
            f"ALL {len(debits)} transactions are debits with ZERO credits - likely parser error"
        )
        score -= 25
    elif len(debits) == 0 and len(credits) > 0:
        issues.append(
            f"ALL {len(credits)} transactions are credits with ZERO debits - likely parser error"
        )
        score -= 25
    else:
        ratio = len(credits) / len(transactions) * 100
        passed.append(f"Credit/Debit mix: {ratio:.0f}% credits, {100 - ratio:.0f}% debits - looks normal")

    return score, passed, issues


def _check_description_quality(score, passed, issues, transactions):
    if not transactions:
        return score, passed, issues

    import re
    bad_count = 0
    for t in transactions:
        desc = str(t.get('description', '')).strip()
        if not desc or len(desc) < 3 or re.match(r'^[\d\s\.\-,]+$', desc):
            bad_count += 1

    bad_pct = (bad_count / len(transactions) * 100) if transactions else 0
    if bad_pct <= 20:
        passed.append(f"Description quality: {100 - bad_pct:.0f}% have meaningful descriptions")
    else:
        issues.append(
            f"Description quality: {bad_count}/{len(transactions)} ({bad_pct:.0f}%) have empty or numeric-only descriptions"
        )
        score -= 15

    return score, passed, issues


def _check_duplicates(score, passed, issues, transactions):
    potential_dupes = []

    if not transactions:
        return score, potential_dupes, passed, issues

    from collections import defaultdict
    groups = defaultdict(list)
    for t in transactions:
        key = (str(t.get('date', '')), round(t.get('amount', t.get('debit', 0) or t.get('credit', 0)), 2))
        groups[key].append(t)

    for key, group in groups.items():
        if len(group) < 2:
            continue
        descs = [str(t.get('description', ''))[:80] for t in group]
        for i in range(len(descs)):
            for j in range(i + 1, len(descs)):
                similarity = SequenceMatcher(None, descs[i].lower(), descs[j].lower()).ratio()
                if similarity > 0.75:
                    potential_dupes.append({
                        'date': key[0],
                        'amount': key[1],
                        'descriptions': [descs[i], descs[j]],
                        'similarity': round(similarity * 100),
                    })

    unique_pairs = []
    seen = set()
    for d in potential_dupes:
        sig = (d['date'], d['amount'], tuple(sorted(d['descriptions'])))
        if sig not in seen:
            seen.add(sig)
            unique_pairs.append(d)

    potential_dupes = unique_pairs

    if not potential_dupes:
        passed.append("Duplicate detection: No suspicious duplicates found")
    else:
        issues.append(f"Duplicate detection: {len(potential_dupes)} potential duplicate pair(s) found for review")
        penalty = min(len(potential_dupes) * 5, 15)
        score -= penalty

    return score, potential_dupes, passed, issues


def _check_date_sanity(score, passed, issues, transactions, statement_start, statement_end):
    if not transactions:
        return score, passed, issues

    start_dt = _parse_date(statement_start) if statement_start else None
    end_dt = _parse_date(statement_end) if statement_end else None

    dates = []
    for t in transactions:
        dt = _parse_date(str(t.get('date', '')))
        if dt:
            dates.append(dt)

    if not dates:
        issues.append("Date sanity: Could not parse any transaction dates")
        score -= 10
        return score, passed, issues

    min_date = min(dates)
    max_date = max(dates)
    now = datetime.now()
    future_count = sum(1 for d in dates if d > now + timedelta(days=30))

    out_of_range = 0
    if start_dt and end_dt:
        margin = timedelta(days=5)
        for d in dates:
            if d < start_dt - margin or d > end_dt + margin:
                out_of_range += 1

    has_issue = False

    if future_count > 0:
        issues.append(f"Date sanity: {future_count} transaction(s) have dates in the future")
        score -= 10
        has_issue = True

    if start_dt and end_dt and out_of_range > 0:
        pct = out_of_range / len(dates) * 100
        issues.append(
            f"Date sanity: {out_of_range} transaction(s) ({pct:.0f}%) fall outside statement period "
            f"({statement_start} to {statement_end})"
        )
        if not has_issue:
            score -= 10
            has_issue = True

    old_threshold = datetime(2000, 1, 1)
    very_old = sum(1 for d in dates if d < old_threshold)
    if very_old > 0:
        issues.append(f"Date sanity: {very_old} transaction(s) have dates before year 2000 (wrong year parsing?)")
        if not has_issue:
            score -= 10
            has_issue = True

    if not has_issue:
        period_str = f" (within {statement_start} to {statement_end})" if start_dt and end_dt else ""
        passed.append(
            f"Date sanity: All dates valid, range {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}{period_str}"
        )

    return score, passed, issues


def _parse_date(date_str: str) -> Optional[datetime]:
    if not date_str or not date_str.strip():
        return None
    date_str = date_str.strip()
    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y"]:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None
