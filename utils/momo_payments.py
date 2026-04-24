"""
Paystack-backed Mobile Money helpers for the POS desktop app.

This module powers the MoMo flow expected by ``views/cashier_view.py``:
- validate Ghana phone numbers and infer the network
- initiate a Paystack mobile money charge
- initialize a Paystack-hosted mobile money checkout page
- verify the transaction status by Paystack reference

The UI polls Paystack directly via the verify endpoint instead of relying on
webhooks, which keeps the desktop flow workable in a local environment.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from urllib import error, parse, request

from database.db import get_db_connection

logger = logging.getLogger(__name__)

PAYSTACK_API_BASE = "https://api.paystack.co"

MOMO_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "mtn": {
        "name": "MTN MoMo",
        "color": "#ffcc00",
        "prefixes": ("024", "025", "053", "054", "055", "059"),
        "paystack_provider": "mtn",
    },
    "telecel": {
        "name": "Telecel Cash",
        "color": "#e60000",
        "prefixes": ("020", "050"),
        "paystack_provider": "vod",
    },
    "airteltigo": {
        "name": "AirtelTigo Money",
        "color": "#0066cc",
        "prefixes": ("026", "027", "056", "057"),
        "paystack_provider": "tgo",
    },
}

PAYSTACK_STATUS_TO_DB = {
    "success": "completed",
    "pending": "pending",
    "processing": "processing",
    "ongoing": "processing",
    "queued": "pending",
    "failed": "failed",
    "abandoned": "failed",
    "reversed": "reversed",
}


def _get_paystack_secret_key() -> str:
    secret = (
        os.getenv("PAYSTACK_SECRET_KEY")
        or os.getenv("PAYSTACK_SECRET")
        or os.getenv("PAYSTACK_SK")
        or ""
    ).strip()
    if not secret:
        raise EnvironmentError(
            "PAYSTACK_SECRET_KEY is not set. Add your Paystack secret key to .env."
        )
    return secret


def _normalize_ghana_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("233") and len(digits) == 12:
        digits = "0" + digits[3:]
    if len(digits) == 9:
        digits = "0" + digits
    return digits


def validate_ghana_phone(phone: str) -> Tuple[bool, str, Optional[str]]:
    """
    Validate and normalize a Ghana phone number.

    Returns ``(is_valid, normalized_local_format, provider_key)``.
    """
    normalized = _normalize_ghana_phone(phone)
    if not re.fullmatch(r"0\d{9}", normalized):
        return False, normalized, None

    prefix = normalized[:3]
    for provider_key, cfg in MOMO_PROVIDERS.items():
        if prefix in cfg["prefixes"]:
            return True, normalized, provider_key

    return True, normalized, None


def _paystack_request(
    method: str, path: str, payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    url = f"{PAYSTACK_API_BASE}{path}"
    data = None
    headers = {
        "Authorization": f"Bearer {_get_paystack_secret_key()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "SOP-POS/1.0 (+desktop-paystack-integration)",
    }

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = request.Request(url, data=data, headers=headers, method=method.upper())

    try:
        with request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.error("Paystack HTTP error %s on %s %s: %s", exc.code, method, path, body)
        try:
            parsed_body = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed_body = {"message": body or str(exc)}
        parsed_body.setdefault("status", False)
        return parsed_body
    except error.URLError as exc:
        logger.error("Paystack network error on %s %s: %s", method, path, exc)
        raise ConnectionError(f"Could not reach Paystack: {exc}") from exc


def _build_reference(sale_id: int) -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"PSK-MOMO-{sale_id}-{timestamp}"


def _get_sale_context(sale_id: int, phone: str) -> Dict[str, Any]:
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT s.sale_id, s.total_amount, c.full_name AS customer_name, c.email
            FROM sales s
            LEFT JOIN customers c ON s.customer_id = c.customer_id
            WHERE s.sale_id = ?
            """,
            (sale_id,),
        ).fetchone()

    if not row:
        return {
            "sale_id": sale_id,
            "email": f"sale-{sale_id}-{re.sub(r'\\D', '', phone)}@example.com",
            "customer_name": "Walk-in Customer",
        }

    context = dict(row)
    email = (context.get("email") or "").strip()
    if not email:
        digits = re.sub(r"\D", "", phone)
        email = f"sale-{sale_id}-{digits}@example.com"
    context["email"] = email
    context["customer_name"] = context.get("customer_name") or "Walk-in Customer"
    return context


def _insert_or_update_pending_payment(
    sale_id: int,
    amount_paid: float,
    reference: str,
    provider_key: str,
    status: str = "pending",
) -> None:
    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT payment_id FROM payments WHERE reference = ?",
            (reference,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE payments
                SET amount_paid = ?, payment_method = 'momo', status = ?, provider = ?
                WHERE reference = ?
                """,
                (amount_paid, status, provider_key, reference),
            )
            return

        conn.execute(
            """
            INSERT INTO payments
                (sale_id, amount_paid, change_given, payment_method, status, reference, provider, fee)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sale_id, amount_paid, 0.0, "momo", status, reference, provider_key, 0.0),
        )


def _update_payment_from_verification(
    reference: str,
    paystack_status: str,
    amount_paid: Optional[float] = None,
    fee: Optional[float] = None,
    provider_key: Optional[str] = None,
) -> None:
    db_status = PAYSTACK_STATUS_TO_DB.get(paystack_status, "pending")
    assignments = ["status = ?"]
    params = [db_status]

    if amount_paid is not None:
        assignments.append("amount_paid = ?")
        params.append(amount_paid)
    if fee is not None:
        assignments.append("fee = ?")
        params.append(fee)
    if provider_key:
        assignments.append("provider = ?")
        params.append(provider_key)

    params.append(reference)

    with get_db_connection() as conn:
        conn.execute(
            f"UPDATE payments SET {', '.join(assignments)} WHERE reference = ?",
            params,
        )


def _map_provider_to_paystack(provider_key: str) -> str:
    provider_key = (provider_key or "mtn").strip().lower()
    aliases = {
        "mtn": "mtn",
        "telecel": "vod",
        "vodafone": "vod",
        "vod": "vod",
        "airteltigo": "tgo",
        "tgo": "tgo",
    }
    return aliases.get(provider_key, "mtn")


def _map_provider_from_paystack(provider_code: Optional[str]) -> Optional[str]:
    if not provider_code:
        return None
    provider_code = provider_code.lower()
    reverse = {
        "mtn": "mtn",
        "vod": "telecel",
        "tgo": "airteltigo",
    }
    return reverse.get(provider_code, provider_code)


def initialize_momo_checkout(
    amount: float,
    sale_id: int,
    customer_phone: str = "",
) -> Tuple[bool, str, str, str]:
    """
    Initialize a Paystack hosted checkout page restricted to mobile money.

    Returns ``(success, reference, checkout_url, message)``.
    """
    normalized = _normalize_ghana_phone(customer_phone) if customer_phone else ""
    context = _get_sale_context(sale_id, normalized)
    reference = _build_reference(sale_id)

    payload = {
        "email": context["email"],
        "amount": str(int(round(float(amount) * 100))),
        "currency": "GHS",
        "reference": reference,
        "channels": ["mobile_money"],
        "metadata": {
            "sale_id": sale_id,
            "customer_phone": normalized,
            "customer_name": context["customer_name"],
            "channel": "mobile_money_checkout",
        },
    }

    response = _paystack_request("POST", "/transaction/initialize", payload)
    if not response.get("status"):
        return False, "", "", response.get("message") or "Could not create checkout page."

    data = response.get("data") or {}
    checkout_url = data.get("authorization_url") or ""
    if not checkout_url:
        return False, "", "", "Paystack did not return a checkout URL."

    _insert_or_update_pending_payment(
        sale_id=sale_id,
        amount_paid=float(amount),
        reference=reference,
        provider_key="checkout",
        status="pending",
    )

    return True, reference, checkout_url, response.get("message") or "Checkout page created."


def initiate_momo_payment(
    phone: str,
    amount: float,
    sale_id: int,
    provider: str = "mtn",
) -> Tuple[bool, str, str]:
    """
    Create a Paystack mobile money charge for a sale.

    Returns ``(success, reference, message)``.
    """
    valid, normalized, detected_provider = validate_ghana_phone(phone)
    if not valid:
        return False, "", "Invalid phone number. Use a valid Ghana mobile money number."

    provider_key = provider if provider not in ("", "auto") else (detected_provider or "")
    if not provider_key:
        provider_key = detected_provider or "mtn"

    context = _get_sale_context(sale_id, normalized)
    reference = _build_reference(sale_id)

    payload = {
        "email": context["email"],
        "amount": str(int(round(float(amount) * 100))),
        "currency": "GHS",
        "reference": reference,
        "mobile_money": {
            "phone": normalized,
            "provider": _map_provider_to_paystack(provider_key),
        },
        "metadata": {
            "sale_id": sale_id,
            "customer_phone": normalized,
            "customer_name": context["customer_name"],
            "channel": "mobile_money",
            "local_provider": provider_key,
        },
    }

    response = _paystack_request("POST", "/charge", payload)
    success = bool(response.get("status"))
    message = response.get("message") or "Charge attempt sent to Paystack."
    data = response.get("data") or {}
    gateway_status = (data.get("status") or "pending").lower()

    if not success:
        return False, "", message

    _insert_or_update_pending_payment(
        sale_id=sale_id,
        amount_paid=float(amount),
        reference=reference,
        provider_key=provider_key,
        status=PAYSTACK_STATUS_TO_DB.get(gateway_status, "pending"),
    )

    if gateway_status == "success":
        _update_payment_from_verification(
            reference=reference,
            paystack_status="success",
            amount_paid=float(amount),
            fee=(data.get("fees") or 0) / 100 if data.get("fees") is not None else 0.0,
            provider_key=provider_key,
        )
        return True, reference, "Payment completed successfully."

    return True, reference, message


def verify_momo_payment(reference: str) -> Tuple[bool, str, str]:
    """
    Verify a Paystack mobile money charge by reference.

    Returns ``(success, status, message)`` where ``status`` is one of:
    ``success``, ``pending``, ``abandoned``, ``failed``, or ``error``.
    """
    if not reference:
        return False, "error", "Missing Paystack reference."

    encoded_reference = parse.quote(reference, safe="")
    response = _paystack_request(
        "GET",
        f"/transaction/verify/{encoded_reference}",
    )

    if not response.get("status"):
        return False, "error", response.get("message") or "Verification failed."

    data = response.get("data") or {}
    paystack_status = (data.get("status") or "pending").lower()
    provider_key = _map_provider_from_paystack(
        ((data.get("authorization") or {}).get("channel")
         if isinstance(data.get("authorization"), dict)
         else None)
    )
    if not provider_key:
        provider_key = _map_provider_from_paystack(
            ((data.get("metadata") or {}).get("local_provider")
             if isinstance(data.get("metadata"), dict)
             else None)
        )

    amount_paid = None
    if data.get("amount") is not None:
        amount_paid = float(data["amount"]) / 100.0
    fee = None
    if data.get("fees") is not None:
        fee = float(data["fees"]) / 100.0

    _update_payment_from_verification(
        reference=reference,
        paystack_status=paystack_status,
        amount_paid=amount_paid,
        fee=fee,
        provider_key=provider_key,
    )

    message = (
        data.get("gateway_response")
        or data.get("message")
        or response.get("message")
        or "Verification complete."
    )

    if paystack_status == "success":
        return True, "success", message
    if paystack_status in {"pending", "processing", "ongoing", "queued"}:
        return False, "pending", message
    if paystack_status == "abandoned":
        return False, "abandoned", message
    if paystack_status in {"failed", "reversed"}:
        return False, "failed", message
    return False, "error", message
