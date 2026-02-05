"""
Reporter - Generates the 5-tab Master Underwriting Excel report.
Tab 1: Master Summary
Tab 2: The Scrub
Tab 3: Reverse Engineering
Tab 4: In-House Forensics
Tab 5: Lender Match
"""

import xlsxwriter
import json
import os
from datetime import datetime
from typing import Dict, List


def generate_report(
    merchant_name: str,
    scrub_data: dict,
    risk_data: dict,
    position_data: dict,
    calculation_data: dict,
    lender_match_data: dict,
    output_path: str,
    fraud_flags: list = None,
) -> str:
    """Main entry point. Generate the complete 5-tab Excel report."""
    os.makedirs(output_path, exist_ok=True)

    safe_name = "".join(c for c in merchant_name if c.isalnum() or c in " _-")[:40].strip()
    if not safe_name:
        safe_name = "Unknown_Merchant"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"Master_Underwriting_File_{safe_name}_{timestamp}.xlsx"
    filepath = os.path.join(output_path, filename)

    workbook = xlsxwriter.Workbook(filepath)
    fmt = _create_formats(workbook)

    _add_master_summary(workbook, fmt, merchant_name, scrub_data, risk_data,
                        position_data, calculation_data)
    _add_scrub_tab(workbook, fmt, scrub_data)
    _add_reverse_engineering_tab(workbook, fmt, position_data)
    _add_forensics_tab(workbook, fmt, risk_data, fraud_flags or [])
    _add_lender_match_tab(workbook, fmt, lender_match_data)

    workbook.close()

    json_filepath = filepath.replace(".xlsx", ".json")
    _write_json_output(json_filepath, merchant_name, scrub_data, risk_data,
                       position_data, calculation_data, lender_match_data)

    return filepath


# ── Formats ───────────────────────────────────────────────────────────

def _create_formats(workbook) -> dict:
    return {
        "title": workbook.add_format({
            "bold": True, "font_size": 16, "font_color": "#1e293b",
            "bottom": 2, "bottom_color": "#2563eb",
        }),
        "header": workbook.add_format({
            "bold": True, "font_size": 11, "bg_color": "#1e293b",
            "font_color": "#ffffff", "border": 1, "text_wrap": True,
        }),
        "header_left": workbook.add_format({
            "bold": True, "font_size": 11, "bg_color": "#1e293b",
            "font_color": "#ffffff", "border": 1, "align": "left",
        }),
        "label": workbook.add_format({
            "bold": True, "font_size": 11, "bg_color": "#f1f5f9",
            "border": 1, "align": "left",
        }),
        "value": workbook.add_format({"font_size": 11, "border": 1, "align": "left"}),
        "currency": workbook.add_format({
            "font_size": 11, "border": 1, "num_format": "$#,##0.00",
        }),
        "currency_bold": workbook.add_format({
            "bold": True, "font_size": 11, "border": 1, "num_format": "$#,##0.00",
        }),
        "percent": workbook.add_format({
            "font_size": 11, "border": 1, "num_format": "0.0%",
        }),
        "number": workbook.add_format({"font_size": 11, "border": 1, "num_format": "#,##0"}),
        "pass": workbook.add_format({
            "font_size": 11, "border": 1, "font_color": "#166534",
            "bg_color": "#dcfce7", "bold": True,
        }),
        "fail": workbook.add_format({
            "font_size": 11, "border": 1, "font_color": "#991b1b",
            "bg_color": "#fee2e2", "bold": True,
        }),
        "warn": workbook.add_format({
            "font_size": 11, "border": 1, "font_color": "#92400e",
            "bg_color": "#fef3c7", "bold": True,
        }),
        "score_good": workbook.add_format({
            "bold": True, "font_size": 14, "font_color": "#166534",
            "border": 1, "align": "center",
        }),
        "score_mid": workbook.add_format({
            "bold": True, "font_size": 14, "font_color": "#92400e",
            "border": 1, "align": "center",
        }),
        "score_bad": workbook.add_format({
            "bold": True, "font_size": 14, "font_color": "#991b1b",
            "border": 1, "align": "center",
        }),
        "section": workbook.add_format({
            "bold": True, "font_size": 12, "bg_color": "#2563eb",
            "font_color": "#ffffff", "border": 1,
        }),
        "date": workbook.add_format({"font_size": 11, "border": 1, "num_format": "yyyy-mm-dd"}),
        "wrap": workbook.add_format({"font_size": 11, "border": 1, "text_wrap": True}),
    }


# ── Tab 1: Master Summary ────────────────────────────────────────────

def _add_master_summary(workbook, fmt, merchant_name, scrub, risk, position, calc):
    ws = workbook.add_worksheet("Master Summary")
    ws.set_column("A:A", 30)
    ws.set_column("B:B", 25)

    ws.write("A1", "MCA UNDERWRITING - MASTER SUMMARY", fmt["title"])
    ws.write("A2", f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", fmt["value"])

    row = 4
    fields = [
        ("Legal Name", merchant_name, "value"),
        ("Net Monthly Revenue", calc.get("monthly_revenue", 0), "currency"),
        ("FICO Score", calc.get("fico_score", "N/A"), "value"),
        ("Time in Business", f"{calc.get('time_in_business_months', 0)} months", "value"),
        ("NSF Count", risk.get("nsf_count", 0), "number"),
        ("Negative Days", risk.get("negative_day_count", 0), "number"),
        ("Position Count", position.get("total_positions", 0), "number"),
        ("Current Holdback", calc.get("current_holdback_percent", 0) / 100, "percent"),
        ("DTI Ratio", calc.get("dti_ratio", 0), "percent"),
    ]

    score = risk.get("risk_score", 0)
    tier = risk.get("risk_tier", "D")

    for label, value, fmt_name in fields:
        ws.write(row, 0, label, fmt["label"])
        ws.write(row, 1, value, fmt[fmt_name])
        row += 1

    ws.write(row, 0, "Risk Score", fmt["label"])
    score_fmt = fmt["score_good"] if score >= 80 else fmt["score_mid"] if score >= 60 else fmt["score_bad"]
    ws.write(row, 1, f"{score}/100 (Tier {tier})", score_fmt)
    row += 1

    ws.write(row, 0, "Max Recommended Funding", fmt["label"])
    ws.write(row, 1, calc.get("max_recommended_funding", 0), fmt["currency_bold"])
    row += 1

    ws.write(row, 0, "Net Available Revenue", fmt["label"])
    ws.write(row, 1, calc.get("net_available_revenue", 0), fmt["currency"])
    row += 1

    ws.write(row, 0, "Cash Flow Coverage", fmt["label"])
    ws.write(row, 1, f"{calc.get('cash_flow_coverage', 0):.2f}x", fmt["value"])
    row += 1

    ws.write(row, 0, "Annualized Revenue", fmt["label"])
    ws.write(row, 1, calc.get("annualized_revenue", 0), fmt["currency"])
    row += 1

    cap = calc.get("advance_cap", {})
    ws.write(row, 0, "Advance Cap Range", fmt["label"])
    ws.write(row, 1, f"${cap.get('min_advance', 0):,.0f} - ${cap.get('max_advance', 0):,.0f}", fmt["value"])
    row += 1

    last_funding = position.get("days_since_last_funding", 0)
    ws.write(row, 0, "Days Since Last Funding", fmt["label"])
    ws.write(row, 1, last_funding, fmt["number"])
    row += 1

    monthly_holdback = calc.get("monthly_holdback", 0)
    ws.write(row, 0, "Current Monthly Holdback", fmt["label"])
    ws.write(row, 1, monthly_holdback, fmt["currency"])
    row += 1

    rv = risk.get("revenue_velocity", 0)
    ws.write(row, 0, "Revenue Velocity", fmt["label"])
    flag = risk.get("velocity_flag", "stable")
    vel_fmt = fmt["fail"] if "decline" in flag else fmt["pass"] if flag == "growth" else fmt["value"]
    ws.write(row, 1, f"{rv:.1f}% MoM ({flag})", vel_fmt)


# ── Tab 2: The Scrub ─────────────────────────────────────────────────

def _add_scrub_tab(workbook, fmt, scrub):
    ws = workbook.add_worksheet("The Scrub")
    ws.set_column("A:A", 14)
    ws.set_column("B:B", 18)
    ws.set_column("C:C", 18)
    ws.set_column("D:D", 18)
    ws.set_column("E:E", 14)
    ws.set_column("F:F", 14)

    ws.write("A1", "REVENUE SCRUB ANALYSIS", fmt["title"])

    row = 3
    headers = ["Month", "Gross Deposits", "Excluded", "Net Revenue", "Deposit Count", "Exclusion Rate"]
    for col, h in enumerate(headers):
        ws.write(row, col, h, fmt["header"])
    row += 1

    monthly_gross = scrub.get("monthly_gross", {})
    monthly_net = scrub.get("monthly_net", {})
    monthly_count = scrub.get("monthly_deposit_count", {})
    all_months = sorted(set(list(monthly_gross.keys()) + list(monthly_net.keys())))

    for month in all_months:
        gross = monthly_gross.get(month, 0)
        net = monthly_net.get(month, 0)
        excluded = gross - net
        count = monthly_count.get(month, 0)
        excl_rate = (excluded / gross) if gross > 0 else 0

        ws.write(row, 0, month, fmt["value"])
        ws.write(row, 1, gross, fmt["currency"])
        ws.write(row, 2, excluded, fmt["currency"])
        ws.write(row, 3, net, fmt["currency"])
        ws.write(row, 4, count, fmt["number"])
        ws.write(row, 5, excl_rate, fmt["percent"])
        row += 1

    ws.write(row, 0, "TOTAL", fmt["label"])
    ws.write(row, 1, scrub.get("total_gross", 0), fmt["currency_bold"])
    ws.write(row, 2, scrub.get("total_gross", 0) - scrub.get("total_net", 0), fmt["currency_bold"])
    ws.write(row, 3, scrub.get("total_net", 0), fmt["currency_bold"])
    row += 2

    ws.write(row, 0, "Avg Monthly Net", fmt["label"])
    ws.write(row, 1, scrub.get("avg_monthly_net", 0), fmt["currency_bold"])
    row += 3

    excluded_txns = scrub.get("excluded_transactions", [])
    if excluded_txns:
        ws.write(row, 0, "EXCLUDED TRANSACTIONS", fmt["section"])
        row += 1
        excl_headers = ["Date", "Description", "Amount", "Reason"]
        for col, h in enumerate(excl_headers):
            ws.write(row, col, h, fmt["header"])
        row += 1

        ws.set_column("C:C", 18)
        ws.set_column("D:D", 40)
        for txn in excluded_txns:
            ws.write(row, 0, txn.get("date", ""), fmt["value"])
            ws.write(row, 1, txn.get("description", ""), fmt["wrap"])
            ws.write(row, 2, txn.get("amount", 0), fmt["currency"])
            ws.write(row, 3, txn.get("reason", ""), fmt["wrap"])
            row += 1


# ── Tab 3: Reverse Engineering ────────────────────────────────────────

def _add_reverse_engineering_tab(workbook, fmt, position):
    ws = workbook.add_worksheet("Reverse Engineering")
    ws.set_column("A:A", 5)
    ws.set_column("B:B", 22)
    ws.set_column("C:K", 16)

    ws.write("A1", "POSITION REVERSE ENGINEERING", fmt["title"])

    positions = position.get("positions", [])

    row = 3
    if not positions:
        ws.write(row, 0, "No existing MCA/loan positions detected.", fmt["value"])
        return

    headers = [
        "#", "Lender", "Payment", "Frequency", "Est. Funding",
        "Factor", "Payback", "Remaining", "Paid In %", "Payoff Date",
    ]
    for col, h in enumerate(headers):
        ws.write(row, col, h, fmt["header"])
    row += 1

    for p in positions:
        ws.write(row, 0, p["position_number"], fmt["number"])
        ws.write(row, 1, p["lender_name"], fmt["value"])
        ws.write(row, 2, p["payment_amount"], fmt["currency"])
        ws.write(row, 3, p["payment_frequency"], fmt["value"])
        ws.write(row, 4, p["estimated_original_funding"], fmt["currency"])
        ws.write(row, 5, p["estimated_factor_rate"], fmt["value"])
        ws.write(row, 6, p["estimated_total_payback"], fmt["currency"])
        ws.write(row, 7, p["estimated_remaining_balance"], fmt["currency"])
        paid_fmt = fmt["pass"] if p["paid_in_percent"] > 50 else fmt["warn"]
        ws.write(row, 8, f"{p['paid_in_percent']:.1f}%", paid_fmt)
        ws.write(row, 9, p["estimated_payoff_date"], fmt["value"])
        row += 1

    row += 1
    ws.write(row, 0, "SUMMARY", fmt["section"])
    row += 1
    ws.write(row, 0, "Total Positions", fmt["label"])
    ws.write(row, 1, position.get("total_positions", 0), fmt["number"])
    row += 1
    ws.write(row, 0, "Total Daily Payment", fmt["label"])
    ws.write(row, 1, position.get("total_daily_payment", 0), fmt["currency"])
    row += 1
    ws.write(row, 0, "Total Monthly Payment", fmt["label"])
    ws.write(row, 1, position.get("total_monthly_payment", 0), fmt["currency"])
    row += 1
    ws.write(row, 0, "Est. Total Remaining", fmt["label"])
    ws.write(row, 1, position.get("estimated_total_remaining", 0), fmt["currency"])
    row += 1
    ws.write(row, 0, "Known Lenders", fmt["label"])
    ws.write(row, 1, ", ".join(position.get("unique_lenders", [])) or "None", fmt["value"])


# ── Tab 4: In-House Forensics ─────────────────────────────────────────

def _add_forensics_tab(workbook, fmt, risk, fraud_flags):
    ws = workbook.add_worksheet("In-House Forensics")
    ws.set_column("A:A", 28)
    ws.set_column("B:B", 14)
    ws.set_column("C:C", 14)
    ws.set_column("D:D", 50)

    ws.write("A1", "IN-HOUSE FORENSICS CHECKLIST", fmt["title"])

    row = 3
    ws.write(row, 0, "Check", fmt["header"])
    ws.write(row, 1, "Value", fmt["header"])
    ws.write(row, 2, "Result", fmt["header"])
    ws.write(row, 3, "Details", fmt["header_left"])
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
        ("Tax Liens/Garnishments", str(sum(1 for f in risk.get("red_flags", []) if f["category"] in ("Tax", "Legal"))),
         not any(f["category"] in ("Tax", "Legal") for f in risk.get("red_flags", [])),
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
        ws.write(row, 0, check_name, fmt["label"])
        ws.write(row, 1, str(value), fmt["value"])
        ws.write(row, 2, "PASS" if passed else "FAIL", fmt["pass"] if passed else fmt["fail"])
        ws.write(row, 3, detail, fmt["wrap"])
        row += 1

    row += 2
    red_flags = risk.get("red_flags", [])
    ws.write(row, 0, "RED FLAGS", fmt["section"])
    row += 1

    if not red_flags:
        ws.write(row, 0, "No red flags detected.", fmt["pass"])
    else:
        ws.write(row, 0, "Severity", fmt["header"])
        ws.write(row, 1, "Category", fmt["header"])
        ws.write(row, 2, "Date", fmt["header"])
        ws.write(row, 3, "Description", fmt["header_left"])
        row += 1
        for flag in red_flags:
            sev = flag.get("severity", "MEDIUM")
            sev_fmt = fmt["fail"] if sev == "HIGH" else fmt["warn"]
            ws.write(row, 0, sev, sev_fmt)
            ws.write(row, 1, flag.get("category", ""), fmt["value"])
            ws.write(row, 2, flag.get("date", ""), fmt["value"])
            ws.write(row, 3, flag.get("description", ""), fmt["wrap"])
            row += 1

    row += 2
    expenses = risk.get("expenses_by_category", {})
    if expenses:
        ws.write(row, 0, "EXPENSE BREAKDOWN", fmt["section"])
        row += 1
        ws.write(row, 0, "Category", fmt["header"])
        ws.write(row, 1, "Monthly Avg", fmt["header"])
        row += 1
        for cat, total in sorted(expenses.items(), key=lambda x: -x[1]):
            ws.write(row, 0, cat.title(), fmt["label"])
            ws.write(row, 1, total, fmt["currency"])
            row += 1


# ── Tab 5: Lender Match ──────────────────────────────────────────────

def _add_lender_match_tab(workbook, fmt, lender_data):
    ws = workbook.add_worksheet("Lender Match")
    ws.set_column("A:A", 22)
    ws.set_column("B:B", 18)
    ws.set_column("C:C", 18)
    ws.set_column("D:D", 14)

    ws.write("A1", "LENDER MATCHING RESULTS", fmt["title"])

    row = 3
    eligible = lender_data.get("eligible_lenders", [])
    ws.write(row, 0, f"ELIGIBLE LENDERS ({len(eligible)})", fmt["section"])
    row += 1

    if eligible:
        ws.write(row, 0, "Lender", fmt["header"])
        ws.write(row, 1, "Products", fmt["header"])
        ws.write(row, 2, "Payment Types", fmt["header"])
        ws.write(row, 3, "Match Score", fmt["header"])
        row += 1
        for lender in eligible:
            ws.write(row, 0, lender["lender_name"], fmt["value"])
            ws.write(row, 1, ", ".join(lender.get("product_types", [])), fmt["value"])
            ws.write(row, 2, ", ".join(lender.get("payment_types", [])), fmt["value"])
            score = lender.get("match_score", 0)
            s_fmt = fmt["pass"] if score >= 70 else fmt["warn"] if score >= 50 else fmt["value"]
            ws.write(row, 3, f"{score:.1f}", s_fmt)
            row += 1
    else:
        ws.write(row, 0, "No eligible lenders found.", fmt["fail"])
        row += 1

    row += 2
    disqualified = lender_data.get("disqualified_lenders", [])
    ws.write(row, 0, f"DISQUALIFIED LENDERS ({len(disqualified)})", fmt["section"])
    row += 1

    if disqualified:
        ws.set_column("B:B", 60)
        ws.write(row, 0, "Lender", fmt["header"])
        ws.write(row, 1, "Disqualifying Reasons", fmt["header_left"])
        row += 1
        for lender in disqualified:
            ws.write(row, 0, lender["lender_name"], fmt["value"])
            reasons = "; ".join(lender.get("reasons", []))
            ws.write(row, 1, reasons, fmt["wrap"])
            row += 1
    else:
        ws.write(row, 0, "All lenders are eligible.", fmt["pass"])

    row += 2
    ws.write(row, 0, "Summary", fmt["label"])
    ws.write(row, 1, f"{lender_data.get('total_lenders_checked', 0)} checked, "
                      f"{lender_data.get('eligible_count', 0)} eligible, "
                      f"{lender_data.get('disqualified_count', 0)} disqualified", fmt["value"])


# ── JSON Output ───────────────────────────────────────────────────────

def _write_json_output(filepath, merchant, scrub, risk, position, calc, lender_match):
    data = {
        "generated_at": datetime.now().isoformat(),
        "merchant_name": merchant,
        "scrub_analysis": scrub,
        "risk_analysis": risk,
        "position_analysis": position,
        "calculations": calc,
        "lender_matching": lender_match,
    }
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)
