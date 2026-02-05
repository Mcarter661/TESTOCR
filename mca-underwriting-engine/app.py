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
from core_logic.deal_input import DealInput, ManualPosition, MonthlyData
from core_logic.deal_summary import generate_deal_summary

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mca-underwriting-dev-key-2026')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'input_pdfs')
CONFIG_FOLDER = os.path.join(BASE_DIR, 'config')
INPUT_CONFIG = os.path.join(BASE_DIR, 'input_config')
PROCESSED_FOLDER = os.path.join(BASE_DIR, 'processed_data')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'output_reports')
DEALS_FOLDER = os.path.join(BASE_DIR, 'saved_deals')
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

for folder in [UPLOAD_FOLDER, INPUT_CONFIG, PROCESSED_FOLDER, OUTPUT_FOLDER, DEALS_FOLDER]:
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
            raw_transactions=all_transactions,
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


# ── Manual Input Routes ──────────────────────────────────────────────

def _load_funder_list():
    """Load funder names from funder_rates_complete.json."""
    data = _load_json('funder_rates_complete.json')
    funders = list(data.get('funder_rates', {}).keys())
    return sorted(funders)


def _get_saved_deals():
    """List saved deal JSON files."""
    deals = []
    if os.path.exists(DEALS_FOLDER):
        for fn in os.listdir(DEALS_FOLDER):
            if fn.endswith('.json'):
                fp = os.path.join(DEALS_FOLDER, fn)
                try:
                    with open(fp, 'r') as f:
                        data = json.load(f)
                    deals.append({
                        'filename': fn,
                        'legal_name': data.get('legal_name', 'Unknown'),
                        'dba': data.get('dba', ''),
                        'modified': data.get('modified_date', ''),
                        'positions': data.get('total_positions', 0),
                        'avg_revenue': data.get('avg_monthly_revenue', 0),
                    })
                except (json.JSONDecodeError, IOError):
                    pass
    return sorted(deals, key=lambda x: x.get('modified', ''), reverse=True)


@app.route('/manual-input')
def manual_input():
    """Render the manual input page."""
    funders = _load_funder_list()
    saved_deals = _get_saved_deals()
    return render_template('manual_input.html',
                           funders=funders,
                           saved_deals=saved_deals)


@app.route('/api/deal', methods=['POST'])
def api_save_deal():
    """Save a deal from manual input form."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    deal = DealInput(
        legal_name=data.get('legal_name', ''),
        dba=data.get('dba', ''),
        industry=data.get('industry', ''),
        state=data.get('state', ''),
        time_in_business_months=int(data.get('time_in_business_months', 0) or 0),
        fico_score=int(data.get('fico_score', 0) or 0),
        ownership_percent=float(data.get('ownership_percent', 100) or 100),
        bank_name=data.get('bank_name', ''),
        account_number=data.get('account_number', ''),
        account_type=data.get('account_type', 'operating'),
        proposed_funding=float(data.get('proposed_funding', 0) or 0),
        proposed_factor_rate=float(data.get('proposed_factor_rate', 1.35) or 1.35),
        proposed_term_months=int(data.get('proposed_term_months', 6) or 6),
        proposed_frequency=data.get('proposed_frequency', 'daily'),
        notes=data.get('notes', ''),
    )

    # Add monthly data
    for m in data.get('monthly_data', []):
        deal.monthly_data.append(MonthlyData(
            month=m.get('month', ''),
            gross_revenue=float(m.get('gross_revenue', 0) or 0),
            net_revenue=float(m.get('net_revenue', 0) or 0),
            nsf_count=int(m.get('nsf_count', 0) or 0),
            negative_days=int(m.get('negative_days', 0) or 0),
            avg_daily_balance=float(m.get('avg_daily_balance', 0) or 0),
            deposit_count=int(m.get('deposit_count', 0) or 0),
            ending_balance=float(m.get('ending_balance', 0) or 0),
            notes=m.get('notes', ''),
        ))

    # Add positions
    for p in data.get('positions', []):
        deal.positions.append(ManualPosition(
            position_number=int(p.get('position_number', len(deal.positions) + 1)),
            funder_name=p.get('funder_name', ''),
            funded_date=p.get('funded_date', ''),
            funded_amount=float(p.get('funded_amount', 0) or 0),
            payment_amount=float(p.get('payment_amount', 0) or 0),
            payment_frequency=p.get('payment_frequency', 'daily'),
            factor_rate=float(p.get('factor_rate', 1.42) or 1.42),
            is_buyout=bool(p.get('is_buyout', False)),
            is_renewal=bool(p.get('is_renewal', False)),
            notes=p.get('notes', ''),
        ))

    deal.calculate_all()

    # Generate filename
    safe_name = "".join(c for c in deal.legal_name if c.isalnum() or c in " _-")[:40].strip()
    if not safe_name:
        safe_name = "deal"
    filename = f"{safe_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(DEALS_FOLDER, filename)
    deal.save(filepath)

    return jsonify({
        'status': 'saved',
        'filename': filename,
        'summary': {
            'avg_monthly_revenue': deal.avg_monthly_revenue,
            'total_positions': deal.total_positions,
            'total_monthly_holdback': deal.total_monthly_holdback,
            'current_holdback_percent': deal.current_holdback_percent,
            'combined_holdback_percent': deal.combined_holdback_percent,
            'net_available_revenue': deal.net_available_revenue,
        }
    })


@app.route('/api/deal/<filename>', methods=['GET'])
def api_load_deal(filename):
    """Load a saved deal."""
    safe = secure_filename(filename)
    filepath = os.path.join(DEALS_FOLDER, safe)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Deal not found'}), 404
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except (json.JSONDecodeError, IOError) as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/deal/<filename>/position', methods=['POST'])
def api_add_position(filename):
    """Add a position to a saved deal."""
    safe = secure_filename(filename)
    filepath = os.path.join(DEALS_FOLDER, safe)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Deal not found'}), 404

    deal = DealInput.load(filepath)
    p = request.get_json()
    if not p:
        return jsonify({'error': 'No position data'}), 400

    position = ManualPosition(
        position_number=len(deal.positions) + 1,
        funder_name=p.get('funder_name', ''),
        funded_date=p.get('funded_date', ''),
        funded_amount=float(p.get('funded_amount', 0) or 0),
        payment_amount=float(p.get('payment_amount', 0) or 0),
        payment_frequency=p.get('payment_frequency', 'daily'),
        factor_rate=float(p.get('factor_rate', 1.42) or 1.42),
        is_buyout=bool(p.get('is_buyout', False)),
        is_renewal=bool(p.get('is_renewal', False)),
        notes=p.get('notes', ''),
    )
    deal.add_position(position)
    deal.save(filepath)

    return jsonify({'status': 'position_added', 'total_positions': deal.total_positions})


@app.route('/api/deal/<filename>/position/<int:index>', methods=['PUT', 'DELETE'])
def api_modify_position(filename, index):
    """Update or delete a position on a saved deal."""
    safe = secure_filename(filename)
    filepath = os.path.join(DEALS_FOLDER, safe)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Deal not found'}), 404

    deal = DealInput.load(filepath)

    if request.method == 'DELETE':
        if 0 <= index < len(deal.positions):
            deal.delete_position(index)
            deal.save(filepath)
            return jsonify({'status': 'position_deleted', 'total_positions': deal.total_positions})
        return jsonify({'error': 'Invalid position index'}), 400

    # PUT - update
    p = request.get_json()
    if not p:
        return jsonify({'error': 'No position data'}), 400

    position = ManualPosition(
        position_number=index + 1,
        funder_name=p.get('funder_name', ''),
        funded_date=p.get('funded_date', ''),
        funded_amount=float(p.get('funded_amount', 0) or 0),
        payment_amount=float(p.get('payment_amount', 0) or 0),
        payment_frequency=p.get('payment_frequency', 'daily'),
        factor_rate=float(p.get('factor_rate', 1.42) or 1.42),
        is_buyout=bool(p.get('is_buyout', False)),
        is_renewal=bool(p.get('is_renewal', False)),
        notes=p.get('notes', ''),
    )
    deal.update_position(index, position)
    deal.save(filepath)

    return jsonify({'status': 'position_updated', 'total_positions': deal.total_positions})


@app.route('/api/generate-summary/<filename>', methods=['POST'])
def api_generate_summary(filename):
    """Generate deal summary and Excel report from a saved deal."""
    safe = secure_filename(filename)
    filepath = os.path.join(DEALS_FOLDER, safe)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Deal not found'}), 404

    deal = DealInput.load(filepath)

    # Run lender matching
    lender_csv = _find_lender_csv()
    calc_data = {
        'merchant_name': deal.legal_name,
        'avg_monthly_revenue': deal.avg_monthly_revenue,
        'fico_score': deal.fico_score,
        'time_in_business_months': deal.time_in_business_months,
        'state': deal.state,
        'industry': deal.industry,
        'total_positions': deal.total_positions,
        'current_holdback_percent': deal.current_holdback_percent,
        'total_nsf_count': deal.total_nsf_count,
        'total_negative_days': deal.total_negative_days,
        'proposed_funding': deal.proposed_funding,
        'proposed_factor_rate': deal.proposed_factor_rate,
        'proposed_term_months': deal.proposed_term_months,
        'proposed_frequency': deal.proposed_frequency,
        'combined_holdback_percent': deal.combined_holdback_percent,
        'ownership_percent': deal.ownership_percent,
        'max_recommended_funding': 0,
    }

    lender_data = match_lenders(calc_data, lender_csv) if lender_csv else {
        "eligible_lenders": [], "disqualified_lenders": [],
        "total_lenders_checked": 0, "eligible_count": 0, "disqualified_count": 0,
    }

    # Generate deal summary
    summary = generate_deal_summary(deal, lender_matches=lender_data)
    from dataclasses import asdict
    summary_dict = asdict(summary)

    # Generate Excel report
    report_path = generate_report(
        merchant_name=deal.legal_name or deal.dba or 'Manual Deal',
        scrub_data={'total_net': deal.avg_monthly_revenue * len(deal.monthly_data),
                    'monthly_net': {m.month: m.net_revenue for m in deal.monthly_data},
                    'monthly_gross': {m.month: m.gross_revenue for m in deal.monthly_data},
                    'clean_transactions': [], 'removed_transactions': [],
                    'total_gross': deal.total_gross_revenue,
                    'nsf_count': deal.total_nsf_count,
                    'negative_days': deal.total_negative_days},
        risk_data={'risk_score': 0, 'risk_tier': summary.tier,
                   'red_flags': [{'description': f, 'severity': 'HIGH'} for f in summary.risk_flags],
                   'cash_risk_flag': False, 'gambling_flag': False},
        position_data={'total_positions': deal.total_positions,
                       'positions': [{'position_number': p.position_number,
                                      'lender_name': p.funder_name,
                                      'funded_amount': p.funded_amount,
                                      'payment_amount': p.payment_amount,
                                      'payment_frequency': p.payment_frequency,
                                      'estimated_original_funding': p.funded_amount,
                                      'estimated_factor_rate': p.factor_rate,
                                      'estimated_total_payback': p.total_payback,
                                      'estimated_remaining_balance': p.estimated_remaining,
                                      'paid_in_percent': p.paid_in_percent,
                                      'estimated_payoff_date': p.estimated_payoff_date}
                                     for p in deal.positions],
                       'total_daily_holdback': deal.total_daily_holdback,
                       'total_monthly_holdback': deal.total_monthly_holdback},
        calculation_data=calc_data,
        lender_match_data=lender_data,
        output_path=OUTPUT_FOLDER,
        deal_summary=summary_dict,
    )

    report_filename = os.path.basename(report_path) if report_path else None

    return jsonify({
        'status': 'complete',
        'summary': summary_dict,
        'report_file': report_filename,
        'eligible_lenders': lender_data.get('eligible_count', 0),
        'tier': summary.tier,
        'risk_flags': summary.risk_flags,
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
