"""Loads the reference CSVs once and serves them from memory.

The catalogue and both registries are small (25 / 3,534 / 2,723 rows), so an
in-memory dict is the simplest correct "database" for the mock APIs.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from .config import DATA_DIR
from .engine.models import Product


def _rows(name: str) -> list[dict[str, str]]:
    with open(Path(DATA_DIR) / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _split(value: str, sep: str) -> list[str]:
    return [v.strip() for v in value.split(sep) if v.strip()] if value else []


@lru_cache
def catalogue() -> dict[str, Product]:
    products = {}
    for r in _rows("product_catalogue.csv"):
        p = Product(
            id=r["product_id"],
            category=r["category"],
            name=r["product_name"],
            description=r["description"],
            unit=r["unit"],
            price_min=int(r["price_min_inr_per_month"]),
            price_max=int(r["price_max_inr_per_month"]),
            setup_fee=int(r["one_time_setup_inr"]),
            min_contract_months=int(r["min_contract_months"]),
            city_tiers=[int(t) for t in _split(r["available_city_tiers"], ";")],
            min_employees=int(r["min_employees"]),
            min_sites=int(r["min_sites"]),
            requires_gstin=r["requires_gstin"].upper() == "Y",
            requires_one_of=_split(r["requires_one_of"], "|"),
            install_days=int(r["typical_install_days"]),
            target_segments=_split(r["target_segments"], ";"),
        )
        products[p.id] = p
    return products


@lru_cache
def gstin_registry() -> dict[str, dict[str, str]]:
    return {r["gstin"]: r for r in _rows("mock_gstin_registry.csv")}


@lru_cache
def udyam_registry() -> dict[str, dict[str, str]]:
    return {r["udyam_number"]: r for r in _rows("mock_udyam_registry.csv")}


@lru_cache
def leads() -> list[dict[str, str]]:
    return _rows("smb_leads.csv")
