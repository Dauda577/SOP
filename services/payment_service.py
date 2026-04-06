"""
Payment Service Layer

Coordinates payment processing with permission checking and error handling.
Supports Cash, Mobile Money (via Paystack), and Card payments.
"""

import logging
from typing import Tuple, Optional, Dict, List, Any
from modules.payments import (
    process_payment,
    get_payment_summary,
    get_pending_payments,
    reconcile_payments,
    get_cash_drawer_summary,
    process_refund,
)
from modules.auth import has_permission

logger = logging.getLogger(__name__)


class PaymentService:
    """High-level payment service with permission checking."""

    CASHIER_PERMISSION = "process_sales"
    MANAGER_PERMISSION = "manage_payments"

    @staticmethod
    def checkout_payment(
        user_id: int,
        amount_paid: float,
        total_amount: float,
        sale_id: int,
        payment_method: str,
        **kwargs,
    ) -> Tuple[bool, Optional[str], str]:
        try:
            if not has_permission(user_id, PaymentService.CASHIER_PERMISSION):
                logger.warning("Unauthorized payment attempt by user %s", user_id)
                return False, None, "Permission denied: cannot process payments"

            success, transaction_id, msg = process_payment(
                amount_paid=amount_paid,
                total_amount=total_amount,
                sale_id=sale_id,
                payment_method=payment_method,
                **kwargs,
            )

            if success:
                logger.info(
                    "User %s processed payment for sale %s (GHS %.2f) via %s",
                    user_id, sale_id, amount_paid, payment_method,
                )
            else:
                logger.warning("Payment failed for sale %s: %s", sale_id, msg)

            return success, transaction_id, msg

        except Exception as e:
            logger.error("Error in checkout_payment: %s", e)
            return False, None, f"Payment service error: {str(e)}"

    @staticmethod
    def get_payment_report(
        user_id: int, start_date: str = None, end_date: str = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        try:
            if not has_permission(user_id, PaymentService.MANAGER_PERMISSION):
                logger.warning("Unauthorized report request by user %s", user_id)
                return False, None

            summary = get_payment_summary(start_date, end_date)
            if "error" in summary:
                return False, None

            logger.info("User %s generated payment report", user_id)
            return True, summary

        except Exception as e:
            logger.error("Error generating payment report: %s", e)
            return False, None

    @staticmethod
    def get_pending_transactions(user_id: int) -> Tuple[bool, List[Dict[str, Any]]]:
        try:
            if not has_permission(user_id, PaymentService.MANAGER_PERMISSION):
                logger.warning("Unauthorized pending request by user %s", user_id)
                return False, []

            pending = get_pending_payments()
            logger.info("User %s viewed %d pending payments", user_id, len(pending))
            return True, pending

        except Exception as e:
            logger.error("Error getting pending payments: %s", e)
            return False, []

    @staticmethod
    def reconcile_day(
        user_id: int, date: str = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        try:
            if not has_permission(user_id, PaymentService.MANAGER_PERMISSION):
                logger.warning(
                    "Unauthorized reconciliation attempt by user %s", user_id
                )
                return False, None

            success, report = reconcile_payments(date)
            if success:
                logger.info("User %s reconciled payments for %s", user_id, date)
            return success, report

        except Exception as e:
            logger.error("Error reconciling payments: %s", e)
            return False, None

    @staticmethod
    def get_cash_drawer(
        user_id: int, date: str = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        try:
            if not has_permission(user_id, PaymentService.MANAGER_PERMISSION):
                logger.warning("Unauthorized drawer request by user %s", user_id)
                return False, None

            drawer = get_cash_drawer_summary(date)
            if "error" in drawer:
                return False, None

            logger.info("User %s viewed cash drawer for %s", user_id, date)
            return True, drawer

        except Exception as e:
            logger.error("Error getting cash drawer: %s", e)
            return False, None

    @staticmethod
    def process_refund_request(
        user_id: int, payment_id: int, reason: str, refund_amount: float = None
    ) -> Tuple[bool, str]:
        try:
            if not has_permission(user_id, PaymentService.MANAGER_PERMISSION):
                logger.warning("Unauthorized refund attempt by user %s", user_id)
                return False, "Permission denied: cannot process refunds"

            success, msg = process_refund(payment_id, reason, refund_amount)
            if success:
                logger.info(
                    "User %s processed refund for payment %s", user_id, payment_id
                )
            return success, msg

        except Exception as e:
            logger.error("Error processing refund: %s", e)
            return False, f"Refund service error: {str(e)}"


# ── Convenience functions ─────────────────────────────────────────────────────

def process_cash_checkout(
    user_id: int, amount_paid: float, total_amount: float, sale_id: int
) -> Tuple[bool, Optional[str], float, str]:
    success, txn_id, msg = PaymentService.checkout_payment(
        user_id=user_id,
        amount_paid=amount_paid,
        total_amount=total_amount,
        sale_id=sale_id,
        payment_method="cash",
    )
    change = amount_paid - total_amount if success else 0
    return success, txn_id, change, msg


def process_momo_checkout(
    user_id: int,
    amount_paid: float,
    total_amount: float,
    sale_id: int,
    phone_number: str,
    provider: str,
) -> Tuple[bool, Optional[str], str]:
    """
    Process a MoMo sale through Paystack.

    Records the sale in the DB first, then initiates the Paystack charge.
    Returns (success, paystack_reference, message).
    """
    # 1. Record the sale
    ok, txn_id, msg = PaymentService.checkout_payment(
        user_id=user_id,
        amount_paid=amount_paid,
        total_amount=total_amount,
        sale_id=sale_id,
        payment_method="momo",
        phone_number=phone_number,
        provider=provider,
    )
    if not ok:
        return False, None, msg

    # 2. Initiate Paystack charge
    try:
        from utils.momo_payments import initiate_momo_payment
        success, ref, momo_msg = initiate_momo_payment(
            phone=phone_number,
            amount=total_amount,
            sale_id=sale_id,
            provider=provider,
        )
        return success, ref, momo_msg
    except Exception as e:
        logger.error("Paystack MoMo initiation error: %s", e)
        # Sale is already recorded — return partial success so cashier knows
        return True, txn_id, f"Sale recorded but MoMo push failed: {str(e)}"


def process_card_checkout(
    user_id: int,
    amount_paid: float,
    total_amount: float,
    sale_id: int,
    card_number: str,
    expiry: str,
    cvv: str,
    cardholder_name: str,
) -> Tuple[bool, Optional[str], str]:
    return PaymentService.checkout_payment(
        user_id=user_id,
        amount_paid=amount_paid,
        total_amount=total_amount,
        sale_id=sale_id,
        payment_method="card",
        card_number=card_number,
        expiry=expiry,
        cvv=cvv,
        cardholder_name=cardholder_name,
    )