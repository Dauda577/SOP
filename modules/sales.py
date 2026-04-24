from database.db import (
    get_connection,
    get_db_connection,
    update_inventory,
)
from modules.products import get_product_by_id
from typing import List, Dict, Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Cart helpers ───────────────────────────────────────────────────────────────


def cart_add_item(
    cart: list, product: dict, quantity: int = 1
) -> Tuple[list, bool, str]:
    """
    Adds a product to the cart or increments quantity if already present.
    Checks stock availability before adding.
    """
    if quantity <= 0:
        return cart, False, "Quantity must be at least 1."

    available = product.get("stock", 0)
    already_in_cart = sum(
        item["quantity"] for item in cart if item["product_id"] == product["product_id"]
    )
    if already_in_cart + quantity > available:
        return (
            cart,
            False,
            f"Only {available} in stock ({already_in_cart} already in cart).",
        )

    for item in cart:
        if item["product_id"] == product["product_id"]:
            item["quantity"] += quantity
            item["subtotal"] = round(item["quantity"] * item["unit_price"], 2)
            logger.info(f"Updated cart: {product['product_name']} x{item['quantity']}")
            return cart, True, "Quantity updated."

    cart.append(
        {
            "product_id": product["product_id"],
            "product_name": product["product_name"],
            "unit_price": product["price"],
            "quantity": quantity,
            "subtotal": round(quantity * product["price"], 2),
        }
    )
    logger.info(f"Added to cart: {product['product_name']} x{quantity}")
    return cart, True, "Item added."


def cart_remove_item(cart: list, product_id: int) -> list:
    """Removes an item from the cart by product_id."""
    removed = [item for item in cart if item["product_id"] == product_id]
    if removed:
        logger.info(f"Removed from cart: {removed[0]['product_name']}")
    return [item for item in cart if item["product_id"] != product_id]


def cart_update_quantity(
    cart: list, product_id: int, new_qty: int
) -> Tuple[list, bool, str]:
    """Updates the quantity of a cart item."""
    if new_qty <= 0:
        return cart_remove_item(cart, product_id), True, "Item removed."

    for item in cart:
        if item["product_id"] == product_id:
            product = get_product_by_id(product_id)
            if product and new_qty > product["stock"]:
                return cart, False, f"Only {product['stock']} in stock."
            item["quantity"] = new_qty
            item["subtotal"] = round(new_qty * item["unit_price"], 2)
            logger.info(f"Updated cart quantity: {item['product_name']} x{new_qty}")
            return cart, True, "Quantity updated."

    return cart, False, "Item not found in cart."


def cart_clear(cart: list) -> list:
    """Returns an empty cart."""
    logger.info("Cart cleared.")
    return []


def cart_totals(cart: list, discount: float = 0.0, tax_rate: float = 0.0) -> dict:
    """
    Calculates subtotal, discount, tax, and grand total.
    discount: fixed GHS amount off
    tax_rate: percentage e.g. 0.15 for 15%
    """
    subtotal = round(sum(item["subtotal"] for item in cart), 2)
    discount = min(round(discount, 2), subtotal)
    after_discount = round(subtotal - discount, 2)
    tax = round(after_discount * tax_rate, 2)
    total = round(after_discount + tax, 2)
    return {
        "subtotal": subtotal,
        "discount": discount,
        "tax": tax,
        "total": total,
    }


def get_cart_item_count(cart: list) -> int:
    """Returns total number of items in cart."""
    return sum(item["quantity"] for item in cart)


def get_cart_summary(cart: list) -> str:
    """Returns a formatted summary of cart items."""
    if not cart:
        return "Cart is empty"
    return "\n".join(
        f"{item['quantity']}x {item['product_name']} - GHS {item['subtotal']:.2f}"
        for item in cart
    )


# ── Sale processing ────────────────────────────────────────────────────────────


def process_sale(
    cart: list,
    user_id: int,
    payment_method: str,
    amount_paid: float,
    discount: float = 0.0,
    tax_rate: float = 0.0,
    customer_id: int = None,
) -> Tuple[bool, Optional[int], float, str]:
    """
    Commits a completed sale to the database.
    Deducts stock for every item in the cart.
    Awards loyalty points to customer if one is attached.

    Returns (True, sale_id, change, "message") or (False, None, 0, "error").
    """
    if not cart:
        return False, None, 0, "Cart is empty."

    if payment_method not in ("cash", "momo", "card"):
        return False, None, 0, "Invalid payment method."

    totals = cart_totals(cart, discount, tax_rate)

    if amount_paid < totals["total"]:
        return (
            False,
            None,
            0,
            (
                f"Amount paid (GHS {amount_paid:.2f}) is less than "
                f"total (GHS {totals['total']:.2f})."
            ),
        )

    change = round(amount_paid - totals["total"], 2)

    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Insert sale record
        cursor.execute(
            """
            INSERT INTO sales
                (user_id, customer_id, total_amount, discount, tax, payment_method)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                user_id,
                customer_id,
                totals["total"],
                totals["discount"],
                totals["tax"],
                payment_method,
            ),
        )
        sale_id = cursor.lastrowid

        # Insert each sale item
        for item in cart:
            cursor.execute(
                """
                INSERT INTO sale_items
                    (sale_id, product_id, quantity, unit_price, subtotal)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    sale_id,
                    item["product_id"],
                    item["quantity"],
                    item["unit_price"],
                    item["subtotal"],
                ),
            )

        # Insert payment record (skip for mobile money - handled separately)
        if payment_method != "momo":
            cursor.execute(
                """
                INSERT INTO payments
                    (sale_id, amount_paid, change_given, payment_method)
                VALUES (?, ?, ?, ?)
            """,
                (sale_id, amount_paid, change, payment_method),
            )

        conn.commit()
        logger.info(
            f"Sale #{sale_id} processed by user {user_id} "
            f"for GHS {totals['total']:.2f}"
        )

        # Deduct stock with transaction logging
        for item in cart:
            success = update_inventory(
                item["product_id"], -item["quantity"], f"Sale #{sale_id}", user_id
            )
            if not success:
                logger.warning(
                    f"Failed to update inventory for product {item['product_id']}"
                )

        # ── Award loyalty points ───────────────────────────────────────────
        # 1 point per GHS spent (on the final total after discount/tax).
        # Only runs when a customer is attached to the sale.
        if customer_id:
            try:
                from modules.customers import award_loyalty_points

                pts = award_loyalty_points(customer_id, totals["total"])
                if pts > 0:
                    logger.info(
                        f"Awarded {pts} loyalty points to customer {customer_id} "
                        f"for sale #{sale_id}"
                    )
            except Exception as loyalty_err:
                # Non-fatal — log but don't fail the sale
                logger.error(f"Error awarding loyalty points: {loyalty_err}")

        return True, sale_id, change, "Sale completed successfully."

    except Exception as e:
        conn.rollback()
        logger.error(f"Error processing sale: {e}")
        return False, None, 0, f"Error processing sale: {str(e)}"
    finally:
        conn.close()


def void_sale(sale_id: int, user_id: int, reason: str = "Voided") -> Tuple[bool, str]:
    """
    Void a sale and restore inventory.
    Only admin/manager should call this.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM sales WHERE sale_id = ?", (sale_id,))
        sale = cursor.fetchone()
        if not sale:
            conn.close()
            return False, "Sale not found."

        cursor.execute(
            "SELECT product_id, quantity FROM sale_items WHERE sale_id = ?", (sale_id,)
        )
        items = cursor.fetchall()
        conn.close()

        # Restore inventory
        for item in items:
            update_inventory(
                item["product_id"],
                item["quantity"],
                f"Voided sale #{sale_id}: {reason}",
                user_id,
            )

        # Mark as voided if column exists
        try:
            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE sales SET status = 'voided' WHERE sale_id = ?", (sale_id,)
                )
        except Exception:
            pass

        logger.info(f"Sale #{sale_id} voided by user {user_id}: {reason}")
        return True, f"Sale #{sale_id} voided successfully."

    except Exception as e:
        logger.error(f"Error voiding sale: {e}")
        return False, f"Error voiding sale: {str(e)}"


# ── Sale retrieval ─────────────────────────────────────────────────────────────


def get_sale_details(sale_id: int) -> dict:
    """Returns full details of a sale including all items (used for receipts)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT s.sale_id, s.sale_date, s.total_amount, s.discount,
               s.tax, s.payment_method,
               u.full_name AS cashier,
               c.full_name AS customer, c.phone AS customer_phone,
               (
                   SELECT p.amount_paid
                   FROM payments p
                   WHERE p.sale_id = s.sale_id
                   ORDER BY p.payment_date DESC, p.payment_id DESC
                   LIMIT 1
               ) AS amount_paid,
               (
                   SELECT p.change_given
                   FROM payments p
                   WHERE p.sale_id = s.sale_id
                   ORDER BY p.payment_date DESC, p.payment_id DESC
                   LIMIT 1
               ) AS change_given
        FROM sales s
        JOIN users u ON s.user_id = u.user_id
        LEFT JOIN customers c ON s.customer_id = c.customer_id
        WHERE s.sale_id = ?
    """,
        (sale_id,),
    )
    sale = cursor.fetchone()

    if not sale:
        conn.close()
        return {}

    sale_dict = dict(sale)
    sale_dict["amount_paid"] = (
        sale_dict["amount_paid"]
        if sale_dict["amount_paid"] is not None
        else sale_dict["total_amount"]
    )
    sale_dict["change_given"] = (
        sale_dict["change_given"] if sale_dict["change_given"] is not None else 0.0
    )

    cursor.execute(
        """
        SELECT si.quantity, si.unit_price, si.subtotal,
               pr.product_name, pr.barcode
        FROM sale_items si
        JOIN products pr ON si.product_id = pr.product_id
        WHERE si.sale_id = ?
    """,
        (sale_id,),
    )
    sale_dict["items"] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return sale_dict


def get_today_sales(user_id: int = None) -> List[Dict]:
    """Returns all sales made today, optionally filtered by cashier."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT s.sale_id, s.sale_date, s.total_amount,
               s.payment_method, s.discount, s.tax,
               u.full_name AS cashier,
               c.full_name AS customer
        FROM sales s
        JOIN users u ON s.user_id = u.user_id
        LEFT JOIN customers c ON s.customer_id = c.customer_id
        WHERE DATE(s.sale_date) = DATE('now')
    """
    params = []
    if user_id:
        query += " AND s.user_id = ?"
        params.append(user_id)
    query += " ORDER BY s.sale_date DESC"

    cursor.execute(query, params)
    sales = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return sales


def get_sales_by_date(
    start_date: str, end_date: str = None, user_id: int = None
) -> List[Dict]:
    """Get sales within a date range."""
    if end_date is None:
        end_date = start_date
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT s.sale_id, s.sale_date, s.total_amount,
               s.payment_method, u.full_name AS cashier,
               COUNT(si.sale_item_id) AS item_count
        FROM sales s
        JOIN users u ON s.user_id = u.user_id
        LEFT JOIN sale_items si ON s.sale_id = si.sale_id
        WHERE DATE(s.sale_date) BETWEEN ? AND ?
    """
    params = [start_date, end_date]
    if user_id:
        query += " AND s.user_id = ?"
        params.append(user_id)
    query += " GROUP BY s.sale_id ORDER BY s.sale_date DESC"

    cursor.execute(query, params)
    sales = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return sales


def get_sales_summary(start_date: str = None, end_date: str = None) -> Dict:
    """Get summary statistics for sales."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            COUNT(*)          AS total_transactions,
            SUM(total_amount) AS total_sales,
            AVG(total_amount) AS average_sale,
            SUM(discount)     AS total_discounts,
            SUM(tax)          AS total_tax,
            MIN(total_amount) AS min_sale,
            MAX(total_amount) AS max_sale
        FROM sales
    """
    params = []
    if start_date and end_date:
        query += " WHERE DATE(sale_date) BETWEEN ? AND ?"
        params = [start_date, end_date]
    elif start_date:
        query += " WHERE DATE(sale_date) >= ?"
        params = [start_date]
    elif end_date:
        query += " WHERE DATE(sale_date) <= ?"
        params = [end_date]

    cursor.execute(query, params)
    summary = cursor.fetchone()
    conn.close()
    return dict(summary) if summary else {}


def get_cashier_performance(start_date: str = None, end_date: str = None) -> List[Dict]:
    """Get performance metrics for cashiers."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            u.user_id,
            u.full_name AS cashier_name,
            COUNT(s.sale_id)      AS transaction_count,
            SUM(s.total_amount)   AS total_sales,
            AVG(s.total_amount)   AS average_sale,
            SUM(s.discount)       AS total_discounts_given
        FROM users u
        LEFT JOIN sales s ON u.user_id = s.user_id
        WHERE u.role IN ('cashier', 'manager', 'admin')
    """
    params = []
    if start_date and end_date:
        query += " AND DATE(s.sale_date) BETWEEN ? AND ?"
        params = [start_date, end_date]
    query += " GROUP BY u.user_id ORDER BY total_sales DESC"

    cursor.execute(query, params)
    performance = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return performance


def generate_receipt(sale_id: int, store_name: str = "POS System") -> str:
    """Generate a formatted receipt string."""
    sale = get_sale_details(sale_id)
    if not sale:
        return "Receipt not found."

    lines = []
    lines.append("=" * 40)
    lines.append(f"{store_name:^40}")
    lines.append("=" * 40)
    lines.append(f"Receipt #: {sale['sale_id']}")
    lines.append(f"Date: {sale['sale_date']}")
    lines.append(f"Cashier: {sale['cashier']}")
    if sale.get("customer"):
        lines.append(f"Customer: {sale['customer']}")
    lines.append("-" * 40)
    lines.append(f"{'Item':<20} {'Qty':>4} {'Price':>8} {'Total':>8}")
    lines.append("-" * 40)

    for item in sale["items"]:
        lines.append(
            f"{item['product_name'][:20]:<20} "
            f"{item['quantity']:>4} "
            f"GHS{item['unit_price']:>7.2f} "
            f"GHS{item['subtotal']:>7.2f}"
        )

    lines.append("-" * 40)
    subtotal = sale["total_amount"] + sale["discount"] - sale["tax"]
    lines.append(
        f"{'Subtotal:':<32} GHS{subtotal:>7.2f}"
    )
    if sale["discount"] > 0:
        lines.append(f"{'Discount:':<32} -GHS{sale['discount']:>6.2f}")
    if sale["tax"] > 0:
        lines.append(f"{'Tax:':<32} +GHS{sale['tax']:>6.2f}")
    lines.append(f"{'Total:':<32} GHS{sale['total_amount']:>7.2f}")
    lines.append(f"{'Amount Paid:':<32} GHS{sale['amount_paid']:>7.2f}")
    if sale["change_given"] > 0:
        lines.append(f"{'Change:':<32} GHS{sale['change_given']:>7.2f}")
    lines.append("-" * 40)
    lines.append(f"{'Payment Method:':<20} {sale['payment_method'].upper()}")
    lines.append("=" * 40)
    lines.append("Thank you for your purchase!")
    lines.append("Please come again!")

    return "\n".join(lines)


# ── SalesProcessor wrapper ─────────────────────────────────────────────────────


class SalesProcessor:
    """Sales processing wrapper class."""

    def __init__(self, auth=None, product_manager=None):
        self.auth = auth
        self.product_manager = product_manager

    def process_sale(self, *args, **kwargs):
        return process_sale(*args, **kwargs)

    def cart_add_item(self, *args, **kwargs):
        return cart_add_item(*args, **kwargs)

    def cart_remove_item(self, *args, **kwargs):
        return cart_remove_item(*args, **kwargs)

    def cart_update_quantity(self, *args, **kwargs):
        return cart_update_quantity(*args, **kwargs)

    def cart_clear(self, *args, **kwargs):
        return cart_clear(*args, **kwargs)

    def cart_totals(self, *args, **kwargs):
        return cart_totals(*args, **kwargs)

    def get_sale_details(self, *args, **kwargs):
        return get_sale_details(*args, **kwargs)

    def get_today_sales(self, *args, **kwargs):
        return get_today_sales(*args, **kwargs)

    def get_sales_by_date(self, *args, **kwargs):
        return get_sales_by_date(*args, **kwargs)

    def get_sales_summary(self, *args, **kwargs):
        return get_sales_summary(*args, **kwargs)

    def get_cashier_performance(self, *args, **kwargs):
        return get_cashier_performance(*args, **kwargs)

    def generate_receipt(self, *args, **kwargs):
        return generate_receipt(*args, **kwargs)


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_cart = []
    test_product = {
        "product_id": 1,
        "product_name": "Test Product",
        "price": 10.99,
        "stock": 5,
    }

    test_cart, success, msg = cart_add_item(test_cart, test_product, 2)
    print(f"Add item: {msg}")
    print(f"Cart: {test_cart}")

    totals = cart_totals(test_cart)
    print(f"Totals: {totals}")
