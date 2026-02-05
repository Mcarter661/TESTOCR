"""
Lender Matcher Module
Matches applicant profiles to appropriate lender criteria.
Supports comprehensive criteria matching against lender database.
"""

import pandas as pd
import os
from typing import List, Dict, Optional


DEFAULT_LENDERS = [
    {
        'lender_name': 'Premier Capital',
        'min_monthly_revenue': 15000,
        'max_monthly_revenue': 500000,
        'min_credit_score': 550,
        'max_nsf_30': 3,
        'max_nsf_90': 6,
        'max_negative_days': 5,
        'min_time_in_business': 12,
        'max_positions': 3,
        'allows_stacking': True,
        'min_factor': 1.20,
        'max_factor': 1.35,
        'min_term': 6,
        'max_term': 12,
        'min_advance': 10000,
        'max_advance': 250000,
        'industries_excluded': ['gambling', 'adult', 'cannabis'],
        'states_excluded': [],
        'daily_ach': True,
        'weekly_ach': True,
    },
    {
        'lender_name': 'Velocity Funding',
        'min_monthly_revenue': 10000,
        'max_monthly_revenue': 300000,
        'min_credit_score': 500,
        'max_nsf_30': 5,
        'max_nsf_90': 10,
        'max_negative_days': 10,
        'min_time_in_business': 6,
        'max_positions': 4,
        'allows_stacking': True,
        'min_factor': 1.30,
        'max_factor': 1.50,
        'min_term': 3,
        'max_term': 9,
        'min_advance': 5000,
        'max_advance': 150000,
        'industries_excluded': ['gambling'],
        'states_excluded': [],
        'daily_ach': True,
        'weekly_ach': False,
    },
    {
        'lender_name': 'Summit Business Capital',
        'min_monthly_revenue': 25000,
        'max_monthly_revenue': 1000000,
        'min_credit_score': 600,
        'max_nsf_30': 2,
        'max_nsf_90': 4,
        'max_negative_days': 3,
        'min_time_in_business': 24,
        'max_positions': 2,
        'allows_stacking': False,
        'min_factor': 1.15,
        'max_factor': 1.28,
        'min_term': 6,
        'max_term': 18,
        'min_advance': 25000,
        'max_advance': 500000,
        'industries_excluded': ['gambling', 'adult', 'cannabis', 'firearms'],
        'states_excluded': ['ND', 'SD'],
        'daily_ach': True,
        'weekly_ach': True,
    },
    {
        'lender_name': 'Quick Bridge Capital',
        'min_monthly_revenue': 8000,
        'max_monthly_revenue': 200000,
        'min_credit_score': 480,
        'max_nsf_30': 8,
        'max_nsf_90': 15,
        'max_negative_days': 15,
        'min_time_in_business': 4,
        'max_positions': 5,
        'allows_stacking': True,
        'min_factor': 1.35,
        'max_factor': 1.55,
        'min_term': 3,
        'max_term': 6,
        'min_advance': 3000,
        'max_advance': 75000,
        'industries_excluded': [],
        'states_excluded': [],
        'daily_ach': True,
        'weekly_ach': False,
    },
    {
        'lender_name': 'Titan Merchant Services',
        'min_monthly_revenue': 20000,
        'max_monthly_revenue': 750000,
        'min_credit_score': 575,
        'max_nsf_30': 4,
        'max_nsf_90': 8,
        'max_negative_days': 7,
        'min_time_in_business': 12,
        'max_positions': 3,
        'allows_stacking': True,
        'min_factor': 1.22,
        'max_factor': 1.40,
        'min_term': 6,
        'max_term': 12,
        'min_advance': 15000,
        'max_advance': 350000,
        'industries_excluded': ['gambling', 'cannabis'],
        'states_excluded': ['VT'],
        'daily_ach': True,
        'weekly_ach': True,
    },
]


def load_lender_profiles(config_path: str = "input_config/lender_template.csv") -> pd.DataFrame:
    """
    Load lender criteria profiles from configuration file or use defaults.
    """
    if os.path.exists(config_path):
        try:
            df = pd.read_csv(config_path)
            return df
        except Exception as e:
            print(f"Error loading lender config: {e}")
    
    return pd.DataFrame(DEFAULT_LENDERS)


def parse_lender_criteria(lender_row: Dict) -> Dict:
    """
    Parse a single lender's criteria into structured format.
    """
    return {
        'lender_name': lender_row.get('lender_name', 'Unknown'),
        'revenue_range': {
            'min': lender_row.get('min_monthly_revenue', 0),
            'max': lender_row.get('max_monthly_revenue', float('inf')),
        },
        'credit_score_min': lender_row.get('min_credit_score', 0),
        'nsf_limits': {
            '30_day': lender_row.get('max_nsf_30', 99),
            '90_day': lender_row.get('max_nsf_90', 99),
        },
        'max_negative_days': lender_row.get('max_negative_days', 99),
        'min_time_in_business': lender_row.get('min_time_in_business', 0),
        'max_positions': lender_row.get('max_positions', 99),
        'allows_stacking': lender_row.get('allows_stacking', True),
        'factor_range': {
            'min': lender_row.get('min_factor', 1.0),
            'max': lender_row.get('max_factor', 2.0),
        },
        'term_range': {
            'min': lender_row.get('min_term', 3),
            'max': lender_row.get('max_term', 18),
        },
        'advance_range': {
            'min': lender_row.get('min_advance', 0),
            'max': lender_row.get('max_advance', float('inf')),
        },
        'industries_excluded': lender_row.get('industries_excluded', []),
        'states_excluded': lender_row.get('states_excluded', []),
        'payment_options': {
            'daily_ach': lender_row.get('daily_ach', True),
            'weekly_ach': lender_row.get('weekly_ach', False),
        }
    }


def check_lender_match(applicant_profile: Dict, lender_criteria: Dict) -> Dict:
    """
    Check if applicant meets a specific lender's criteria.
    Returns match details with score and disqualifying factors.
    """
    score = 100
    disqualifying_factors = []
    warnings = []
    
    monthly_revenue = applicant_profile.get('monthly_revenue', 0)
    rev_range = lender_criteria.get('revenue_range', {})
    
    if monthly_revenue < rev_range.get('min', 0):
        disqualifying_factors.append(f"Revenue ${monthly_revenue:,.0f} below minimum ${rev_range['min']:,.0f}")
        score -= 50
    elif monthly_revenue > rev_range.get('max', float('inf')):
        disqualifying_factors.append(f"Revenue ${monthly_revenue:,.0f} above maximum")
        score -= 30
    
    nsf_count = applicant_profile.get('nsf_count', 0)
    nsf_limits = lender_criteria.get('nsf_limits', {})
    
    if nsf_count > nsf_limits.get('30_day', 99):
        disqualifying_factors.append(f"NSF count {nsf_count} exceeds limit {nsf_limits['30_day']}")
        score -= 40
    elif nsf_count > nsf_limits.get('30_day', 99) * 0.7:
        warnings.append("NSF count approaching limit")
        score -= 10
    
    negative_days = applicant_profile.get('negative_days', 0)
    max_negative = lender_criteria.get('max_negative_days', 99)
    
    if negative_days > max_negative:
        disqualifying_factors.append(f"Negative days {negative_days} exceeds limit {max_negative}")
        score -= 35
    
    positions = applicant_profile.get('existing_positions', 0)
    max_positions = lender_criteria.get('max_positions', 99)
    allows_stacking = lender_criteria.get('allows_stacking', True)
    
    if positions > max_positions:
        disqualifying_factors.append(f"Position count {positions} exceeds maximum {max_positions}")
        score -= 45
    elif positions > 0 and not allows_stacking:
        disqualifying_factors.append("Lender does not allow stacking")
        score -= 50
    
    tib = applicant_profile.get('time_in_business_months', 12)
    min_tib = lender_criteria.get('min_time_in_business', 0)
    
    if tib < min_tib:
        disqualifying_factors.append(f"Time in business {tib} months below minimum {min_tib}")
        score -= 40
    
    is_match = len(disqualifying_factors) == 0 and score >= 50
    
    return {
        'lender_name': lender_criteria.get('lender_name', 'Unknown'),
        'is_match': is_match,
        'match_score': max(0, score),
        'disqualifying_factors': disqualifying_factors,
        'warnings': warnings,
        'max_advance': lender_criteria.get('advance_range', {}).get('max', 0),
        'factor_range': lender_criteria.get('factor_range', {}),
        'term_range': lender_criteria.get('term_range', {}),
    }


def filter_eligible_lenders(applicant_profile: Dict, all_lenders: pd.DataFrame = None) -> List[Dict]:
    """
    Filter all lenders to find eligible matches for applicant.
    """
    if all_lenders is None:
        all_lenders = load_lender_profiles()
    
    matches = []
    
    if isinstance(all_lenders, pd.DataFrame):
        lender_list = all_lenders.to_dict('records')
    else:
        lender_list = all_lenders
    
    for lender in lender_list:
        criteria = parse_lender_criteria(lender)
        match_result = check_lender_match(applicant_profile, criteria)
        matches.append(match_result)
    
    matches.sort(key=lambda x: (-x['is_match'], -x['match_score']))
    
    return matches


def rank_lender_matches(matches: List[Dict], preferences: Dict = None) -> List[Dict]:
    """
    Rank eligible lenders based on terms and preferences.
    """
    if preferences is None:
        preferences = {
            'prefer_lower_factor': True,
            'prefer_longer_term': True,
            'max_factor': 1.50,
        }
    
    for match in matches:
        if not match['is_match']:
            match['preference_score'] = 0
            continue
        
        pref_score = match['match_score']
        
        factor_range = match.get('factor_range', {})
        if preferences.get('prefer_lower_factor') and factor_range:
            avg_factor = (factor_range.get('min', 1.5) + factor_range.get('max', 1.5)) / 2
            if avg_factor < 1.30:
                pref_score += 15
            elif avg_factor < 1.40:
                pref_score += 10
        
        term_range = match.get('term_range', {})
        if preferences.get('prefer_longer_term') and term_range:
            if term_range.get('max', 6) >= 12:
                pref_score += 10
        
        match['preference_score'] = pref_score
    
    matches.sort(key=lambda x: (-x.get('preference_score', 0)))
    
    return matches


def generate_lender_summary(matches: List[Dict]) -> Dict:
    """
    Generate summary of lender matching results.
    """
    eligible = [m for m in matches if m['is_match']]
    ineligible = [m for m in matches if not m['is_match']]
    
    best_match = eligible[0] if eligible else None
    
    all_factors = []
    for m in ineligible:
        all_factors.extend(m.get('disqualifying_factors', []))
    
    common_issues = {}
    for factor in all_factors:
        key = factor.split()[0] if factor else 'Unknown'
        common_issues[key] = common_issues.get(key, 0) + 1
    
    return {
        'total_lenders_checked': len(matches),
        'eligible_count': len(eligible),
        'ineligible_count': len(ineligible),
        'best_match': best_match,
        'eligible_lenders': [m['lender_name'] for m in eligible],
        'common_disqualifying_factors': common_issues,
        'approval_rate': round(len(eligible) / len(matches) * 100, 1) if matches else 0,
    }


def find_matching_lenders(applicant_profile: Dict, config_path: str = None) -> Dict:
    """
    Main function to find all matching lenders for an applicant.
    Returns complete matching results with ranked recommendations.
    """
    if config_path:
        all_lenders = load_lender_profiles(config_path)
    else:
        all_lenders = load_lender_profiles()
    
    matches = filter_eligible_lenders(applicant_profile, all_lenders)
    
    ranked_matches = rank_lender_matches(matches)
    
    summary = generate_lender_summary(ranked_matches)
    
    return {
        'matches': ranked_matches,
        'summary': summary,
        'applicant_profile': applicant_profile,
        'lenders_checked': len(all_lenders),
    }
