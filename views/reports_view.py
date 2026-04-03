import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, timedelta
from modules.reports import (
    get_daily_summary,
    get_top_products,
    get_payment_method_breakdown,
    get_cashier_performance,
    get_inventory_report,
    get_recent_transactions,
    get_sales_by_date_range,
    get_profit_analysis,
    get_hourly_sales_pattern,
    get_customer_loyalty_report,
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ReportsView(tk.Toplevel):
    """
    Reports & Analytics dashboard.
    Tabs: Overview | Weekly | Top Products | Inventory |
          Transactions | Cashier Performance | Profit | Customers
    """

    def __init__(
        self, parent, current_user: dict, product_manager=None, sales_processor=None
    ):
        super().__init__(parent)
        self.current_user = current_user
        self.product_manager = product_manager
        self.sales_processor = sales_processor

        self.title("Reports & Analytics")
        self.geometry("1200x720")
        self.resizable(True, True)
        self.minsize(1000, 600)
        self.configure(bg="#f0f2f5")
        self._center_window()
        self._build_ui()

    def _center_window(self):
        self.update_idletasks()
        w, h = 1200, 720
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── UI Construction ────────────────────────────────────────────────────

    def _build_ui(self):
        topbar = tk.Frame(self, bg="#1a1a2e", pady=10)
        topbar.pack(fill="x")
        tk.Label(
            topbar,
            text="  📊  Reports & Analytics",
            font=("Segoe UI", 14, "bold"),
            bg="#1a1a2e",
            fg="white",
        ).pack(side="left", padx=10)

        date_presets = tk.Frame(topbar, bg="#1a1a2e")
        date_presets.pack(side="left", padx=20)
        for label, days in [("Today", 0), ("Week", 7), ("Month", 30), ("Quarter", 90)]:
            tk.Button(
                date_presets,
                text=label,
                font=("Segoe UI", 8),
                bg="#0f3460",
                fg="white",
                relief="flat",
                cursor="hand2",
                command=lambda d=days: self._set_date_preset(d),
            ).pack(side="left", padx=2)

        date_row = tk.Frame(topbar, bg="#1a1a2e")
        date_row.pack(side="right", padx=16)

        tk.Label(
            date_row, text="From:", font=("Segoe UI", 9), bg="#1a1a2e", fg="#8892b0"
        ).pack(side="left")
        self.start_var = tk.StringVar(
            value=(date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
        )
        tk.Entry(
            date_row,
            textvariable=self.start_var,
            width=11,
            font=("Segoe UI", 9),
            relief="flat",
        ).pack(side="left", padx=(2, 8))

        tk.Label(
            date_row, text="To:", font=("Segoe UI", 9), bg="#1a1a2e", fg="#8892b0"
        ).pack(side="left")
        self.end_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        tk.Entry(
            date_row,
            textvariable=self.end_var,
            width=11,
            font=("Segoe UI", 9),
            relief="flat",
        ).pack(side="left", padx=(2, 8))

        tk.Button(
            date_row,
            text="Apply",
            font=("Segoe UI", 9),
            bg="#e94560",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._refresh_all,
        ).pack(side="left")

        tk.Button(
            date_row,
            text="Export",
            font=("Segoe UI", 9),
            bg="#27ae60",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._export_current_report,
        ).pack(side="left", padx=5)

        style = ttk.Style()
        style.configure("TNotebook.Tab", font=("Segoe UI", 10), padding=[12, 6])

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=10)

        self._build_overview_tab()
        self._build_weekly_tab()  # ← NEW
        self._build_top_products_tab()
        self._build_inventory_tab()
        self._build_transactions_tab()
        self._build_cashier_tab()
        self._build_profit_tab()
        self._build_customers_tab()

        self._build_status_bar()
        self._refresh_all()

    def _build_status_bar(self):
        status_bar = tk.Frame(self, bg="#1a1a2e", height=25)
        status_bar.pack(fill="x", side="bottom")
        self.status_label = tk.Label(
            status_bar, text="Ready", font=("Segoe UI", 8), bg="#1a1a2e", fg="#8892b0"
        )
        self.status_label.pack(side="left", padx=5, pady=2)
        self.export_label = tk.Label(
            status_bar, text="", font=("Segoe UI", 8), bg="#1a1a2e", fg="#27ae60"
        )
        self.export_label.pack(side="right", padx=5, pady=2)

    def _set_date_preset(self, days):
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        self.start_var.set(start_date.strftime("%Y-%m-%d"))
        self.end_var.set(end_date.strftime("%Y-%m-%d"))
        self._refresh_all()

    # ── Tab 1: Overview ────────────────────────────────────────────────────

    def _build_overview_tab(self):
        tab = tk.Frame(self.notebook, bg="#f0f2f5")
        self.notebook.add(tab, text="📈  Overview")

        self.kpi_frame = tk.Frame(tab, bg="#f0f2f5")
        self.kpi_frame.pack(fill="x", padx=16, pady=16)

        self.kpi_vars = {}
        for label, key, color in [
            ("Today's Revenue", "revenue", "#27ae60"),
            ("Transactions Today", "transactions", "#2980b9"),
            ("Avg Sale Value", "avg", "#8e44ad"),
            ("Total Discounts", "discounts", "#e67e22"),
        ]:
            card = tk.Frame(
                self.kpi_frame, bg="white", padx=20, pady=16, relief="flat", bd=1
            )
            card.pack(side="left", fill="both", expand=True, padx=6)
            var = tk.StringVar(value="—")
            self.kpi_vars[key] = var
            tk.Label(
                card, text=label, font=("Segoe UI", 9), bg="white", fg="#888"
            ).pack(anchor="w")
            tk.Label(
                card,
                textvariable=var,
                font=("Segoe UI", 18, "bold"),
                bg="white",
                fg=color,
            ).pack(anchor="w")

        breakdown_frame = tk.Frame(tab, bg="white", padx=16, pady=12)
        breakdown_frame.pack(fill="x", padx=16, pady=(0, 10))
        tk.Label(
            breakdown_frame,
            text="Payment Method Breakdown",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#1a1a2e",
        ).pack(anchor="w", pady=(0, 8))

        cols = ("Method", "Transactions", "Revenue (GHS)", "Percentage")
        self.breakdown_tree = ttk.Treeview(
            breakdown_frame, columns=cols, show="headings"
        )
        for col in cols:
            self.breakdown_tree.heading(col, text=col)
            self.breakdown_tree.column(col, width=150, anchor="center")
        self.breakdown_tree.pack(fill="x")

        range_frame = tk.Frame(tab, bg="white", padx=16, pady=12)
        range_frame.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        range_header = tk.Frame(range_frame, bg="white")
        range_header.pack(fill="x", pady=(0, 8))
        tk.Label(
            range_header,
            text="Daily Revenue (Date Range)",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#1a1a2e",
        ).pack(side="left")
        tk.Button(
            range_header,
            text="Export Daily Data",
            font=("Segoe UI", 8),
            relief="flat",
            bg="#0f3460",
            fg="white",
            cursor="hand2",
            command=self._export_daily_data,
        ).pack(side="right")

        range_cols = ("Date", "Transactions", "Revenue (GHS)", "Discounts", "Tax")
        self.range_tree = ttk.Treeview(range_frame, columns=range_cols, show="headings")
        for col in range_cols:
            self.range_tree.heading(col, text=col)
            self.range_tree.column(col, width=150, anchor="center")

        range_sb = ttk.Scrollbar(
            range_frame, orient="vertical", command=self.range_tree.yview
        )
        self.range_tree.configure(yscrollcommand=range_sb.set)
        self.range_tree.pack(side="left", fill="both", expand=True)
        range_sb.pack(side="left", fill="y")

        hourly_frame = tk.Frame(tab, bg="white", padx=16, pady=12)
        hourly_frame.pack(fill="x", padx=16, pady=(0, 10))
        tk.Label(
            hourly_frame,
            text="Hourly Sales Pattern (Today)",
            font=("Segoe UI", 10, "bold"),
            bg="white",
            fg="#1a1a2e",
        ).pack(anchor="w", pady=(0, 8))
        self.hourly_tree = ttk.Treeview(
            hourly_frame,
            columns=("Hour", "Transactions", "Revenue"),
            show="headings",
        )
        for col, w in [("Hour", 80), ("Transactions", 100), ("Revenue", 120)]:
            self.hourly_tree.heading(col, text=col)
            self.hourly_tree.column(col, width=w, anchor="center")
        self.hourly_tree.pack(fill="x")

    # ── Tab 2: Weekly Report (NEW) ─────────────────────────────────────────

    def _build_weekly_tab(self):
        tab = tk.Frame(self.notebook, bg="#f0f2f5")
        self.notebook.add(tab, text="📅  Weekly")

        # Week selector row
        week_row = tk.Frame(tab, bg="#f0f2f5", pady=10)
        week_row.pack(fill="x", padx=16)

        tk.Label(
            week_row, text="Week starting:", font=("Segoe UI", 10, "bold"), bg="#f0f2f5"
        ).pack(side="left")

        # Default to start of current week (Monday)
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        self.week_start_var = tk.StringVar(value=monday.strftime("%Y-%m-%d"))
        tk.Entry(
            week_row,
            textvariable=self.week_start_var,
            font=("Segoe UI", 10),
            relief="flat",
            bd=3,
            width=12,
        ).pack(side="left", padx=(6, 8), ipady=4)

        tk.Button(
            week_row,
            text="◀ Prev Week",
            font=("Segoe UI", 9),
            relief="flat",
            bg="#0f3460",
            fg="white",
            cursor="hand2",
            command=self._prev_week,
        ).pack(side="left", padx=2)

        tk.Button(
            week_row,
            text="This Week",
            font=("Segoe UI", 9),
            relief="flat",
            bg="#0f3460",
            fg="white",
            cursor="hand2",
            command=self._this_week,
        ).pack(side="left", padx=2)

        tk.Button(
            week_row,
            text="Next Week ▶",
            font=("Segoe UI", 9),
            relief="flat",
            bg="#0f3460",
            fg="white",
            cursor="hand2",
            command=self._next_week,
        ).pack(side="left", padx=2)

        tk.Button(
            week_row,
            text="Load",
            font=("Segoe UI", 9),
            relief="flat",
            bg="#e94560",
            fg="white",
            cursor="hand2",
            command=self._load_weekly,
        ).pack(side="left", padx=(12, 0))

        # Weekly KPI cards
        self.week_kpi_frame = tk.Frame(tab, bg="#f0f2f5")
        self.week_kpi_frame.pack(fill="x", padx=16, pady=(0, 10))

        self.week_kpi_vars = {}
        for label, key, color in [
            ("Week Revenue", "revenue", "#27ae60"),
            ("Transactions", "transactions", "#2980b9"),
            ("Avg Daily Revenue", "avg_daily", "#8e44ad"),
            ("Total Discounts", "discounts", "#e67e22"),
            ("Best Day", "best_day", "#e94560"),
        ]:
            card = tk.Frame(
                self.week_kpi_frame, bg="white", padx=14, pady=14, relief="flat", bd=1
            )
            card.pack(side="left", fill="both", expand=True, padx=4)
            var = tk.StringVar(value="—")
            self.week_kpi_vars[key] = var
            tk.Label(
                card, text=label, font=("Segoe UI", 9), bg="white", fg="#888"
            ).pack(anchor="w")
            tk.Label(
                card,
                textvariable=var,
                font=("Segoe UI", 14, "bold"),
                bg="white",
                fg=color,
            ).pack(anchor="w")

        # Day-by-day table
        day_frame = tk.Frame(tab, bg="white", padx=16, pady=12)
        day_frame.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        day_header = tk.Frame(day_frame, bg="white")
        day_header.pack(fill="x", pady=(0, 8))
        self.week_title_var = tk.StringVar(value="Day-by-Day Breakdown")
        tk.Label(
            day_header,
            textvariable=self.week_title_var,
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#1a1a2e",
        ).pack(side="left")
        tk.Button(
            day_header,
            text="Export Week",
            font=("Segoe UI", 8),
            relief="flat",
            bg="#27ae60",
            fg="white",
            cursor="hand2",
            command=self._export_week,
        ).pack(side="right")

        day_cols = (
            "Day",
            "Date",
            "Transactions",
            "Revenue (GHS)",
            "Discounts (GHS)",
            "Tax (GHS)",
        )
        self.week_tree = ttk.Treeview(day_frame, columns=day_cols, show="headings")
        col_w = {
            "Day": 100,
            "Date": 110,
            "Transactions": 110,
            "Revenue (GHS)": 130,
            "Discounts (GHS)": 130,
            "Tax (GHS)": 100,
        }
        for col in day_cols:
            self.week_tree.heading(col, text=col)
            self.week_tree.column(col, width=col_w[col], anchor="center")
        self.week_tree.column("Day", anchor="w")

        # Highlight best day in green, zero-sale days in grey
        self.week_tree.tag_configure("best", background="#f0fdf4", foreground="#166534")
        self.week_tree.tag_configure("zero", background="#f5f5f5", foreground="#95a5a6")
        self.week_tree.tag_configure("normal", background="white")

        week_sb = ttk.Scrollbar(
            day_frame, orient="vertical", command=self.week_tree.yview
        )
        self.week_tree.configure(yscrollcommand=week_sb.set)
        self.week_tree.pack(side="left", fill="both", expand=True)
        week_sb.pack(side="left", fill="y")

        # Week totals row
        totals_row = tk.Frame(tab, bg="white", padx=16, pady=8)
        totals_row.pack(fill="x", padx=16, pady=(0, 10))
        self.week_totals_var = tk.StringVar(value="")
        tk.Label(
            totals_row,
            textvariable=self.week_totals_var,
            font=("Segoe UI", 10, "bold"),
            bg="white",
            fg="#1a1a2e",
        ).pack(anchor="w")

    def _get_week_dates(self):
        """Return (monday, sunday) date objects for the selected week."""
        try:
            monday = date.fromisoformat(self.week_start_var.get().strip())
        except ValueError:
            monday = date.today() - timedelta(days=date.today().weekday())
        sunday = monday + timedelta(days=6)
        return monday, sunday

    def _prev_week(self):
        monday, _ = self._get_week_dates()
        self.week_start_var.set((monday - timedelta(weeks=1)).strftime("%Y-%m-%d"))
        self._load_weekly()

    def _next_week(self):
        monday, _ = self._get_week_dates()
        self.week_start_var.set((monday + timedelta(weeks=1)).strftime("%Y-%m-%d"))
        self._load_weekly()

    def _this_week(self):
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        self.week_start_var.set(monday.strftime("%Y-%m-%d"))
        self._load_weekly()

    def _load_weekly(self):
        monday, sunday = self._get_week_dates()
        start_str = monday.strftime("%Y-%m-%d")
        end_str = sunday.strftime("%Y-%m-%d")

        self.week_title_var.set(
            f"Week of {monday.strftime('%d %b %Y')} — {sunday.strftime('%d %b %Y')}"
        )

        # Fetch data for the full week
        daily_data = get_sales_by_date_range(start_str, end_str)

        # Build a dict keyed by date string for quick lookup
        data_by_date = {row["sale_date"]: row for row in daily_data}

        DAY_NAMES = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        self.week_tree.delete(*self.week_tree.get_children())

        week_revenue = 0.0
        week_transactions = 0
        week_discounts = 0.0
        week_tax = 0.0
        best_revenue = -1.0
        best_day_name = "—"

        rows_data = []
        for i, day_name in enumerate(DAY_NAMES):
            day_date = monday + timedelta(days=i)
            day_date_str = day_date.strftime("%Y-%m-%d")
            row = data_by_date.get(day_date_str, {})

            revenue = float(row.get("total_revenue", 0) or 0)
            transactions = int(row.get("total_transactions", 0) or 0)
            discounts = float(row.get("total_discounts", 0) or 0)
            tax = float(row.get("total_tax", 0) or 0)

            week_revenue += revenue
            week_transactions += transactions
            week_discounts += discounts
            week_tax += tax

            if revenue > best_revenue:
                best_revenue = revenue
                best_day_name = day_name

            rows_data.append(
                (day_name, day_date_str, transactions, revenue, discounts, tax)
            )

        # Insert rows with tags
        for day_name, day_date_str, transactions, revenue, discounts, tax in rows_data:
            if revenue == best_revenue and best_revenue > 0:
                tag = "best"
            elif transactions == 0:
                tag = "zero"
            else:
                tag = "normal"

            self.week_tree.insert(
                "",
                "end",
                tags=(tag,),
                values=(
                    day_name,
                    day_date_str,
                    transactions,
                    f"{revenue:.2f}",
                    f"{discounts:.2f}",
                    f"{tax:.2f}",
                ),
            )

        # Update KPI cards
        avg_daily = week_revenue / 7
        self.week_kpi_vars["revenue"].set(f"GHS {week_revenue:,.2f}")
        self.week_kpi_vars["transactions"].set(str(week_transactions))
        self.week_kpi_vars["avg_daily"].set(f"GHS {avg_daily:,.2f}")
        self.week_kpi_vars["discounts"].set(f"GHS {week_discounts:,.2f}")
        self.week_kpi_vars["best_day"].set(best_day_name)

        # Totals summary
        self.week_totals_var.set(
            f"Week Total:  GHS {week_revenue:,.2f}  |  "
            f"{week_transactions} transactions  |  "
            f"Discounts: GHS {week_discounts:,.2f}  |  "
            f"Tax: GHS {week_tax:,.2f}"
        )

    def _export_week(self):
        monday, sunday = self._get_week_dates()
        data = [
            self.week_tree.item(item)["values"]
            for item in self.week_tree.get_children()
        ]
        if not data:
            messagebox.showinfo("Export", "No data to export.")
            return

        filename = (
            f"weekly_report_{monday.strftime('%Y%m%d')}_"
            f"{sunday.strftime('%Y%m%d')}.csv"
        )
        headers = [
            "Day",
            "Date",
            "Transactions",
            "Revenue (GHS)",
            "Discounts (GHS)",
            "Tax (GHS)",
        ]
        try:
            import csv

            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(data)
            self.export_label.config(text=f"Exported to {filename}")
            self.after(3000, lambda: self.export_label.config(text=""))
            messagebox.showinfo(
                "Export Complete", f"Weekly report exported to {filename}"
            )
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {str(e)}")

    # ── Tab 3: Top Products ────────────────────────────────────────────────

    def _build_top_products_tab(self):
        tab = tk.Frame(self.notebook, bg="#f0f2f5")
        self.notebook.add(tab, text="🏆  Top Products")

        tk.Label(
            tab,
            text="Best-selling products (by units sold)",
            font=("Segoe UI", 10),
            bg="#f0f2f5",
            fg="#555",
        ).pack(anchor="w", padx=16, pady=(12, 6))

        cols = (
            "Rank",
            "Product",
            "Category",
            "Units Sold",
            "Revenue (GHS)",
            "Contribution %",
        )
        self.products_tree = ttk.Treeview(tab, columns=cols, show="headings")
        col_w = {
            "Rank": 50,
            "Product": 280,
            "Category": 140,
            "Units Sold": 100,
            "Revenue (GHS)": 120,
            "Contribution %": 100,
        }
        for col in cols:
            self.products_tree.heading(col, text=col)
            self.products_tree.column(col, width=col_w[col], anchor="center")
        self.products_tree.column("Product", anchor="w")

        sb = ttk.Scrollbar(tab, orient="vertical", command=self.products_tree.yview)
        self.products_tree.configure(yscrollcommand=sb.set)
        self.products_tree.pack(
            side="left", fill="both", expand=True, padx=(16, 0), pady=(0, 16)
        )
        sb.pack(side="left", fill="y", pady=(0, 16))

    # ── Tab 4: Inventory ───────────────────────────────────────────────────

    def _build_inventory_tab(self):
        tab = tk.Frame(self.notebook, bg="#f0f2f5")
        self.notebook.add(tab, text="📦  Inventory")

        self.inv_summary_frame = tk.Frame(tab, bg="#f0f2f5")
        self.inv_summary_frame.pack(fill="x", padx=16, pady=12)

        self.inv_vars = {}
        for label, key, color in [
            ("Total Products", "total", "#2980b9"),
            ("OK", "ok", "#27ae60"),
            ("Low Stock", "low", "#e67e22"),
            ("Out of Stock", "out", "#e74c3c"),
            ("Total Value", "value", "#8e44ad"),
        ]:
            card = tk.Frame(
                self.inv_summary_frame,
                bg="white",
                padx=16,
                pady=12,
                relief="flat",
                bd=1,
            )
            card.pack(side="left", fill="both", expand=True, padx=6)
            var = tk.StringVar(value="0")
            self.inv_vars[key] = var
            tk.Label(
                card, text=label, font=("Segoe UI", 9), bg="white", fg="#888"
            ).pack(anchor="w")
            tk.Label(
                card,
                textvariable=var,
                font=("Segoe UI", 14, "bold"),
                bg="white",
                fg=color,
            ).pack(anchor="w")

        cols = (
            "Product",
            "Category",
            "Price",
            "Stock",
            "Alert Level",
            "Status",
            "Last Updated",
        )
        self.inv_tree = ttk.Treeview(tab, columns=cols, show="headings")
        col_w = {
            "Product": 200,
            "Category": 110,
            "Price": 80,
            "Stock": 60,
            "Alert Level": 80,
            "Status": 100,
            "Last Updated": 140,
        }
        for col in cols:
            self.inv_tree.heading(col, text=col)
            self.inv_tree.column(col, width=col_w[col], anchor="center")
        self.inv_tree.column("Product", anchor="w")
        self.inv_tree.tag_configure("out", background="#fdecea", foreground="#c0392b")
        self.inv_tree.tag_configure("low", background="#fef9e7", foreground="#d35400")
        self.inv_tree.tag_configure("ok", background="white")

        sb = ttk.Scrollbar(tab, orient="vertical", command=self.inv_tree.yview)
        self.inv_tree.configure(yscrollcommand=sb.set)
        self.inv_tree.pack(
            side="left", fill="both", expand=True, padx=(16, 0), pady=(0, 16)
        )
        sb.pack(side="left", fill="y", pady=(0, 16))

    # ── Tab 5: Recent Transactions ─────────────────────────────────────────

    def _build_transactions_tab(self):
        tab = tk.Frame(self.notebook, bg="#f0f2f5")
        self.notebook.add(tab, text="🧾  Transactions")

        tk.Label(
            tab,
            text="50 most recent sales",
            font=("Segoe UI", 10),
            bg="#f0f2f5",
            fg="#555",
        ).pack(anchor="w", padx=16, pady=(12, 6))

        cols = (
            "Sale #",
            "Date & Time",
            "Cashier",
            "Customer",
            "Payment",
            "Items",
            "Discount",
            "Total (GHS)",
        )
        self.tx_tree = ttk.Treeview(tab, columns=cols, show="headings")
        col_w = {
            "Sale #": 60,
            "Date & Time": 150,
            "Cashier": 140,
            "Customer": 120,
            "Payment": 80,
            "Items": 60,
            "Discount": 80,
            "Total (GHS)": 100,
        }
        for col in cols:
            self.tx_tree.heading(col, text=col)
            self.tx_tree.column(col, width=col_w[col], anchor="center")
        self.tx_tree.column("Date & Time", anchor="w")
        self.tx_tree.column("Cashier", anchor="w")
        self.tx_tree.column("Customer", anchor="w")

        sb = ttk.Scrollbar(tab, orient="vertical", command=self.tx_tree.yview)
        self.tx_tree.configure(yscrollcommand=sb.set)
        self.tx_tree.pack(
            side="left", fill="both", expand=True, padx=(16, 0), pady=(0, 16)
        )
        sb.pack(side="left", fill="y", pady=(0, 16))
        self.tx_tree.bind("<Double-1>", self._view_transaction_details)

    # ── Tab 6: Cashier Performance ─────────────────────────────────────────

    def _build_cashier_tab(self):
        tab = tk.Frame(self.notebook, bg="#f0f2f5")
        self.notebook.add(tab, text="👤  Cashier Performance")

        tk.Label(
            tab,
            text="Sales performance per cashier (selected date range)",
            font=("Segoe UI", 10),
            bg="#f0f2f5",
            fg="#555",
        ).pack(anchor="w", padx=16, pady=(12, 6))

        cols = (
            "Rank",
            "Cashier",
            "Role",
            "Transactions",
            "Revenue (GHS)",
            "Avg Sale",
            "Unique Customers",
        )
        self.cashier_tree = ttk.Treeview(tab, columns=cols, show="headings")
        col_w = {
            "Rank": 60,
            "Cashier": 200,
            "Role": 100,
            "Transactions": 120,
            "Revenue (GHS)": 140,
            "Avg Sale": 120,
            "Unique Customers": 120,
        }
        for col in cols:
            self.cashier_tree.heading(col, text=col)
            self.cashier_tree.column(col, width=col_w[col], anchor="center")
        self.cashier_tree.column("Cashier", anchor="w")

        sb = ttk.Scrollbar(tab, orient="vertical", command=self.cashier_tree.yview)
        self.cashier_tree.configure(yscrollcommand=sb.set)
        self.cashier_tree.pack(
            side="left", fill="both", expand=True, padx=(16, 0), pady=(0, 16)
        )
        sb.pack(side="left", fill="y", pady=(0, 16))

    # ── Tab 7: Profit Analysis ─────────────────────────────────────────────

    def _build_profit_tab(self):
        tab = tk.Frame(self.notebook, bg="#f0f2f5")
        self.notebook.add(tab, text="💰  Profit Analysis")

        profit_frame = tk.Frame(tab, bg="#f0f2f5")
        profit_frame.pack(fill="x", padx=16, pady=16)

        self.profit_vars = {}
        for label, key, color in [
            ("Total Revenue", "revenue", "#27ae60"),
            ("Total Discounts", "discounts", "#e67e22"),
            ("Total Tax", "tax", "#2980b9"),
            ("Est. COGS", "cogs", "#8e44ad"),
            ("Gross Profit", "profit", "#e94560"),
            ("Profit Margin", "margin", "#f39c12"),
        ]:
            card = tk.Frame(
                profit_frame, bg="white", padx=15, pady=12, relief="flat", bd=1
            )
            card.pack(side="left", fill="both", expand=True, padx=4)
            var = tk.StringVar(value="—")
            self.profit_vars[key] = var
            tk.Label(
                card, text=label, font=("Segoe UI", 9), bg="white", fg="#888"
            ).pack(anchor="w")
            tk.Label(
                card,
                textvariable=var,
                font=("Segoe UI", 13, "bold"),
                bg="white",
                fg=color,
            ).pack(anchor="w")

        detail_frame = tk.Frame(tab, bg="white", padx=16, pady=12)
        detail_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        tk.Label(
            detail_frame,
            text="Daily Profit Breakdown",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#1a1a2e",
        ).pack(anchor="w", pady=(0, 8))

        profit_cols = (
            "Date",
            "Transactions",
            "Revenue",
            "Est. COGS",
            "Profit",
            "Margin %",
        )
        self.profit_tree = ttk.Treeview(
            detail_frame, columns=profit_cols, show="headings"
        )
        for col in profit_cols:
            self.profit_tree.heading(col, text=col)
            self.profit_tree.column(col, width=120, anchor="center")

        sb = ttk.Scrollbar(
            detail_frame, orient="vertical", command=self.profit_tree.yview
        )
        self.profit_tree.configure(yscrollcommand=sb.set)
        self.profit_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

    # ── Tab 8: Customer Loyalty ────────────────────────────────────────────

    def _build_customers_tab(self):
        tab = tk.Frame(self.notebook, bg="#f0f2f5")
        self.notebook.add(tab, text="👥  Customers")

        cust_frame = tk.Frame(tab, bg="#f0f2f5")
        cust_frame.pack(fill="x", padx=16, pady=12)

        self.cust_vars = {}
        for label, key, color in [
            ("Total Customers", "total", "#2980b9"),
            ("Platinum", "platinum", "#e94560"),
            ("Gold", "gold", "#f39c12"),
            ("Silver", "silver", "#95a5a6"),
            ("Bronze", "bronze", "#cd6139"),
        ]:
            card = tk.Frame(
                cust_frame, bg="white", padx=15, pady=12, relief="flat", bd=1
            )
            card.pack(side="left", fill="both", expand=True, padx=4)
            var = tk.StringVar(value="0")
            self.cust_vars[key] = var
            tk.Label(
                card, text=label, font=("Segoe UI", 9), bg="white", fg="#888"
            ).pack(anchor="w")
            tk.Label(
                card,
                textvariable=var,
                font=("Segoe UI", 13, "bold"),
                bg="white",
                fg=color,
            ).pack(anchor="w")

        top_cust_frame = tk.Frame(tab, bg="white", padx=16, pady=12)
        top_cust_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        tk.Label(
            top_cust_frame,
            text="Top Customers by Spending",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#1a1a2e",
        ).pack(anchor="w", pady=(0, 8))

        cust_cols = (
            "Rank",
            "Customer",
            "Phone",
            "Tier",
            "Total Spent",
            "Purchases",
            "Loyalty Points",
        )
        self.cust_tree = ttk.Treeview(
            top_cust_frame, columns=cust_cols, show="headings"
        )
        col_w = {
            "Rank": 50,
            "Customer": 200,
            "Phone": 120,
            "Tier": 80,
            "Total Spent": 120,
            "Purchases": 80,
            "Loyalty Points": 100,
        }
        for col in cust_cols:
            self.cust_tree.heading(col, text=col)
            self.cust_tree.column(col, width=col_w[col], anchor="center")
        self.cust_tree.column("Customer", anchor="w")

        sb = ttk.Scrollbar(
            top_cust_frame, orient="vertical", command=self.cust_tree.yview
        )
        self.cust_tree.configure(yscrollcommand=sb.set)
        self.cust_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

    # ── Data loading ───────────────────────────────────────────────────────

    def _refresh_all(self):
        start = self.start_var.get().strip()
        end = self.end_var.get().strip()
        self.status_label.config(text="Loading reports...")
        self.update()
        try:
            self._load_overview(start, end)
            self._load_weekly()
            self._load_top_products(start, end)
            self._load_inventory()
            self._load_transactions()
            self._load_cashier_performance(start, end)
            self._load_profit_analysis(start, end)
            self._load_customer_loyalty()
            self.status_label.config(text=f"Reports updated: {start} to {end}")
        except Exception as e:
            self.status_label.config(text=f"Error: {str(e)}")
            logger.error(f"Error refreshing reports: {e}")

    def _load_overview(self, start, end):
        today = get_daily_summary()
        self.kpi_vars["revenue"].set(f"GHS {today.get('total_revenue', 0):.2f}")
        self.kpi_vars["transactions"].set(str(today.get("total_transactions", 0)))
        self.kpi_vars["avg"].set(f"GHS {today.get('avg_sale_value', 0):.2f}")
        self.kpi_vars["discounts"].set(f"GHS {today.get('total_discounts', 0):.2f}")

        self.breakdown_tree.delete(*self.breakdown_tree.get_children())
        for row in get_payment_method_breakdown(start, end):
            self.breakdown_tree.insert(
                "",
                "end",
                values=(
                    row["payment_method"].upper(),
                    row["transactions"],
                    f"{row['revenue']:.2f}",
                    f"{row.get('percentage', 0):.1f}%",
                ),
            )

        self.range_tree.delete(*self.range_tree.get_children())
        for row in get_sales_by_date_range(start, end):
            self.range_tree.insert(
                "",
                "end",
                values=(
                    row["sale_date"],
                    row["total_transactions"],
                    f"{row['total_revenue']:.2f}",
                    f"{row.get('total_discounts', 0):.2f}",
                    f"{row.get('total_tax', 0):.2f}",
                ),
            )

        self.hourly_tree.delete(*self.hourly_tree.get_children())
        for row in get_hourly_sales_pattern():
            self.hourly_tree.insert(
                "",
                "end",
                values=(
                    f"{row['hour']:02d}:00",
                    row["transactions"],
                    f"{row['revenue']:.2f}",
                ),
            )

    def _load_top_products(self, start, end):
        self.products_tree.delete(*self.products_tree.get_children())
        for i, row in enumerate(get_top_products(20, start, end), 1):
            self.products_tree.insert(
                "",
                "end",
                values=(
                    i,
                    row["product_name"],
                    row["category"],
                    row["units_sold"],
                    f"{row['revenue']:.2f}",
                    f"{row.get('contribution_percentage', 0):.1f}%",
                ),
            )

    def _load_inventory(self):
        self.inv_tree.delete(*self.inv_tree.get_children())
        rows = get_inventory_report()

        if rows and "_summary" in rows[0]:
            rows = rows[1:]

        counts = {"total": len(rows), "ok": 0, "low": 0, "out": 0}
        total_value = 0

        for row in rows:
            status = row["status"]
            if status == "OK":
                tag = "ok"
                counts["ok"] += 1
            elif status == "Low stock":
                tag = "low"
                counts["low"] += 1
            else:
                tag = "out"
                counts["out"] += 1

            total_value += row["price"] * row["stock"]
            self.inv_tree.insert(
                "",
                "end",
                tags=(tag,),
                values=(
                    row["product_name"],
                    row["category"],
                    f"GHS {row['price']:.2f}",
                    row["stock"],
                    row["low_stock_alert"],
                    status,
                    row["last_updated"][:16] if row["last_updated"] else "—",
                ),
            )

        for key, val in counts.items():
            self.inv_vars[key].set(str(val))
        self.inv_vars["value"].set(f"GHS {total_value:,.2f}")

    def _load_transactions(self):
        self.tx_tree.delete(*self.tx_tree.get_children())
        for row in get_recent_transactions(50):
            self.tx_tree.insert(
                "",
                "end",
                values=(
                    row["sale_id"],
                    row["sale_date"][:19],
                    row["cashier"],
                    row.get("customer_name", "Walk-in"),
                    row["payment_method"].upper(),
                    row.get("total_items", 0),
                    f"GHS {row['discount']:.2f}",
                    f"GHS {row['total_amount']:.2f}",
                ),
            )

    def _load_cashier_performance(self, start, end):
        self.cashier_tree.delete(*self.cashier_tree.get_children())
        for i, row in enumerate(get_cashier_performance(start, end), 1):
            self.cashier_tree.insert(
                "",
                "end",
                values=(
                    i,
                    row["cashier"],
                    row.get("role", "cashier").capitalize(),
                    row["transactions"],
                    f"{row['revenue']:.2f}",
                    f"GHS {row.get('avg_sale_value', 0):.2f}",
                    row.get("unique_customers", 0),
                ),
            )

    def _load_profit_analysis(self, start, end):
        profit_data = get_profit_analysis(start, end)
        if profit_data:
            self.profit_vars["revenue"].set(
                f"GHS {profit_data.get('total_revenue', 0):,.2f}"
            )
            self.profit_vars["discounts"].set(
                f"GHS {profit_data.get('total_discounts', 0):,.2f}"
            )
            self.profit_vars["tax"].set(f"GHS {profit_data.get('total_tax', 0):,.2f}")
            self.profit_vars["cogs"].set(
                f"GHS {profit_data.get('estimated_cogs', 0):,.2f}"
            )
            self.profit_vars["profit"].set(
                f"GHS {profit_data.get('estimated_gross_profit', 0):,.2f}"
            )
            self.profit_vars["margin"].set(
                f"{profit_data.get('profit_margin_percentage', 0):.1f}%"
            )

        self.profit_tree.delete(*self.profit_tree.get_children())
        for row in get_sales_by_date_range(start, end):
            revenue = row["total_revenue"]
            cogs = revenue * 0.6
            profit = revenue - cogs
            margin = (profit / revenue * 100) if revenue > 0 else 0
            self.profit_tree.insert(
                "",
                "end",
                values=(
                    row["sale_date"],
                    row["total_transactions"],
                    f"GHS {revenue:.2f}",
                    f"GHS {cogs:.2f}",
                    f"GHS {profit:.2f}",
                    f"{margin:.1f}%",
                ),
            )

    def _load_customer_loyalty(self):
        customers = get_customer_loyalty_report()
        if customers:
            tiers = {"platinum": 0, "gold": 0, "silver": 0, "bronze": 0}
            for cust in customers:
                tier = cust.get("tier", "Bronze").lower()
                tiers[tier] = tiers.get(tier, 0) + 1
            self.cust_vars["total"].set(str(len(customers)))
            for k in tiers:
                self.cust_vars[k].set(str(tiers[k]))

        self.cust_tree.delete(*self.cust_tree.get_children())
        for i, cust in enumerate(customers[:20], 1):
            self.cust_tree.insert(
                "",
                "end",
                values=(
                    i,
                    cust.get("full_name", "Unknown"),
                    cust.get("phone", "—"),
                    cust.get("tier", "Bronze"),
                    f"GHS {cust.get('total_spent', 0):.2f}",
                    cust.get("total_purchases", 0),
                    cust.get("loyalty_points", 0),
                ),
            )

    def _view_transaction_details(self, event):
        selected = self.tx_tree.selection()
        if not selected:
            return
        sale_id = self.tx_tree.item(selected[0])["values"][0]

        from modules.sales import get_sale_details

        sale = get_sale_details(sale_id)
        if not sale:
            return

        win = tk.Toplevel(self)
        win.title(f"Transaction #{sale_id} Details")
        win.geometry("500x500")
        win.configure(bg="white")

        text = tk.Text(win, font=("Courier New", 10), bg="white", padx=10, pady=10)
        text.pack(fill="both", expand=True)

        lines = [
            "=" * 50,
            f"TRANSACTION #{sale_id}",
            "=" * 50,
            f"Date:     {sale['sale_date']}",
            f"Cashier:  {sale['cashier']}",
            f"Customer: {sale.get('customer', 'Walk-in')}",
            "-" * 50,
            "ITEMS:",
        ]
        for item in sale["items"]:
            lines.append(
                f"  {item['quantity']}x {item['product_name']} "
                f"@ GHS {item['unit_price']:.2f} = GHS {item['subtotal']:.2f}"
            )
        lines.extend(
            [
                "-" * 50,
                f"Subtotal: GHS {sale['total_amount'] + sale['discount'] - sale['tax']:.2f}",
                f"Discount: GHS {sale['discount']:.2f}",
                f"Tax:      GHS {sale['tax']:.2f}",
                f"TOTAL:    GHS {sale['total_amount']:.2f}",
                f"Paid:     GHS {sale['amount_paid']:.2f}",
                f"Change:   GHS {sale['change_given']:.2f}",
                f"Payment:  {sale['payment_method'].upper()}",
                "=" * 50,
            ]
        )
        text.insert("1.0", "\n".join(lines))
        text.config(state="disabled")

        tk.Button(
            win,
            text="Close",
            command=win.destroy,
            bg="#e94560",
            fg="white",
            relief="flat",
            pady=5,
        ).pack(pady=10)

    # ── Export helpers ─────────────────────────────────────────────────────

    def _export_current_report(self):
        current_tab = self.notebook.index(self.notebook.select())
        tab_name = self.notebook.tab(current_tab, "text")
        filename = f"report_{date.today().strftime('%Y%m%d_%H%M%S')}.csv"

        tree_map = {
            "Overview": (
                self.range_tree,
                ["Date", "Transactions", "Revenue (GHS)", "Discounts", "Tax"],
            ),
            "Weekly": (
                self.week_tree,
                [
                    "Day",
                    "Date",
                    "Transactions",
                    "Revenue (GHS)",
                    "Discounts (GHS)",
                    "Tax (GHS)",
                ],
            ),
            "Top Products": (
                self.products_tree,
                [
                    "Rank",
                    "Product",
                    "Category",
                    "Units Sold",
                    "Revenue (GHS)",
                    "Contribution %",
                ],
            ),
            "Inventory": (
                self.inv_tree,
                [
                    "Product",
                    "Category",
                    "Price",
                    "Stock",
                    "Alert Level",
                    "Status",
                    "Last Updated",
                ],
            ),
            "Transactions": (
                self.tx_tree,
                [
                    "Sale #",
                    "Date & Time",
                    "Cashier",
                    "Customer",
                    "Payment",
                    "Items",
                    "Discount",
                    "Total (GHS)",
                ],
            ),
        }

        matched = next(
            (
                (tree, headers)
                for key, (tree, headers) in tree_map.items()
                if key in tab_name
            ),
            None,
        )
        if not matched:
            messagebox.showinfo("Export", "Export not available for this tab.")
            return

        tree, headers = matched
        data = [tree.item(item)["values"] for item in tree.get_children()]
        if not data:
            messagebox.showinfo("Export", "No data to export.")
            return

        try:
            import csv

            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(data)
            self.export_label.config(text=f"Exported to {filename}")
            self.after(3000, lambda: self.export_label.config(text=""))
            messagebox.showinfo("Export Complete", f"Report exported to {filename}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {str(e)}")

    def _export_daily_data(self):
        data = [
            self.range_tree.item(item)["values"]
            for item in self.range_tree.get_children()
        ]
        if not data:
            messagebox.showinfo("Export", "No data to export.")
            return

        filename = f"daily_sales_{self.start_var.get()}" f"_to_{self.end_var.get()}.csv"
        headers = ["Date", "Transactions", "Revenue (GHS)", "Discounts", "Tax"]
        try:
            import csv

            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(data)
            self.export_label.config(text=f"Exported to {filename}")
            self.after(3000, lambda: self.export_label.config(text=""))
            messagebox.showinfo("Export Complete", f"Daily data exported to {filename}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {str(e)}")
