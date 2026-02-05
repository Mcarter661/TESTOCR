"""
Calculator Module
DTI calculations, holdback percentages, max funding amounts,
and position sizing based on risk profiles.
"""

from typing import Dict, Optional


def calculate_dti_ratio(monthly_revenue: float, existing_debt_payments: float) -> float:
    """
    Calculate Debt-to-Income ratio.
    """
    if monthly_revenue <= 0:
        return 1.0
    
    dti = existing_debt_payments / monthly_revenue
    return round(min(dti, 1.0), 4)


def calculate_max_holdback(monthly_revenue: float, risk_tier: str) -> Dict:
    """
    Calculate maximum holdback percentage based on risk tier.
    """
    holdback_limits = {
        'A': {'min': 0.10, 'max': 0.15, 'recommended': 0.12},
        'B': {'min': 0.12, 'max': 0.18, 'recommended': 0.15},
        'C': {'min': 0.15, 'max': 0.22, 'recommended': 0.18},
        'D': {'min': 0.18, 'max': 0.25, 'recommended': 0.22},
        'Decline': {'min': 0, 'max': 0, 'recommended': 0},
    }
    
    limits = holdback_limits.get(risk_tier, holdback_limits['C'])
    
    daily_revenue = monthly_revenue / 22  # Business days
    
    return {
        'min_holdback_pct': limits['min'],
        'max_holdback_pct': limits['max'],
        'recommended_holdback_pct': limits['recommended'],
        'daily_payment_min': round(daily_revenue * limits['min'], 2),
        'daily_payment_max': round(daily_revenue * limits['max'], 2),
        'daily_payment_recommended': round(daily_revenue * limits['recommended'], 2),
    }


def calculate_max_funding(
    monthly_revenue: float,
    risk_tier: str,
    existing_positions: int = 0,
    time_in_business_months: int = 12
) -> Dict:
    """
    Calculate maximum funding amount based on revenue and risk.
    """
    base_multipliers = {
        'A': 1.5,
        'B': 1.2,
        'C': 1.0,
        'D': 0.75,
        'Decline': 0,
    }
    
    multiplier = base_multipliers.get(risk_tier, 1.0)
    
    if existing_positions >= 3:
        multiplier *= 0.5
    elif existing_positions >= 2:
        multiplier *= 0.7
    elif existing_positions >= 1:
        multiplier *= 0.85
    
    if time_in_business_months < 6:
        multiplier *= 0.6
    elif time_in_business_months < 12:
        multiplier *= 0.8
    elif time_in_business_months < 24:
        multiplier *= 0.9
    
    max_advance = monthly_revenue * multiplier
    
    max_advance = max(0, min(max_advance, 500000))
    
    return {
        'max_funding_amount': round(max_advance, -2),
        'multiplier_used': round(multiplier, 2),
        'monthly_revenue': monthly_revenue,
        'risk_tier': risk_tier,
        'position_adjustment': existing_positions,
        'tib_adjustment': time_in_business_months,
    }


def calculate_factor_rate_range(risk_tier: str, term_months: int = 6) -> Dict:
    """
    Calculate appropriate factor rate range based on risk.
    """
    base_rates = {
        'A': {'min': 1.15, 'max': 1.25},
        'B': {'min': 1.20, 'max': 1.35},
        'C': {'min': 1.30, 'max': 1.45},
        'D': {'min': 1.40, 'max': 1.55},
        'Decline': {'min': 0, 'max': 0},
    }
    
    rates = base_rates.get(risk_tier, base_rates['C'])
    
    if term_months > 9:
        adjustment = 0.05
    elif term_months > 6:
        adjustment = 0.02
    else:
        adjustment = 0
    
    return {
        'min_factor': round(rates['min'] + adjustment, 2),
        'max_factor': round(rates['max'] + adjustment, 2),
        'recommended_factor': round((rates['min'] + rates['max']) / 2 + adjustment, 2),
        'term_months': term_months,
    }


def calculate_payback_amount(funding_amount: float, factor_rate: float) -> Dict:
    """
    Calculate total payback and payment schedule.
    """
    total_payback = funding_amount * factor_rate
    
    cost_of_capital = total_payback - funding_amount
    
    daily_payment_6mo = total_payback / 132  # 22 days * 6 months
    daily_payment_9mo = total_payback / 198
    daily_payment_12mo = total_payback / 264
    
    return {
        'funding_amount': funding_amount,
        'factor_rate': factor_rate,
        'total_payback': round(total_payback, 2),
        'cost_of_capital': round(cost_of_capital, 2),
        'daily_payment_6mo': round(daily_payment_6mo, 2),
        'daily_payment_9mo': round(daily_payment_9mo, 2),
        'daily_payment_12mo': round(daily_payment_12mo, 2),
        'weekly_payment_6mo': round(daily_payment_6mo * 5, 2),
    }


def calculate_position_sizing(
    monthly_revenue: float,
    risk_score: int,
    risk_tier: str,
    existing_mca_payments: float = 0,
    existing_positions: int = 0
) -> Dict:
    """
    Calculate recommended MCA position size based on risk.
    """
    max_funding = calculate_max_funding(
        monthly_revenue, risk_tier, existing_positions
    )
    
    holdback = calculate_max_holdback(monthly_revenue, risk_tier)
    
    factor_rates = calculate_factor_rate_range(risk_tier)
    
    recommended_advance = max_funding['max_funding_amount'] * 0.8
    
    if existing_mca_payments > 0:
        available_room = (monthly_revenue * holdback['max_holdback_pct']) - existing_mca_payments
        if available_room < recommended_advance * holdback['recommended_holdback_pct']:
            recommended_advance *= 0.5
    
    terms = [6, 9, 12] if risk_tier in ['A', 'B'] else [6, 9]
    
    return {
        'recommended_advance': round(recommended_advance, -2),
        'max_advance': max_funding['max_funding_amount'],
        'holdback_percentage': holdback['recommended_holdback_pct'],
        'daily_payment': holdback['daily_payment_recommended'],
        'factor_rate_range': factor_rates,
        'recommended_terms': terms,
        'risk_tier': risk_tier,
        'risk_score': risk_score,
        'existing_positions': existing_positions,
        'room_for_stacking': existing_positions < 2 and risk_tier in ['A', 'B', 'C'],
    }


def calculate_full_deal_metrics(
    monthly_revenue: float,
    risk_profile: Dict,
    funding_amount: Optional[float] = None
) -> Dict:
    """
    Calculate comprehensive deal metrics for underwriting decision.
    """
    risk_score_data = risk_profile.get('risk_score', {})
    risk_score = risk_score_data.get('risk_score', 50)
    risk_tier = risk_score_data.get('risk_tier', 'C')
    
    mca_data = risk_profile.get('mca_positions', {})
    existing_positions = mca_data.get('unique_mca_lenders', 0)
    existing_payments = mca_data.get('mca_total_payments', 0) / max(1, mca_data.get('mca_payment_count', 1))
    
    position = calculate_position_sizing(
        monthly_revenue, risk_score, risk_tier, existing_payments, existing_positions
    )
    
    if funding_amount is None:
        funding_amount = position['recommended_advance']
    
    factor_rate = position['factor_rate_range']['recommended_factor']
    payback = calculate_payback_amount(funding_amount, factor_rate)
    
    dti = calculate_dti_ratio(monthly_revenue, payback['daily_payment_6mo'] * 22 + existing_payments)
    
    return {
        'position_sizing': position,
        'payback_schedule': payback,
        'dti_ratio': dti,
        'dti_healthy': dti < 0.25,
        'approval_recommendation': risk_tier != 'Decline' and dti < 0.35,
        'monthly_revenue': monthly_revenue,
        'risk_tier': risk_tier,
        'risk_score': risk_score,
    }
