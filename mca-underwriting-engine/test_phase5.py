"""
Phase 5 Tests - Manual Input, Funder Rates, Deal Summary, Web Routes
"""
import os
import sys
import json
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

passed = 0
failed = 0

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name} - {detail}")
        failed += 1


# ── Test 1: Funder Rates ────────────────────────────────────────────

print("\n=== TEST 1: Funder Rates Complete ===")
rates_path = os.path.join(BASE_DIR, 'config', 'funder_rates_complete.json')
test("File exists", os.path.exists(rates_path))

with open(rates_path) as f:
    rates_data = json.load(f)

funders = rates_data.get('funder_rates', {})
test("Has 100+ funders", len(funders) >= 100, f"Only {len(funders)} funders")
test("Has default_rate", 'default_rate' in rates_data)
test("Has rate_tiers", 'rate_tiers' in rates_data)

# Check specific funders
test("Has Kalamata Capital", "Kalamata Capital" in funders)
test("Has OnDeck", "OnDeck" in funders)
test("Has Shopify Capital", "Shopify Capital" in funders)

# Rate ranges
rates_vals = list(funders.values())
test("Min rate >= 1.0", min(rates_vals) >= 1.0)
test("Max rate <= 2.0", max(rates_vals) <= 2.0)
print(f"  Funder count: {len(funders)}")


# ── Test 2: Deal Input Module ───────────────────────────────────────

print("\n=== TEST 2: Deal Input Module ===")
from core_logic.deal_input import DealInput, ManualPosition, MonthlyData

deal = DealInput(
    legal_name="Test Business LLC",
    dba="Test Biz",
    industry="Restaurant",
    state="FL",
    time_in_business_months=36,
    fico_score=650,
    proposed_funding=50000,
    proposed_factor_rate=1.35,
    proposed_term_months=6,
    proposed_frequency="daily",
)

# Add monthly data
for i, rev in enumerate([85000, 90000, 82000]):
    deal.monthly_data.append(MonthlyData(
        month=f"2024-{10+i:02d}",
        gross_revenue=rev * 1.1,
        net_revenue=rev,
        nsf_count=1 if i == 0 else 0,
        negative_days=0,
        avg_daily_balance=5000 + i * 500,
        deposit_count=30 + i,
    ))

# Add a position
deal.positions.append(ManualPosition(
    position_number=1,
    funder_name="Kalamata Capital",
    funded_date="2024-08-15",
    funded_amount=30000,
    payment_amount=280,
    payment_frequency="daily",
    factor_rate=1.38,
))

deal.calculate_all()

test("Avg monthly revenue calculated", deal.avg_monthly_revenue > 0, f"{deal.avg_monthly_revenue}")
test("Total positions = 1", deal.total_positions == 1)
test("Monthly holdback calculated", deal.total_monthly_holdback > 0, f"{deal.total_monthly_holdback}")
test("Current holdback % calculated", deal.current_holdback_percent > 0, f"{deal.current_holdback_percent:.1f}%")
test("New deal impact calculated", deal.new_monthly_payment > 0, f"{deal.new_monthly_payment}")
test("Combined holdback calculated", deal.combined_holdback_percent > 0, f"{deal.combined_holdback_percent:.1f}%")

# Save and load
with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as tf:
    temp_path = tf.name
deal.save(temp_path)
loaded = DealInput.load(temp_path)
test("Save/load preserves legal name", loaded.legal_name == "Test Business LLC")
test("Save/load preserves positions", len(loaded.positions) == 1)
test("Save/load preserves monthly data", len(loaded.monthly_data) == 3)
test("Save/load recalculates", loaded.avg_monthly_revenue > 0)
os.unlink(temp_path)

# Add/delete position
deal.add_position(ManualPosition(
    position_number=2,
    funder_name="OnDeck",
    funded_date="2024-09-01",
    funded_amount=20000,
    payment_amount=200,
    payment_frequency="daily",
    factor_rate=1.30,
))
test("Add position works", deal.total_positions == 2)

deal.delete_position(1)
test("Delete position works", deal.total_positions == 1)
test("Position renumbered", deal.positions[0].position_number == 1)

print(f"  Avg Monthly Revenue: ${deal.avg_monthly_revenue:,.2f}")
print(f"  Current Holdback: {deal.current_holdback_percent:.1f}%")
print(f"  Combined Holdback: {deal.combined_holdback_percent:.1f}%")


# ── Test 3: Deal Summary Generator ──────────────────────────────────

print("\n=== TEST 3: Deal Summary Generator ===")
from core_logic.deal_summary import generate_deal_summary, DealSummary

summary = generate_deal_summary(deal)

test("Summary has legal name", summary.legal_name == "Test Business LLC")
test("Summary has tier", summary.tier in ['A', 'B', 'C', 'D'], f"tier={summary.tier}")
test("Summary has avg_monthly_revenue", summary.avg_monthly_revenue > 0)
test("Summary has monthly breakdown", len(summary.monthly_breakdown) == 3)
test("Summary has positions", len(summary.positions) == 1)
test("Summary has proposed payment", summary.proposed_payment > 0)
test("Summary has deal type", summary.deal_type in ['New', 'Renewal', 'Add-On'], f"type={summary.deal_type}")
test("Summary has revenue trend", summary.revenue_trend in ['Growing', 'Declining', 'Stable', ''])

print(f"  Tier: {summary.tier}")
print(f"  Deal Type: {summary.deal_type}")
print(f"  Revenue Trend: {summary.revenue_trend}")
print(f"  Risk Flags: {summary.risk_flags}")
print(f"  Max Recommended Funding: ${summary.max_recommended_funding:,.2f}")
print(f"  ADB/Payment Ratio: {summary.adb_to_payment_ratio:.2f}x")


# ── Test 4: Deal Summary with Lender Matches ────────────────────────

print("\n=== TEST 4: Deal Summary with Lender Data ===")
mock_lender_data = {
    "eligible_count": 3,
    "eligible_lenders": [
        {"lender_name": "TestLender1", "match_score": 85},
        {"lender_name": "TestLender2", "match_score": 72},
        {"lender_name": "TestLender3", "match_score": 60},
    ]
}
summary2 = generate_deal_summary(deal, lender_matches=mock_lender_data)
test("Lender count populated", summary2.eligible_lender_count == 3)
test("Top lenders populated", len(summary2.top_lender_matches) == 3)


# ── Test 5: Flask App Routes ────────────────────────────────────────

print("\n=== TEST 5: Flask App Manual Input Routes ===")
from app import app as flask_app

flask_app.config['TESTING'] = True
client = flask_app.test_client()

# Manual input page
resp = client.get('/manual-input')
test("GET /manual-input returns 200", resp.status_code == 200)
test("Page has funder list", b'Kalamata Capital' in resp.data)
test("Page has form fields", b'legal_name' in resp.data)
test("Page has monthly table", b'monthly-table' in resp.data)
test("Page has positions table", b'positions-table' in resp.data)

# Save deal via API
deal_data = {
    "legal_name": "API Test Corp",
    "dba": "ATC",
    "industry": "Tech",
    "state": "NY",
    "fico_score": 700,
    "time_in_business_months": 48,
    "proposed_funding": 40000,
    "proposed_factor_rate": 1.30,
    "proposed_term_months": 6,
    "proposed_frequency": "daily",
    "monthly_data": [
        {"month": "2024-10", "gross_revenue": 100000, "net_revenue": 95000, "nsf_count": 0,
         "negative_days": 0, "avg_daily_balance": 8000, "deposit_count": 35},
        {"month": "2024-11", "gross_revenue": 105000, "net_revenue": 98000, "nsf_count": 0,
         "negative_days": 0, "avg_daily_balance": 9000, "deposit_count": 38},
        {"month": "2024-12", "gross_revenue": 110000, "net_revenue": 102000, "nsf_count": 0,
         "negative_days": 0, "avg_daily_balance": 8500, "deposit_count": 40},
    ],
    "positions": [
        {"funder_name": "OnDeck", "funded_date": "2024-07-01", "funded_amount": 25000,
         "payment_amount": 250, "payment_frequency": "daily", "factor_rate": 1.30},
    ],
}

resp = client.post('/api/deal',
                   data=json.dumps(deal_data),
                   content_type='application/json')
test("POST /api/deal returns 200", resp.status_code == 200)
result = json.loads(resp.data)
test("Save returns filename", 'filename' in result)
test("Save returns summary", 'summary' in result)
saved_filename = result.get('filename', '')
print(f"  Saved as: {saved_filename}")

# Load deal
if saved_filename:
    resp = client.get(f'/api/deal/{saved_filename}')
    test("GET /api/deal/<file> returns 200", resp.status_code == 200)
    loaded_data = json.loads(resp.data)
    test("Loaded deal has correct name", loaded_data.get('legal_name') == 'API Test Corp')
    test("Loaded deal has monthly data", len(loaded_data.get('monthly_data', [])) == 3)
    test("Loaded deal has positions", len(loaded_data.get('positions', [])) == 1)

    # Add position
    new_pos = {
        "funder_name": "Fundbox",
        "funded_date": "2024-09-15",
        "funded_amount": 15000,
        "payment_amount": 150,
        "payment_frequency": "daily",
        "factor_rate": 1.25,
    }
    resp = client.post(f'/api/deal/{saved_filename}/position',
                       data=json.dumps(new_pos),
                       content_type='application/json')
    test("POST position returns 200", resp.status_code == 200)
    pos_result = json.loads(resp.data)
    test("Position added (count=2)", pos_result.get('total_positions') == 2)

    # Delete position
    resp = client.delete(f'/api/deal/{saved_filename}/position/1')
    test("DELETE position returns 200", resp.status_code == 200)
    del_result = json.loads(resp.data)
    test("Position deleted (count=1)", del_result.get('total_positions') == 1)

    # Generate summary
    resp = client.post(f'/api/generate-summary/{saved_filename}')
    test("POST generate-summary returns 200", resp.status_code == 200)
    summary_result = json.loads(resp.data)
    test("Summary has tier", 'tier' in summary_result)
    test("Summary has report_file", 'report_file' in summary_result)
    test("Summary has risk_flags", 'risk_flags' in summary_result)
    print(f"  Tier: {summary_result.get('tier')}")
    print(f"  Report: {summary_result.get('report_file')}")
    print(f"  Eligible Lenders: {summary_result.get('eligible_lenders')}")
    print(f"  Risk Flags: {summary_result.get('risk_flags')}")


# ── Test 6: Base HTML Nav Update ────────────────────────────────────

print("\n=== TEST 6: Navigation ===")
resp = client.get('/')
test("Dashboard loads", resp.status_code == 200)
test("Nav has Manual Input link", b'Manual Input' in resp.data)


# ── Summary ─────────────────────────────────────────────────────────

print(f"\n{'='*50}")
print(f"RESULTS: {passed} passed, {failed} failed out of {passed+failed} tests")
if failed == 0:
    print("ALL TESTS PASSED!")
else:
    print(f"WARNING: {failed} test(s) failed")
    sys.exit(1)
