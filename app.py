"""
MCA Underwriting Command Center - Web Application
Flask-based web interface for bank statement analysis.
"""

import os
import json
import pandas as pd
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from dataclasses import asdict

from core_logic.ocr_engine import process_bank_statement
from core_logic.scrubber import scrub_transactions, detect_inter_account_transfers, analyze_concentration
from core_logic.risk_engine import generate_risk_profile, analyze_risk
from core_logic.lender_matcher import find_matching_lenders
from core_logic.reporter import generate_master_report
from core_logic.position_detector import detect_positions
from core_logic.calculator import calculate_full_deal_metrics, calculate_deal_summary
from core_logic.deal_input import DealInput, MonthlyData, ManualPosition
from core_logic.deal_summary import generate_deal_summary, DealSummary

CONFIG_DIR = 'config'

def load_keywords():
    kw_path = os.path.join(CONFIG_DIR, 'keywords.json')
    if os.path.exists(kw_path):
        with open(kw_path, 'r') as f:
            return json.load(f)
    return {}

def load_factor_rates():
    fr_path = os.path.join(CONFIG_DIR, 'factor_rates.json')
    if os.path.exists(fr_path):
        with open(fr_path, 'r') as f:
            return json.load(f)
    frc_path = os.path.join(CONFIG_DIR, 'funder_rates_complete.json')
    if os.path.exists(frc_path):
        with open(frc_path, 'r') as f:
            return json.load(f)
    return {"default_rate": 1.35, "lender_rates": {}}

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mca-underwriting-dev-key')

UPLOAD_FOLDER = 'input_pdfs'
CONFIG_FOLDER = 'input_config'
PROCESSED_FOLDER = 'processed_data'
OUTPUT_FOLDER = 'output_reports'
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

for folder in [UPLOAD_FOLDER, CONFIG_FOLDER, PROCESSED_FOLDER, OUTPUT_FOLDER]:
    os.makedirs(folder, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_uploaded_files():
    """Get list of uploaded PDF files."""
    files = []
    if os.path.exists(UPLOAD_FOLDER):
        for filename in os.listdir(UPLOAD_FOLDER):
            if filename.lower().endswith('.pdf'):
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                stat = os.stat(filepath)
                files.append({
                    'name': filename,
                    'size': round(stat.st_size / 1024, 2),  # KB
                    'uploaded': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                })
    return sorted(files, key=lambda x: x['uploaded'], reverse=True)


def get_generated_reports():
    """Get list of generated reports."""
    reports = []
    if os.path.exists(OUTPUT_FOLDER):
        for filename in os.listdir(OUTPUT_FOLDER):
            if filename.endswith(('.xlsx', '.json')):
                filepath = os.path.join(OUTPUT_FOLDER, filename)
                stat = os.stat(filepath)
                reports.append({
                    'name': filename,
                    'size': round(stat.st_size / 1024, 2),
                    'created': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                    'type': 'Excel' if filename.endswith('.xlsx') else 'JSON'
                })
    return sorted(reports, key=lambda x: x['created'], reverse=True)


@app.route('/')
def index():
    """Home page - Dashboard overview."""
    files = get_uploaded_files()
    reports = get_generated_reports()
    return render_template('index.html', 
                         files=files, 
                         reports=reports,
                         file_count=len(files),
                         report_count=len(reports))


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """Upload page for bank statements."""
    if request.method == 'POST':
        if 'files' not in request.files:
            flash('No files selected', 'error')
            return redirect(request.url)
        
        files = request.files.getlist('files')
        uploaded_count = 0
        
        for file in files:
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                filename = timestamp + filename
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                uploaded_count += 1
        
        if uploaded_count > 0:
            flash(f'Successfully uploaded {uploaded_count} file(s)', 'success')
        else:
            flash('No valid PDF files were uploaded', 'error')
        
        return redirect(url_for('upload'))
    
    files = get_uploaded_files()
    return render_template('upload.html', files=files)


@app.route('/process', methods=['GET', 'POST'])
def process():
    """Process uploaded bank statements."""
    if request.method == 'POST':
        selected_files = request.form.getlist('selected_files')
        
        if not selected_files:
            flash('No files selected for processing', 'error')
            return redirect(url_for('process'))
        
        pdf_paths = []
        for filename in selected_files:
            pdf_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.exists(pdf_path):
                pdf_paths.append(pdf_path)
        
        if pdf_paths:
            result = run_combined_pipeline(pdf_paths)
            if result and result.get('status') == 'success':
                flash(f'Processed {len(pdf_paths)} file(s) into 1 consolidated report', 'success')
            else:
                flash('Processing completed with some issues', 'warning')
        
        return redirect(url_for('results'))
    
    files = get_uploaded_files()
    return render_template('process.html', files=files)


def _build_deal_input(scrubbed_data, position_data, risk_profile, account_info, deal_metrics):
    """Build DealInput from pipeline extraction results, then generate DealSummary."""
    deal = DealInput(
        data_source='ocr',
        bank_name=account_info.get('bank_name', ''),
        account_number=account_info.get('account_number', ''),
    )

    monthly_df = scrubbed_data.get('monthly_data')
    if monthly_df is not None and hasattr(monthly_df, 'iterrows'):
        for _, row in monthly_df.iterrows():
            deal.monthly_data.append(MonthlyData(
                month=str(row.get('month', '')),
                gross_revenue=float(row.get('deposits', 0) or 0),
                net_revenue=float(row.get('deposits', 0) or 0),
                deposit_count=int(row.get('deposit_count', 0)) if 'deposit_count' in row.index else 0,
                ending_balance=float(row.get('ending_balance', 0)) if 'ending_balance' in row.index else 0,
            ))

    pos_list = position_data.get('positions', []) if position_data else []
    for i, p in enumerate(pos_list):
        has_funding = p.get('has_known_funding', True)
        deal.positions.append(ManualPosition(
            position_number=i + 1,
            funder_name=p.get('lender_name', 'Unknown'),
            funded_date=p.get('first_payment_date', ''),
            funded_amount=float(p.get('estimated_original_funding', 0) or 0),
            payment_amount=float(p.get('payment_amount', 0) or 0),
            payment_frequency=p.get('payment_frequency', 'daily'),
            factor_rate=float(p.get('estimated_factor_rate', 1.42) or 1.42),
            notes="no_known_funding" if not has_funding else "",
        ))

    max_funding = deal_metrics.get('max_recommended_funding', 0) if deal_metrics else 0
    if max_funding > 0:
        deal.proposed_funding = max_funding
        deal.proposed_factor_rate = 1.35
        deal.proposed_term_months = 6
        deal.proposed_frequency = 'daily'

    deal.calculate_all()

    nsf_data = risk_profile.get('nsf_analysis', {})
    neg_data = risk_profile.get('negative_days', {})
    deal.total_nsf_count = nsf_data.get('nsf_count', 0)
    deal.total_negative_days = neg_data.get('negative_days_count', 0)
    adb = risk_profile.get('average_daily_balance', 0)
    if not adb:
        adb = risk_profile.get('avg_daily_balance', 0)
    deal.avg_daily_balance = adb

    return deal


def run_combined_pipeline(pdf_paths):
    """
    Run the complete underwriting pipeline on MULTIPLE PDFs.
    Combines all transactions into ONE consolidated report.
    Enhanced with position detection, keyword-based analysis, and fraud detection.
    """
    keywords = load_keywords()
    factor_rates = load_factor_rates()
    
    result = {
        'filenames': [os.path.basename(p) for p in pdf_paths],
        'timestamp': datetime.now().isoformat(),
        'steps': [],
        'status': 'processing'
    }
    
    try:
        all_transactions = []
        all_account_info = {}
        bank_formats = []
        total_pages = 0
        all_fraud_flags = []
        ocr_total_deposits = 0
        ocr_total_withdrawals = 0
        
        per_file_transactions = {}
        for pdf_path in pdf_paths:
            ocr_data = process_bank_statement(pdf_path)
            if ocr_data and ocr_data.get('success'):
                transactions = ocr_data.get('transactions', [])
                bank_fmt = ocr_data.get('bank_format', 'unknown')
                bank_label = ocr_data.get('account_info', {}).get('bank_name', bank_fmt.replace('_', ' ').title())
                for txn in transactions:
                    txn['source_bank'] = bank_label
                all_transactions.extend(transactions)
                bank_formats.append(bank_fmt)
                if bank_label not in per_file_transactions:
                    per_file_transactions[bank_label] = []
                per_file_transactions[bank_label].extend(transactions)
                total_pages += ocr_data.get('page_count', 1)
                
                if ocr_data.get('fraud_flags'):
                    all_fraud_flags.extend(ocr_data['fraud_flags'])
                
                ocr_summary = ocr_data.get('summary', {})
                ocr_total_deposits += ocr_summary.get('total_deposits', 0)
                ocr_total_withdrawals += ocr_summary.get('total_withdrawals', 0)
                
                acct = ocr_data.get('account_info', {})
                if acct:
                    if not all_account_info:
                        all_account_info = dict(acct)
                    else:
                        if acct.get('bank_name') and not all_account_info.get('bank_name'):
                            all_account_info['bank_name'] = acct['bank_name']
                        if acct.get('statement_period_start') and not all_account_info.get('statement_period_start'):
                            all_account_info['statement_period_start'] = acct['statement_period_start']
                        if acct.get('statement_period_end'):
                            all_account_info['statement_period_end'] = acct['statement_period_end']
                        if acct.get('closing_balance'):
                            all_account_info['closing_balance'] = acct['closing_balance']
        
        unique_banks = list(set(bank_formats))
        bank_str = ', '.join(unique_banks) if unique_banks else 'unknown'
        
        fraud_msg = f', {len(all_fraud_flags)} fraud flag(s)' if all_fraud_flags else ''
        result['steps'].append({
            'name': 'OCR Extraction',
            'status': 'complete',
            'message': f'Extracted {len(all_transactions)} transactions from {len(pdf_paths)} files ({bank_str}){fraud_msg}'
        })
        
        if not all_transactions:
            result['steps'].append({
                'name': 'Pipeline',
                'status': 'error',
                'message': 'No transactions found in any files'
            })
            result['status'] = 'error'
            return result
        
        all_transactions.sort(key=lambda x: x.get('date', ''))
        
        scrubbed_data = scrub_transactions(all_transactions, keywords=keywords if keywords else None)
        
        if scrubbed_data and scrubbed_data.get('transactions'):
            revenue = scrubbed_data.get('revenue_metrics', {})
            monthly_avg = revenue.get('monthly_average_deposits', 0)
            transfer_count = scrubbed_data.get('transfer_count', 0)
            excluded_count = len(scrubbed_data.get('excluded_transactions', []))
            monthly_data = scrubbed_data.get('monthly_data', {})
            if isinstance(monthly_data, pd.DataFrame):
                months_count = len(monthly_data)
            elif isinstance(monthly_data, dict):
                months_count = len(monthly_data.get('monthly_breakdown', []))
            else:
                months_count = 0
            excl_msg = f', {excluded_count} excluded' if excluded_count > 0 else ''
            result['steps'].append({
                'name': 'Transaction Scrubbing',
                'status': 'complete',
                'message': f'{months_count} months analyzed, Monthly avg: ${monthly_avg:,.0f}, {transfer_count} transfers{excl_msg}'
            })
        else:
            scrubbed_data = {'transactions': [], 'revenue_metrics': {}, 'monthly_data': None, 'daily_balances': None}
            result['steps'].append({
                'name': 'Transaction Scrubbing',
                'status': 'complete',
                'message': 'Transactions processed'
            })
        
        daily_balances = scrubbed_data.get('daily_balances')
        scrubbed_transactions = scrubbed_data.get('transactions', [])
        monthly_revenue = scrubbed_data.get('revenue_metrics', {}).get('monthly_average_deposits', 0)
        
        risk_profile = generate_risk_profile(scrubbed_transactions, daily_balances)
        
        enhanced_risk = {}
        if keywords:
            try:
                enhanced_risk = analyze_risk(
                    scrubbed_transactions,
                    daily_balances=daily_balances,
                    keywords=keywords,
                    net_revenue=monthly_revenue,
                )
            except Exception:
                enhanced_risk = {}
        
        if risk_profile:
            risk_score = risk_profile.get('risk_score', {})
            tier = risk_score.get('risk_tier', 'N/A')
            score = risk_score.get('risk_score', 0)
            nsf = risk_profile.get('nsf_analysis', {}).get('nsf_count', 0)
            mca_count = risk_profile.get('mca_positions', {}).get('unique_mca_lenders', 0)
            
            velocity_msg = ''
            if enhanced_risk.get('velocity_flag') and enhanced_risk['velocity_flag'] != 'stable':
                velocity_msg = f', Revenue: {enhanced_risk["velocity_flag"]}'
            red_flag_count = len(enhanced_risk.get('red_flags', []))
            rf_msg = f', {red_flag_count} red flag(s)' if red_flag_count > 0 else ''
            
            result['steps'].append({
                'name': 'Risk Analysis',
                'status': 'complete',
                'message': f'Tier {tier} (Score: {score}), {nsf} NSFs, {mca_count} MCA positions{velocity_msg}{rf_msg}'
            })
        else:
            risk_profile = {}
        
        position_data = {}
        if keywords:
            try:
                position_data = detect_positions(scrubbed_transactions, keywords, factor_rates)
                pos_count = position_data.get('total_positions', 0)
                total_monthly = position_data.get('total_monthly_payment', 0)
                if pos_count > 0:
                    result['steps'].append({
                        'name': 'Position Detection',
                        'status': 'complete',
                        'message': f'{pos_count} MCA positions detected, ${total_monthly:,.0f}/mo total holdback'
                    })
            except Exception:
                position_data = {}
        
        deal_metrics = calculate_full_deal_metrics(monthly_revenue, risk_profile) if monthly_revenue > 0 else {}
        
        applicant_profile = {
            'monthly_revenue': monthly_revenue,
            'nsf_count': risk_profile.get('nsf_analysis', {}).get('nsf_count', 0),
            'negative_days': risk_profile.get('negative_days', {}).get('negative_days_count', 0),
            'existing_positions': risk_profile.get('mca_positions', {}).get('unique_mca_lenders', 0),
            'time_in_business_months': 12,
            'credit_score': 600,
            'industry': 'general',
            'state': 'CA',
        }
        lender_matches = find_matching_lenders(applicant_profile)
        
        if lender_matches:
            summary = lender_matches.get('summary', {})
            eligible = summary.get('eligible_count', 0)
            total = summary.get('total_lenders_checked', 0)
            result['steps'].append({
                'name': 'Lender Matching',
                'status': 'complete',
                'message': f'{eligible} of {total} lenders matched'
            })
        else:
            lender_matches = {'matches': []}
        
        revenue_metrics = scrubbed_data.get('revenue_metrics', {})
        if not revenue_metrics.get('gross_deposits') and ocr_total_deposits > 0:
            revenue_metrics['gross_deposits'] = ocr_total_deposits
        if not revenue_metrics.get('gross_withdrawals') and ocr_total_withdrawals > 0:
            revenue_metrics['gross_withdrawals'] = ocr_total_withdrawals
        
        summary_data = {
            'account_info': all_account_info,
            'revenue_metrics': revenue_metrics,
            'risk_profile': risk_profile,
            'enhanced_risk': enhanced_risk,
            'deal_metrics': deal_metrics,
            'position_data': position_data,
            'files_processed': len(pdf_paths),
            'total_pages': total_pages,
        }
        
        deal_input = _build_deal_input(
            scrubbed_data, position_data, risk_profile, all_account_info, deal_metrics
        )

        expense_data = risk_profile.get('recurring_expenses', {})

        risk_data_for_summary = {
            'risk_score': risk_profile.get('risk_score', {}).get('risk_score', 0),
            'risk_tier': risk_profile.get('risk_score', {}).get('risk_tier', 'C'),
            'cash_risk_flag': enhanced_risk.get('cash_risk_flag', False),
            'gambling_flag': enhanced_risk.get('gambling_flag', False),
            'red_flags': enhanced_risk.get('red_flags', []),
            'cash_deposit_percent': risk_profile.get('cash_deposit_percent', 0),
        }
        lender_data_for_summary = {
            'eligible_count': lender_matches.get('summary', {}).get('eligible_count', 0),
            'eligible_lenders': lender_matches.get('matches', []),
        }

        deal_summary_obj = generate_deal_summary(
            deal_input,
            risk_data=risk_data_for_summary,
            lender_matches=lender_data_for_summary,
            expense_data=expense_data,
        )
        deal_summary = asdict(deal_summary_obj)

        report_path = generate_master_report(
            summary_data=summary_data,
            transactions=scrubbed_transactions,
            monthly_data=scrubbed_data.get('monthly_data'),
            risk_profile=risk_profile,
            lender_matches=lender_matches.get('matches', []),
            output_dir=OUTPUT_FOLDER,
            fraud_flags=all_fraud_flags,
            deal_summary=deal_summary,
            per_bank_transactions=per_file_transactions,
            excluded_deposits=scrubbed_data.get('excluded_transactions', []),
        )

        if report_path:
            report_name = os.path.basename(report_path)
            result['steps'].append({
                'name': 'Report Generation',
                'status': 'complete',
                'message': f'Generated consolidated report: {report_name}'
            })
            result['report_path'] = report_path
        else:
            result['steps'].append({
                'name': 'Report Generation',
                'status': 'error',
                'message': 'Failed to generate report'
            })

        result['status'] = 'success'
        result['summary'] = {
            'files_processed': len(pdf_paths),
            'total_transactions': len(scrubbed_transactions),
            'monthly_revenue': monthly_revenue,
            'risk_tier': risk_profile.get('risk_score', {}).get('risk_tier', 'N/A'),
            'eligible_lenders': lender_matches.get('summary', {}).get('eligible_count', 0) if lender_matches else 0,
            'positions_detected': position_data.get('total_positions', 0),
            'fraud_flags': len(all_fraud_flags),
        }
        
    except Exception as e:
        result['steps'].append({
            'name': 'Pipeline Error',
            'status': 'error',
            'message': str(e)
        })
        result['status'] = 'error'
    
    result_filename = f"combined_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    result_path = os.path.join(PROCESSED_FOLDER, result_filename)
    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    return result


def run_pipeline(pdf_path):
    """
    Run the complete underwriting pipeline on a single PDF.
    Enhanced with position detection, keyword-based analysis, and fraud detection.
    """
    keywords = load_keywords()
    factor_rates = load_factor_rates()
    
    result = {
        'filename': os.path.basename(pdf_path),
        'timestamp': datetime.now().isoformat(),
        'steps': []
    }
    
    try:
        ocr_data = process_bank_statement(pdf_path)
        if ocr_data and ocr_data.get('success'):
            txn_count = len(ocr_data.get('transactions', []))
            bank = ocr_data.get('bank_format', 'unknown')
            fraud_flags = ocr_data.get('fraud_flags', [])
            fraud_msg = f', {len(fraud_flags)} fraud flag(s)' if fraud_flags else ''
            result['steps'].append({
                'name': 'OCR Extraction', 
                'status': 'complete', 
                'message': f'Extracted {txn_count} transactions from {bank} statement{fraud_msg}'
            })
        else:
            error_msg = ocr_data.get('error', 'Unknown error') if ocr_data else 'Failed to process PDF'
            result['steps'].append({
                'name': 'OCR Extraction', 
                'status': 'error', 
                'message': error_msg
            })
            ocr_data = {'transactions': [], 'account_info': {}, 'summary': {}, 'fraud_flags': []}
        
        transactions = ocr_data.get('transactions', [])
        scrubbed_data = scrub_transactions(transactions, keywords=keywords if keywords else None)
        
        if scrubbed_data and scrubbed_data.get('transactions'):
            revenue = scrubbed_data.get('revenue_metrics', {})
            monthly_avg = revenue.get('monthly_average_deposits', 0)
            transfer_count = scrubbed_data.get('transfer_count', 0)
            result['steps'].append({
                'name': 'Transaction Scrubbing', 
                'status': 'complete', 
                'message': f'Monthly avg: ${monthly_avg:,.0f}, {transfer_count} transfers identified'
            })
        else:
            result['steps'].append({
                'name': 'Transaction Scrubbing', 
                'status': 'complete', 
                'message': 'No transactions to process'
            })
            scrubbed_data = {'transactions': [], 'revenue_metrics': {}, 'monthly_data': None, 'daily_balances': None}
        
        daily_balances = scrubbed_data.get('daily_balances')
        scrubbed_transactions = scrubbed_data.get('transactions', [])
        monthly_revenue = scrubbed_data.get('revenue_metrics', {}).get('monthly_average_deposits', 0)
        risk_profile = generate_risk_profile(scrubbed_transactions, daily_balances)
        
        enhanced_risk = {}
        if keywords:
            try:
                enhanced_risk = analyze_risk(
                    scrubbed_transactions,
                    daily_balances=daily_balances,
                    keywords=keywords,
                    net_revenue=monthly_revenue,
                )
            except Exception:
                enhanced_risk = {}
        
        if risk_profile:
            risk_score = risk_profile.get('risk_score', {})
            tier = risk_score.get('risk_tier', 'N/A')
            score = risk_score.get('risk_score', 0)
            nsf = risk_profile.get('nsf_analysis', {}).get('nsf_count', 0)
            result['steps'].append({
                'name': 'Risk Analysis', 
                'status': 'complete', 
                'message': f'Tier {tier} (Score: {score}), {nsf} NSFs detected'
            })
        else:
            risk_profile = {}
        
        position_data = {}
        if keywords:
            try:
                position_data = detect_positions(scrubbed_transactions, keywords, factor_rates)
                pos_count = position_data.get('total_positions', 0)
                total_monthly = position_data.get('total_monthly_payment', 0)
                if pos_count > 0:
                    result['steps'].append({
                        'name': 'Position Detection',
                        'status': 'complete',
                        'message': f'{pos_count} MCA positions detected, ${total_monthly:,.0f}/mo total holdback'
                    })
            except Exception:
                position_data = {}
        
        deal_metrics = calculate_full_deal_metrics(monthly_revenue, risk_profile) if monthly_revenue > 0 else {}
        
        applicant_profile = {
            'monthly_revenue': monthly_revenue,
            'nsf_count': risk_profile.get('nsf_analysis', {}).get('nsf_count', 0),
            'negative_days': risk_profile.get('negative_days', {}).get('negative_days_count', 0),
            'existing_positions': risk_profile.get('mca_positions', {}).get('unique_mca_lenders', 0),
            'time_in_business_months': 12,
            'credit_score': 600,
            'industry': 'general',
            'state': 'CA',
        }
        lender_matches = find_matching_lenders(applicant_profile)
        
        if lender_matches:
            summary = lender_matches.get('summary', {})
            eligible = summary.get('eligible_count', 0)
            total = summary.get('total_lenders_checked', 0)
            result['steps'].append({
                'name': 'Lender Matching', 
                'status': 'complete', 
                'message': f'{eligible} of {total} lenders matched'
            })
        else:
            lender_matches = {'matches': []}
        
        revenue_metrics = scrubbed_data.get('revenue_metrics', {})
        ocr_summary = ocr_data.get('summary', {})
        if not revenue_metrics.get('gross_deposits') and ocr_summary.get('total_deposits'):
            revenue_metrics['gross_deposits'] = ocr_summary['total_deposits']
        if not revenue_metrics.get('gross_withdrawals') and ocr_summary.get('total_withdrawals'):
            revenue_metrics['gross_withdrawals'] = ocr_summary['total_withdrawals']
        
        summary_data = {
            'account_info': ocr_data.get('account_info', {}),
            'revenue_metrics': revenue_metrics,
            'risk_profile': risk_profile,
            'enhanced_risk': enhanced_risk,
            'deal_metrics': deal_metrics,
            'position_data': position_data,
        }
        
        deal_input = _build_deal_input(
            scrubbed_data, position_data, risk_profile,
            ocr_data.get('account_info', {}), deal_metrics
        )

        expense_data_single = risk_profile.get('recurring_expenses', {})

        risk_data_for_summary = {
            'risk_score': risk_profile.get('risk_score', {}).get('risk_score', 0),
            'risk_tier': risk_profile.get('risk_score', {}).get('risk_tier', 'C'),
            'cash_risk_flag': enhanced_risk.get('cash_risk_flag', False),
            'gambling_flag': enhanced_risk.get('gambling_flag', False),
            'red_flags': enhanced_risk.get('red_flags', []),
            'cash_deposit_percent': risk_profile.get('cash_deposit_percent', 0),
        }
        lender_data_for_summary = {
            'eligible_count': lender_matches.get('summary', {}).get('eligible_count', 0),
            'eligible_lenders': lender_matches.get('matches', []),
        }

        deal_summary_obj = generate_deal_summary(
            deal_input,
            risk_data=risk_data_for_summary,
            lender_matches=lender_data_for_summary,
            expense_data=expense_data_single,
        )
        deal_summary = asdict(deal_summary_obj)

        report_path = generate_master_report(
            summary_data=summary_data,
            transactions=scrubbed_transactions,
            monthly_data=scrubbed_data.get('monthly_data'),
            risk_profile=risk_profile,
            lender_matches=lender_matches.get('matches', []),
            output_dir=OUTPUT_FOLDER,
            fraud_flags=ocr_data.get('fraud_flags', []),
            deal_summary=deal_summary,
            excluded_deposits=scrubbed_data.get('excluded_transactions', []),
        )
        
        if report_path:
            report_name = os.path.basename(report_path)
            result['steps'].append({
                'name': 'Report Generation', 
                'status': 'complete', 
                'message': f'Generated: {report_name}'
            })
            result['report_path'] = report_path
        else:
            result['steps'].append({
                'name': 'Report Generation', 
                'status': 'error', 
                'message': 'Failed to generate report'
            })
        
        all_complete = all(s['status'] == 'complete' for s in result['steps'])
        result['status'] = 'complete' if all_complete else 'partial'
        
        result['summary'] = {
            'bank': ocr_data.get('bank_format', 'unknown'),
            'transaction_count': len(scrubbed_transactions),
            'monthly_revenue': monthly_revenue,
            'risk_tier': risk_profile.get('risk_score', {}).get('risk_tier', 'N/A'),
            'eligible_lenders': lender_matches.get('summary', {}).get('eligible_count', 0),
            'positions_detected': position_data.get('total_positions', 0),
            'fraud_flags': len(ocr_data.get('fraud_flags', [])),
        }
        
    except Exception as e:
        result['steps'].append({
            'name': 'Pipeline Error',
            'status': 'error',
            'message': str(e)
        })
        result['status'] = 'error'
    
    result_filename = os.path.basename(pdf_path).replace('.pdf', '_result.json')
    with open(os.path.join(PROCESSED_FOLDER, result_filename), 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    return result


@app.route('/results')
def results():
    """View processing results and reports."""
    reports = get_generated_reports()
    
    # Load processed results
    processed_results = []
    if os.path.exists(PROCESSED_FOLDER):
        for filename in os.listdir(PROCESSED_FOLDER):
            if filename.endswith('_result.json'):
                with open(os.path.join(PROCESSED_FOLDER, filename), 'r') as f:
                    try:
                        data = json.load(f)
                        processed_results.append(data)
                    except:
                        pass
    
    return render_template('results.html', reports=reports, processed_results=processed_results)


@app.route('/download/<path:filename>')
def download_file(filename):
    """Download generated report with path traversal protection."""
    safe_filename = secure_filename(filename)
    if not safe_filename:
        flash('Invalid filename', 'error')
        return redirect(url_for('results'))
    
    existing_reports = [f for f in os.listdir(OUTPUT_FOLDER) if f.endswith(('.xlsx', '.json'))]
    if safe_filename not in existing_reports:
        flash('Report not found', 'error')
        return redirect(url_for('results'))
    
    return send_from_directory(OUTPUT_FOLDER, safe_filename, as_attachment=True)


@app.route('/api/status')
def api_status():
    """API endpoint for processing status."""
    return jsonify({
        'status': 'ready',
        'uploaded_files': len(get_uploaded_files()),
        'generated_reports': len(get_generated_reports())
    })


@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    """Delete an uploaded file."""
    filepath = os.path.join(UPLOAD_FOLDER, secure_filename(filename))
    if os.path.exists(filepath):
        os.remove(filepath)
        flash(f'Deleted {filename}', 'success')
    else:
        flash('File not found', 'error')
    return redirect(url_for('upload'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
