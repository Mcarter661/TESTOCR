"""
MCA Underwriting Command Center - Flask Web Application
Handles file upload, analysis pipeline execution, and report delivery.
"""

import os
import json
from datetime import datetime
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, send_from_directory)
from werkzeug.utils import secure_filename

from core_logic.ocr_engine import extract_from_pdf
from core_logic.scrubber import scrub_statement, analyze_concentration
from core_logic.risk_engine import analyze_risk
from core_logic.position_detector import detect_positions
from core_logic.calculator import calculate_deal_summary
from core_logic.lender_matcher import match_lenders
from core_logic.reporter import generate_report

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mca-underwriting-dev-key-2026')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'input_pdfs')
CONFIG_FOLDER = os.path.join(BASE_DIR, 'config')
INPUT_CONFIG = os.path.join(BASE_DIR, 'input_config')
PROCESSED_FOLDER = os.path.join(BASE_DIR, 'processed_data')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'output_reports')
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

for folder in [UPLOAD_FOLDER, INPUT_CONFIG, PROCESSED_FOLDER, OUTPUT_FOLDER]:
    os.makedirs(folder, exist_ok=True)


def _load_json(filename):
    path = os.path.join(CONFIG_FOLDER, filename)
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {}


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_uploaded_files():
    files = []
    if os.path.exists(UPLOAD_FOLDER):
        for fn in os.listdir(UPLOAD_FOLDER):
            if fn.lower().endswith('.pdf'):
                fp = os.path.join(UPLOAD_FOLDER, fn)
                stat = os.stat(fp)
                files.append({
                    'name': fn,
                    'size': round(stat.st_size / 1024, 2),
                    'uploaded': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                })
    return sorted(files, key=lambda x: x['uploaded'], reverse=True)


def _get_reports():
    reports = []
    if os.path.exists(OUTPUT_FOLDER):
        for fn in os.listdir(OUTPUT_FOLDER):
            if fn.endswith(('.xlsx', '.json')):
                fp = os.path.join(OUTPUT_FOLDER, fn)
                stat = os.stat(fp)
                reports.append({
                    'name': fn,
                    'size': round(stat.st_size / 1024, 2),
                    'created': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                    'type': 'Excel' if fn.endswith('.xlsx') else 'JSON',
                })
    return sorted(reports, key=lambda x: x['created'], reverse=True)


def _get_processed_results():
    results = []
    if os.path.exists(PROCESSED_FOLDER):
        for fn in os.listdir(PROCESSED_FOLDER):
            if fn.endswith('_result.json'):
                try:
                    with open(os.path.join(PROCESSED_FOLDER, fn), 'r') as f:
                        results.append(json.load(f))
                except (json.JSONDecodeError, IOError):
                    pass
    return sorted(results, key=lambda x: x.get('timestamp', ''), reverse=True)


def _find_lender_csv():
    if os.path.exists(INPUT_CONFIG):
        for fn in os.listdir(INPUT_CONFIG):
            if fn.endswith('.csv'):
                return os.path.join(INPUT_CONFIG, fn)
    test_csv = os.path.join(BASE_DIR, 'test_data', 'test_lenders.csv')
    if os.path.exists(test_csv):
        return test_csv
    return None


# ── Routes ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    files = _get_uploaded_files()
    reports = _get_reports()
    results = _get_processed_results()
    return render_template('index.html',
                           files=files, reports=reports,
                           results=results,
                           file_count=len(files),
                           report_count=len(reports))


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        if 'files' not in request.files:
            flash('No files selected', 'error')
            return redirect(request.url)
        uploaded = 0
        for file in request.files.getlist('files'):
            if file and file.filename and _allowed_file(file.filename):
                fn = secure_filename(file.filename)
                ts = datetime.now().strftime('%Y%m%d_%H%M%S_')
                file.save(os.path.join(UPLOAD_FOLDER, ts + fn))
                uploaded += 1
        if uploaded:
            flash(f'Uploaded {uploaded} file(s)', 'success')
        else:
            flash('No valid PDF files uploaded', 'error')
        return redirect(url_for('upload'))
    return render_template('upload.html', files=_get_uploaded_files())


@app.route('/process', methods=['GET', 'POST'])
def process():
    if request.method == 'POST':
        selected = request.form.getlist('selected_files')
        if not selected:
            flash('No files selected', 'error')
            return redirect(url_for('process'))

        merchant_name = request.form.get('merchant_name', '').strip() or 'Unknown Merchant'
        fico = int(request.form.get('fico_score', '0') or '0')
        tib = int(request.form.get('time_in_business', '0') or '0')
        ownership = float(request.form.get('ownership_percent', '100') or '100')
        state = request.form.get('state', '').strip()
        industry = request.form.get('industry', '').strip()

        keywords = _load_json('keywords.json')
        factor_rates = _load_json('factor_rates.json')

        all_transactions = []
        all_fraud_flags = []
        all_statements = []
        extraction_results = []

        for fn in selected:
            pdf_path = os.path.join(UPLOAD_FOLDER, fn)
            if not os.path.exists(pdf_path):
                continue
            ocr_result = extract_from_pdf(pdf_path)
            extraction_results.append(ocr_result)
            txns = ocr_result.get('transactions', [])
            all_transactions.extend(txns)
            all_statements.append(txns)
            all_fraud_flags.extend(ocr_result.get('fraud_flags', []))

        if not all_transactions:
            flash('No transactions extracted from the selected files', 'error')
            return redirect(url_for('process'))

        scrub_data = scrub_statement(all_transactions, keywords)

        if len(all_statements) > 1:
            inter_transfers = scrub_statement(all_transactions, keywords)
        else:
            inter_transfers = None

        concentration = analyze_concentration(
            scrub_data.get('clean_transactions', []),
            scrub_data.get('total_net', 0)
        )

        risk_data = analyze_risk(all_transactions, scrub_data.get('total_net', 0), keywords)

        position_data = detect_positions(all_transactions, keywords, factor_rates)

        calc_data = calculate_deal_summary(
            scrub_data=scrub_data,
            risk_data=risk_data,
            position_data=position_data,
            fico_score=fico,
            time_in_business_months=tib,
            ownership_percent=ownership,
            state=state,
            industry=industry,
        )

        lender_csv = _find_lender_csv()
        lender_data = match_lenders(calc_data, lender_csv) if lender_csv else {
            "eligible_lenders": [], "disqualified_lenders": [],
            "total_lenders_checked": 0, "eligible_count": 0, "disqualified_count": 0,
        }

        report_path = generate_report(
            merchant_name=merchant_name,
            scrub_data=scrub_data,
            risk_data=risk_data,
            position_data=position_data,
            calculation_data=calc_data,
            lender_match_data=lender_data,
            output_path=OUTPUT_FOLDER,
            fraud_flags=all_fraud_flags,
        )

        pipeline_result = {
            'merchant_name': merchant_name,
            'files_processed': selected,
            'timestamp': datetime.now().isoformat(),
            'transactions_extracted': len(all_transactions),
            'risk_score': risk_data.get('risk_score', 0),
            'risk_tier': risk_data.get('risk_tier', 'D'),
            'positions_detected': position_data.get('total_positions', 0),
            'eligible_lenders': lender_data.get('eligible_count', 0),
            'max_funding': calc_data.get('max_recommended_funding', 0),
            'report_file': os.path.basename(report_path) if report_path else None,
            'fraud_flags': all_fraud_flags,
            'concentration': concentration,
            'status': 'complete',
        }

        result_fn = f"{merchant_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_result.json"
        with open(os.path.join(PROCESSED_FOLDER, result_fn), 'w') as f:
            json.dump(pipeline_result, f, indent=2, default=str)

        flash(f'Analysis complete! Risk: {risk_data["risk_tier"]} ({risk_data["risk_score"]}/100), '
              f'{position_data["total_positions"]} positions, '
              f'{lender_data["eligible_count"]} eligible lenders', 'success')
        return redirect(url_for('results'))

    return render_template('process.html', files=_get_uploaded_files())


@app.route('/results')
def results():
    return render_template('results.html',
                           reports=_get_reports(),
                           results=_get_processed_results())


@app.route('/download/<path:filename>')
def download_file(filename):
    safe = secure_filename(filename)
    if not safe:
        flash('Invalid filename', 'error')
        return redirect(url_for('results'))
    existing = [f for f in os.listdir(OUTPUT_FOLDER) if f.endswith(('.xlsx', '.json'))]
    if safe not in existing:
        flash('Report not found', 'error')
        return redirect(url_for('results'))
    return send_from_directory(OUTPUT_FOLDER, safe, as_attachment=True)


@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    fp = os.path.join(UPLOAD_FOLDER, secure_filename(filename))
    if os.path.exists(fp):
        os.remove(fp)
        flash(f'Deleted {filename}', 'success')
    else:
        flash('File not found', 'error')
    return redirect(url_for('upload'))


@app.route('/api/status')
def api_status():
    return jsonify({
        'status': 'ready',
        'version': '2.0',
        'uploaded_files': len(_get_uploaded_files()),
        'generated_reports': len(_get_reports()),
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
