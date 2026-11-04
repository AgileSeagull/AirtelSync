"""Domain models shared by the engine, the API and the advisor tools."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Segment = Literal["micro", "prof", "multi", "mfg"]
GstinStatus = Literal["Active", "Cancelled", "Suspended"]
ContractChoice = Literal["flexible", "12", "24"]

SEGMENT_LABELS: dict[str, str] = {
    "micro": "Micro retail & services",
    "prof": "Professional offices",
    "multi": "Small multi-site businesses",
    "mfg": "Small manufacturers",
}

# Fixed vocabulary of needs the advisor can capture. Keeping it closed means the
# LLM maps free text onto known tags and the engine never sees an unknown need.
NEEDS: dict[str, str] = {
    "internet": "Reliable internet at the premises",
    "mobile_lines": "Business mobile numbers for owner/staff",
    "billing_pos": "GST billing, inventory and UPI/card acceptance",
    "whatsapp": "Reach customers on WhatsApp with a catalogue",
    "sms": "Bulk SMS alerts and promotions",
    "website": "A simple website on your own domain",
    "cctv": "CCTV with mobile viewing",
    "email_office": "Business email, documents and video meetings",
    "backup": "Automatic backup of PCs and phones",
    "device_security": "Antivirus / ransomware protection",
    "firewall": "Managed network firewall",
    "guest_wifi": "Separate Wi-Fi for customers",
    "failover": "Stay online when the main line is down",
    "telephony": "Office phone lines with IVR and call recording",
    "toll_free": "A 1800 toll-free number",
    "static_ip": "Fixed IP for CCTV, servers or remote access",
    "machine_monitoring": "Machine uptime and energy monitoring",
    "fleet_tracking": "GPS tracking for vehicles",
    "multi_site_network": "Central management of internet across branches",
    "dedicated_line": "Dedicated 1:1 internet with an uptime SLA",
    "high_speed": "Very high bandwidth (large files, many users)",
}


class Product(BaseModel):
    id: str
    category: str
    name: str
    description: str
    unit: str
    price_min: int
    price_max: int
    setup_fee: int
    min_contract_months: int
    city_tiers: list[int]
    min_employees: int
    min_sites: int
    requires_gstin: bool
    requires_one_of: list[str]
    install_days: int
    target_segments: list[str]


class Profile(BaseModel):
    """What we know about the business. Everything except business_type is optional
    so the advisor can call the engine as soon as the minimum is known."""

    business_type: str = Field(..., examples=["Dental clinic"])
    segment: Segment | None = None
    city: str | None = None
    city_tier: int | None = Field(None, ge=1, le=2)
    state: str | None = None
    employees: int = Field(1, ge=1)
    sites: int = Field(1, ge=1)
    has_gstin: bool = False
    gstin: str | None = None
    gstin_status: GstinStatus | None = None
    current_internet: str | None = None
    monthly_telecom_spend: int | None = Field(None, ge=0)
    needs: list[str] = Field(default_factory=list)
    fibre_feasible: bool | None = None
    # Optional explicit quantities; the engine derives sensible defaults otherwise.
    mobile_users: int | None = Field(None, ge=0)
    desk_users: int | None = Field(None, ge=0)
    cameras: int | None = Field(None, ge=0)
    counters: int | None = Field(None, ge=0)
    machines: int | None = Field(None, ge=0)
    vehicles: int | None = Field(None, ge=0)

    @property
    def gstin_active(self) -> bool:
        # A GSTIN we have not looked up yet is trusted only if the caller says it exists;
        # once looked up, only an Active status counts.
        if self.gstin_status is not None:
            return self.gstin_status == "Active"
        return self.has_gstin


class LineItem(BaseModel):
    product_id: str
    qty: int = Field(1, ge=1)


class Violation(BaseModel):
    product_id: str
    rule: Literal["unknown_product", "city_tier", "min_employees", "min_sites", "gstin", "dependency", "quantity"]
    message: str


class RecommendedItem(BaseModel):
    product_id: str
    name: str
    category: str
    qty: int
    unit: str
    reasons: list[str]  # reason codes, e.g. NEED_CCTV, SEG_PROF, DEP_FOR_P23
    why: str  # plain-English explanation assembled from the codes
    optional: bool = False  # the owner can toggle it off without breaking the bundle


class BundleTier(BaseModel):
    tier: Literal["essential", "recommended", "complete"]
    title: str
    items: list[RecommendedItem]


class Recommendation(BaseModel):
    profile: Profile
    segment: Segment
    tiers: list[BundleTier]
    excluded: list[Violation]  # requested/typical products the business cannot have yet, with why
    notes: list[str]


class QuoteLine(BaseModel):
    product_id: str
    name: str
    qty: int
    unit: str
    contract_months: int
    unit_price: int
    monthly: int
    setup: int
    install_days: int


class Quote(BaseModel):
    lines: list[QuoteLine]
    contract: ContractChoice
    subtotal_monthly: int
    bundle_discount_pct: int
    bundle_discount: int
    monthly_ex_gst: int
    gst: int
    monthly_total: int
    setup_ex_gst: int
    setup_waived: int
    setup_total: int
    earliest_activation_days: int
    current_spend: int | None
    monthly_difference: int | None  # positive = owner pays more than today
    violations: list[Violation]
    notes: list[str]
