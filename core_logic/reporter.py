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
    monthly_data: pd.DataFrame,
    risk_profile: Dict,
    lender_matches: List[Dict],
    output_dir: str = "output_reports"
) -> str:
    """
    Main function to generate the complete Master Excel report.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"MCA_Analysis_{timestamp}.xlsx"
    output_path = os.path.join(output_dir, filename)
    
    workbook = create_workbook(output_path)
    formats = get_formats(workbook)
    
    full_summary = {
        'account_info': summary_data if isinstance(summary_data, dict) else {},
        'revenue_metrics': {},
        'risk_profile': risk_profile if risk_profile else {},
    }
    add_summary_sheet(workbook, full_summary, formats)
    
    if transactions:
        add_transactions_sheet(workbook, transactions, formats)
    
    if monthly_data is not None and not monthly_data.empty:
        add_monthly_analysis_sheet(workbook, monthly_data, formats)
    
    if risk_profile:
        add_risk_analysis_sheet(workbook, risk_profile, formats)
    
    if lender_matches:
        add_lender_matches_sheet(workbook, lender_matches, formats)
    
    workbook.close()
    
    json_path = output_path.replace('.xlsx', '.json')
    json_data = {
        'generated_at': datetime.now().isoformat(),
        'summary': summary_data,
        'transaction_count': len(transactions) if transactions else 0,
        'risk_profile': risk_profile,
        'lender_match_count': len([m for m in lender_matches if m.get('is_match')]) if lender_matches else 0,
    }
    generate_json_output(json_data, json_path)
    
    return output_path
