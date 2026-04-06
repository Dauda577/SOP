from database.db import get_connection
from typing import List, Dict
import logging
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_daily_summary(date: str = None) -> Dict:
    """
    Returns a summary for a given date (YYYY-MM-DD).
    Defaults to today if no date given.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        date_filter = date or "date('now')"
        param = (date,) if date else ()

        query = f"""
            SELECT
                COUNT(*)                    AS total_transactions,
                COALESCE(SUM(total_amount), 0) AS total_revenue,
                COALESCE(SUM(discount), 0)     AS total_discounts,
                COALESCE(SUM(tax), 0)          AS total_tax,
                COALESCE(AVG(total_amount), 0) AS avg_sale_value,
                COALESCE(MAX(total_amount), 0) AS max_sale_value,
                COALESCE(MIN(total_amount), 0) AS min_sale_value
            FROM sales
            WHERE DATE(sale_date) = {'?' if date else date_filter}
        """
        cursor.execute(query, param)
        row = cursor.fetchone()
        conn.close()

        result = dict(row) if row else {}

        # Add additional derived fields
        if result:
            result["net_revenue"] = result["total_revenue"] - result["total_discounts"]
            result["transaction_count"] = result["total_transactions"]

        return result
    except Exception as e:
        logger.error(f"Error getting daily summary: {e}")
        return {}


def get_sales_by_date_range(start_date: str, end_date: str) -> List[Dict]:
    """
    Returns daily totals between two dates (YYYY-MM-DD).
    Useful for weekly / monthly charts.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                DATE(sale_date)                AS sale_date,
                COUNT(*)                       AS total_transactions,
                COALESCE(SUM(total_amount), 0) AS total_revenue,
                COALESCE(SUM(discount), 0)     AS total_discounts,
                COALESCE(SUM(tax), 0)          AS total_tax
            FROM sales
            WHERE DATE(sale_date) BETWEEN ? AND ?
            GROUP BY DATE(sale_date)
            ORDER BY DATE(sale_date)
        """,
            (start_date, end_date),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Error getting sales by date range: {e}")
        return []


def get_top_products(
    limit: int = 10, start_date: str = None, end_date: str = None
) -> List[Dict]:
    """
    Returns top-selling products by quantity sold.
    Optionally filter by date range.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        where = ""
        params = []
        if start_date and end_date:
            where = "WHERE DATE(s.sale_date) BETWEEN ? AND ?"
            params = [start_date, end_date]

        cursor.execute(
            f"""
            SELECT
                p.product_id,
                p.product_name,
                p.category,
                SUM(si.quantity)  AS units_sold,
                SUM(si.subtotal)  AS revenue,
                AVG(si.unit_price) AS avg_price
            FROM sale_items si
            JOIN products p ON si.product_id = p.product_id
            JOIN sales s    ON si.sale_id    = s.sale_id
            {where}
            GROUP BY si.product_id
            ORDER BY units_sold DESC
            LIMIT ?
        """,
            params + [limit],
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Add contribution percentage
        total_revenue = sum(row["revenue"] for row in rows)
        for row in rows:
            row["contribution_percentage"] = (
                (row["revenue"] / total_revenue * 100) if total_revenue > 0 else 0
            )

        return rows
    except Exception as e:
        logger.error(f"Error getting top products: {e}")
        return []


def get_low_performing_products(limit: int = 10, days: int = 30) -> List[Dict]:
    """
    Returns products with low sales volume in the last N days.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        cursor.execute(
            """
            SELECT
                p.product_id,
                p.product_name,
                p.category,
                p.price,
                COALESCE(SUM(si.quantity), 0) AS units_sold,
                COALESCE(SUM(si.subtotal), 0) AS revenue,
                COALESCE(i.quantity, 0) AS current_stock
            FROM products p
            LEFT JOIN sale_items si ON p.product_id = si.product_id
            LEFT JOIN sales s ON si.sale_id = s.sale_id AND DATE(s.sale_date) >= ?
            LEFT JOIN inventory i ON p.product_id = i.product_id
            WHERE p.is_active = 1
            GROUP BY p.product_id
            HAVING units_sold = 0 OR units_sold < ?
            ORDER BY units_sold ASC
            LIMIT ?
        """,
            (cutoff_date, limit, limit),
        )

        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Error getting low performing products: {e}")
        return []


def get_payment_method_breakdown(
    start_date: str = None, end_date: str = None
) -> List[Dict]:
    """
    Returns revenue split by payment method for a date range.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        where = ""
        params = []
        if start_date and end_date:
            where = "WHERE DATE(sale_date) BETWEEN ? AND ?"
            params = [start_date, end_date]

        cursor.execute(
            f"""
            SELECT
                payment_method,
                COUNT(*)                       AS transactions,
                COALESCE(SUM(total_amount), 0) AS revenue,
                COALESCE(AVG(total_amount), 0) AS avg_transaction_value
            FROM sales
            {where}
            GROUP BY payment_method
            ORDER BY revenue DESC
        """,
            params,
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Calculate percentage
        total_revenue = sum(row["revenue"] for row in rows)
        for row in rows:
            row["percentage"] = (
                (row["revenue"] / total_revenue * 100) if total_revenue > 0 else 0
            )

        return rows
    except Exception as e:
        logger.error(f"Error getting payment method breakdown: {e}")
        return []


def get_cashier_performance(start_date: str = None, end_date: str = None) -> List[Dict]:
    """
    Returns sales totals per cashier for a date range.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        where = ""
        params = []
        if start_date and end_date:
            where = "AND DATE(s.sale_date) BETWEEN ? AND ?"
            params = [start_date, end_date]

        cursor.execute(
            f"""
            SELECT
                u.user_id,
                u.full_name                    AS cashier,
                u.role,
                COUNT(DISTINCT s.sale_id)      AS transactions,
                COALESCE(SUM(s.total_amount), 0) AS revenue,
                COALESCE(AVG(s.total_amount), 0) AS avg_sale_value,
                COALESCE(SUM(s.discount), 0)   AS total_discounts,
                COALESCE(COUNT(DISTINCT s.customer_id), 0) AS unique_customers
            FROM sales s
            JOIN users u ON s.user_id = u.user_id
            WHERE 1=1 {where}
            GROUP BY s.user_id
            ORDER BY revenue DESC
        """,
            params,
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Add performance metrics
        for row in rows:
            if row["transactions"] > 0:
                row["avg_items_per_sale"] = "N/A"  # Would need additional query
            else:
                row["avg_items_per_sale"] = 0

        return rows
    except Exception as e:
        logger.error(f"Error getting cashier performance: {e}")
        return []


def get_inventory_report() -> List[Dict]:
    """
    Returns current stock levels for all active products.
    Flags items that are low stock or out of stock.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                p.product_id,
                p.product_name,
                p.category,
                p.price,
                COALESCE(i.quantity, 0)      AS stock,
                COALESCE(i.low_stock_alert, 5) AS low_stock_alert,
                CASE
                    WHEN COALESCE(i.quantity, 0) = 0            THEN 'Out of stock'
                    WHEN COALESCE(i.quantity, 0) <= COALESCE(i.low_stock_alert, 5) THEN 'Low stock'
                    ELSE 'OK'
                END             AS status,
                i.last_updated,
                (SELECT COUNT(*) FROM sale_items si WHERE si.product_id = p.product_id) AS times_sold
            FROM products p
            LEFT JOIN inventory i ON p.product_id = i.product_id
            WHERE p.is_active = 1
            ORDER BY
                CASE
                    WHEN COALESCE(i.quantity, 0) = 0 THEN 0
                    WHEN COALESCE(i.quantity, 0) <= COALESCE(i.low_stock_alert, 5) THEN 1
                    ELSE 2
                END,
                i.quantity ASC
        """
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Add summary statistics
        if rows:
            summary = {
                "total_products": len(rows),
                "out_of_stock": sum(1 for r in rows if r["status"] == "Out of stock"),
                "low_stock": sum(1 for r in rows if r["status"] == "Low stock"),
                "healthy_stock": sum(1 for r in rows if r["status"] == "OK"),
                "total_inventory_value": sum(r["price"] * r["stock"] for r in rows),
            }
            rows.insert(0, {"_summary": summary})

        return rows
    except Exception as e:
        logger.error(f"Error getting inventory report: {e}")
        return []


def get_recent_transactions(limit: int = 50) -> List[Dict]:
    """Returns the most recent sales with cashier name and item count."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                s.sale_id,
                s.sale_date,
                s.total_amount,
                s.payment_method,
                s.discount,
                s.tax,
                u.full_name AS cashier,
                c.full_name AS customer_name,
                COUNT(si.sale_item_id) AS item_count,
                (SELECT SUM(quantity) FROM sale_items WHERE sale_id = s.sale_id) AS total_items
            FROM sales s
            JOIN users u ON s.user_id = u.user_id
            LEFT JOIN customers c ON s.customer_id = c.customer_id
            LEFT JOIN sale_items si ON s.sale_id = si.sale_id
            GROUP BY s.sale_id
            ORDER BY s.sale_date DESC
            LIMIT ?
        """,
            (limit,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Error getting recent transactions: {e}")
        return []


def get_profit_analysis(start_date: str = None, end_date: str = None) -> Dict:
    """
    Returns profit analysis including COGS (Cost of Goods Sold) estimation.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        where = ""
        params = []
        if start_date and end_date:
            where = "WHERE DATE(s.sale_date) BETWEEN ? AND ?"
            params = [start_date, end_date]

        cursor.execute(
            f"""
            SELECT
                COUNT(DISTINCT s.sale_id) AS total_transactions,
                SUM(s.total_amount) AS total_revenue,
                SUM(s.discount) AS total_discounts,
                SUM(s.tax) AS total_tax,
                SUM(si.quantity * p.price) AS estimated_cogs,
                SUM(s.total_amount) - SUM(si.quantity * p.price) AS estimated_gross_profit,
                (SUM(s.total_amount) - SUM(si.quantity * p.price)) / NULLIF(SUM(s.total_amount), 0) * 100 AS profit_margin_percentage
            FROM sales s
            JOIN sale_items si ON s.sale_id = si.sale_id
            JOIN products p ON si.product_id = p.product_id
            {where}
        """,
            params,
        )

        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else {}
    except Exception as e:
        logger.error(f"Error getting profit analysis: {e}")
        return {}


def get_hourly_sales_pattern(date: str = None) -> List[Dict]:
    """
    Returns sales distribution by hour of day.
    Useful for staffing decisions.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        date_filter = date or "date('now')"
        param = (date,) if date else ()

        query = f"""
            SELECT
                CAST(strftime('%H', sale_date) AS INTEGER) AS hour,
                COUNT(*) AS transactions,
                SUM(total_amount) AS revenue,
                AVG(total_amount) AS avg_transaction_value
            FROM sales
            WHERE DATE(sale_date) = {'?' if date else date_filter}
            GROUP BY hour
            ORDER BY hour
        """
        cursor.execute(query, param)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Error getting hourly sales pattern: {e}")
        return []


def get_customer_loyalty_report() -> List[Dict]:
    """
    Returns top customers by purchase frequency and value.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                c.customer_id,
                c.full_name,
                c.phone,
                c.email,
                c.loyalty_points,
                COUNT(s.sale_id) AS total_purchases,
                SUM(s.total_amount) AS total_spent,
                AVG(s.total_amount) AS avg_purchase_value,
                MAX(s.sale_date) AS last_purchase_date,
                julianday('now') - julianday(MAX(s.sale_date)) AS days_since_last_purchase
            FROM customers c
            LEFT JOIN sales s ON c.customer_id = s.customer_id
            WHERE c.loyalty_points > 0 OR s.sale_id IS NOT NULL
            GROUP BY c.customer_id
            ORDER BY total_spent DESC
        """
        )

        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Add customer tier based on loyalty points
        for row in rows:
            if row["loyalty_points"] >= 1000:
                row["tier"] = "Platinum"
            elif row["loyalty_points"] >= 500:
                row["tier"] = "Gold"
            elif row["loyalty_points"] >= 100:
                row["tier"] = "Silver"
            else:
                row["tier"] = "Bronze"

        return rows
    except Exception as e:
        logger.error(f"Error getting customer loyalty report: {e}")
        return []


def export_report_to_csv(data: List[Dict], filename: str) -> bool:
    """
    Export report data to CSV file.
    """
    import csv

    try:
        if not data:
            return False

        with open(filename, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = data[0].keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        logger.info(f"Report exported to {filename}")
        return True
    except Exception as e:
        logger.error(f"Error exporting report: {e}")
        return False


# ── Quick test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Test reports
    print("Daily Summary:")
    summary = get_daily_summary()
    print(f"  {summary}")

    print("\nTop Products:")
    top = get_top_products(5)
    for product in top:
        print(
            f"  {product['product_name']}: {product['units_sold']} units - ${product['revenue']:.2f}"
        )

    print("\nInventory Report:")
    inventory = get_inventory_report()
    if inventory and "_summary" in inventory[0]:
        summary_data = inventory[0]["_summary"]
        print(f"  Total Products: {summary_data['total_products']}")
        print(f"  Out of Stock: {summary_data['out_of_stock']}")
        print(f"  Low Stock: {summary_data['low_stock']}")
        print(f"  Inventory Value: ${summary_data['total_inventory_value']:.2f}")