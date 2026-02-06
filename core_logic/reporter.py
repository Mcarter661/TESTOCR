"""
Reporter Module
Generates Master Excel reports with multiple tabs using XlsxWriter.
"""

import xlsxwriter
import json
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
import os


def create_workbook(output_path: str) -> xlsxwriter.Workbook:
    """
    Create a new Excel workbook for the report.
    """
    workbook = xlsxwriter.Workbook(output_path)
    return workbook


def get_formats(workbook: xlsxwriter.Workbook) -> Dict:
    """
    Create standard formats for the workbook.
    """
    return {
        'title': workbook.add_format({
            'bold': True, 'font_size': 16, 'font_color': '#1e3a5f',
            'bottom': 2, 'bottom_color': '#1e3a5f'
        }),
        'header': workbook.add_format({
            'bold': True, 'bg_color': '#1e3a5f', 'font_color': 'white',
            'border': 1, 'text_wrap': True, 'valign': 'vcenter'
        }),
        'subheader': workbook.add_format({
            'bold': True, 'bg_color': '#e8f0fe', 'border': 1
        }),
        'currency': workbook.add_format({
            'num_format': '$#,##0.00', 'border': 1
        }),
        'currency_negative': workbook.add_format({
            'num_format': '$#,##0.00', 'border': 1, 'font_color': 'red'
        }),
        'percent': workbook.add_format({
            'num_format': '0.00%', 'border': 1
        }),
        'number': workbook.add_format({
            'num_format': '#,##0', 'border': 1
        }),
        'date': workbook.add_format({
            'num_format': 'yyyy-mm-dd', 'border': 1
        }),
        'text': workbook.add_format({
            'border': 1, 'text_wrap': True
        }),
        'good': workbook.add_format({
            'bg_color': '#c6efce', 'font_color': '#006100', 'border': 1
        }),
        'warning': workbook.add_format({
            'bg_color': '#ffeb9c', 'font_color': '#9c5700', 'border': 1
        }),
        'bad': workbook.add_format({
            'bg_color': '#ffc7ce', 'font_color': '#9c0006', 'border': 1
        }),
        'label': workbook.add_format({
            'bold': True, 'bg_color': '#f0f0f0', 'border': 1
        }),
        'header_left': workbook.add_format({
            'bold': True, 'bg_color': '#1e3a5f', 'font_color': 'white',
            'border': 1, 'align': 'left'
        }),
        'value': workbook.add_format({
            'border': 1, 'align': 'left'
        }),
        'pass': workbook.add_format({
            'bg_color': '#dcfce7', 'font_color': '#166534', 'border': 1, 'bold': True
        }),
        'fail': workbook.add_format({
            'bg_color': '#fee2e2', 'font_color': '#991b1b', 'border': 1, 'bold': True
        }),
        'warn': workbook.add_format({
            'bg_color': '#fef3c7', 'font_color': '#92400e', 'border': 1, 'bold': True
        }),
        'section': workbook.add_format({
            'bold': True, 'font_size': 12, 'bg_color': '#2563eb',
            'font_color': 'white', 'border': 1
        }),
        'wrap': workbook.add_format({
            'border': 1, 'text_wrap': True
        }),
        'currency_bold': workbook.add_format({
            'bold': True, 'num_format': '$#,##0.00', 'border': 1
        }),
    }


def add_summary_sheet(workbook: xlsxwriter.Workbook, summary_data: Dict, formats: Dict) -> None:
    """
    Add executive summary sheet to workbook.
    """
    sheet = workbook.add_worksheet('Summary')
    sheet.set_column('A:A', 25)
    sheet.set_column('B:B', 20)
    sheet.set_column('C:C', 25)
    sheet.set_column('D:D', 20)
    
    sheet.write('A1', 'MCA UNDERWRITING ANALYSIS', formats['title'])
    sheet.write('A2', f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", formats['text'])
    
    row = 4
    sheet.write(row, 0, 'ACCOUNT INFORMATION', formats['subheader'])
    sheet.merge_range(row, 0, row, 3, 'ACCOUNT INFORMATION', formats['subheader'])
    row += 1
    
    account_info = summary_data.get('account_info', {})
    fields = [
        ('Bank', account_info.get('bank_name', 'N/A')),
        ('Account Number', account_info.get('account_number', 'N/A')),
        ('Statement Period', f"{account_info.get('statement_period_start', 'N/A')} to {account_info.get('statement_period_end', 'N/A')}"),
        ('Opening Balance', account_info.get('opening_balance', 0)),
        ('Closing Balance', account_info.get('closing_balance', 0)),
    ]
    
    for label, value in fields:
        sheet.write(row, 0, label, formats['label'])
        if isinstance(value, (int, float)) and 'Balance' in label:
            sheet.write(row, 1, value, formats['currency'])
        else:
            sheet.write(row, 1, str(value), formats['text'])
        row += 1
    
    row += 1
    sheet.merge_range(row, 0, row, 3, 'REVENUE METRICS', formats['subheader'])
    row += 1
    
    revenue = summary_data.get('revenue_metrics', {})
    revenue_fields = [
        ('Gross Deposits', revenue.get('gross_deposits', 0)),
        ('Gross Withdrawals', revenue.get('gross_withdrawals', 0)),
        ('Net Revenue', revenue.get('net_revenue', 0)),
        ('Monthly Avg Deposits', revenue.get('monthly_average_deposits', 0)),
        ('Deposit Count', revenue.get('deposit_count', 0)),
        ('Avg Deposit Size', revenue.get('average_deposit_size', 0)),
    ]
    
    for label, value in revenue_fields:
        sheet.write(row, 0, label, formats['label'])
        if label == 'Deposit Count':
            sheet.write(row, 1, value, formats['number'])
        else:
            sheet.write(row, 1, value, formats['currency'])
        row += 1
    
    row += 1
    sheet.merge_range(row, 0, row, 3, 'RISK ASSESSMENT', formats['subheader'])
    row += 1
    
    risk = summary_data.get('risk_profile', {})
    risk_score = risk.get('risk_score', {})
    
    tier = risk_score.get('risk_tier', 'N/A')
    tier_format = formats['good'] if tier in ['A', 'B'] else (formats['warning'] if tier == 'C' else formats['bad'])
    
    sheet.write(row, 0, 'Risk Tier', formats['label'])
    sheet.write(row, 1, tier, tier_format)
    sheet.write(row, 2, 'Risk Score', formats['label'])
    sheet.write(row, 3, risk_score.get('risk_score', 0), formats['number'])
    row += 1
    
    nsf = risk.get('nsf_analysis', {})
    sheet.write(row, 0, 'NSF Count', formats['label'])
    nsf_count = nsf.get('nsf_count', 0)
    nsf_format = formats['bad'] if nsf_count >= 3 else (formats['warning'] if nsf_count >= 1 else formats['good'])
    sheet.write(row, 1, nsf_count, nsf_format)
    sheet.write(row, 2, 'NSF Fees', formats['label'])
    sheet.write(row, 3, nsf.get('nsf_total_fees', 0), formats['currency'])
    row += 1
    
    neg = risk.get('negative_days', {})
    sheet.write(row, 0, 'Negative Days', formats['label'])
    neg_count = neg.get('negative_days_count', 0)
    neg_format = formats['bad'] if neg_count >= 5 else (formats['warning'] if neg_count >= 2 else formats['good'])
    sheet.write(row, 1, neg_count, neg_format)
    sheet.write(row, 2, 'Negative %', formats['label'])
    sheet.write(row, 3, neg.get('negative_percentage', 0) / 100, formats['percent'])
    row += 1
    
    mca = risk.get('mca_positions', {})
    sheet.write(row, 0, 'Existing MCAs', formats['label'])
    mca_count = mca.get('unique_mca_lenders', 0)
    mca_format = formats['bad'] if mca_count >= 2 else (formats['warning'] if mca_count >= 1 else formats['good'])
    sheet.write(row, 1, mca_count, mca_format)
    sheet.write(row, 2, 'Stacking', formats['label'])
    stacking = 'YES' if mca.get('stacking_detected') else 'NO'
    sheet.write(row, 3, stacking, formats['bad'] if stacking == 'YES' else formats['good'])
    row += 2
    
    sheet.merge_range(row, 0, row, 3, 'RISK FACTORS', formats['subheader'])
    row += 1
    
    for factor in risk_score.get('risk_factors', [])[:5]:
        sheet.write(row, 0, factor, formats['text'])
        sheet.merge_range(row, 0, row, 3, factor, formats['warning'])
        row += 1


def add_transactions_sheet(workbook: xlsxwriter.Workbook, transactions: List[Dict], formats: Dict) -> None:
    """
    Add detailed transactions sheet to workbook.
    """
    sheet = workbook.add_worksheet('Transactions')
    
    sheet.set_column('A:A', 12)
    sheet.set_column('B:B', 40)
    sheet.set_column('C:C', 15)
    sheet.set_column('D:D', 12)
    sheet.set_column('E:E', 12)
    sheet.set_column('F:F', 15)
    sheet.set_column('G:G', 15)
    
    headers = ['Date', 'Description', 'Category', 'Debit', 'Credit', 'Amount', 'Balance']
    for col, header in enumerate(headers):
        sheet.write(0, col, header, formats['header'])
    
    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, len(transactions) + 1, len(headers) - 1)
    
    for row, txn in enumerate(transactions, start=1):
        sheet.write(row, 0, txn.get('date', ''), formats['date'])
        sheet.write(row, 1, txn.get('cleaned_description', txn.get('description', '')), formats['text'])
        sheet.write(row, 2, txn.get('category', 'other'), formats['text'])
        
        debit = txn.get('debit', 0)
        credit = txn.get('credit', 0)
        
        if debit > 0:
            sheet.write(row, 3, debit, formats['currency_negative'])
        else:
            sheet.write(row, 3, '', formats['text'])
        
        if credit > 0:
            sheet.write(row, 4, credit, formats['currency'])
        else:
            sheet.write(row, 4, '', formats['text'])
        
        sheet.write(row, 5, txn.get('amount', 0), formats['currency'])
        
        balance = txn.get('balance')
        if balance is not None:
            sheet.write(row, 6, balance, formats['currency'])


def add_monthly_analysis_sheet(workbook: xlsxwriter.Workbook, monthly_data: pd.DataFrame, formats: Dict) -> None:
    """
    Add monthly breakdown analysis sheet.
    """
    sheet = workbook.add_worksheet('Monthly Analysis')
    
    sheet.set_column('A:A', 15)
    sheet.set_column('B:B', 15)
    sheet.set_column('C:C', 15)
    sheet.set_column('D:D', 15)
    sheet.set_column('E:E', 15)
    
    headers = ['Month', 'Deposits', 'Withdrawals', 'Net', 'Change %']
    for col, header in enumerate(headers):
        sheet.write(0, col, header, formats['header'])
    
    if monthly_data is not None and not monthly_data.empty:
        for row, (_, data) in enumerate(monthly_data.iterrows(), start=1):
            sheet.write(row, 0, str(data.get('month', '')), formats['text'])
            sheet.write(row, 1, data.get('deposits', 0), formats['currency'])
            sheet.write(row, 2, data.get('withdrawals', 0), formats['currency'])
            
            net = data.get('net', 0)
            net_format = formats['currency'] if net >= 0 else formats['currency_negative']
            sheet.write(row, 3, net, net_format)
            
            change = data.get('deposit_change', 0) / 100 if 'deposit_change' in data else 0
            change_format = formats['good'] if change > 0 else (formats['bad'] if change < -0.1 else formats['text'])
            sheet.write(row, 4, change, formats['percent'])
        
        if len(monthly_data) >= 2:
            chart = workbook.add_chart({'type': 'column'})
            chart.add_series({
                'name': 'Deposits',
                'categories': ['Monthly Analysis', 1, 0, len(monthly_data), 0],
                'values': ['Monthly Analysis', 1, 1, len(monthly_data), 1],
                'fill': {'color': '#4CAF50'},
            })
            chart.add_series({
                'name': 'Withdrawals',
                'categories': ['Monthly Analysis', 1, 0, len(monthly_data), 0],
                'values': ['Monthly Analysis', 1, 2, len(monthly_data), 2],
                'fill': {'color': '#f44336'},
            })
            chart.set_title({'name': 'Monthly Cash Flow'})
            chart.set_style(10)
            sheet.insert_chart('G2', chart, {'x_scale': 1.5, 'y_scale': 1.2})


def add_risk_analysis_sheet(workbook: xlsxwriter.Workbook, risk_profile: Dict, formats: Dict) -> None:
    """
    Add risk analysis sheet to workbook.
    """
    sheet = workbook.add_worksheet('Risk Analysis')
    
    sheet.set_column('A:A', 25)
    sheet.set_column('B:B', 15)
    sheet.set_column('C:C', 25)
    sheet.set_column('D:D', 15)
    
    row = 0
    sheet.write(row, 0, 'RISK ANALYSIS REPORT', formats['title'])
    row += 2
    
    risk_score = risk_profile.get('risk_score', {})
    sheet.merge_range(row, 0, row, 3, 'OVERALL RISK ASSESSMENT', formats['subheader'])
    row += 1
    
    sheet.write(row, 0, 'Risk Score', formats['label'])
    sheet.write(row, 1, risk_score.get('risk_score', 0), formats['number'])
    sheet.write(row, 2, 'Risk Tier', formats['label'])
    tier = risk_score.get('risk_tier', 'N/A')
    tier_format = formats['good'] if tier in ['A', 'B'] else (formats['warning'] if tier == 'C' else formats['bad'])
    sheet.write(row, 3, tier, tier_format)
    row += 2
    
    sheet.merge_range(row, 0, row, 3, 'NSF ANALYSIS', formats['subheader'])
    row += 1
    
    nsf = risk_profile.get('nsf_analysis', {})
    sheet.write(row, 0, 'Total NSF Count', formats['label'])
    sheet.write(row, 1, nsf.get('nsf_count', 0), formats['number'])
    sheet.write(row, 2, 'Total NSF Fees', formats['label'])
    sheet.write(row, 3, nsf.get('nsf_total_fees', 0), formats['currency'])
    row += 1
    
    for i, nsf_txn in enumerate(nsf.get('nsf_transactions', [])[:5]):
        sheet.write(row, 0, nsf_txn.get('date', ''), formats['date'])
        sheet.write(row, 1, nsf_txn.get('amount', 0), formats['currency'])
        row += 1
    
    row += 1
    sheet.merge_range(row, 0, row, 3, 'NEGATIVE BALANCE ANALYSIS', formats['subheader'])
    row += 1
    
    neg = risk_profile.get('negative_days', {})
    sheet.write(row, 0, 'Negative Days', formats['label'])
    sheet.write(row, 1, neg.get('negative_days_count', 0), formats['number'])
    sheet.write(row, 2, 'Percentage', formats['label'])
    sheet.write(row, 3, neg.get('negative_percentage', 0) / 100, formats['percent'])
    row += 1
    sheet.write(row, 0, 'Max Negative', formats['label'])
    sheet.write(row, 1, neg.get('max_negative', 0), formats['currency'])
    row += 2
    
    sheet.merge_range(row, 0, row, 3, 'EXISTING MCA POSITIONS', formats['subheader'])
    row += 1
    
    mca = risk_profile.get('mca_positions', {})
    sheet.write(row, 0, 'Detected Lenders', formats['label'])
    sheet.write(row, 1, mca.get('unique_mca_lenders', 0), formats['number'])
    sheet.write(row, 2, 'Stacking Detected', formats['label'])
    stacking = 'YES' if mca.get('stacking_detected') else 'NO'
    sheet.write(row, 3, stacking, formats['bad'] if stacking == 'YES' else formats['good'])
    row += 1
    sheet.write(row, 0, 'Total MCA Payments', formats['label'])
    sheet.write(row, 1, mca.get('mca_total_payments', 0), formats['currency'])
    row += 2
    
    sheet.merge_range(row, 0, row, 3, 'CASH ACTIVITY', formats['subheader'])
    row += 1
    
    cash = risk_profile.get('cash_activity', {})
    sheet.write(row, 0, 'Cash Deposits', formats['label'])
    sheet.write(row, 1, cash.get('cash_deposit_total', 0), formats['currency'])
    sheet.write(row, 2, 'Cash %', formats['label'])
    sheet.write(row, 3, cash.get('cash_percentage', 0) / 100, formats['percent'])
    row += 1
    sheet.write(row, 0, 'ATM Withdrawals', formats['label'])
    sheet.write(row, 1, cash.get('atm_withdrawal_total', 0), formats['currency'])


def add_lender_matches_sheet(workbook: xlsxwriter.Workbook, matches: List[Dict], formats: Dict) -> None:
    """
    Add lender matching results sheet.
    """
    sheet = workbook.add_worksheet('Lender Matches')
    
    sheet.set_column('A:A', 25)
    sheet.set_column('B:B', 12)
    sheet.set_column('C:C', 12)
    sheet.set_column('D:D', 15)
    sheet.set_column('E:E', 15)
    sheet.set_column('F:F', 40)
    
    headers = ['Lender', 'Match', 'Score', 'Max Advance', 'Factor Range', 'Notes']
    for col, header in enumerate(headers):
        sheet.write(0, col, header, formats['header'])
    
    for row, match in enumerate(matches[:20], start=1):
        sheet.write(row, 0, match.get('lender_name', ''), formats['text'])
        
        is_match = match.get('is_match', False)
        match_format = formats['good'] if is_match else formats['bad']
        sheet.write(row, 1, 'YES' if is_match else 'NO', match_format)
        
        sheet.write(row, 2, match.get('match_score', 0), formats['number'])
        sheet.write(row, 3, match.get('max_advance', 0), formats['currency'])
        
        factor_range = match.get('factor_range', {})
        factor_str = f"{factor_range.get('min', 0):.2f} - {factor_range.get('max', 0):.2f}"
        sheet.write(row, 4, factor_str, formats['text'])
        
        notes = '; '.join(match.get('disqualifying_factors', [])[:2])
        if match.get('warnings'):
            notes += ' | ' + '; '.join(match.get('warnings', [])[:2])
        sheet.write(row, 5, notes[:100], formats['text'])


def add_mca_positions_sheet(workbook: xlsxwriter.Workbook, risk_profile: Dict, formats: Dict, position_data: Optional[Dict] = None) -> None:
    """
    Add detailed MCA positions sheet with reverse-engineered data.
    Uses position_detector data when available for more accurate results.
    """
    sheet = workbook.add_worksheet('MCA Positions')
    
    sheet.set_column('A:A', 25)
    sheet.set_column('B:B', 12)
    sheet.set_column('C:C', 12)
    sheet.set_column('D:D', 15)
    sheet.set_column('E:E', 15)
    sheet.set_column('F:F', 15)
    sheet.set_column('G:G', 15)
    sheet.set_column('H:H', 15)
    sheet.set_column('I:I', 12)
    
    row = 0
    sheet.write(row, 0, 'EXISTING MCA POSITIONS ANALYSIS', formats['title'])
    row += 2
    
    use_position_detector = position_data and position_data.get('positions')
    
    if use_position_detector:
        pos_list = position_data.get('positions', [])
        total_positions = position_data.get('total_positions', len(pos_list))
        total_monthly = position_data.get('total_monthly_payment', 0)
        total_remaining = position_data.get('estimated_total_remaining', 0)
        
        sheet.merge_range(row, 0, row, 8, 'POSITION SUMMARY', formats['subheader'])
        row += 1
        sheet.write(row, 0, 'Total Positions Detected', formats['label'])
        sheet.write(row, 1, total_positions, formats['number'])
        sheet.write(row, 2, 'Stacking', formats['label'])
        stacking = 'YES' if total_positions > 1 else 'NO'
        sheet.write(row, 3, stacking, formats['bad'] if stacking == 'YES' else formats['good'])
        row += 1
        sheet.write(row, 0, 'Total Monthly Holdback', formats['label'])
        sheet.write(row, 1, total_monthly, formats['currency'])
        sheet.write(row, 2, 'Est. Total Remaining', formats['label'])
        sheet.write(row, 3, total_remaining, formats['currency'])
        row += 1
        sheet.write(row, 0, 'Total Daily Payment', formats['label'])
        sheet.write(row, 1, position_data.get('total_daily_payment', 0), formats['currency'])
        sheet.write(row, 2, 'Days Since Last Funding', formats['label'])
        sheet.write(row, 3, position_data.get('days_since_last_funding', 0), formats['number'])
        row += 2
        
        sheet.merge_range(row, 0, row, 8, 'REVERSE-ENGINEERED POSITIONS', formats['subheader'])
        row += 1
        
        headers = ['Funder', 'Frequency', 'Payments', 'Avg Payment', 'Monthly Cost',
                   'Est. Funding', 'Est. Remaining', 'Paid In %', 'Est. Payoff']
        for col, header in enumerate(headers):
            sheet.write(row, col, header, formats['header'])
        row += 1
        
        for pos in pos_list[:15]:
            lender = pos.get('lender_name', 'Unknown')
            freq = pos.get('payment_frequency', 'unknown')
            pmt_count = pos.get('payments_detected', 0)
            avg_pmt = pos.get('payment_amount', 0)
            
            if freq == 'daily':
                monthly_cost = avg_pmt * 21.5
            elif freq == 'weekly':
                monthly_cost = avg_pmt * 4.33
            elif freq == 'biweekly':
                monthly_cost = avg_pmt * 2.17
            else:
                monthly_cost = avg_pmt
            
            sheet.write(row, 0, lender, formats['text'])
            sheet.write(row, 1, freq, formats['text'])
            sheet.write(row, 2, pmt_count, formats['number'])
            sheet.write(row, 3, avg_pmt, formats['currency'])
            sheet.write(row, 4, monthly_cost, formats['currency'])
            sheet.write(row, 5, pos.get('estimated_original_funding', 0), formats['currency'])
            sheet.write(row, 6, pos.get('estimated_remaining_balance', 0), formats['currency'])
            paid_pct = pos.get('paid_in_percent', 0)
            pct_fmt = formats['good'] if paid_pct > 50 else (formats['warning'] if paid_pct > 25 else formats['text'])
            sheet.write(row, 7, f"{paid_pct:.1f}%", pct_fmt)
            sheet.write(row, 8, pos.get('estimated_payoff_date', 'Unknown'), formats['text'])
            row += 1
    else:
        mca_data = risk_profile.get('mca_positions', {})
        
        sheet.merge_range(row, 0, row, 7, 'POSITION SUMMARY', formats['subheader'])
        row += 1
        
        sheet.write(row, 0, 'Total Lenders Detected', formats['label'])
        sheet.write(row, 1, mca_data.get('unique_mca_lenders', 0), formats['number'])
        sheet.write(row, 2, 'Stacking', formats['label'])
        stacking = 'YES' if mca_data.get('stacking_detected') else 'NO'
        sheet.write(row, 3, stacking, formats['bad'] if stacking == 'YES' else formats['good'])
        row += 1
        
        sheet.write(row, 0, 'Total Monthly Debt', formats['label'])
        sheet.write(row, 1, mca_data.get('total_monthly_debt', 0), formats['currency'])
        sheet.write(row, 2, 'Est. Outstanding', formats['label'])
        sheet.write(row, 3, mca_data.get('total_outstanding', 0), formats['currency'])
        row += 2
        
        sheet.merge_range(row, 0, row, 7, 'REVERSE-ENGINEERED POSITIONS', formats['subheader'])
        row += 1
        
        headers = ['Funder', 'Frequency', 'Payments', 'Avg Payment', 'Monthly Cost', 'Est. Funding', 'Est. Remaining', 'Status']
        for col, header in enumerate(headers):
            sheet.write(row, col, header, formats['header'])
        row += 1
        
        positions = mca_data.get('mca_positions', [])
        payment_changes = mca_data.get('payment_changes', {})
        
        for pos in positions[:15]:
            lender = pos.get('lender', 'Unknown')
            status = payment_changes.get(lender, {}).get('status', 'ACTIVE')
            
            sheet.write(row, 0, lender, formats['text'])
            sheet.write(row, 1, pos.get('frequency', 'unknown'), formats['text'])
            sheet.write(row, 2, pos.get('payment_count', 0), formats['number'])
            sheet.write(row, 3, pos.get('avg_payment', 0), formats['currency'])
            sheet.write(row, 4, pos.get('monthly_cost', 0), formats['currency'])
            sheet.write(row, 5, pos.get('est_funding', 0), formats['currency'])
            sheet.write(row, 6, pos.get('est_remaining', 0), formats['currency'])
            
            status_format = formats['good'] if status == 'ACTIVE' else (formats['warning'] if status == 'REDUCED' else formats['bad'])
            sheet.write(row, 7, status, status_format)
            row += 1
    
    row += 1
    mca_data = risk_profile.get('mca_positions', {})
    payment_changes = mca_data.get('payment_changes', {})
    if payment_changes:
        sheet.merge_range(row, 0, row, 7, 'PAYMENT CHANGE TRACKING', formats['subheader'])
        row += 1
        
        headers2 = ['Funder', 'First Avg', 'Recent Avg', '% Change', 'Status', 'Last Payment', 'Days Since', '']
        for col, header in enumerate(headers2):
            sheet.write(row, col, header, formats['header'])
        row += 1
        
        for lender, change in payment_changes.items():
            sheet.write(row, 0, lender, formats['text'])
            sheet.write(row, 1, change.get('first_avg', 0), formats['currency'])
            sheet.write(row, 2, change.get('second_avg', 0), formats['currency'])
            
            pct = change.get('pct_change', 0)
            pct_format = formats['good'] if pct < -20 else (formats['bad'] if pct > 20 else formats['text'])
            sheet.write(row, 3, pct / 100, formats['percent'])
            
            status = change.get('status', 'ACTIVE')
            status_format = formats['good'] if status == 'ACTIVE' else (formats['warning'] if status == 'REDUCED' else formats['bad'])
            sheet.write(row, 4, status, status_format)
            sheet.write(row, 5, change.get('last_payment', ''), formats['date'])
            sheet.write(row, 6, change.get('days_since_last', 0), formats['number'])
            row += 1


def add_funding_analysis_sheet(workbook: xlsxwriter.Workbook, risk_profile: Dict, formats: Dict) -> None:
    """
    Add funding events analysis sheet.
    """
    sheet = workbook.add_worksheet('Funding Analysis')
    
    sheet.set_column('A:A', 12)
    sheet.set_column('B:B', 40)
    sheet.set_column('C:C', 15)
    sheet.set_column('D:D', 12)
    sheet.set_column('E:E', 15)
    
    row = 0
    sheet.write(row, 0, 'FUNDING EVENTS ANALYSIS', formats['title'])
    row += 2
    
    funding = risk_profile.get('funding_analysis', {})
    
    sheet.merge_range(row, 0, row, 4, 'FUNDING SUMMARY', formats['subheader'])
    row += 1
    
    sheet.write(row, 0, 'Total Funding Events', formats['label'])
    sheet.write(row, 1, funding.get('funding_count', 0), formats['number'])
    row += 1
    sheet.write(row, 0, 'Total Funding Amount', formats['label'])
    sheet.write(row, 1, funding.get('total_funding', 0), formats['currency'])
    row += 1
    sheet.write(row, 0, 'Days Since Last', formats['label'])
    days = funding.get('days_since_last_funding', 999)
    days_format = formats['bad'] if days <= 30 else formats['good']
    sheet.write(row, 1, days if days < 999 else 'N/A', days_format if days < 999 else formats['text'])
    row += 2
    
    sheet.merge_range(row, 0, row, 4, 'FUNDING EVENTS (Wire Transfers)', formats['subheader'])
    row += 1
    
    headers = ['Date', 'Description', 'Amount', 'Type', 'Likely MCA']
    for col, header in enumerate(headers):
        sheet.write(row, col, header, formats['header'])
    row += 1
    
    for event in funding.get('funding_events', [])[:20]:
        sheet.write(row, 0, event.get('date', ''), formats['date'])
        sheet.write(row, 1, event.get('description', '')[:40], formats['text'])
        sheet.write(row, 2, event.get('amount', 0), formats['currency'])
        sheet.write(row, 3, event.get('funding_type', ''), formats['text'])
        
        likely = 'YES' if event.get('likely_mca') else 'NO'
        likely_format = formats['warning'] if likely == 'YES' else formats['text']
        sheet.write(row, 4, likely, likely_format)
        row += 1
    
    row += 2
    revenue = risk_profile.get('revenue_sources', {})
    sheet.merge_range(row, 0, row, 4, 'REVENUE SOURCES', formats['subheader'])
    row += 1
    
    headers2 = ['Source', 'Type', 'Total', 'Monthly Avg', '% of Revenue']
    for col, header in enumerate(headers2):
        sheet.write(row, col, header, formats['header'])
    row += 1
    
    for source in revenue.get('sources', [])[:10]:
        sheet.write(row, 0, source.get('source', ''), formats['text'])
        sheet.write(row, 1, source.get('type', ''), formats['text'])
        sheet.write(row, 2, source.get('total', 0), formats['currency'])
        sheet.write(row, 3, source.get('monthly_avg', 0), formats['currency'])
        sheet.write(row, 4, source.get('pct_of_revenue', 0) / 100, formats['percent'])
        row += 1
    
    row += 2
    expenses = risk_profile.get('recurring_expenses', {})
    sheet.merge_range(row, 0, row, 4, 'RECURRING EXPENSES', formats['subheader'])
    row += 1
    
    headers3 = ['Expense', 'Type', 'Total', 'Monthly Est', 'Avg Payment']
    for col, header in enumerate(headers3):
        sheet.write(row, col, header, formats['header'])
    row += 1
    
    for exp in expenses.get('expenses', [])[:10]:
        sheet.write(row, 0, exp.get('expense', ''), formats['text'])
        sheet.write(row, 1, exp.get('type', ''), formats['text'])
        sheet.write(row, 2, exp.get('total', 0), formats['currency'])
        sheet.write(row, 3, exp.get('monthly_est', 0), formats['currency'])
        sheet.write(row, 4, exp.get('avg_payment', 0), formats['currency'])
        row += 1


def add_red_flags_sheet(workbook: xlsxwriter.Workbook, risk_profile: Dict, formats: Dict) -> None:
    """
    Add red flags summary sheet.
    """
    sheet = workbook.add_worksheet('Red Flags')
    
    sheet.set_column('A:A', 25)
    sheet.set_column('B:B', 15)
    sheet.set_column('C:C', 50)
    
    row = 0
    sheet.write(row, 0, 'RED FLAGS & WARNINGS', formats['title'])
    row += 2
    
    red_flags = risk_profile.get('red_flags', {})
    
    sheet.merge_range(row, 0, row, 2, 'SUMMARY', formats['subheader'])
    row += 1
    
    critical = red_flags.get('critical_count', 0)
    high = red_flags.get('high_count', 0)
    
    sheet.write(row, 0, 'Critical Flags', formats['label'])
    sheet.write(row, 1, critical, formats['bad'] if critical > 0 else formats['good'])
    row += 1
    sheet.write(row, 0, 'High Priority Flags', formats['label'])
    sheet.write(row, 1, high, formats['warning'] if high > 0 else formats['good'])
    row += 2
    
    sheet.merge_range(row, 0, row, 2, 'DETAILED FLAGS', formats['subheader'])
    row += 1
    
    headers = ['Flag', 'Severity', 'Detail']
    for col, header in enumerate(headers):
        sheet.write(row, col, header, formats['header'])
    row += 1
    
    for flag in red_flags.get('red_flags', []):
        sheet.write(row, 0, flag.get('flag', ''), formats['text'])
        
        severity = flag.get('severity', '')
        sev_format = formats['bad'] if severity == 'critical' else formats['warning']
        sheet.write(row, 1, severity.upper(), sev_format)
        
        sheet.write(row, 2, flag.get('detail', ''), formats['text'])
        row += 1


def _add_forensics_tab(workbook: xlsxwriter.Workbook, formats: Dict, risk: Dict, fraud_flags: List) -> None:
    ws = workbook.add_worksheet("In-House Forensics")
    ws.set_column("A:A", 28)
    ws.set_column("B:B", 14)
    ws.set_column("C:C", 14)
    ws.set_column("D:D", 50)

    ws.write("A1", "IN-HOUSE FORENSICS CHECKLIST", formats['title'])

    row = 3
    ws.write(row, 0, "Check", formats['header'])
    ws.write(row, 1, "Value", formats['header'])
    ws.write(row, 2, "Result", formats['header'])
    ws.write(row, 3, "Details", formats['header_left'])
    row += 1

    checks = [
        ("NSF Count", risk.get("nsf_count", 0), risk.get("nsf_count", 0) <= 5,
         f"{risk.get('nsf_count', 0)} NSFs, ${risk.get('nsf_total_fees', 0):.2f} in fees"),
        ("Negative Days", risk.get("negative_day_count", 0), risk.get("negative_day_count", 0) <= 5,
         f"{risk.get('consecutive_negative_days', 0)} consecutive, max ${abs(risk.get('max_negative_balance', 0)):,.2f}"),
        ("Cash Deposits", f"{risk.get('cash_deposit_percent', 0):.1f}%",
         not risk.get("cash_risk_flag", False),
         f"${risk.get('cash_deposit_total', 0):,.2f} total cash deposits"),
        ("Gambling Activity", "Detected" if risk.get("gambling_flag") else "None",
         not risk.get("gambling_flag", False),
         f"${risk.get('gambling_total', 0):,.2f} total" if risk.get("gambling_flag") else "No gambling transactions found"),
        ("Tax Liens/Garnishments", str(sum(1 for f in risk.get("red_flags", []) if isinstance(f, dict) and f.get("category") in ("Tax", "Legal"))),
         not any(isinstance(f, dict) and f.get("category") in ("Tax", "Legal") for f in risk.get("red_flags", [])),
         "See red flags below" if risk.get("red_flags") else "No tax liens or garnishments found"),
        ("DTI Ratio", "N/A", True, "See Master Summary"),
        ("Revenue Trend", risk.get("velocity_flag", "stable"),
         risk.get("velocity_flag", "stable") not in ("declining", "accelerating_decline"),
         f"Velocity: {risk.get('revenue_velocity', 0):.1f}% MoM, Accel: {risk.get('revenue_acceleration', 0):.1f}%"),
    ]

    if fraud_flags:
        checks.append(("PDF Metadata", "ALERT", False, "; ".join(fraud_flags)))
    else:
        checks.append(("PDF Metadata", "Clean", True, "No editing software detected"))

    for check_name, value, passed, detail in checks:
        ws.write(row, 0, check_name, formats['label'])
        ws.write(row, 1, str(value), formats['value'])
        ws.write(row, 2, "PASS" if passed else "FAIL", formats['pass'] if passed else formats['fail'])
        ws.write(row, 3, detail, formats['wrap'])
        row += 1

    row += 2
    red_flags = risk.get("red_flags", [])
    ws.write(row, 0, "RED FLAGS", formats['section'])
    row += 1

    if not red_flags:
        ws.write(row, 0, "No red flags detected.", formats['pass'])
    else:
        ws.write(row, 0, "Severity", formats['header'])
        ws.write(row, 1, "Category", formats['header'])
        ws.write(row, 2, "Date", formats['header'])
        ws.write(row, 3, "Description", formats['header_left'])
        row += 1
        for flag in red_flags:
            if isinstance(flag, str):
                ws.write(row, 0, "MEDIUM", formats['warn'])
                ws.write(row, 1, "", formats['value'])
                ws.write(row, 2, "", formats['value'])
                ws.write(row, 3, flag, formats['wrap'])
            else:
                sev = flag.get("severity", "MEDIUM")
                sev_fmt = formats['fail'] if sev == "HIGH" else formats['warn']
                ws.write(row, 0, sev, sev_fmt)
                ws.write(row, 1, flag.get("category", ""), formats['value'])
                ws.write(row, 2, flag.get("date", ""), formats['value'])
                ws.write(row, 3, flag.get("description", ""), formats['wrap'])
            row += 1

    row += 2
    expenses = risk.get("expenses_by_category", {})
    if expenses:
        ws.write(row, 0, "EXPENSE BREAKDOWN", formats['section'])
        row += 1
        ws.write(row, 0, "Category", formats['header'])
        ws.write(row, 1, "Monthly Avg", formats['header'])
        row += 1
        for cat, total in sorted(expenses.items(), key=lambda x: -x[1]):
            ws.write(row, 0, cat.title(), formats['label'])
            ws.write(row, 1, total, formats['currency'])
            row += 1


def _add_deal_summary_tab(workbook: xlsxwriter.Workbook, formats: Dict, summary: Dict) -> None:
    ws = workbook.add_worksheet("Deal Summary")
    ws.set_column("A:A", 28)
    ws.set_column("B:B", 20)
    ws.set_column("C:C", 24)
    ws.set_column("D:D", 18)
    ws.set_column("E:H", 14)

    row = 0
    ws.write(row, 0, "DEAL SUMMARY - SPEC SHEET", formats['title'])
    row += 2

    ws.write(row, 0, "BUSINESS INFORMATION", formats['section'])
    row += 1
    info_fields = [
        ("Legal Name", summary.get("legal_name", "")),
        ("DBA", summary.get("dba", "")),
        ("Industry", summary.get("industry", "")),
        ("State", summary.get("state", "")),
        ("FICO Score", summary.get("fico_score", 0)),
        ("Time in Business", f"{summary.get('time_in_business_months', 0)} months"),
        ("Ownership", f"{summary.get('ownership_percent', 100)}%"),
        ("Deal Type", summary.get("deal_type", "")),
        ("Tier", summary.get("tier", "")),
    ]
    for label, value in info_fields:
        ws.write(row, 0, label, formats['label'])
        if label == "Tier":
            t = str(value)
            t_fmt = formats['pass'] if t in ("A", "B") else formats['warn'] if t == "C" else formats['fail']
            ws.write(row, 1, t, t_fmt)
        else:
            ws.write(row, 1, value, formats['value'])
        row += 1

    row += 1
    ws.write(row, 0, "REVENUE SUMMARY", formats['section'])
    row += 1
    ws.write(row, 0, "Avg Monthly Revenue", formats['label'])
    ws.write(row, 1, summary.get("avg_monthly_revenue", 0), formats['currency'])
    ws.write(row, 2, "Annualized Revenue", formats['label'])
    ws.write(row, 3, summary.get("annualized_revenue", 0), formats['currency'])
    row += 1
    ws.write(row, 0, "Lowest Month", formats['label'])
    ws.write(row, 1, summary.get("lowest_month_revenue", 0), formats['currency'])
    ws.write(row, 2, "Highest Month", formats['label'])
    ws.write(row, 3, summary.get("highest_month_revenue", 0), formats['currency'])
    row += 1
    trend = summary.get("revenue_trend", "")
    ws.write(row, 0, "Revenue Trend", formats['label'])
    t_fmt = formats['pass'] if trend == "Growing" else formats['fail'] if trend == "Declining" else formats['value']
    ws.write(row, 1, trend or "N/A", t_fmt)
    ws.write(row, 2, "Avg Daily Balance", formats['label'])
    ws.write(row, 3, summary.get("avg_daily_balance", 0), formats['currency'])
    row += 1
    ws.write(row, 0, "Total NSFs", formats['label'])
    nsf = summary.get("total_nsf_count", 0)
    ws.write(row, 1, nsf, formats['fail'] if nsf > 3 else formats['value'])
    ws.write(row, 2, "Total Negative Days", formats['label'])
    neg = summary.get("total_negative_days", 0)
    ws.write(row, 3, neg, formats['fail'] if neg > 5 else formats['value'])

    row += 2
    ws.write(row, 0, "CURRENT POSITIONS", formats['section'])
    row += 1
    ws.write(row, 0, "Position Count", formats['label'])
    ws.write(row, 1, summary.get("position_count", 0), formats['number'])
    ws.write(row, 2, "Days Since Last Funding", formats['label'])
    ws.write(row, 3, summary.get("days_since_last_funding", 0), formats['number'])
    row += 1
    ws.write(row, 0, "Current Monthly Holdback", formats['label'])
    ws.write(row, 1, summary.get("total_current_holdback", 0), formats['currency'])
    ws.write(row, 2, "Current Holdback %", formats['label'])
    hb_pct = summary.get("current_holdback_percent", 0)
    ws.write(row, 3, f"{hb_pct:.1f}%", formats['fail'] if hb_pct > 40 else formats['warn'] if hb_pct > 30 else formats['value'])
    row += 1
    ws.write(row, 0, "Total Remaining Balance", formats['label'])
    ws.write(row, 1, summary.get("total_remaining_balance", 0), formats['currency'])
    row += 1

    positions = summary.get("positions", [])
    if positions:
        row += 1
        pos_headers = ["#", "Funder", "Payment", "Freq", "Funded Amt", "Remaining", "Paid In %", "Est. Payoff"]
        for col, h in enumerate(pos_headers):
            ws.write(row, col, h, formats['header'])
        row += 1
        for pos in positions:
            ws.write(row, 0, pos.get("position", ""), formats['number'])
            ws.write(row, 1, pos.get("funder", ""), formats['value'])
            ws.write(row, 2, pos.get("payment", 0), formats['currency'])
            ws.write(row, 3, pos.get("frequency", ""), formats['value'])
            ws.write(row, 4, pos.get("funded_amount", 0), formats['currency'])
            ws.write(row, 5, pos.get("remaining", 0), formats['currency'])
            pct = pos.get("paid_in_pct", 0)
            ws.write(row, 6, f"{pct:.1f}%", formats['pass'] if pct > 50 else formats['warn'])
            ws.write(row, 7, pos.get("est_payoff", ""), formats['value'])
            row += 1

    row += 1
    ws.write(row, 0, "PROPOSED DEAL", formats['section'])
    row += 1
    ws.write(row, 0, "Funding Amount", formats['label'])
    ws.write(row, 1, summary.get("proposed_funding", 0), formats['currency_bold'])
    ws.write(row, 2, "Factor Rate", formats['label'])
    ws.write(row, 3, summary.get("proposed_factor_rate", 0), formats['value'])
    row += 1
    ws.write(row, 0, "Total Payback", formats['label'])
    ws.write(row, 1, summary.get("proposed_payback", 0), formats['currency'])
    ws.write(row, 2, "Term", formats['label'])
    ws.write(row, 3, f"{summary.get('proposed_term_months', 0)} months", formats['value'])
    row += 1
    ws.write(row, 0, "Payment Amount", formats['label'])
    ws.write(row, 1, summary.get("proposed_payment", 0), formats['currency'])
    ws.write(row, 2, "Frequency", formats['label'])
    ws.write(row, 3, summary.get("proposed_frequency", ""), formats['value'])

    row += 2
    ws.write(row, 0, "NEW DEAL IMPACT", formats['section'])
    row += 1
    ws.write(row, 0, "New Monthly Holdback", formats['label'])
    ws.write(row, 1, summary.get("new_holdback_amount", 0), formats['currency'])
    row += 1
    ws.write(row, 0, "Combined Monthly Holdback", formats['label'])
    ws.write(row, 1, summary.get("combined_holdback", 0), formats['currency_bold'])
    ws.write(row, 2, "Combined Holdback %", formats['label'])
    cb_pct = summary.get("combined_holdback_percent", 0)
    ws.write(row, 3, f"{cb_pct:.1f}%", formats['fail'] if cb_pct > 40 else formats['warn'] if cb_pct > 30 else formats['pass'])
    row += 1
    ws.write(row, 0, "Net Available After", formats['label'])
    ws.write(row, 1, summary.get("net_available_after", 0), formats['currency'])
    ws.write(row, 2, "ADB/Payment Ratio", formats['label'])
    adb_r = summary.get("adb_to_payment_ratio", 0)
    ws.write(row, 3, f"{adb_r:.2f}x", formats['pass'] if adb_r >= 3.5 else formats['fail'] if adb_r > 0 else formats['value'])

    row += 2
    ws.write(row, 0, "RECOMMENDATIONS", formats['section'])
    row += 1
    ws.write(row, 0, "Max Recommended Funding", formats['label'])
    ws.write(row, 1, summary.get("max_recommended_funding", 0), formats['currency_bold'])
    ws.write(row, 2, "Max Daily Payment", formats['label'])
    ws.write(row, 3, summary.get("max_daily_payment", 0), formats['currency'])

    row += 2
    ws.write(row, 0, "RISK FLAGS", formats['section'])
    row += 1
    risk_flags = summary.get("risk_flags", [])
    if risk_flags:
        for flag in risk_flags:
            ws.write(row, 0, "WARNING", formats['fail'])
            ws.write(row, 1, flag, formats['wrap'])
            row += 1
    else:
        ws.write(row, 0, "CLEAR", formats['pass'])
        ws.write(row, 1, "No major risk flags identified", formats['pass'])
        row += 1

    row += 1
    top_matches = summary.get("top_lender_matches", [])
    ws.write(row, 0, "TOP LENDER MATCHES", formats['section'])
    row += 1
    ws.write(row, 0, "Eligible Lenders", formats['label'])
    ws.write(row, 1, summary.get("eligible_lender_count", 0), formats['number'])
    row += 1
    if top_matches:
        for m in top_matches[:5]:
            ws.write(row, 0, m.get("lender_name", ""), formats['value'])
            ws.write(row, 1, f"Score: {m.get('match_score', 0)}", formats['value'])
            row += 1

    row += 1
    monthly = summary.get("monthly_breakdown", [])
    if monthly:
        ws.write(row, 0, "MONTHLY BREAKDOWN", formats['section'])
        row += 1
        m_headers = ["Month", "Net Revenue", "NSFs", "Neg Days", "ADB", "Deposits", "Holdback $", "Holdback %"]
        for col, h in enumerate(m_headers):
            ws.write(row, col, h, formats['header'])
        row += 1
        for mo in monthly:
            ws.write(row, 0, mo.get("month", ""), formats['value'])
            ws.write(row, 1, mo.get("net_revenue", 0), formats['currency'])
            ws.write(row, 2, mo.get("nsf_count", 0), formats['number'])
            ws.write(row, 3, mo.get("negative_days", 0), formats['number'])
            ws.write(row, 4, mo.get("avg_daily_balance", 0), formats['currency'])
            ws.write(row, 5, mo.get("deposit_count", 0), formats['number'])
            ws.write(row, 6, mo.get("holdback_amount", 0), formats['currency'])
            hb = mo.get("holdback_percent", 0)
            ws.write(row, 7, f"{hb:.1f}%", formats['warn'] if hb > 30 else formats['value'])
            row += 1


def generate_json_output(full_data: Dict, output_path: str) -> None:
    """
    Generate JSON output file with all analysis data.
    """
    def json_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, pd.DataFrame):
            return obj.to_dict('records')
        if pd.isna(obj):
            return None
        return str(obj)
    
    with open(output_path, 'w') as f:
        json.dump(full_data, f, indent=2, default=json_serializer)


def generate_master_report(
    summary_data: Dict,
    transactions: List[Dict],
    monthly_data: Optional[pd.DataFrame],
    risk_profile: Dict,
    lender_matches: List[Dict],
    output_dir: str = "output_reports",
    fraud_flags: Optional[List] = None,
    deal_summary: Optional[Dict] = None
) -> str:
    """
    Main function to generate the complete Master Excel report.
    Now includes enhanced MCA positions, funding analysis, red flags,
    forensics tab, and deal summary (spec sheet) tab.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"MCA_Analysis_{timestamp}.xlsx"
    output_path = os.path.join(output_dir, filename)
    
    workbook = create_workbook(output_path)
    formats = get_formats(workbook)
    
    full_summary = {
        'account_info': summary_data.get('account_info', {}) if isinstance(summary_data, dict) else {},
        'revenue_metrics': summary_data.get('revenue_metrics', {}) if isinstance(summary_data, dict) else {},
        'risk_profile': risk_profile if risk_profile else {},
        'deal_metrics': summary_data.get('deal_metrics', {}) if isinstance(summary_data, dict) else {},
    }
    add_summary_sheet(workbook, full_summary, formats)
    
    if transactions:
        add_transactions_sheet(workbook, transactions, formats)
    
    if monthly_data is not None and not monthly_data.empty:
        add_monthly_analysis_sheet(workbook, monthly_data, formats)
    
    if risk_profile:
        add_risk_analysis_sheet(workbook, risk_profile, formats)
        
        position_data = summary_data.get('position_data', {}) if isinstance(summary_data, dict) else {}
        add_mca_positions_sheet(workbook, risk_profile, formats, position_data=position_data)
        
        add_funding_analysis_sheet(workbook, risk_profile, formats)
        
        add_red_flags_sheet(workbook, risk_profile, formats)
        
        nsf = risk_profile.get('nsf_analysis', {})
        neg = risk_profile.get('negative_days', {})
        cash = risk_profile.get('cash_activity', {})
        gamb = risk_profile.get('gambling', {})
        rf_data = risk_profile.get('red_flags', {})
        rf_list = rf_data.get('red_flags', []) if isinstance(rf_data, dict) else (rf_data if isinstance(rf_data, list) else [])
        vel_raw = risk_profile.get('revenue_velocity', 0)
        vel_flag = risk_profile.get('velocity_flag', 'stable')
        accel_raw = risk_profile.get('revenue_acceleration', 0)
        flat_risk = {
            'nsf_count': nsf.get('nsf_count', 0),
            'nsf_total_fees': nsf.get('nsf_total_fees', 0),
            'negative_day_count': neg.get('negative_days_count', 0),
            'consecutive_negative_days': neg.get('max_consecutive_negative', neg.get('negative_days_count', 0)),
            'max_negative_balance': neg.get('max_negative', 0),
            'cash_deposit_percent': risk_profile.get('cash_deposit_percent', cash.get('cash_percentage', 0)),
            'cash_deposit_total': risk_profile.get('cash_deposit_total', cash.get('cash_deposit_total', 0)),
            'cash_risk_flag': risk_profile.get('cash_risk_flag', cash.get('high_cash_flag', False)),
            'gambling_flag': risk_profile.get('gambling_flag', gamb.get('gambling_flag', False)),
            'gambling_total': risk_profile.get('gambling_total', gamb.get('gambling_total', 0)),
            'red_flags': rf_list,
            'velocity_flag': vel_flag if isinstance(vel_flag, str) else 'stable',
            'revenue_velocity': vel_raw if isinstance(vel_raw, (int, float)) else 0,
            'revenue_acceleration': accel_raw if isinstance(accel_raw, (int, float)) else 0,
            'expenses_by_category': risk_profile.get('expenses_by_category', {}),
        }
        enhanced_risk = summary_data.get('enhanced_risk', {}) if summary_data else {}
        if enhanced_risk:
            flat_risk.update({
                'velocity_flag': enhanced_risk.get('velocity_flag', flat_risk.get('velocity_flag', 'stable')),
                'revenue_velocity': enhanced_risk.get('revenue_velocity', flat_risk.get('revenue_velocity', 0)),
                'revenue_acceleration': enhanced_risk.get('revenue_acceleration', flat_risk.get('revenue_acceleration', 0)),
                'red_flags': enhanced_risk.get('red_flags', flat_risk.get('red_flags', [])),
                'expenses_by_category': enhanced_risk.get('expenses_by_category', flat_risk.get('expenses_by_category', {})),
            })
        _add_forensics_tab(workbook, formats, flat_risk, fraud_flags or [])
    
    if lender_matches:
        add_lender_matches_sheet(workbook, lender_matches, formats)
    
    if deal_summary:
        _add_deal_summary_tab(workbook, formats, deal_summary)
    
    workbook.close()
    
    json_path = output_path.replace('.xlsx', '.json')
    json_data = {
        'generated_at': datetime.now().isoformat(),
        'summary': summary_data,
        'transaction_count': len(transactions) if transactions else 0,
        'risk_profile': risk_profile,
        'lender_match_count': len([m for m in lender_matches if m.get('is_match')]) if lender_matches else 0,
        'mca_positions': risk_profile.get('mca_positions', {}) if risk_profile else {},
        'funding_analysis': risk_profile.get('funding_analysis', {}) if risk_profile else {},
        'red_flags': risk_profile.get('red_flags', {}) if risk_profile else {},
    }
    generate_json_output(json_data, json_path)
    
    return output_path


def generate_report(
    merchant_name: str,
    scrub_data: dict,
    risk_data: dict,
    position_data: dict,
    calculation_data: dict,
    lender_match_data: dict,
    output_path: str,
    fraud_flags: list = None,
    raw_transactions: list = None,
    deal_summary: dict = None,
) -> str:
    """
    Engine-compatible alias for generate_master_report().
    Wraps the engine API signature to call the existing report generation logic.
    """
    summary_data = {
        'account_info': {
            'bank_name': scrub_data.get('bank_name', 'N/A'),
            'account_number': scrub_data.get('account_number', 'N/A'),
        },
        'revenue_metrics': {
            'gross_deposits': scrub_data.get('total_gross', 0),
            'net_revenue': scrub_data.get('total_net', 0),
            'monthly_average_deposits': scrub_data.get('avg_monthly_net', 0),
        },
    }

    transactions = raw_transactions or []

    monthly_data = None
    monthly_gross = scrub_data.get('monthly_gross', {})
    monthly_net = scrub_data.get('monthly_net', {})
    if monthly_gross or monthly_net:
        all_months = sorted(set(list(monthly_gross.keys()) + list(monthly_net.keys())))
        rows = []
        for m in all_months:
            rows.append({
                'month': m,
                'deposits': monthly_gross.get(m, 0),
                'withdrawals': 0,
                'net': monthly_net.get(m, 0),
            })
        if rows:
            monthly_data = pd.DataFrame(rows)

    risk_profile = {
        'risk_score': {
            'risk_score': risk_data.get('risk_score', 0),
            'risk_tier': risk_data.get('risk_tier', 'D'),
            'risk_factors': risk_data.get('risk_factors', []),
        },
        'nsf_analysis': {
            'nsf_count': risk_data.get('nsf_count', 0),
            'nsf_total_fees': risk_data.get('nsf_total_fees', 0),
        },
        'negative_days': {
            'negative_days_count': risk_data.get('negative_day_count', 0),
            'negative_percentage': risk_data.get('negative_percentage', 0),
            'max_negative': risk_data.get('max_negative_balance', 0),
        },
        'mca_positions': {
            'unique_mca_lenders': position_data.get('total_positions', 0),
            'stacking_detected': position_data.get('total_positions', 0) > 1,
            'mca_total_payments': position_data.get('total_monthly_payment', 0),
        },
        'cash_activity': {
            'cash_deposit_total': risk_data.get('cash_deposit_total', 0),
            'cash_percentage': risk_data.get('cash_deposit_percent', 0),
        },
        'red_flags': risk_data.get('red_flags', []),
        'nsf_count': risk_data.get('nsf_count', 0),
        'nsf_total_fees': risk_data.get('nsf_total_fees', 0),
        'negative_day_count': risk_data.get('negative_day_count', 0),
        'consecutive_negative_days': risk_data.get('consecutive_negative_days', 0),
        'max_negative_balance': risk_data.get('max_negative_balance', 0),
        'cash_deposit_percent': risk_data.get('cash_deposit_percent', 0),
        'cash_risk_flag': risk_data.get('cash_risk_flag', False),
        'cash_deposit_total': risk_data.get('cash_deposit_total', 0),
        'gambling_flag': risk_data.get('gambling_flag', False),
        'gambling_total': risk_data.get('gambling_total', 0),
        'velocity_flag': risk_data.get('velocity_flag', 'stable'),
        'revenue_velocity': risk_data.get('revenue_velocity', 0),
        'revenue_acceleration': risk_data.get('revenue_acceleration', 0),
        'expenses_by_category': risk_data.get('expenses_by_category', {}),
    }

    lender_matches = lender_match_data.get('eligible_lenders', []) if isinstance(lender_match_data, dict) else []

    return generate_master_report(
        summary_data=summary_data,
        transactions=transactions,
        monthly_data=monthly_data,
        risk_profile=risk_profile,
        lender_matches=lender_matches,
        output_dir=output_path,
        fraud_flags=fraud_flags,
        deal_summary=deal_summary,
    )
