"""
Deal Summary Generator - Creates the SPEC SHEET style summary
with monthly holdback breakdown and lender matching integration.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from .deal_input import DealInput, ManualPosition, MonthlyData


@dataclass
class DealSummary:
    """Complete deal summary for underwriting review."""

    # Basic Info
    legal_name: str = ""
    dba: str = ""
    industry: str = ""
    state: str = ""
    deal_type: str = ""
    tier: str = ""

    # Business Metrics
    time_in_business_months: int = 0
    fico_score: int = 0
    ownership_percent: float = 100.0

    # Revenue Summary
    avg_monthly_revenue: float = 0.0
    annualized_revenue: float = 0.0
    revenue_trend: str = ""
    lowest_month_revenue: float = 0.0
    highest_month_revenue: float = 0.0

    # Bank Health
    avg_daily_balance: float = 0.0
    avg_deposits_per_month: float = 0.0
    total_nsf_count: int = 0
    total_negative_days: int = 0

    # Current Position Summary
    position_count: int = 0
    positions: List[Dict] = field(default_factory=list)
    total_current_holdback: float = 0.0
    current_holdback_percent: float = 0.0
    total_remaining_balance: float = 0.0
    days_since_last_funding: int = 0

    # Leverage Metrics
    total_outstanding_debt: float = 0.0
    leverage_ratio: float = 0.0
    dti_ratio: float = 0.0
    dscr: float = 0.0

    # Expense Summary
    payroll_monthly: float = 0.0
    rent_monthly: float = 0.0
    utilities_monthly: float = 0.0
    supplies_monthly: float = 0.0
    total_fixed_expenses: float = 0.0
    net_available_cash_flow: float = 0.0

    # Monthly Breakdown
    monthly_breakdown: List[Dict] = field(default_factory=list)

    # Proposed Deal
    proposed_funding: float = 0.0
    proposed_factor_rate: float = 1.35
    proposed_payback: float = 0.0
    proposed_term_months: int = 6
    proposed_frequency: str = "daily"
    proposed_payment: float = 0.0

    # New Deal Impact
    new_holdback_amount: float = 0.0
    combined_holdback: float = 0.0
    combined_holdback_percent: float = 0.0
    net_available_after: float = 0.0
    adb_to_payment_ratio: float = 0.0

    # Recommended Limits
    max_recommended_funding: float = 0.0
    max_daily_payment: float = 0.0

    # Risk Flags
    risk_flags: List[str] = field(default_factory=list)

    # Lender Match Summary
    eligible_lender_count: int = 0
    top_lender_matches: List[Dict] = field(default_factory=list)


def generate_deal_summary(deal: DealInput, risk_data: dict = None, lender_matches: dict = None, expense_data: dict = None) -> DealSummary:
    """Generate a complete deal summary from DealInput."""
    summary = DealSummary()

    # Basic Info
    summary.legal_name = deal.legal_name
    summary.dba = deal.dba
    summary.industry = deal.industry
    summary.state = deal.state

    # Business Metrics
    summary.time_in_business_months = deal.time_in_business_months
    summary.fico_score = deal.fico_score
    summary.ownership_percent = deal.ownership_percent

    # Revenue Summary
    summary.avg_monthly_revenue = deal.avg_monthly_revenue
    summary.annualized_revenue = deal.avg_monthly_revenue * 12

    if deal.monthly_data:
        revenues = [m.net_revenue for m in deal.monthly_data if m.net_revenue > 0]
        if revenues:
            summary.lowest_month_revenue = min(revenues)
            summary.highest_month_revenue = max(revenues)
            if len(revenues) >= 3:
                first_half = sum(revenues[:len(revenues) // 2]) / (len(revenues) // 2)
                second_half = sum(revenues[len(revenues) // 2:]) / (len(revenues) - len(revenues) // 2)
                change = (second_half - first_half) / first_half * 100 if first_half > 0 else 0
                if change > 5:
                    summary.revenue_trend = "Growing"
                elif change < -5:
                    summary.revenue_trend = "Declining"
                else:
                    summary.revenue_trend = "Stable"

    # Bank Health
    summary.avg_daily_balance = deal.avg_daily_balance
    summary.total_nsf_count = deal.total_nsf_count
    summary.total_negative_days = deal.total_negative_days

    if deal.monthly_data:
        deposits = [m.deposit_count for m in deal.monthly_data if m.deposit_count > 0]
        summary.avg_deposits_per_month = sum(deposits) / len(deposits) if deposits else 0

    # Position Summary
    summary.position_count = deal.total_positions
    summary.total_current_holdback = deal.total_monthly_holdback
    summary.current_holdback_percent = deal.current_holdback_percent
    summary.total_remaining_balance = deal.total_remaining_balance

    for pos in deal.positions:
        pos_holdback_pct = (pos.monthly_payment / deal.avg_monthly_revenue * 100) if deal.avg_monthly_revenue > 0 else 0
        summary.positions.append({
            "position": pos.position_number,
            "funder": pos.funder_name,
            "funded_date": pos.funded_date,
            "funded_amount": pos.funded_amount,
            "payment": pos.payment_amount,
            "frequency": pos.payment_frequency,
            "factor_rate": pos.factor_rate,
            "total_payback": pos.total_payback,
            "paid_to_date": pos.estimated_paid,
            "remaining": pos.estimated_remaining,
            "paid_in_pct": pos.paid_in_percent,
            "est_payoff": pos.estimated_payoff_date,
            "monthly_holdback": pos.monthly_payment,
            "holdback_percent": round(pos_holdback_pct, 1),
            "is_buyout": pos.is_buyout,
            "notes": pos.notes,
            "has_known_funding": pos.notes != "estimated" if hasattr(pos, 'notes') else True,
        })

    # Days since last funding
    if deal.positions:
        funded_dates = []
        for pos in deal.positions:
            try:
                fd = datetime.strptime(pos.funded_date, "%Y-%m-%d")
                funded_dates.append(fd)
            except (ValueError, TypeError):
                pass
        if funded_dates:
            most_recent = max(funded_dates)
            summary.days_since_last_funding = (datetime.now() - most_recent).days

    # Monthly Breakdown
    for month in deal.monthly_data:
        summary.monthly_breakdown.append({
            "month": month.month,
            "gross_revenue": month.gross_revenue,
            "net_revenue": month.net_revenue,
            "nsf_count": month.nsf_count,
            "negative_days": month.negative_days,
            "avg_daily_balance": month.avg_daily_balance,
            "deposit_count": month.deposit_count,
            "holdback_amount": month.holdback_amount,
            "holdback_percent": month.holdback_percent,
            "notes": month.notes,
        })

    # Leverage Metrics
    summary.total_outstanding_debt = summary.total_remaining_balance
    if summary.annualized_revenue > 0:
        summary.leverage_ratio = summary.total_outstanding_debt / summary.annualized_revenue
    if summary.avg_monthly_revenue > 0:
        summary.dti_ratio = summary.total_current_holdback / summary.avg_monthly_revenue * 100
    net_operating_income = summary.avg_monthly_revenue - summary.total_current_holdback
    if summary.total_current_holdback > 0:
        summary.dscr = net_operating_income / summary.total_current_holdback
    else:
        summary.dscr = 0.0

    # Expense Summary
    if expense_data:
        summary.payroll_monthly = expense_data.get('payroll_monthly', 0)
        summary.rent_monthly = expense_data.get('rent_monthly', 0)
        summary.utilities_monthly = expense_data.get('utilities_monthly', 0)
        summary.supplies_monthly = expense_data.get('supplies_monthly', 0)
        summary.total_fixed_expenses = (
            summary.payroll_monthly + summary.rent_monthly +
            summary.utilities_monthly + summary.supplies_monthly
        )
    summary.net_available_cash_flow = (
        summary.avg_monthly_revenue - summary.total_current_holdback - summary.total_fixed_expenses
    )

    # Proposed Deal
    summary.proposed_funding = deal.proposed_funding
    summary.proposed_factor_rate = deal.proposed_factor_rate
    summary.proposed_payback = deal.proposed_funding * deal.proposed_factor_rate
    summary.proposed_term_months = deal.proposed_term_months
    summary.proposed_frequency = deal.proposed_frequency

    if deal.proposed_funding > 0:
        if deal.proposed_frequency == "daily":
            total_payments = deal.proposed_term_months * 21.5
        else:
            total_payments = deal.proposed_term_months * 4.33
        summary.proposed_payment = summary.proposed_payback / total_payments if total_payments > 0 else 0

    # New Deal Impact
    summary.new_holdback_amount = deal.new_monthly_payment
    summary.combined_holdback = deal.total_monthly_holdback + deal.new_monthly_payment
    summary.combined_holdback_percent = deal.combined_holdback_percent
    summary.net_available_after = deal.net_available_revenue

    if deal.new_daily_payment > 0 and deal.avg_daily_balance > 0:
        summary.adb_to_payment_ratio = deal.avg_daily_balance / deal.new_daily_payment

    # Recommended Limits - max funding where combined holdback stays under 35%
    if deal.avg_monthly_revenue > 0:
        available_for_new = (deal.avg_monthly_revenue * 0.35) - deal.total_monthly_holdback
        if available_for_new > 0:
            if deal.proposed_frequency == "daily":
                max_total_payback = available_for_new / 21.5 * deal.proposed_term_months * 21.5
            else:
                max_total_payback = available_for_new / 4.33 * deal.proposed_term_months * 4.33
            summary.max_recommended_funding = max_total_payback / deal.proposed_factor_rate
        else:
            summary.max_recommended_funding = 0

    if summary.lowest_month_revenue > 0:
        summary.max_daily_payment = (summary.lowest_month_revenue * 0.10) / 21.5

    # Tier
    summary.tier = _calculate_tier(summary, risk_data)

    # Deal type
    if deal.total_positions == 0:
        summary.deal_type = "New"
    elif any(p.is_renewal for p in deal.positions):
        summary.deal_type = "Renewal"
    else:
        summary.deal_type = "Add-On"

    # Risk Flags
    summary.risk_flags = _generate_risk_flags(summary, risk_data)

    # Lender Matches
    if lender_matches:
        summary.eligible_lender_count = lender_matches.get("eligible_count", 0)
        summary.top_lender_matches = lender_matches.get("eligible_lenders", [])[:5]

    return summary


def _calculate_tier(summary: DealSummary, risk_data: dict = None) -> str:
    score = 100
    if summary.fico_score < 500:
        score -= 25
    elif summary.fico_score < 550:
        score -= 15
    elif summary.fico_score < 600:
        score -= 10
    elif summary.fico_score < 650:
        score -= 5

    score -= min(summary.total_nsf_count * 5, 25)
    score -= min(summary.total_negative_days * 2, 20)
    score -= summary.position_count * 8

    if summary.current_holdback_percent > 50:
        score -= 20
    elif summary.current_holdback_percent > 40:
        score -= 10
    elif summary.current_holdback_percent > 35:
        score -= 5

    if summary.time_in_business_months < 12:
        score -= 15
    elif summary.time_in_business_months < 24:
        score -= 5
    elif summary.time_in_business_months >= 60:
        score += 5

    if summary.revenue_trend == "Declining":
        score -= 10
    elif summary.revenue_trend == "Growing":
        score += 5

    if risk_data:
        if risk_data.get("cash_risk_flag"):
            score -= 10
        if risk_data.get("gambling_flag"):
            score -= 15
        score -= risk_data.get("high_risk_count", 0) * 10

    if score >= 80:
        return "A"
    elif score >= 60:
        return "B"
    elif score >= 40:
        return "C"
    else:
        return "D"


def _generate_risk_flags(summary: DealSummary, risk_data: dict = None) -> List[str]:
    flags = []
    if summary.fico_score > 0 and summary.fico_score < 550:
        flags.append(f"LOW FICO: {summary.fico_score}")
    if summary.total_nsf_count > 3:
        flags.append(f"HIGH NSF COUNT: {summary.total_nsf_count}")
    if summary.total_negative_days > 5:
        flags.append(f"NEGATIVE BALANCE DAYS: {summary.total_negative_days}")
    if summary.current_holdback_percent > 40:
        flags.append(f"HIGH CURRENT HOLDBACK: {summary.current_holdback_percent:.1f}%")
    if summary.combined_holdback_percent > 50:
        flags.append(f"COMBINED HOLDBACK EXCEEDS 50%: {summary.combined_holdback_percent:.1f}%")
    if summary.position_count >= 3:
        flags.append(f"HIGH POSITION COUNT: {summary.position_count}")
    if 0 < summary.days_since_last_funding < 30:
        flags.append(f"RECENT FUNDING: {summary.days_since_last_funding} days ago")
    if summary.revenue_trend == "Declining":
        flags.append("DECLINING REVENUE TREND")
    if summary.time_in_business_months > 0 and summary.time_in_business_months < 12:
        flags.append(f"SHORT TIME IN BUSINESS: {summary.time_in_business_months} months")
    if 0 < summary.adb_to_payment_ratio < 3.5:
        flags.append(f"LOW ADB/PAYMENT RATIO: {summary.adb_to_payment_ratio:.2f}x")
    if 0 < summary.avg_deposits_per_month < 20:
        flags.append(f"LOW DEPOSIT FREQUENCY: {summary.avg_deposits_per_month:.0f}/month")

    if risk_data:
        if risk_data.get("cash_risk_flag"):
            flags.append(f"HIGH CASH DEPOSITS: {risk_data.get('cash_deposit_percent', 0):.1f}%")
        if risk_data.get("gambling_flag"):
            flags.append("GAMBLING ACTIVITY DETECTED")
        for rf in risk_data.get("red_flags", []):
            if rf.get("severity") == "HIGH":
                flags.append(rf.get("description", "RED FLAG"))

    return flags
