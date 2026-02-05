"""
Financial Calculator - All underwriting math formulas.
Pure functions, no side effects.
"""


def calculate_dti(total_monthly_debt: float, net_monthly_revenue: float) -> float:
    """Debt-to-Income ratio as decimal (e.g., 0.36 = 36%). Flag if > 0.36."""
    if net_monthly_revenue <= 0:
        return 0.0
    return round(total_monthly_debt / net_monthly_revenue, 4)


def calculate_holdback_percent(daily_mca_payments: float, avg_daily_deposits: float) -> float:
    """What percentage of daily deposits go to MCA payments."""
    if avg_daily_deposits <= 0:
        return 0.0
    return round((daily_mca_payments / avg_daily_deposits) * 100, 2)


def calculate_net_available_revenue(monthly_revenue: float, monthly_holdback: float) -> float:
    """Revenue minus existing MCA payments."""
    return round(monthly_revenue - monthly_holdback, 2)


def calculate_payment_to_revenue_ratio(monthly_holdback: float, monthly_revenue: float) -> float:
    """Total holdback as percentage of monthly revenue."""
    if monthly_revenue <= 0:
        return 0.0
    return round((monthly_holdback / monthly_revenue) * 100, 2)


def calculate_max_recommended_funding(monthly_revenue: float, monthly_holdback: float) -> float:
    """
    Max funding where total holdback stays under 35% of revenue.
    Formula: ((monthly_revenue * 0.35) - monthly_holdback) / 22 * 180 / 1.35
    """
    available_for_new = (monthly_revenue * 0.35) - monthly_holdback
    if available_for_new <= 0:
        return 0.0
    daily_available = available_for_new / 22  # business days per month
    total_payback = daily_available * 180  # ~8 month term in business days
    max_funding = total_payback / 1.35  # reverse factor rate
    return round(max(0, max_funding), 2)


def calculate_max_daily_payment(lowest_monthly_revenue: float) -> float:
    """10% of lowest month divided by 22 business days, for seasonality safety."""
    return round((lowest_monthly_revenue * 0.10) / 22, 2)


def calculate_cash_flow_coverage(avg_daily_net_cash: float, proposed_daily_payment: float) -> float:
    """Cash flow coverage ratio. Target >= 1.25x."""
    if proposed_daily_payment <= 0:
        return 0.0
    return round(avg_daily_net_cash / proposed_daily_payment, 2)


def calculate_annualized_revenue(avg_monthly_revenue: float) -> float:
    """For advance cap calculations."""
    return round(avg_monthly_revenue * 12, 2)


def calculate_advance_cap(annualized_revenue: float, tier: str) -> dict:
    """
    Returns min/max advance based on risk tier.
    A: 15-25% of annual
    B: 12-20% of annual
    C: 10-15% of annual
    D: 8-12% of annual
    """
    caps = {
        "A": (0.15, 0.25),
        "B": (0.12, 0.20),
        "C": (0.10, 0.15),
        "D": (0.08, 0.12),
    }
    min_pct, max_pct = caps.get(tier, (0.10, 0.15))
    return {
        "min_advance": round(annualized_revenue * min_pct, 2),
        "max_advance": round(annualized_revenue * max_pct, 2),
    }


def calculate_average_daily_balance(transactions: list) -> float:
    """Calculate average daily balance from transactions with running_balance."""
    balances = [t["running_balance"] for t in transactions if t.get("running_balance") is not None]
    if not balances:
        return 0.0
    return round(sum(balances) / len(balances), 2)


def calculate_deal_summary(
    scrub_data: dict,
    risk_data: dict,
    position_data: dict,
    fico_score: int = 0,
    time_in_business_months: int = 0,
    ownership_percent: float = 100.0,
    state: str = "",
    industry: str = "",
) -> dict:
    """
    Assemble the full deal summary used for lender matching and reporting.
    Combines results from all analysis modules into a single deal profile.
    """
    avg_monthly_net = scrub_data.get("avg_monthly_net", 0)
    monthly_holdback = position_data.get("total_monthly_payment", 0)
    total_positions = position_data.get("total_positions", 0)

    net_available = calculate_net_available_revenue(avg_monthly_net, monthly_holdback)
    max_funding = calculate_max_recommended_funding(avg_monthly_net, monthly_holdback)
    dti = calculate_dti(monthly_holdback, avg_monthly_net)
    holdback_pct = calculate_payment_to_revenue_ratio(monthly_holdback, avg_monthly_net)
    annualized = calculate_annualized_revenue(avg_monthly_net)
    tier = risk_data.get("risk_tier", "C")
    advance_cap = calculate_advance_cap(annualized, tier)

    monthly_nets = scrub_data.get("monthly_net", {})
    monthly_values = list(monthly_nets.values()) if monthly_nets else [avg_monthly_net]
    lowest_month = min(monthly_values) if monthly_values else 0
    max_daily_pmt = calculate_max_daily_payment(lowest_month)

    daily_mca = position_data.get("total_daily_payment", 0)
    avg_daily_deposits = (avg_monthly_net / 22) if avg_monthly_net > 0 else 0
    avg_daily_net_cash = avg_daily_deposits - daily_mca
    cfcr = calculate_cash_flow_coverage(avg_daily_net_cash, max_daily_pmt) if max_daily_pmt > 0 else 0

    days_since_last = position_data.get("days_since_last_funding", 999)
    avg_daily_bal = risk_data.get("avg_daily_balance", 0)

    return {
        "fico_score": fico_score,
        "monthly_revenue": avg_monthly_net,
        "time_in_business_months": time_in_business_months,
        "nsf_count": risk_data.get("nsf_count", 0),
        "negative_days": risk_data.get("negative_day_count", 0),
        "position_count": total_positions,
        "days_since_last_funding": days_since_last,
        "ownership_percent": ownership_percent,
        "avg_daily_balance": avg_daily_bal,
        "current_holdback_percent": holdback_pct,
        "state": state,
        "industry": industry,
        "net_available_revenue": net_available,
        "max_recommended_funding": max_funding,
        "dti_ratio": dti,
        "annualized_revenue": annualized,
        "advance_cap": advance_cap,
        "max_daily_payment": max_daily_pmt,
        "cash_flow_coverage": cfcr,
        "risk_score": risk_data.get("risk_score", 0),
        "risk_tier": tier,
        "lowest_monthly_revenue": lowest_month,
        "monthly_holdback": monthly_holdback,
        "daily_mca_payment": daily_mca,
    }


def calculate_full_deal_metrics(monthly_revenue, risk_profile=None):
    """Backward-compatible wrapper for app.py pipeline."""
    if risk_profile is None:
        risk_profile = {}
    risk_score_data = risk_profile.get('risk_score', {})
    tier = risk_score_data.get('risk_tier', 'C')
    mca_data = risk_profile.get('mca_positions', {})
    monthly_holdback = mca_data.get('total_monthly_debt', 0)

    dti = calculate_dti(monthly_holdback, monthly_revenue)
    net_available = calculate_net_available_revenue(monthly_revenue, monthly_holdback)
    max_funding = calculate_max_recommended_funding(monthly_revenue, monthly_holdback)
    holdback_pct = calculate_payment_to_revenue_ratio(monthly_holdback, monthly_revenue)
    annualized = calculate_annualized_revenue(monthly_revenue)
    advance_cap = calculate_advance_cap(annualized, tier)
    max_daily = calculate_max_daily_payment(monthly_revenue)

    return {
        'dti_ratio': dti,
        'net_available_revenue': net_available,
        'max_recommended_funding': max_funding,
        'current_holdback_percent': holdback_pct,
        'annualized_revenue': annualized,
        'advance_cap': advance_cap,
        'max_daily_payment': max_daily,
        'risk_tier': tier,
    }
