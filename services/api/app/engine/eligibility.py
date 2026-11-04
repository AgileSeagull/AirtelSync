"""Hard catalogue rules. Every bundle the system quotes passes through validate_bundle."""
from __future__ import annotations

from ..data_store import catalogue
from .models import LineItem, Product, Profile, Violation


def product_violations(profile: Profile, product: Product) -> list[Violation]:
    """Rules that depend only on the business, not on the rest of the bundle."""
    v: list[Violation] = []
    tier = profile.city_tier or 2
    if tier not in product.city_tiers:
        v.append(Violation(product_id=product.id, rule="city_tier",
                           message=f"{product.name} is only available in tier-{'/'.join(map(str, product.city_tiers))} cities"))
    if profile.employees < product.min_employees:
        v.append(Violation(product_id=product.id, rule="min_employees",
                           message=f"{product.name} needs at least {product.min_employees} employees"))
    if profile.sites < product.min_sites:
        v.append(Violation(product_id=product.id, rule="min_sites",
                           message=f"{product.name} needs at least {product.min_sites} sites"))
    if product.requires_gstin and not profile.gstin_active:
        reason = (f"your GSTIN is {profile.gstin_status.lower()}" if profile.gstin_status and profile.gstin_status != "Active"
                  else "it needs an active GST registration")
        v.append(Violation(product_id=product.id, rule="gstin",
                           message=f"{product.name} cannot be sold because {reason}"))
    return v


def is_eligible(profile: Profile, product_id: str) -> bool:
    p = catalogue().get(product_id)
    return p is not None and not product_violations(profile, p)


def validate_bundle(profile: Profile, items: list[LineItem]) -> list[Violation]:
    cat = catalogue()
    ids = {i.product_id for i in items}
    out: list[Violation] = []
    for item in items:
        p = cat.get(item.product_id)
        if p is None:
            out.append(Violation(product_id=item.product_id, rule="unknown_product",
                                 message=f"{item.product_id} is not in the catalogue"))
            continue
        if item.qty < 1:
            out.append(Violation(product_id=p.id, rule="quantity", message="Quantity must be at least 1"))
        out.extend(product_violations(profile, p))
        if p.requires_one_of and not ids.intersection(p.requires_one_of):
            deps = [cat[d] for d in p.requires_one_of if d in cat]
            if all(d.category == "Connectivity" for d in deps):
                msg = f"{p.name} needs an internet line in the same bundle"
            else:
                msg = f"{p.name} needs one of: " + ", ".join(d.name for d in deps)
            out.append(Violation(product_id=p.id, rule="dependency", message=msg))
    return out
