"""
Deal Input Module - Manual data entry and override system.
Allows entering deal info when PDFs aren't available or need correction.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict


@dataclass
class ManualPosition:
    """Manually entered or overridden MCA position."""
    position_number: int
    funder_name: str
    funded_date: str  # YYYY-MM-DD
    funded_amount: float
    payment_amount: float
    payment_frequency: str  # "daily", "weekly", "biweekly", "monthly"
    factor_rate: float = 1.42
    is_buyout: bool = False
    is_renewal: bool = False
    notes: str = ""

    # Calculated fields (filled in by system)
    total_payback: float = 0.0
    estimated_remaining: float = 0.0
    estimated_paid: float = 0.0
    paid_in_percent: float = 0.0
    estimated_payoff_date: str = ""
    monthly_payment: float = 0.0

    def calculate_terms(self, as_of_date: str = None):
        """Calculate payback, remaining balance, etc."""
        if as_of_date is None:
            as_of_date = datetime.now().strftime("%Y-%m-%d")

        self.total_payback = self.funded_amount * self.factor_rate

        try:
            funded = datetime.strptime(self.funded_date, "%Y-%m-%d")
        except (ValueError, TypeError):
            self.monthly_payment = self.payment_amount * 21.5 if self.payment_frequency == "daily" else self.payment_amount * 4.33
            return

        today = datetime.strptime(as_of_date, "%Y-%m-%d")
        days_elapsed = max(0, (today - funded).days)

        if self.payment_frequency == "daily":
            payments_made = days_elapsed * 0.71  # ~5 biz days / 7
            self.monthly_payment = self.payment_amount * 21.5
        elif self.payment_frequency == "weekly":
            payments_made = days_elapsed / 7
            self.monthly_payment = self.payment_amount * 4.33
        elif self.payment_frequency == "biweekly":
            payments_made = days_elapsed / 14
            self.monthly_payment = self.payment_amount * 2.17
        else:  # monthly
            payments_made = days_elapsed / 30
            self.monthly_payment = self.payment_amount

        self.estimated_paid = payments_made * self.payment_amount
        self.estimated_remaining = max(0, self.total_payback - self.estimated_paid)
        self.paid_in_percent = (self.estimated_paid / self.total_payback * 100) if self.total_payback > 0 else 0

        if self.estimated_remaining > 0 and self.payment_amount > 0:
            remaining_payments = self.estimated_remaining / self.payment_amount
            if self.payment_frequency == "daily":
                days_to_payoff = remaining_payments / 0.71
            elif self.payment_frequency == "weekly":
                days_to_payoff = remaining_payments * 7
            elif self.payment_frequency == "biweekly":
                days_to_payoff = remaining_payments * 14
            else:
                days_to_payoff = remaining_payments * 30
            payoff = today + timedelta(days=int(days_to_payoff))
            self.estimated_payoff_date = payoff.strftime("%Y-%m-%d")


@dataclass
class MonthlyData:
    """Monthly bank statement data - manual entry."""
    month: str = ""  # "2024-01" or "January 2024"
    gross_revenue: float = 0.0
    net_revenue: float = 0.0
    nsf_count: int = 0
    negative_days: int = 0
    avg_daily_balance: float = 0.0
    deposit_count: int = 0
    ending_balance: float = 0.0
    notes: str = ""

    # Calculated
    holdback_amount: float = 0.0
    holdback_percent: float = 0.0


@dataclass
class DealInput:
    """Complete deal input - can be from OCR or manual entry."""

    # Basic Info
    legal_name: str = ""
    dba: str = ""
    industry: str = ""
    state: str = ""

    # Business Info
    time_in_business_months: int = 0
    fico_score: int = 0
    ownership_percent: float = 100.0

    # Bank Info
    bank_name: str = ""
    account_number: str = ""
    account_type: str = "operating"

    # Monthly Data
    monthly_data: List[MonthlyData] = field(default_factory=list)

    # Positions
    positions: List[ManualPosition] = field(default_factory=list)

    # Proposed Deal
    proposed_funding: float = 0.0
    proposed_factor_rate: float = 1.35
    proposed_term_months: int = 6
    proposed_frequency: str = "daily"

    # Metadata
    data_source: str = "manual"
    created_date: str = ""
    modified_date: str = ""
    notes: str = ""

    # Calculated Summary
    total_gross_revenue: float = 0.0
    avg_monthly_revenue: float = 0.0
    total_nsf_count: int = 0
    total_negative_days: int = 0
    avg_daily_balance: float = 0.0

    # Position Summary
    total_positions: int = 0
    total_daily_holdback: float = 0.0
    total_monthly_holdback: float = 0.0
    current_holdback_percent: float = 0.0
    total_remaining_balance: float = 0.0

    # New Deal Impact
    new_daily_payment: float = 0.0
    new_monthly_payment: float = 0.0
    combined_holdback_percent: float = 0.0
    net_available_revenue: float = 0.0

    def __post_init__(self):
        if not self.created_date:
            self.created_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.modified_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def calculate_all(self):
        """Calculate all derived fields."""
        self._calculate_monthly_summary()
        self._calculate_position_summary()
        self._calculate_new_deal_impact()
        self._calculate_monthly_holdbacks()

    def _calculate_monthly_summary(self):
        if not self.monthly_data:
            return
        self.total_gross_revenue = sum(m.gross_revenue for m in self.monthly_data)
        revenues = [m.net_revenue for m in self.monthly_data if m.net_revenue > 0]
        self.avg_monthly_revenue = sum(revenues) / len(revenues) if revenues else 0
        self.total_nsf_count = sum(m.nsf_count for m in self.monthly_data)
        self.total_negative_days = sum(m.negative_days for m in self.monthly_data)
        adbs = [m.avg_daily_balance for m in self.monthly_data if m.avg_daily_balance > 0]
        self.avg_daily_balance = sum(adbs) / len(adbs) if adbs else 0

    def _calculate_position_summary(self):
        self.total_positions = len(self.positions)
        total_daily = 0.0
        total_remaining = 0.0
        for pos in self.positions:
            pos.calculate_terms()
            total_remaining += pos.estimated_remaining
            if pos.payment_frequency == "daily":
                total_daily += pos.payment_amount
            elif pos.payment_frequency == "weekly":
                total_daily += pos.payment_amount / 5
            elif pos.payment_frequency == "biweekly":
                total_daily += pos.payment_amount / 10
            else:
                total_daily += pos.payment_amount / 21.5
        self.total_daily_holdback = total_daily
        self.total_monthly_holdback = total_daily * 21.5
        self.total_remaining_balance = total_remaining
        if self.avg_monthly_revenue > 0:
            self.current_holdback_percent = (self.total_monthly_holdback / self.avg_monthly_revenue) * 100

    def _calculate_new_deal_impact(self):
        if self.proposed_funding <= 0:
            return
        total_payback = self.proposed_funding * self.proposed_factor_rate
        if self.proposed_frequency == "daily":
            total_payments = self.proposed_term_months * 21.5
        else:
            total_payments = self.proposed_term_months * 4.33
        payment = total_payback / total_payments if total_payments > 0 else 0
        if self.proposed_frequency == "daily":
            self.new_daily_payment = payment
            self.new_monthly_payment = payment * 21.5
        else:
            self.new_daily_payment = payment / 5
            self.new_monthly_payment = payment * 4.33
        combined_monthly = self.total_monthly_holdback + self.new_monthly_payment
        if self.avg_monthly_revenue > 0:
            self.combined_holdback_percent = (combined_monthly / self.avg_monthly_revenue) * 100
        self.net_available_revenue = self.avg_monthly_revenue - combined_monthly

    def _calculate_monthly_holdbacks(self):
        for month in self.monthly_data:
            month.holdback_amount = self.total_monthly_holdback
            if month.net_revenue > 0:
                month.holdback_percent = (self.total_monthly_holdback / month.net_revenue) * 100
            else:
                month.holdback_percent = 0

    def add_position(self, position: ManualPosition):
        position.position_number = len(self.positions) + 1
        self.positions.append(position)
        self.calculate_all()

    def update_position(self, index: int, position: ManualPosition):
        if 0 <= index < len(self.positions):
            position.position_number = index + 1
            self.positions[index] = position
            self.calculate_all()

    def delete_position(self, index: int):
        if 0 <= index < len(self.positions):
            self.positions.pop(index)
            for i, pos in enumerate(self.positions):
                pos.position_number = i + 1
            self.calculate_all()

    def add_monthly_data(self, month_data: MonthlyData):
        self.monthly_data.append(month_data)
        self.calculate_all()

    def to_dict(self) -> dict:
        return {
            "legal_name": self.legal_name,
            "dba": self.dba,
            "industry": self.industry,
            "state": self.state,
            "time_in_business_months": self.time_in_business_months,
            "fico_score": self.fico_score,
            "ownership_percent": self.ownership_percent,
            "bank_name": self.bank_name,
            "account_number": self.account_number,
            "account_type": self.account_type,
            "monthly_data": [asdict(m) for m in self.monthly_data],
            "positions": [asdict(p) for p in self.positions],
            "proposed_funding": self.proposed_funding,
            "proposed_factor_rate": self.proposed_factor_rate,
            "proposed_term_months": self.proposed_term_months,
            "proposed_frequency": self.proposed_frequency,
            "data_source": self.data_source,
            "created_date": self.created_date,
            "modified_date": self.modified_date,
            "notes": self.notes,
            "total_gross_revenue": self.total_gross_revenue,
            "avg_monthly_revenue": self.avg_monthly_revenue,
            "total_nsf_count": self.total_nsf_count,
            "total_negative_days": self.total_negative_days,
            "avg_daily_balance": self.avg_daily_balance,
            "total_positions": self.total_positions,
            "total_daily_holdback": self.total_daily_holdback,
            "total_monthly_holdback": self.total_monthly_holdback,
            "current_holdback_percent": self.current_holdback_percent,
            "total_remaining_balance": self.total_remaining_balance,
            "new_daily_payment": self.new_daily_payment,
            "new_monthly_payment": self.new_monthly_payment,
            "combined_holdback_percent": self.combined_holdback_percent,
            "net_available_revenue": self.net_available_revenue,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DealInput':
        deal = cls(
            legal_name=data.get("legal_name", ""),
            dba=data.get("dba", ""),
            industry=data.get("industry", ""),
            state=data.get("state", ""),
            time_in_business_months=data.get("time_in_business_months", 0),
            fico_score=data.get("fico_score", 0),
            ownership_percent=data.get("ownership_percent", 100.0),
            bank_name=data.get("bank_name", ""),
            account_number=data.get("account_number", ""),
            account_type=data.get("account_type", "operating"),
            proposed_funding=data.get("proposed_funding", 0.0),
            proposed_factor_rate=data.get("proposed_factor_rate", 1.35),
            proposed_term_months=data.get("proposed_term_months", 6),
            proposed_frequency=data.get("proposed_frequency", "daily"),
            data_source=data.get("data_source", "manual"),
            created_date=data.get("created_date", ""),
            notes=data.get("notes", ""),
        )
        for m in data.get("monthly_data", []):
            if isinstance(m, dict):
                deal.monthly_data.append(MonthlyData(**{k: v for k, v in m.items()
                                                        if k in MonthlyData.__dataclass_fields__}))
        for p in data.get("positions", []):
            if isinstance(p, dict):
                deal.positions.append(ManualPosition(**{k: v for k, v in p.items()
                                                        if k in ManualPosition.__dataclass_fields__}))
        deal.calculate_all()
        return deal

    def save(self, filepath: str):
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> 'DealInput':
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)


def merge_ocr_with_manual(ocr_data: dict, manual_overrides: DealInput) -> DealInput:
    """Merge OCR-extracted data with manual overrides. Manual takes precedence."""
    deal = DealInput(data_source="hybrid")
    deal.legal_name = manual_overrides.legal_name or ocr_data.get("merchant_name", "")
    deal.bank_name = manual_overrides.bank_name or ocr_data.get("bank_name", "")
    deal.account_number = manual_overrides.account_number or ocr_data.get("account_number", "")

    if manual_overrides.monthly_data:
        deal.monthly_data = manual_overrides.monthly_data
    else:
        for month, revenue in ocr_data.get("monthly_net", {}).items():
            deal.monthly_data.append(MonthlyData(
                month=month,
                net_revenue=revenue,
                gross_revenue=ocr_data.get("monthly_gross", {}).get(month, revenue),
            ))

    if manual_overrides.positions:
        deal.positions = manual_overrides.positions
    else:
        for pos in ocr_data.get("positions", []):
            deal.positions.append(ManualPosition(
                position_number=pos.get("position_number", 1),
                funder_name=pos.get("lender_name", "Unknown"),
                funded_date=pos.get("first_payment_date", ""),
                funded_amount=pos.get("estimated_original_funding", 0),
                payment_amount=pos.get("payment_amount", 0),
                payment_frequency=pos.get("payment_frequency", "daily"),
                factor_rate=pos.get("estimated_factor_rate", 1.42),
            ))

    deal.calculate_all()
    return deal
