from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import fulfilment
from .models import Order

router = APIRouter(prefix="/orders", tags=["orders"])


class MandateReq(BaseModel):
    upi_id: str


class AdvanceReq(BaseModel):
    fibre_feasible: bool = True


def _order(oid: str) -> Order:
    o = Order.load(oid)
    if o is None:
        raise HTTPException(404, "Order not found")
    return o


def _do(fn, *a):
    try:
        return fn(*a)
    except fulfilment.FulfilmentError as e:
        raise HTTPException(409, str(e))


@router.get("/{oid}/track")
def track(oid: str) -> dict:
    return fulfilment.track(_order(oid))


@router.post("/{oid}/mandate")
def mandate(oid: str, req: MandateReq) -> dict:
    o = _order(oid)
    try:
        fulfilment.set_mandate(o, req.upi_id)
    except fulfilment.FulfilmentError as e:
        raise HTTPException(422 if "UPI ID" in str(e) else 409, str(e))
    return fulfilment.track(o)


@router.post("/{oid}/advance")
def advance(oid: str, req: AdvanceReq) -> dict:
    """Demo simulator: what the back office / field team would do next."""
    o = _order(oid)
    _do(fulfilment.advance, o, req.fibre_feasible)
    return fulfilment.track(o)


@router.post("/{oid}/delay")
def delay(oid: str) -> dict:
    o = _order(oid)
    _do(fulfilment.delay, o)
    return fulfilment.track(o)
