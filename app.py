"""
MCA Underwriting Command Center - Web Application
Flask-based web interface for bank statement analysis.
"""

import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from core_logic.ocr_engine import process_bank_statement
from core_logic.scrubber import scrub_transactions
from core_logic.risk_engine import generate_risk_profile
from core_logic.lender_matcher import find_matching_lenders
from core_logic.reporter import generate_master_report

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
        
        results = []
        for filename in selected_files:
            pdf_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.exists(pdf_path):
                result = run_pipeline(pdf_path)
                results.append({
                    'filename': filename,
                    'status': 'success' if result else 'pending',
                    'result': result
                })
        
        flash(f'Processed {len(results)} file(s)', 'success')
        return redirect(url_for('results'))
    
    files = get_uploaded_files()
    return render_template('process.html', files=files)


def run_pipeline(pdf_path):
    """
    Run the complete underwriting pipeline on a single PDF.
    Returns processing result dictionary with full analysis.
    """
    from core_logic.calculator import calculate_full_deal_metrics
    
    result = {
        'filename': os.path.basename(pdf_path),
        'timestamp': datetime.now().isoformat(),
        'steps': []
    }
    
    try:
        # Step 1: OCR - Extract text and parse transactions
        ocr_data = process_bank_statement(pdf_path)
        if ocr_data and ocr_data.get('success'):
            txn_count = len(ocr_data.get('transactions', []))
            bank = ocr_data.get('bank_format', 'unknown')
            result['steps'].append({
                'name': 'OCR Extraction', 
                'status': 'complete', 
                'message': f'Extracted {txn_count} transactions from {bank} statement'
            })
        else:
            error_msg = ocr_data.get('error', 'Unknown error') if ocr_data else 'Failed to process PDF'
            result['steps'].append({
                'name': 'OCR Extraction', 
                'status': 'error', 
                'message': error_msg
            })
            ocr_data = {'transactions': [], 'account_info': {}, 'summary': {}}
        
        # Step 2: Scrubbing - Clean transactions and calculate revenue
        transactions = ocr_data.get('transactions', [])
        scrubbed_data = scrub_transactions(transactions)
        
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
        
        # Step 3: Risk Analysis - NSFs, negative days, MCAs
        daily_balances = scrubbed_data.get('daily_balances')
        scrubbed_transactions = scrubbed_data.get('transactions', [])
        risk_profile = generate_risk_profile(scrubbed_transactions, daily_balances)
        
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
            result['steps'].append({
                'name': 'Risk Analysis', 
                'status': 'complete', 
                'message': 'Risk analysis complete'
            })
            risk_profile = {}
        
        # Step 4: Calculate Deal Metrics using calculator
        monthly_revenue = scrubbed_data.get('revenue_metrics', {}).get('monthly_average_deposits', 0)
        deal_metrics = calculate_full_deal_metrics(monthly_revenue, risk_profile) if monthly_revenue > 0 else {}
        
        # Step 5: Lender Matching - Find eligible lenders
        applicant_profile = {
            'monthly_revenue': monthly_revenue,
            'nsf_count': risk_profile.get('nsf_analysis', {}).get('nsf_count', 0),
            'negative_days': risk_profile.get('negative_days', {}).get('negative_days_count', 0),
            'existing_positions': risk_profile.get('mca_positions', {}).get('unique_mca_lenders', 0),
            'time_in_business_months': 12,  # Default assumption
            'credit_score': 600,  # Default assumption for matching
            'industry': 'general',  # Default industry
            'state': 'CA',  # Default state
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
            result['steps'].append({
                'name': 'Lender Matching', 
                'status': 'complete', 
                'message': 'Lender matching complete'
            })
            lender_matches = {'matches': []}
        
        # Step 6: Report Generation - Create Excel report
        # Build proper summary_data structure expected by reporter
        summary_data = {
            'account_info': ocr_data.get('account_info', {}),
            'revenue_metrics': scrubbed_data.get('revenue_metrics', {}),
            'risk_profile': risk_profile,
            'deal_metrics': deal_metrics,
        }
        
        report_path = generate_master_report(
            summary_data=summary_data,
            transactions=scrubbed_transactions,
            monthly_data=scrubbed_data.get('monthly_data'),
            risk_profile=risk_profile,
            lender_matches=lender_matches.get('matches', []),
            output_dir=OUTPUT_FOLDER
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
        
        # Overall status
        all_complete = all(s['status'] == 'complete' for s in result['steps'])
        result['status'] = 'complete' if all_complete else 'partial'
        
        # Add summary data to result
        result['summary'] = {
            'bank': ocr_data.get('bank_format', 'unknown'),
            'transaction_count': len(scrubbed_transactions),
            'monthly_revenue': monthly_revenue,
            'risk_tier': risk_profile.get('risk_score', {}).get('risk_tier', 'N/A'),
            'eligible_lenders': lender_matches.get('summary', {}).get('eligible_count', 0),
        }
        
    except Exception as e:
        result['steps'].append({
            'name': 'Pipeline Error',
            'status': 'error',
            'message': str(e)
        })
        result['status'] = 'error'
    
    # Save result to processed data
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
