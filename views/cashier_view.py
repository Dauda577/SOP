import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from modules.products import (
    search_products,
    get_product_by_barcode,
    get_product_by_id,
    get_low_stock_products,
)
from modules.sales import (
    cart_add_item,
    cart_remove_item,
    cart_update_quantity,
    cart_clear,
    cart_totals,
    process_sale,
    get_cart_item_count,
    generate_receipt,
)
import logging
import os
import tempfile
import webbrowser
from datetime import datetime

logger = logging.getLogger(__name__)


class CashierView(tk.Toplevel):
    TAX_RATE = 0.0

    def __init__(
        self, parent, current_user: dict, product_manager=None, sales_processor=None
    ):
        super().__init__(parent)
        self.parent = parent
        self.current_user = current_user
        self.product_manager = product_manager
        self.sales_processor = sales_processor
        self.cart = []
        self.last_sale_id = None
        self.current_customer_id = None
        self.current_customer_name = None

        # MoMo state — stored so we can resend if customer abandons
        self._last_momo_ref = ""
        self._last_momo_phone = ""
        self._last_momo_provider = ""
        self._last_momo_amount = 0.0
        self._last_momo_sale_id = None
        self._last_momo_checkout_url = ""
        self._last_momo_flow = ""

        self.title(f"POS — Cashier ({current_user['full_name']})")
        self.geometry("1280x700")
        self.resizable(True, True)
        self.minsize(1000, 600)
        self.configure(bg="#f0f2f5")
        self._center_window()
        self._build_ui()
        self._check_low_stock()
        self._update_status_bar()

    def _center_window(self):
        self.update_idletasks()
        w, h = 1280, 700
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        topbar = tk.Frame(self, bg="#1a1a2e", pady=10)
        topbar.pack(fill="x")

        tk.Label(
            topbar,
            text="  🛒  Point of Sale",
            font=("Segoe UI", 14, "bold"),
            bg="#1a1a2e",
            fg="white",
        ).pack(side="left", padx=10)

        quick_actions = tk.Frame(topbar, bg="#1a1a2e")
        quick_actions.pack(side="left", padx=20)

        tk.Button(
            quick_actions,
            text="📱 Scan Barcode",
            font=("Segoe UI", 9),
            bg="#0f3460",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._barcode_dialog,
        ).pack(side="left", padx=2)

        tk.Button(
            quick_actions,
            text="👤 Add Customer",
            font=("Segoe UI", 9),
            bg="#0f3460",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._add_customer_dialog,
        ).pack(side="left", padx=2)

        info_frame = tk.Frame(topbar, bg="#1a1a2e")
        info_frame.pack(side="right", padx=10)

        tk.Label(
            info_frame,
            text=f"Cashier: {self.current_user['full_name']}",
            font=("Segoe UI", 9),
            bg="#1a1a2e",
            fg="#8892b0",
        ).pack(side="right")

        self.time_var = tk.StringVar()
        self._update_time()
        tk.Label(
            info_frame,
            textvariable=self.time_var,
            font=("Segoe UI", 9),
            bg="#1a1a2e",
            fg="#8892b0",
        ).pack(side="left", padx=10)

        body = tk.Frame(self, bg="#f0f2f5")
        body.pack(fill="both", expand=True, padx=12, pady=10)

        self._build_product_panel(body)
        self._build_cart_panel(body)
        self._build_payment_panel(body)
        self._build_status_bar()

    def _build_status_bar(self):
        self.status_bar = tk.Frame(self, bg="#1a1a2e", height=25)
        self.status_bar.pack(fill="x", side="bottom")
        self.status_label = tk.Label(
            self.status_bar,
            text="Ready",
            font=("Segoe UI", 8),
            bg="#1a1a2e",
            fg="#8892b0",
        )
        self.status_label.pack(side="left", padx=5, pady=2)
        self.cart_count_label = tk.Label(
            self.status_bar,
            text="Items: 0",
            font=("Segoe UI", 8),
            bg="#1a1a2e",
            fg="#8892b0",
        )
        self.cart_count_label.pack(side="right", padx=5, pady=2)

    def _update_time(self):
        self.time_var.set(datetime.now().strftime("%H:%M:%S"))
        self.after(1000, self._update_time)

    def _update_status_bar(self):
        item_count = get_cart_item_count(self.cart)
        self.cart_count_label.config(text=f"Items: {item_count}")
        if self.current_customer_name:
            self.status_label.config(text=f"Customer: {self.current_customer_name}")
        else:
            self.status_label.config(text="Ready")

    def _build_product_panel(self, parent):
        frame = tk.Frame(parent, bg="white", bd=0, relief="flat")
        frame.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(
            frame,
            text="Products",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#1a1a2e",
        ).pack(anchor="w", padx=12, pady=(10, 4))

        search_row = tk.Frame(frame, bg="white")
        search_row.pack(fill="x", padx=12, pady=(0, 6))

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            search_row,
            textvariable=self.search_var,
            font=("Segoe UI", 12),
            relief="flat",
            bd=3,
            bg="#f7f8fa",
        )
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.search_entry.bind("<Return>", lambda e: self._search_products())
        self.search_entry.bind("<KeyRelease>", lambda e: self._live_search())
        self.search_entry.focus()

        tk.Button(
            search_row,
            text="Search",
            font=("Segoe UI", 10),
            bg="#e94560",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._search_products,
        ).pack(side="left", padx=(6, 0), ipady=8, ipadx=6)

        filter_row = tk.Frame(frame, bg="white")
        filter_row.pack(fill="x", padx=12, pady=(0, 6))
        tk.Label(filter_row, text="Category:", bg="white", font=("Segoe UI", 9)).pack(
            side="left"
        )
        self.category_var = tk.StringVar(value="All")
        self.category_combo = ttk.Combobox(
            filter_row,
            textvariable=self.category_var,
            values=["All"],
            state="readonly",
            width=15,
        )
        self.category_combo.pack(side="left", padx=5)
        self.category_combo.bind(
            "<<ComboboxSelected>>", lambda e: self._search_products()
        )
        self._load_categories()

        cols = ("Name", "Category", "Price", "Stock")
        self.product_tree = ttk.Treeview(
            frame, columns=cols, show="headings", selectmode="browse"
        )
        col_w = {"Name": 200, "Category": 100, "Price": 80, "Stock": 60}
        for col in cols:
            self.product_tree.heading(col, text=col)
            self.product_tree.column(col, width=col_w[col], anchor="center")
        self.product_tree.column("Name", anchor="w")
        self.product_tree.tag_configure("out_of_stock", foreground="#bbb")
        self.product_tree.tag_configure("low_stock", foreground="#e94560")

        sb = ttk.Scrollbar(frame, orient="vertical", command=self.product_tree.yview)
        self.product_tree.configure(yscrollcommand=sb.set)
        self.product_tree.pack(
            side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 10)
        )
        sb.pack(side="left", fill="y", pady=(0, 10))

        self.product_tree.bind("<Double-1>", self._on_product_double_click)
        self.product_tree.bind("<Return>", self._on_product_double_click)
        self._search_products()

    def _load_categories(self):
        try:
            from modules.products import get_categories

            self.category_combo["values"] = ["All"] + get_categories()
        except Exception as e:
            logger.error("Error loading categories: %s", e)

    def _search_products(self):
        keyword = self.search_var.get().strip()
        category = self.category_var.get()

        if not keyword and category == "All":
            from modules.products import get_all_products

            products = get_all_products()
        elif not keyword:
            from modules.products import get_products_by_category

            products = get_products_by_category(category)
        else:
            products = search_products(keyword)
            if category != "All":
                products = [p for p in products if p.get("category") == category]

        self.product_tree.delete(*self.product_tree.get_children())
        for p in products:
            tag = (
                "out_of_stock"
                if p["stock"] == 0
                else "low_stock"
                if p["stock"] <= p.get("low_stock_alert", 5)
                else ""
            )
            self.product_tree.insert(
                "",
                "end",
                iid=str(p["product_id"]),
                tags=(tag,),
                values=(
                    p["product_name"],
                    p["category"],
                    f"GHS {p['price']:.2f}",
                    p["stock"],
                ),
            )

    def _live_search(self):
        self._search_products()

    def _on_product_double_click(self, event=None):
        selected = self.product_tree.selection()
        if not selected:
            return
        product = get_product_by_id(int(selected[0]))
        if product:
            self._add_to_cart(product)

    def _build_cart_panel(self, parent):
        frame = tk.Frame(parent, bg="white", bd=0)
        frame.pack(side="left", fill="both", expand=True, padx=6)

        header_row = tk.Frame(frame, bg="white")
        header_row.pack(fill="x", padx=12, pady=(10, 4))

        tk.Label(
            header_row,
            text="Cart",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#1a1a2e",
        ).pack(side="left")

        self.customer_label = tk.Label(
            header_row,
            text="Customer: Walk-in",
            font=("Segoe UI", 9),
            bg="white",
            fg="#e94560",
        )
        self.customer_label.pack(side="left", padx=10)

        tk.Button(
            header_row,
            text="🗑 Clear Cart",
            font=("Segoe UI", 9),
            relief="flat",
            bg="#e74c3c",
            fg="white",
            cursor="hand2",
            command=self._clear_cart,
        ).pack(side="right")

        cart_cols = ("Product", "Qty", "Unit Price", "Subtotal")
        self.cart_tree = ttk.Treeview(
            frame, columns=cart_cols, show="headings", selectmode="browse"
        )
        cart_w = {"Product": 180, "Qty": 50, "Unit Price": 90, "Subtotal": 90}
        for col in cart_cols:
            self.cart_tree.heading(col, text=col)
            self.cart_tree.column(col, width=cart_w[col], anchor="center")
        self.cart_tree.column("Product", anchor="w")

        cart_sb = ttk.Scrollbar(frame, orient="vertical", command=self.cart_tree.yview)
        self.cart_tree.configure(yscrollcommand=cart_sb.set)
        self.cart_tree.pack(
            side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 10)
        )
        cart_sb.pack(side="left", fill="y", pady=(0, 10))

        self.cart_menu = tk.Menu(self, tearoff=0)
        self.cart_menu.add_command(label="➕  Increase qty", command=self._increase_qty)
        self.cart_menu.add_command(label="➖  Decrease qty", command=self._decrease_qty)
        self.cart_menu.add_separator()
        self.cart_menu.add_command(
            label="🗑  Remove item", command=self._remove_from_cart
        )
        self.cart_tree.bind("<Button-3>", self._show_cart_menu)

    def _show_cart_menu(self, event):
        row = self.cart_tree.identify_row(event.y)
        if row:
            self.cart_tree.selection_set(row)
            self.cart_menu.post(event.x_root, event.y_root)

    def _build_payment_panel(self, parent):
        outer = tk.Frame(parent, bg="white", bd=0)
        outer.pack(side="right", fill="both", expand=True, padx=(6, 0))

        canvas = tk.Canvas(outer, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        frame = tk.Frame(canvas, bg="white", bd=0)
        frame_id = canvas.create_window((0, 0), window=frame, anchor="nw")

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(frame_id, width=event.width)

        frame.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        pad = dict(padx=16)

        tk.Label(
            frame,
            text="Payment",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#1a1a2e",
        ).pack(anchor="w", pady=(12, 8), **pad)

        totals_frame = tk.Frame(frame, bg="#f7f8fa", pady=10)
        totals_frame.pack(fill="x", padx=12, pady=(0, 10))

        def total_row(label, var, big=False):
            row = tk.Frame(totals_frame, bg="#f7f8fa")
            row.pack(fill="x", padx=10, pady=2)
            font = ("Segoe UI", 13, "bold") if big else ("Segoe UI", 10)
            fg = "#e94560" if big else "#555"
            tk.Label(row, text=label, font=font, bg="#f7f8fa", fg=fg).pack(side="left")
            tk.Label(row, textvariable=var, font=font, bg="#f7f8fa", fg=fg).pack(
                side="right"
            )

        self.subtotal_var = tk.StringVar(value="GHS 0.00")
        self.discount_var = tk.StringVar(value="GHS 0.00")
        self.tax_var = tk.StringVar(value="GHS 0.00")
        self.total_var = tk.StringVar(value="GHS 0.00")

        total_row("Subtotal", self.subtotal_var)
        total_row("Discount", self.discount_var)
        total_row("Tax", self.tax_var)
        ttk.Separator(totals_frame).pack(fill="x", padx=10, pady=4)
        total_row("TOTAL", self.total_var, big=True)

        tk.Label(
            frame,
            text="Discount (GHS)",
            font=("Segoe UI", 9, "bold"),
            bg="white",
            fg="#333",
        ).pack(anchor="w", **pad)
        self.discount_entry_var = tk.StringVar(value="0")
        tk.Entry(
            frame,
            textvariable=self.discount_entry_var,
            font=("Segoe UI", 11),
            relief="flat",
            bd=3,
            bg="#f7f8fa",
        ).pack(fill="x", ipady=6, pady=(2, 10), **pad)
        self.discount_entry_var.trace("w", lambda *a: self._refresh_totals())

        tk.Label(
            frame,
            text="Payment Method",
            font=("Segoe UI", 9, "bold"),
            bg="white",
            fg="#333",
        ).pack(anchor="w", **pad)
        self.payment_var = tk.StringVar(value="cash")
        payment_options = [
            ("Cash", "cash", "#27ae60"),
            ("MoMo Checkout Page", "momo_checkout", "#f5a623"),
            ("Direct MoMo", "momo_direct", "#d17a00"),
            ("Card", "card", "#2980b9"),
        ]
        for text, val, color in payment_options:
            rb = tk.Radiobutton(
                frame,
                text=text,
                variable=self.payment_var,
                value=val,
                font=("Segoe UI", 10),
                bg="white",
                cursor="hand2",
                activebackground="white",
                fg=color,
                selectcolor="white",
            )
            rb.pack(anchor="w", padx=20, pady=2)

        self.momo_frame = tk.Frame(frame, bg="#fffbf0", relief="flat", bd=1)

        self.momo_provider_var = tk.StringVar(value="Auto-detect")
        providers = [
            ("Auto-detect", "auto"),
            ("MTN MoMo", "mtn"),
            ("Telecel Cash", "telecel"),
            ("AirtelTigo", "airteltigo"),
        ]
        self._provider_keys = {p[0]: p[1] for p in providers}
        self.momo_phone_var = tk.StringVar()
        self.momo_phone_var.trace("w", self._on_phone_change)

        self._build_momo_panel_contents("momo_checkout")

        self.payment_var.trace("w", self._on_payment_method_change)
        self.momo_frame.pack_forget()

        self._amount_label = tk.Label(
            frame,
            text="Amount Paid (GHS)",
            font=("Segoe UI", 9, "bold"),
            bg="white",
            fg="#333",
        )
        self._amount_label.pack(anchor="w", pady=(10, 0), **pad)
        self.amount_paid_var = tk.StringVar(value="0")
        self.amount_entry = tk.Entry(
            frame,
            textvariable=self.amount_paid_var,
            font=("Segoe UI", 13, "bold"),
            relief="flat",
            bd=3,
            bg="#f7f8fa",
        )
        self.amount_entry.pack(fill="x", ipady=8, pady=(2, 4), **pad)
        self.amount_entry.bind("<KeyRelease>", lambda e: self._refresh_totals())

        self.change_var = tk.StringVar(value="Change: GHS 0.00")
        tk.Label(
            frame,
            textvariable=self.change_var,
            font=("Segoe UI", 10, "bold"),
            bg="white",
            fg="#27ae60",
        ).pack(anchor="w", **pad)

        tk.Button(
            frame,
            text="✔  CHARGE",
            font=("Segoe UI", 13, "bold"),
            relief="flat",
            bg="#e94560",
            fg="white",
            cursor="hand2",
            pady=12,
            command=self._charge,
        ).pack(fill="x", padx=12, pady=(16, 6))

        receipt_frame = tk.Frame(frame, bg="white")
        receipt_frame.pack(fill="x", padx=12, pady=4)

        self.receipt_btn = tk.Button(
            receipt_frame,
            text="🖨  View Receipt",
            font=("Segoe UI", 10),
            relief="flat",
            bg="#0f3460",
            fg="white",
            cursor="hand2",
            pady=8,
            state="disabled",
            command=self._show_receipt,
        )
        self.receipt_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.save_receipt_btn = tk.Button(
            receipt_frame,
            text="💾 Save",
            font=("Segoe UI", 10),
            relief="flat",
            bg="#1b4332",
            fg="white",
            cursor="hand2",
            pady=8,
            state="disabled",
            command=self._save_receipt_to_file,
        )
        self.save_receipt_btn.pack(side="left")

        quick_amounts = tk.Frame(frame, bg="white")
        quick_amounts.pack(fill="x", padx=12, pady=5)
        for amount in [20, 50, 100, 200]:
            tk.Button(
                quick_amounts,
                text=f"GHS {amount}",
                font=("Segoe UI", 8),
                relief="flat",
                bg="#f0f2f5",
                fg="#333",
                command=lambda a=amount: self._set_amount_paid(a),
            ).pack(side="left", padx=2, expand=True, fill="x")

        self.pay_msg_var = tk.StringVar()
        self.pay_msg_label = tk.Label(
            frame,
            textvariable=self.pay_msg_var,
            font=("Segoe UI", 9),
            bg="white",
            fg="#e74c3c",
            wraplength=240,
        )
        self.pay_msg_label.pack(pady=(8, 0), **pad)

    # ── MoMo helpers ──────────────────────────────────────────────────────────

    def _on_phone_change(self, *args):
        try:
            from utils.momo_payments import validate_ghana_phone, MOMO_PROVIDERS

            phone = self.momo_phone_var.get()
            valid, normalized, provider = validate_ghana_phone(phone)
            if valid and provider:
                cfg = MOMO_PROVIDERS[provider]
                self.provider_badge.config(
                    text=f"✓ Detected: {cfg['name']}", fg=cfg["color"]
                )
                display = next(
                    (k for k, v in self._provider_keys.items() if v == provider),
                    "Auto-detect",
                )
                self.momo_provider_var.set(display)
            else:
                self.provider_badge.config(text="", fg="#f5a623")
        except Exception:
            pass

    def _on_payment_method_change(self, *args):
        mode = self.payment_var.get()
        if mode in ("momo_checkout", "momo_direct"):
            for widget in self.momo_frame.winfo_children():
                widget.destroy()
            self._build_momo_panel_contents(mode)
            self.momo_frame.pack(
                fill="x", padx=12, pady=(0, 6), before=self._amount_label
            )
        else:
            self.momo_frame.pack_forget()
            self.momo_phone_var.set("")
            self.provider_badge.config(text="")
            self._last_momo_ref = ""
            self._last_momo_checkout_url = ""
            self._last_momo_flow = ""
            self.verify_btn.config(state="disabled")

    def _show_momo_waiting_state(
        self,
        sale_id,
        phone,
        provider_name,
        amount,
        provider_key="",
        flow_type="direct",
        checkout_url="",
    ):
        """Replace MoMo input panel with a compact waiting-for-approval state."""
        self._last_momo_phone = phone
        self._last_momo_provider = provider_key
        self._last_momo_amount = amount
        self._last_momo_sale_id = sale_id
        self._last_momo_checkout_url = checkout_url
        self._last_momo_flow = flow_type

        for widget in self.momo_frame.winfo_children():
            widget.destroy()

        tk.Label(
            self.momo_frame,
            text=(
                "Hosted Checkout In Progress"
                if flow_type == "checkout"
                else "Awaiting Customer Approval"
            ),
            font=("Segoe UI", 10, "bold"),
            bg="#fffbf0",
            fg="#8a6000",
        ).pack(anchor="w", padx=10, pady=(10, 4))

        info = (
            f"Flow:     {'Hosted Checkout' if flow_type == 'checkout' else 'Direct Charge'}\n"
            f"Network:  {provider_name}\n"
            f"Phone:    {phone or 'Entered on checkout page'}\n"
            f"Amount:   GHS {amount:.2f}\n"
            f"Sale #:   {sale_id}"
        )
        tk.Label(
            self.momo_frame,
            text=info,
            font=("Segoe UI", 9),
            bg="#fffbf0",
            fg="#333",
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 6))

        tk.Label(
            self.momo_frame,
            text=(
                "Customer should complete the payment on the Paystack checkout page."
                if flow_type == "checkout"
                else "Ask customer to approve the prompt on their phone."
            ),
            font=("Segoe UI", 7),
            bg="#fffbf0",
            fg="#888",
            wraplength=220,
        ).pack(anchor="w", padx=10, pady=(0, 6))

        btn_row = tk.Frame(self.momo_frame, bg="#fffbf0")
        btn_row.pack(fill="x", padx=10, pady=(0, 4))

        self.verify_btn = tk.Button(
            btn_row,
            text="Verify Payment",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            bg="#27ae60",
            fg="white",
            cursor="hand2",
            pady=8,
            command=self._verify_momo_payment,
        )
        self.verify_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        if flow_type == "checkout":
            tk.Button(
                btn_row,
                text="Open Checkout",
                font=("Segoe UI", 9),
                relief="flat",
                bg="#f39c12",
                fg="white",
                cursor="hand2",
                command=self._open_momo_checkout_again,
            ).pack(side="left")
        else:
            tk.Button(
                btn_row,
                text="Resend",
                font=("Segoe UI", 9),
                relief="flat",
                bg="#f39c12",
                fg="white",
                cursor="hand2",
                command=self._resend_momo_prompt,
            ).pack(side="left")

        tk.Button(
            self.momo_frame,
            text="Cancel & New Sale",
            font=("Segoe UI", 9),
            relief="flat",
            bg="#e74c3c",
            fg="white",
            cursor="hand2",
            command=self._reset_momo_panel,
        ).pack(fill="x", padx=10, pady=(0, 10))

        self.momo_frame.pack(fill="x", padx=12, pady=(0, 6), before=self._amount_label)

    def _reset_momo_panel(self):
        for widget in self.momo_frame.winfo_children():
            widget.destroy()
        self._build_momo_panel_contents("momo_checkout")
        self.momo_frame.pack_forget()
        self.payment_var.set("cash")
        self._last_momo_ref = ""
        self._last_momo_phone = ""
        self._last_momo_provider = ""
        self._last_momo_amount = 0.0
        self._last_momo_sale_id = None
        self._last_momo_checkout_url = ""
        self._last_momo_flow = ""

    def _build_momo_panel_contents(self, mode="momo_checkout"):
        tk.Label(
            self.momo_frame,
            text=(
                "MoMo Checkout Page"
                if mode == "momo_checkout"
                else "Direct Mobile Money"
            ),
            font=("Segoe UI", 9, "bold"),
            bg="#fffbf0",
            fg="#8a6000",
        ).pack(anchor="w", padx=10, pady=(8, 4))

        self.provider_badge = tk.Label(
            self.momo_frame,
            text="",
            font=("Segoe UI", 8, "bold"),
            bg="#fffbf0",
            fg="#f5a623",
        )
        self.provider_badge.pack(anchor="w", padx=10)

        if mode == "momo_checkout":
            tk.Label(
                self.momo_frame,
                text=(
                    "Paystack will open in the browser so the customer can choose "
                    "Mobile Money, enter the code or OTP, and confirm the payment."
                ),
                font=("Segoe UI", 8),
                bg="#fffbf0",
                fg="#555",
                wraplength=220,
                justify="left",
            ).pack(anchor="w", padx=10, pady=(0, 8))

            self.verify_btn = tk.Button(
                self.momo_frame,
                text="Verify Payment",
                font=("Segoe UI", 9),
                relief="flat",
                bg="#27ae60",
                fg="white",
                cursor="hand2",
                command=self._verify_momo_payment,
                state="disabled",
            )
            self.verify_btn.pack(fill="x", padx=10, pady=(0, 8))
            return

        provider_row = tk.Frame(self.momo_frame, bg="#fffbf0")
        provider_row.pack(fill="x", padx=10, pady=(0, 6))
        tk.Label(
            provider_row, text="Network:", font=("Segoe UI", 9), bg="#fffbf0", fg="#333"
        ).pack(side="left")

        self.provider_combo = ttk.Combobox(
            provider_row,
            textvariable=self.momo_provider_var,
            values=list(self._provider_keys.keys()),
            state="readonly",
            width=14,
        )
        self.provider_combo.pack(side="left", padx=(6, 0))
        self.momo_provider_var.set("Auto-detect")

        tk.Label(
            self.momo_frame,
            text="Customer Phone *",
            font=("Segoe UI", 9, "bold"),
            bg="#fffbf0",
            fg="#333",
        ).pack(anchor="w", padx=10, pady=(4, 2))
        phone_entry = tk.Entry(
            self.momo_frame,
            textvariable=self.momo_phone_var,
            font=("Segoe UI", 12),
            relief="flat",
            bd=3,
            bg="white",
        )
        phone_entry.pack(fill="x", ipady=7, padx=10, pady=(0, 4))

        tk.Label(
            self.momo_frame,
            text="Customer will receive a MoMo prompt on their phone to approve.",
            font=("Segoe UI", 7),
            bg="#fffbf0",
            fg="#888",
            wraplength=220,
        ).pack(anchor="w", padx=10, pady=(0, 8))

        self.verify_btn = tk.Button(
            self.momo_frame,
            text="Verify Payment",
            font=("Segoe UI", 9),
            relief="flat",
            bg="#27ae60",
            fg="white",
            cursor="hand2",
            command=self._verify_momo_payment,
            state="disabled",
        )
        self.verify_btn.pack(fill="x", padx=10, pady=(0, 8))

    def _open_momo_checkout_again(self):
        if not self._last_momo_checkout_url:
            self._pay_msg("No checkout page available to reopen.", error=True)
            return
        if webbrowser.open(self._last_momo_checkout_url):
            self._pay_msg("Checkout page opened in browser.", error=False)
        else:
            self._pay_msg("Could not open checkout page automatically.", error=True)

    def _verify_momo_payment(self):
        """Poll Paystack to confirm the customer approved the MoMo prompt."""
        if not self._last_momo_ref:
            self._pay_msg("No pending MoMo transaction to verify.", error=True)
            return
        try:
            from utils.momo_payments import verify_momo_payment

            success, status, msg = verify_momo_payment(self._last_momo_ref)

            if success:
                self._pay_msg(f"✔ {msg}", error=False)
                messagebox.showinfo("Payment Confirmed", msg)
                self._reset_momo_panel()

            elif status == "pending":
                # Still waiting — keep the panel open, just update the message
                self._pay_msg(msg, error=True)

            elif status == "abandoned":
                # Customer dismissed the prompt — offer to resend or switch method
                choice = messagebox.askyesnocancel(
                    "Payment Abandoned",
                    f"The customer dismissed the payment prompt without approving.\n\n"
                    f"Yes    → Resend the MoMo prompt\n"
                    f"No     → Switch to Cash/Card\n"
                    f"Cancel → Keep waiting",
                )
                if choice is True:
                    self._resend_momo_prompt()
                elif choice is False:
                    self._reset_momo_panel()
                    self.payment_var.set("cash")
                # choice is None (Cancel) → do nothing, leave panel open

            elif status == "failed":
                if messagebox.askyesno(
                    "Payment Failed",
                    f"{msg}\n\nSwitch to a different payment method?",
                ):
                    self._reset_momo_panel()
                    self.payment_var.set("cash")

            else:
                # Network/gateway error
                self._pay_msg(msg, error=True)

        except Exception as e:
            self._pay_msg(f"Verification error: {e}", error=True)

    def _resend_momo_prompt(self):
        """Re-initiate the Paystack MoMo charge with the same stored details."""
        if not self._last_momo_phone or not self._last_momo_sale_id:
            self._pay_msg("Cannot resend — missing payment details.", error=True)
            return
        try:
            from utils.momo_payments import initiate_momo_payment

            success, ref, momo_msg = initiate_momo_payment(
                phone=self._last_momo_phone,
                amount=self._last_momo_amount,
                sale_id=self._last_momo_sale_id,
                provider=self._last_momo_provider,
            )
            if success:
                self._last_momo_ref = ref
                self._pay_msg(
                    "Prompt resent. Ask the customer to approve.", error=False
                )
            else:
                self._pay_msg(f"Resend failed: {momo_msg}", error=True)
        except Exception as e:
            self._pay_msg(f"Resend error: {e}", error=True)

    # ── Cart helpers ──────────────────────────────────────────────────────────

    def _set_amount_paid(self, amount):
        self.amount_paid_var.set(str(amount))

    def _add_to_cart(self, product: dict, qty: int = 1):
        if product["stock"] == 0:
            self._pay_msg("Out of stock.", error=True)
            return
        self.cart, ok, msg = cart_add_item(self.cart, product, qty)
        if not ok:
            self._pay_msg(msg, error=True)
        else:
            self._refresh_cart_tree()
            self._refresh_totals()
            self._update_status_bar()

    def _remove_from_cart(self):
        selected = self.cart_tree.selection()
        if not selected:
            return
        self.cart = cart_remove_item(self.cart, int(selected[0]))
        self._refresh_cart_tree()
        self._refresh_totals()
        self._update_status_bar()

    def _increase_qty(self):
        self._change_qty(+1)

    def _decrease_qty(self):
        self._change_qty(-1)

    def _change_qty(self, delta: int):
        selected = self.cart_tree.selection()
        if not selected:
            return
        product_id = int(selected[0])
        for item in self.cart:
            if item["product_id"] == product_id:
                new_qty = item["quantity"] + delta
                self.cart, ok, msg = cart_update_quantity(
                    self.cart, product_id, new_qty
                )
                if not ok:
                    self._pay_msg(msg, error=True)
                self._refresh_cart_tree()
                self._refresh_totals()
                self._update_status_bar()
                return

    def _clear_cart(self):
        if not self.cart:
            return
        if messagebox.askyesno("Clear Cart", "Remove all items from the cart?"):
            self.cart = cart_clear(self.cart)
            self._refresh_cart_tree()
            self._refresh_totals()
            self.last_sale_id = None
            self.receipt_btn.config(state="disabled")
            self.save_receipt_btn.config(state="disabled")
            self._pay_msg("")
            self._update_status_bar()

    def _refresh_cart_tree(self):
        self.cart_tree.delete(*self.cart_tree.get_children())
        for item in self.cart:
            self.cart_tree.insert(
                "",
                "end",
                iid=str(item["product_id"]),
                values=(
                    item["product_name"],
                    item["quantity"],
                    f"GHS {item['unit_price']:.2f}",
                    f"GHS {item['subtotal']:.2f}",
                ),
            )

    def _refresh_totals(self):
        try:
            discount = float(self.discount_entry_var.get())
        except ValueError:
            discount = 0.0

        totals = cart_totals(self.cart, discount, self.TAX_RATE)
        self.subtotal_var.set(f"GHS {totals['subtotal']:.2f}")
        self.discount_var.set(f"GHS {totals['discount']:.2f}")
        self.tax_var.set(f"GHS {totals['tax']:.2f}")
        self.total_var.set(f"GHS {totals['total']:.2f}")

        try:
            paid = float(self.amount_paid_var.get())
            change = paid - totals["total"]
            self.change_var.set(
                f"Change: GHS {change:.2f}"
                if change >= 0
                else f"Short: GHS {abs(change):.2f}"
            )
        except ValueError:
            self.change_var.set("Change: GHS 0.00")

    # ── Charge ────────────────────────────────────────────────────────────────

    def _charge(self):  # noqa: C901
        if not self.cart:
            self._pay_msg("Cart is empty.", error=True)
            return

        try:
            amount_paid = float(self.amount_paid_var.get())
        except ValueError:
            self._pay_msg("Enter a valid amount paid.", error=True)
            return

        try:
            discount = float(self.discount_entry_var.get())
        except ValueError:
            discount = 0.0

        totals = cart_totals(self.cart, discount, self.TAX_RATE)
        payment_method = self.payment_var.get()

        if payment_method in ("momo_checkout", "momo_direct"):
            amount_paid = totals["total"]

        if amount_paid < totals["total"]:
            self._pay_msg(
                f"Insufficient payment. Total: GHS {totals['total']:.2f}", error=True
            )
            return

        if payment_method in ("momo_checkout", "momo_direct"):
            normalized = ""
            provider_key = ""
            provider_name = "Paystack Checkout"

            if payment_method == "momo_direct":
                phone = self.momo_phone_var.get().strip()
                if not phone:
                    self._pay_msg("Enter customer phone number for MoMo.", error=True)
                    return

                try:
                    from utils.momo_payments import validate_ghana_phone, MOMO_PROVIDERS

                    valid, normalized, detected = validate_ghana_phone(phone)
                    if not valid:
                        self._pay_msg(
                            "Invalid phone number. Use format: 0241234567 or +233241234567",
                            error=True,
                        )
                        return

                    selected_display = self.momo_provider_var.get()
                    provider_key = self._provider_keys.get(selected_display, "auto")
                    if provider_key == "auto":
                        provider_key = detected

                    if not provider_key:
                        self._pay_msg(
                            "Could not detect network. Select provider manually.",
                            error=True,
                        )
                        return

                    provider_name = MOMO_PROVIDERS[provider_key]["name"]
                except ImportError:
                    normalized, provider_key, provider_name = phone, "mtn", "MTN MoMo"

                confirm = messagebox.askyesno(
                    "Confirm Direct MoMo Payment",
                    f"Network:  {provider_name}\n"
                    f"Phone:    {normalized}\n"
                    f"Amount:   GHS {totals['total']:.2f}\n\n"
                    f"Send payment prompt to customer's phone?",
                )
                if not confirm:
                    return
            else:
                confirm = messagebox.askyesno(
                    "Open MoMo Checkout Page",
                    f"Amount: GHS {totals['total']:.2f}\n\n"
                    "Open Paystack checkout in the browser for the customer to complete payment?",
                )
                if not confirm:
                    return

            ok, sale_id, change, msg = process_sale(
                cart=self.cart,
                user_id=self.current_user["user_id"],
                payment_method="momo",
                amount_paid=amount_paid,
                discount=discount,
                tax_rate=self.TAX_RATE,
                customer_id=self.current_customer_id,
            )
            if not ok:
                self._pay_msg(msg, error=True)
                return

            try:
                if payment_method == "momo_checkout":
                    from utils.momo_payments import initialize_momo_checkout

                    success, ref, checkout_url, momo_msg = initialize_momo_checkout(
                        amount=totals["total"],
                        sale_id=sale_id,
                        customer_phone=self.momo_phone_var.get().strip(),
                    )
                    if success:
                        self._last_momo_ref = ref
                        self._show_momo_waiting_state(
                            sale_id=sale_id,
                            phone="",
                            provider_name="Paystack Checkout",
                            amount=totals["total"],
                            provider_key="checkout",
                            flow_type="checkout",
                            checkout_url=checkout_url,
                        )
                        webbrowser.open(checkout_url)
                    else:
                        self._pay_msg(
                            f"Sale #{sale_id} recorded but checkout setup failed:\n{momo_msg}",
                            error=True,
                        )
                        return
                else:
                    from utils.momo_payments import initiate_momo_payment

                    success, ref, momo_msg = initiate_momo_payment(
                        phone=normalized,
                        amount=totals["total"],
                        sale_id=sale_id,
                        provider=provider_key,
                    )
                    if success:
                        self._last_momo_ref = ref
                        self._show_momo_waiting_state(
                            sale_id=sale_id,
                            phone=normalized,
                            provider_name=provider_name,
                            amount=totals["total"],
                            provider_key=provider_key,
                            flow_type="direct",
                        )
                    else:
                        self._pay_msg(
                            f"Sale #{sale_id} recorded but MoMo push failed:\n{momo_msg}",
                            error=True,
                        )
                        return

                self.last_sale_id = sale_id
                self.receipt_btn.config(state="normal")
                self.save_receipt_btn.config(state="normal")
                self.cart = cart_clear(self.cart)
                self._refresh_cart_tree()
                self._refresh_totals()
                self.discount_entry_var.set("0")
                self.amount_paid_var.set("0")
                self.current_customer_id = None
                self.current_customer_name = None
                self.customer_label.config(text="Customer: Walk-in")
                self._search_products()
                self._check_low_stock()
                self._update_status_bar()
                self._pay_msg(
                    (
                        f"Checkout page opened for sale #{sale_id}."
                        if payment_method == "momo_checkout"
                        else f"MoMo prompt sent for sale #{sale_id}."
                    ),
                    error=False,
                )
                return
            except ImportError:
                self._last_momo_ref = f"MOMO-{sale_id}"
                msg = f"Sale #{sale_id} complete (MoMo module unavailable)."

        else:
            ok, sale_id, change, msg = process_sale(
                cart=self.cart,
                user_id=self.current_user["user_id"],
                payment_method=payment_method,
                amount_paid=amount_paid,
                discount=discount,
                tax_rate=self.TAX_RATE,
                customer_id=self.current_customer_id,
            )
            if not ok:
                self._pay_msg(msg, error=True)
                return
            msg = f"Sale #{sale_id} complete! Change: GHS {change:.2f}"

        self.last_sale_id = sale_id
        self._pay_msg(msg, error=False)
        self.receipt_btn.config(state="normal")
        self.save_receipt_btn.config(state="normal")

        self.cart = cart_clear(self.cart)
        self._refresh_cart_tree()
        self._refresh_totals()
        self.discount_entry_var.set("0")
        self.amount_paid_var.set("0")
        self.payment_var.set("cash")
        self.momo_phone_var.set("")
        self.provider_badge.config(text="")
        self.current_customer_id = None
        self.current_customer_name = None
        self.customer_label.config(text="Customer: Walk-in")

        self._search_products()
        self._check_low_stock()
        self._update_status_bar()

        if messagebox.askyesno("Receipt", "Print receipt?"):
            self._show_receipt()

    # Receipt

    def _show_receipt(self):
        if not self.last_sale_id:
            return
        receipt_text = generate_receipt(self.last_sale_id, "POS System")
        if not receipt_text:
            return

        win = tk.Toplevel(self)
        win.title(f"Receipt — Sale #{self.last_sale_id}")
        win.geometry("420x640")
        win.configure(bg="white")
        win.resizable(False, True)

        text_frame = tk.Frame(win, bg="white")
        text_frame.pack(fill="both", expand=True, padx=10, pady=10)

        text = tk.Text(
            text_frame, font=("Courier New", 9), bg="white", relief="flat", wrap="word"
        )
        text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
        scrollbar.pack(side="right", fill="y")
        text.configure(yscrollcommand=scrollbar.set)
        text.insert("1.0", receipt_text)
        text.config(state="disabled")

        btn_frame = tk.Frame(win, bg="white")
        btn_frame.pack(fill="x", pady=8, padx=10)

        tk.Button(
            btn_frame,
            text="🖨  Print",
            relief="flat",
            bg="#0f3460",
            fg="white",
            font=("Segoe UI", 10),
            width=10,
            command=lambda: self._print_receipt(receipt_text),
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            btn_frame,
            text="💾  Save to File",
            relief="flat",
            bg="#1b4332",
            fg="white",
            font=("Segoe UI", 10),
            width=12,
            command=lambda: self._save_receipt_dialog(receipt_text),
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            btn_frame,
            text="📋  Copy",
            relief="flat",
            bg="#444",
            fg="white",
            font=("Segoe UI", 10),
            width=8,
            command=lambda: self._copy_receipt(receipt_text),
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            btn_frame,
            text="Close",
            relief="flat",
            bg="#e94560",
            fg="white",
            font=("Segoe UI", 10),
            width=8,
            command=win.destroy,
        ).pack(side="right")

    def _print_receipt(self, receipt_text: str):
        try:
            import sys

            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            )
            tmp.write(receipt_text)
            tmp.close()
            if sys.platform.startswith("win"):
                os.startfile(tmp.name, "print")
            else:
                os.system(f'lpr "{tmp.name}"')
            self._pay_msg("Sent to printer.", error=False)
        except Exception as e:
            messagebox.showerror("Print Error", f"Could not print receipt:\n{str(e)}")

    def _save_receipt_dialog(self, receipt_text: str):
        default_name = f"receipt_{self.last_sale_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=default_name,
            title="Save Receipt",
        )
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(receipt_text)
                self._pay_msg("Receipt saved.", error=False)
            except Exception as e:
                messagebox.showerror("Save Error", f"Could not save receipt:\n{str(e)}")

    def _save_receipt_to_file(self):
        if not self.last_sale_id:
            return
        receipt_text = generate_receipt(self.last_sale_id, "POS System")
        if receipt_text:
            self._save_receipt_dialog(receipt_text)

    def _copy_receipt(self, receipt_text: str):
        self.clipboard_clear()
        self.clipboard_append(receipt_text)
        self._pay_msg("Receipt copied to clipboard!", error=False)

    # ── Customer dialogs ──────────────────────────────────────────────────────

    def _add_customer_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Customer Management")
        dialog.geometry("400x300")
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text="Customer Phone:").pack(pady=5)
        phone_entry = tk.Entry(dialog, width=30)
        phone_entry.pack(pady=5)
        phone_entry.focus()

        def search_customer():
            phone = phone_entry.get().strip()
            if not phone:
                return
            try:
                from modules.customers import get_customer_by_phone

                customer = get_customer_by_phone(phone)
                if customer:
                    self.current_customer_id = customer["customer_id"]
                    self.current_customer_name = customer["full_name"]
                    pts = customer.get("loyalty_points", 0)
                    self.customer_label.config(
                        text=f"Customer: {customer['full_name']} ({pts} pts)"
                    )
                    self._pay_msg(
                        f"Customer: {customer['full_name']} | {pts} loyalty pts",
                        error=False,
                    )
                    dialog.destroy()
                else:
                    if messagebox.askyesno(
                        "New Customer", "Customer not found. Create new?"
                    ):
                        self._create_customer_dialog(phone)
                        dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Error finding customer: {e}")

        phone_entry.bind("<Return>", lambda e: search_customer())
        tk.Button(dialog, text="Search", command=search_customer).pack(pady=10)
        tk.Button(dialog, text="Cancel", command=dialog.destroy).pack(pady=5)

    def _create_customer_dialog(self, phone=""):
        dialog = tk.Toplevel(self)
        dialog.title("New Customer")
        dialog.geometry("350x300")
        dialog.transient(self)
        dialog.grab_set()

        fields = [
            ("Full Name:", "name"),
            ("Phone:", "phone"),
            ("Email:", "email"),
            ("Address:", "address"),
        ]
        entries = {}
        for i, (label, attr) in enumerate(fields):
            tk.Label(dialog, text=label).grid(
                row=i, column=0, sticky="w", padx=5, pady=5
            )
            entry = tk.Entry(dialog, width=30)
            entry.grid(row=i, column=1, padx=5, pady=5)
            if attr == "phone" and phone:
                entry.insert(0, phone)
            entries[attr] = entry

        def save_customer():
            try:
                from modules.customers import add_customer

                success, msg = add_customer(
                    full_name=entries["name"].get(),
                    phone=entries["phone"].get(),
                    email=entries["email"].get(),
                    address=entries["address"].get(),
                )
                if success:
                    messagebox.showinfo("Success", msg)
                    dialog.destroy()
                    self._add_customer_dialog()
                else:
                    messagebox.showerror("Error", msg)
            except Exception as e:
                messagebox.showerror("Error", f"Error creating customer: {e}")

        tk.Button(dialog, text="Save", command=save_customer).grid(
            row=4, column=0, columnspan=2, pady=10
        )

    def _barcode_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Scan Barcode")
        dialog.geometry("300x150")
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text="Scan or enter barcode:").pack(pady=10)
        barcode_var = tk.StringVar()
        entry = tk.Entry(dialog, textvariable=barcode_var, font=("Courier", 14))
        entry.pack(pady=5, padx=20, fill="x")
        entry.focus()

        def process_barcode():
            barcode = barcode_var.get().strip()
            if barcode:
                product = get_product_by_barcode(barcode)
                if product:
                    self._add_to_cart(product)
                    dialog.destroy()
                else:
                    messagebox.showerror("Error", "Product not found!")
                    barcode_var.set("")
                    entry.focus()

        entry.bind("<Return>", lambda e: process_barcode())
        tk.Button(dialog, text="Add to Cart", command=process_barcode).pack(pady=10)

    def _check_low_stock(self):
        try:
            low_stock = get_low_stock_products()
            if low_stock:
                msg = "⚠️ Low Stock Alert ⚠️\n\n"
                for product in low_stock[:5]:
                    msg += f"• {product['product_name']}: {product['quantity']} units left\n"
                if len(low_stock) > 5:
                    msg += f"\n... and {len(low_stock) - 5} more products"
                messagebox.showwarning("Low Stock Alert", msg)
        except Exception as e:
            logger.error("Error checking low stock: %s", e)

    def _pay_msg(self, msg: str, error: bool = False):
        self.pay_msg_var.set(msg)
        self.pay_msg_label.config(fg="#e74c3c" if error else "#27ae60")
