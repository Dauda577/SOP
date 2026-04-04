import tkinter as tk
from tkinter import ttk, messagebox
from modules.products import (
    get_all_products,
    add_product,
    update_product,
    delete_product,
    adjust_stock,
    get_categories,
    get_low_stock_products,
    restore_product,
    get_product_with_details,
    bulk_import_products,
)
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ProductView(tk.Toplevel):
    def __init__(self, parent, current_user: dict, product_manager=None):
        super().__init__(parent)
        self.parent = parent
        self.current_user = current_user
        self.product_manager = product_manager
        self.selected_product_id = None

        self.title("Product Management")
        self.geometry("1200x720")
        self.resizable(True, True)
        self.minsize(1050, 620)
        self.configure(bg="#f0f2f5")
        self._center_window()
        self._build_ui()
        self._load_products()
        self._check_low_stock_alert()

    def _center_window(self):
        self.update_idletasks()
        w, h = 1200, 720
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        topbar = tk.Frame(self, bg="#1a1a2e", pady=12)
        topbar.pack(fill="x")

        tk.Label(topbar, text="  📦  Product Management",
                 font=("Segoe UI", 14, "bold"), bg="#1a1a2e", fg="white").pack(side="left", padx=10)

        quick_actions = tk.Frame(topbar, bg="#1a1a2e")
        quick_actions.pack(side="left", padx=20)

        for text, color, cmd in [
            ("📊 Low Stock Report", "#0f3460", self._show_low_stock_report),
            ("🚚 Supplier Restock", "#27ae60", self._supplier_restock_dialog),
            ("📥 Bulk Import", "#0f3460", self._bulk_import_dialog),
        ]:
            tk.Button(quick_actions, text=text, font=("Segoe UI", 9), bg=color,
                      fg="white", relief="flat", cursor="hand2",
                      command=cmd).pack(side="left", padx=2)

        self.show_inactive_var = tk.BooleanVar(value=False)
        tk.Checkbutton(topbar, text="Show Inactive Products", variable=self.show_inactive_var,
                       command=self._load_products, bg="#1a1a2e", fg="#8892b0",
                       selectcolor="#1a1a2e", activebackground="#1a1a2e").pack(side="right", padx=10)

        tk.Label(topbar,
                 text=f"Logged in as: {self.current_user['full_name']} ({self.current_user['role']})",
                 font=("Segoe UI", 9), bg="#1a1a2e", fg="#8892b0").pack(side="right", padx=16)

        main = tk.Frame(self, bg="#f0f2f5")
        main.pack(fill="both", expand=True, padx=16, pady=12)

        self._build_left_panel(main)
        self._build_right_panel(main)

    def _build_left_panel(self, parent):
        left = tk.Frame(parent, bg="#f0f2f5")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        search_frame = tk.Frame(left, bg="#f0f2f5")
        search_frame.pack(fill="x", pady=(0, 8))

        tk.Label(search_frame, text="Search:", bg="#f0f2f5", font=("Segoe UI", 10)).pack(side="left")

        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *a: self._on_search())
        tk.Entry(search_frame, textvariable=self.search_var, font=("Segoe UI", 11),
                 relief="flat", bd=4).pack(side="left", fill="x", expand=True, padx=(6, 8))

        tk.Label(search_frame, text="Category:", bg="#f0f2f5", font=("Segoe UI", 10)).pack(side="left", padx=(8, 4))
        self.category_filter_var = tk.StringVar(value="All")
        self.category_combo = ttk.Combobox(search_frame, textvariable=self.category_filter_var,
                                            values=["All"], state="readonly", width=15)
        self.category_combo.pack(side="left", padx=(0, 8))
        self.category_combo.bind("<<ComboboxSelected>>", lambda e: self._on_search())
        self._load_categories()

        tk.Button(search_frame, text="⟳ Refresh", font=("Segoe UI", 9), relief="flat",
                  bg="#e94560", fg="white", cursor="hand2",
                  command=self._load_products).pack(side="left")

        tk.Button(search_frame, text="📎 Export CSV", font=("Segoe UI", 9), relief="flat",
                  bg="#27ae60", fg="white", cursor="hand2",
                  command=self._export_to_csv).pack(side="left", padx=(8, 0))

        cols = ("ID", "Name", "Category", "Price (GHS)", "Stock", "Alert", "Barcode", "Status")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        col_widths = {"ID": 40, "Name": 180, "Category": 100, "Price (GHS)": 80,
                      "Stock": 60, "Alert": 50, "Barcode": 100, "Status": 80}
        for col in cols:
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_tree(c))
            self.tree.column(col, width=col_widths[col], anchor="center")
        self.tree.column("Name", anchor="w")

        scrollbar = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="left", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.tag_configure("low_stock", background="#fff0f0", foreground="#c0392b")
        self.tree.tag_configure("inactive", background="#f5f5f5", foreground="#95a5a6")
        self.tree.tag_configure("normal", background="white")

        self.status_var = tk.StringVar(value="")
        tk.Label(left, textvariable=self.status_var, bg="#f0f2f5",
                 font=("Segoe UI", 9), fg="#555").pack(anchor="w", pady=(4, 0))

    def _build_right_panel(self, parent):
        # Outer container with fixed width
        right_outer = tk.Frame(parent, bg="white", relief="flat", bd=1, width=360)
        right_outer.pack(side="right", fill="y")
        right_outer.pack_propagate(False)

        # Scrollable canvas
        canvas = tk.Canvas(right_outer, bg="white", highlightthickness=0)
        scrollbar = tk.Scrollbar(right_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        right = tk.Frame(canvas, bg="white", padx=20, pady=20)
        canvas_window = canvas.create_window((0, 0), window=right, anchor="nw")

        def on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(e):
            canvas.itemconfig(canvas_window, width=e.width)

        right.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        def on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        tk.Label(right, text="Product Details", font=("Segoe UI", 13, "bold"),
                 bg="white", fg="#1a1a2e").pack(anchor="w", pady=(0, 14))

        fields = [
            ("Product Name *", "name"),
            ("Category", "category"),
            ("Price (GHS) *", "price"),
            ("Barcode", "barcode"),
            ("Supplier", "supplier"),
            ("Initial Stock", "stock"),
            ("Low Stock Alert", "low_alert"),
        ]

        self.form_vars = {}
        for label, key in fields:
            tk.Label(right, text=label, font=("Segoe UI", 9, "bold"),
                     bg="white", fg="#333", anchor="w").pack(fill="x")
            var = tk.StringVar()
            self.form_vars[key] = var
            state = "readonly" if key == "stock" else "normal"
            tk.Entry(right, textvariable=var, font=("Segoe UI", 11),
                     relief="flat", bd=3, bg="#f7f8fa",
                     state=state).pack(fill="x", ipady=6, pady=(2, 10))

        # Stock adjust
        self.adjust_frame = tk.Frame(right, bg="white")
        self.adjust_frame.pack(fill="x", pady=(0, 10))
        tk.Label(self.adjust_frame, text="Adjust Stock (±)", font=("Segoe UI", 9, "bold"),
                 bg="white", fg="#333").pack(anchor="w")
        adj_row = tk.Frame(self.adjust_frame, bg="white")
        adj_row.pack(fill="x")
        self.adjust_var = tk.StringVar(value="0")
        tk.Entry(adj_row, textvariable=self.adjust_var, font=("Segoe UI", 11),
                 relief="flat", bd=3, bg="#f7f8fa", width=10).pack(side="left")
        tk.Button(adj_row, text="Apply", font=("Segoe UI", 9), relief="flat",
                  bg="#0f3460", fg="white", cursor="hand2",
                  command=self._apply_stock_adjust).pack(side="left", padx=6)

        self.adjust_reason_var = tk.StringVar()
        reason_entry = tk.Entry(self.adjust_frame, textvariable=self.adjust_reason_var,
                                 font=("Segoe UI", 9), relief="flat", bd=2, bg="#f7f8fa")
        reason_entry.insert(0, "Reason (optional)")
        reason_entry.bind("<FocusIn>",
                          lambda e: reason_entry.delete(0, tk.END)
                          if reason_entry.get() == "Reason (optional)" else None)
        reason_entry.bind("<FocusOut>",
                          lambda e: reason_entry.insert(0, "Reason (optional)")
                          if not reason_entry.get() else None)
        reason_entry.pack(fill="x", pady=(4, 0))
        self.adjust_frame.pack_forget()

        btn_cfg = dict(font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2", pady=9)

        self.add_btn = tk.Button(right, text="➕  Add Product", bg="#27ae60", fg="white",
                                  command=self._add_product, **btn_cfg)
        self.add_btn.pack(fill="x", pady=(4, 4))

        self.update_btn = tk.Button(right, text="✏️  Update Product", bg="#2980b9", fg="white",
                                     command=self._update_product, state="disabled", **btn_cfg)
        self.update_btn.pack(fill="x", pady=4)

        self.restore_btn = tk.Button(right, text="🔄  Restore Product", bg="#f39c12", fg="white",
                                      command=self._restore_product, state="disabled", **btn_cfg)
        self.restore_btn.pack(fill="x", pady=4)

        self.delete_btn = tk.Button(right, text="🗑️  Delete Product", bg="#e74c3c", fg="white",
                                     command=self._delete_product, state="disabled", **btn_cfg)
        self.delete_btn.pack(fill="x", pady=4)

        tk.Button(right, text="✖  Clear Form", bg="#95a5a6", fg="white",
                  command=self._clear_form, **btn_cfg).pack(fill="x", pady=(12, 4))

        self.stats_frame = tk.LabelFrame(right, text="Product Stats", bg="white",
                                          fg="#333", font=("Segoe UI", 9))
        self.stats_frame.pack(fill="x", pady=(8, 0))
        self.times_sold_var = tk.StringVar(value="Times sold: --")
        tk.Label(self.stats_frame, textvariable=self.times_sold_var,
                 bg="white", font=("Segoe UI", 9)).pack(anchor="w", padx=5, pady=2)
        self.last_updated_var = tk.StringVar(value="Last updated: --")
        tk.Label(self.stats_frame, textvariable=self.last_updated_var,
                 bg="white", font=("Segoe UI", 9)).pack(anchor="w", padx=5, pady=2)

        self.msg_var = tk.StringVar()
        self.msg_label = tk.Label(right, textvariable=self.msg_var, font=("Segoe UI", 9),
                                   bg="white", wraplength=300)
        self.msg_label.pack(pady=(10, 0))

    def _load_categories(self):
        try:
            categories = get_categories()
            self.category_combo["values"] = ["All"] + categories
        except Exception as e:
            logger.error("Error loading categories: %s", e)

    def _load_products(self, products=None):
        self.tree.delete(*self.tree.get_children())
        if products is None:
            products = get_all_products(include_inactive=self.show_inactive_var.get())

        category_filter = self.category_filter_var.get()
        if category_filter != "All":
            products = [p for p in products if p["category"] == category_filter]

        keyword = self.search_var.get().strip()
        if keyword:
            products = [p for p in products
                        if keyword.lower() in p["product_name"].lower()
                        or keyword.lower() in p["category"].lower()
                        or (p["barcode"] and keyword in p["barcode"])]

        for p in products:
            if p.get("is_active", 1) == 0:
                tag = "inactive"
            elif p["stock"] <= p.get("low_stock_alert", 5):
                tag = "low_stock"
            else:
                tag = "normal"

            self.tree.insert("", "end", iid=str(p["product_id"]), tags=(tag,),
                             values=(p["product_id"], p["product_name"], p["category"],
                                     f"{p['price']:.2f}", p["stock"],
                                     p.get("low_stock_alert", 5),
                                     p["barcode"] or "—",
                                     "Active" if p.get("is_active", 1) == 1 else "Inactive"))
        self.status_var.set(f"{len(products)} product(s) loaded.")

    def _on_search(self):
        self._load_products()

    def _on_select(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return

        self.selected_product_id = int(selected[0])
        values = self.tree.item(selected[0])["values"]
        is_active = values[7] == "Active"

        self.form_vars["name"].set(values[1])
        self.form_vars["category"].set(values[2])
        self.form_vars["price"].set(values[3])
        self.form_vars["stock"].set(values[4])
        self.form_vars["low_alert"].set(values[5])
        self.form_vars["barcode"].set(values[6] if values[6] != "—" else "")

        product_details = get_product_with_details(self.selected_product_id)
        if product_details:
            self.form_vars["supplier"].set(product_details.get("supplier", ""))
            self.times_sold_var.set(f"Times sold: {product_details.get('total_quantity_sold', 0)}")
            self.last_updated_var.set(f"Last updated: {str(product_details.get('last_updated', '--'))[:16]}")

        self.update_btn.config(state="normal" if is_active else "disabled")
        self.delete_btn.config(state="normal" if is_active else "disabled")
        self.restore_btn.config(state="disabled" if is_active else "normal")

        if is_active:
            self.adjust_frame.pack(fill="x", pady=(0, 10))
        else:
            self.adjust_frame.pack_forget()

        self.adjust_var.set("0")
        self.adjust_reason_var.set("")
        self._clear_msg()

    def _add_product(self):
        if not self.form_vars["name"].get().strip():
            self._show_msg("Product name is required.", success=False); return
        price = self._parse_float(self.form_vars["price"].get())
        if price <= 0:
            self._show_msg("Price must be greater than 0.", success=False); return

        ok, msg = add_product(
            product_name=self.form_vars["name"].get(),
            category=self.form_vars["category"].get() or "General",
            price=price,
            barcode=self.form_vars["barcode"].get(),
            supplier=self.form_vars["supplier"].get(),
            initial_stock=self._parse_int(self.form_vars["stock"].get()),
            low_stock_alert=self._parse_int(self.form_vars["low_alert"].get(), default=5),
            user_id=self.current_user.get("user_id"),
        )
        if ok:
            self._show_msg(msg, success=True)
            self._load_products()
            self._clear_form()
        else:
            self._show_msg(msg, success=False)

    def _update_product(self):
        if not self.selected_product_id:
            return
        price = self._parse_float(self.form_vars["price"].get())
        if price <= 0:
            self._show_msg("Price must be greater than 0.", success=False); return

        ok, msg = update_product(
            product_id=self.selected_product_id,
            product_name=self.form_vars["name"].get(),
            category=self.form_vars["category"].get() or "General",
            price=price,
            barcode=self.form_vars["barcode"].get(),
            supplier=self.form_vars["supplier"].get(),
            low_stock_alert=self._parse_int(self.form_vars["low_alert"].get(), default=5),
            user_id=self.current_user.get("user_id"),
        )
        if ok:
            self._show_msg(msg, success=True)
            self._load_products()
        else:
            self._show_msg(msg, success=False)

    def _restore_product(self):
        if not self.selected_product_id:
            return
        name = self.form_vars["name"].get()
        if messagebox.askyesno("Confirm Restore", f"Restore '{name}' to active products?"):
            ok, msg = restore_product(self.selected_product_id)
            if ok:
                self._show_msg(msg, success=True)
                self._load_products()
                self._clear_form()
            else:
                self._show_msg(msg, success=False)

    def _delete_product(self):
        if not self.selected_product_id:
            return
        name = self.form_vars["name"].get()
        stock = self._parse_int(self.form_vars["stock"].get())
        msg = (f"'{name}' has {stock} units in stock. It will be deactivated.\n\nProceed?"
               if stock > 0 else f"Remove '{name}' from the product list?")
        if not messagebox.askyesno("Confirm Delete", msg):
            return
        ok, msg = delete_product(self.selected_product_id)
        if ok:
            self._show_msg(msg, success=True)
            self._clear_form()
            self._load_products()
        else:
            self._show_msg(msg, success=False)

    def _apply_stock_adjust(self):
        if not self.selected_product_id:
            return
        try:
            delta = int(self.adjust_var.get())
            if delta == 0:
                self._show_msg("Enter a non-zero value.", success=False); return
        except ValueError:
            self._show_msg("Enter a valid integer.", success=False); return

        reason = self.adjust_reason_var.get().strip() or "Manual adjustment"
        ok, result = adjust_stock(self.selected_product_id, delta, reason, self.current_user.get("user_id"))
        if ok:
            self._show_msg(f"Stock updated. New quantity: {result}", success=True)
            self._load_products()
            self.form_vars["stock"].set(str(result))
            self._refresh_product_stats()
        else:
            self._show_msg(result, success=False)

    def _refresh_product_stats(self):
        if self.selected_product_id:
            d = get_product_with_details(self.selected_product_id)
            if d:
                self.times_sold_var.set(f"Times sold: {d.get('total_quantity_sold', 0)}")
                self.last_updated_var.set(f"Last updated: {str(d.get('last_updated', '--'))[:16]}")

    def _supplier_restock_dialog(self):  # noqa: C901
        dialog = tk.Toplevel(self)
        dialog.title("Supplier Restock")
        dialog.geometry("700x560")
        dialog.configure(bg="#f0f2f5")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(True, True)
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 350
        y = (dialog.winfo_screenheight() // 2) - 280
        dialog.geometry(f"700x560+{x}+{y}")

        header = tk.Frame(dialog, bg="#1a1a2e", pady=10)
        header.pack(fill="x")
        tk.Label(header, text="  🚚  Supplier Restock", font=("Segoe UI", 13, "bold"),
                 bg="#1a1a2e", fg="white").pack(side="left", padx=10)

        info_row = tk.Frame(dialog, bg="#f0f2f5", pady=8)
        info_row.pack(fill="x", padx=16)
        tk.Label(info_row, text="Supplier Name:", font=("Segoe UI", 10, "bold"), bg="#f0f2f5").pack(side="left")
        supplier_var = tk.StringVar()
        tk.Entry(info_row, textvariable=supplier_var, font=("Segoe UI", 11), relief="flat",
                 bd=3, bg="white", width=25).pack(side="left", padx=(6, 20), ipady=5)
        tk.Label(info_row, text="Filter:", font=("Segoe UI", 10), bg="#f0f2f5").pack(side="left")
        filter_var = tk.StringVar(value="Low/Out of Stock")
        filter_combo = ttk.Combobox(info_row, textvariable=filter_var,
                                     values=["Low/Out of Stock", "All Products"],
                                     state="readonly", width=16)
        filter_combo.pack(side="left", padx=6)

        col_frame = tk.Frame(dialog, bg="#1a1a2e", pady=6)
        col_frame.pack(fill="x", padx=16)
        for text, w in [("Product", 220), ("Category", 100), ("Current Stock", 100),
                         ("Restock Qty", 100), ("Supplier", 120)]:
            tk.Label(col_frame, text=text, font=("Segoe UI", 9, "bold"), bg="#1a1a2e",
                     fg="#8892b0", width=w // 8, anchor="w").pack(side="left", padx=4)

        canvas_frame = tk.Frame(dialog, bg="#f0f2f5")
        canvas_frame.pack(fill="both", expand=True, padx=16, pady=4)
        canvas = tk.Canvas(canvas_frame, bg="#f0f2f5", highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#f0f2f5")
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        restock_rows = []

        def populate_rows(show_all=False):
            for w in scroll_frame.winfo_children():
                w.destroy()
            restock_rows.clear()
            products = get_all_products() if show_all else get_low_stock_products()
            if not products:
                tk.Label(scroll_frame, text="No products to display.", font=("Segoe UI", 10),
                         bg="#f0f2f5", fg="#888").pack(pady=20)
                return
            for i, p in enumerate(products):
                bg = "white" if i % 2 == 0 else "#f7f8fa"
                row = tk.Frame(scroll_frame, bg=bg, pady=4)
                row.pack(fill="x", padx=2, pady=1)
                tk.Label(row, text=p["product_name"][:28], font=("Segoe UI", 10),
                         bg=bg, anchor="w", width=28).pack(side="left", padx=4)
                tk.Label(row, text=p["category"][:12], font=("Segoe UI", 9),
                         bg=bg, fg="#666", width=12, anchor="w").pack(side="left", padx=4)
                current_qty = p.get("quantity", p.get("stock", 0))
                stock_color = ("#e74c3c" if current_qty == 0 else
                               "#e67e22" if current_qty <= p.get("low_stock_alert", 5) else "#27ae60")
                tk.Label(row, text=str(current_qty), font=("Segoe UI", 10, "bold"),
                         fg=stock_color, bg=bg, width=10).pack(side="left", padx=4)
                qty_var = tk.StringVar(value="10")
                tk.Entry(row, textvariable=qty_var, font=("Segoe UI", 10),
                         width=8, relief="flat", bd=2, bg="#fff9e6").pack(side="left", padx=4)
                row_sup_var = tk.StringVar(value=p.get("supplier", "") or "")
                tk.Entry(row, textvariable=row_sup_var, font=("Segoe UI", 9),
                         width=14, relief="flat", bd=2, bg="#f0f2f5").pack(side="left", padx=4)
                restock_rows.append((p, qty_var, row_sup_var))

        filter_combo.bind("<<ComboboxSelected>>",
                          lambda e: populate_rows(show_all=filter_var.get() == "All Products"))
        populate_rows(show_all=False)

        footer = tk.Frame(dialog, bg="#f0f2f5", pady=10)
        footer.pack(fill="x", padx=16)
        msg_var = tk.StringVar()
        tk.Label(footer, textvariable=msg_var, font=("Segoe UI", 9),
                 bg="#f0f2f5", fg="#27ae60").pack(side="left")

        def apply_restock():
            if not restock_rows:
                return
            global_supplier = supplier_var.get().strip()
            applied, errors = 0, []
            for product, qty_var, row_sup_var in restock_rows:
                try:
                    qty = int(qty_var.get())
                    if qty <= 0:
                        continue
                except ValueError:
                    errors.append(f"{product['product_name']}: invalid qty"); continue
                supplier_name = row_sup_var.get().strip() or global_supplier or "Supplier restock"
                ok, result = adjust_stock(product.get("product_id"), qty,
                                          f"Restock from {supplier_name}",
                                          self.current_user.get("user_id"))
                if ok:
                    applied += 1
                else:
                    errors.append(f"{product['product_name']}: {result}")
            if applied:
                msg_var.set(f"✓ Restocked {applied} product(s) successfully.")
                self._load_products()
                populate_rows(show_all=filter_var.get() == "All Products")
            if errors:
                messagebox.showwarning("Restock Warnings", "Some items had errors:\n\n" + "\n".join(errors[:10]))

        tk.Button(footer, text="✔  Apply Restock", font=("Segoe UI", 11, "bold"),
                  relief="flat", bg="#27ae60", fg="white", cursor="hand2",
                  pady=8, command=apply_restock).pack(side="right", padx=(8, 0))
        tk.Button(footer, text="Close", font=("Segoe UI", 10), relief="flat",
                  bg="#95a5a6", fg="white", cursor="hand2",
                  pady=8, command=dialog.destroy).pack(side="right")

    def _show_low_stock_report(self):
        low_stock = get_low_stock_products()
        if not low_stock:
            messagebox.showinfo("Low Stock Report", "No low stock products found.")
            return
        win = tk.Toplevel(self)
        win.title("Low Stock Report")
        win.geometry("500x400")
        text = tk.Text(win, font=("Courier", 10))
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert(tk.END, "=" * 50 + "\nLOW STOCK PRODUCTS REPORT\n" + "=" * 50 + "\n\n")
        for product in low_stock:
            text.insert(tk.END, f"Product:       {product['product_name']}\n")
            text.insert(tk.END, f"Category:      {product['category']}\n")
            text.insert(tk.END, f"Current Stock: {product['quantity']}\n")
            text.insert(tk.END, f"Alert Level:   {product['low_stock_alert']}\n")
            text.insert(tk.END, "-" * 30 + "\n")
        text.config(state="disabled")
        tk.Button(win, text="Close", command=win.destroy,
                  relief="flat", bg="#e94560", fg="white").pack(pady=10)

    def _check_low_stock_alert(self):
        low_stock = get_low_stock_products()
        if low_stock:
            self._show_msg(f"⚠️ {len(low_stock)} product(s) are low on stock!", success=False)

    def _export_to_csv(self):
        try:
            import csv
            filename = f"products_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            products = [{"ID": v[0], "Name": v[1], "Category": v[2], "Price": v[3],
                         "Stock": v[4], "Alert Level": v[5], "Barcode": v[6], "Status": v[7]}
                        for item in self.tree.get_children()
                        for v in [self.tree.item(item)["values"]]]
            if not products:
                self._show_msg("No products to export.", success=False); return
            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=products[0].keys())
                writer.writeheader()
                writer.writerows(products)
            self._show_msg(f"Exported to {filename}", success=True)
        except Exception as e:
            self._show_msg(f"Export failed: {str(e)}", success=False)

    def _bulk_import_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Bulk Import Products")
        dialog.geometry("500x400")
        dialog.transient(self)
        dialog.grab_set()
        tk.Label(dialog, text="Paste CSV data (Name,Category,Price,Stock,Barcode,Supplier)",
                 font=("Segoe UI", 10, "bold")).pack(pady=10)
        text_area = tk.Text(dialog, height=10, width=60)
        text_area.pack(padx=10, pady=5)
        tk.Label(dialog, text="Example:\nLaptop,Electronics,999.99,10,BAR001,TechSupplier",
                 font=("Courier", 8), fg="#666").pack()

        def process_import():
            data = text_area.get("1.0", tk.END).strip()
            if not data:
                return
            products = []
            for line in data.split("\n"):
                if line.strip():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 4:
                        try:
                            products.append({"name": parts[0],
                                             "category": parts[1] if len(parts) > 1 else "General",
                                             "price": float(parts[2]),
                                             "stock": int(parts[3]) if len(parts) > 3 else 0,
                                             "barcode": parts[4] if len(parts) > 4 else None,
                                             "supplier": parts[5] if len(parts) > 5 else None})
                        except ValueError:
                            continue
            if products:
                success, msg, count = bulk_import_products(products, self.current_user.get("user_id"))
                if success:
                    messagebox.showinfo("Import Complete", f"Imported {count} products successfully!")
                    self._load_products()
                    dialog.destroy()
                else:
                    messagebox.showerror("Import Error", msg)
            else:
                messagebox.showerror("Error", "No valid products found in input.")

        tk.Button(dialog, text="Import", command=process_import,
                  bg="#27ae60", fg="white", relief="flat", pady=5).pack(pady=10)
        tk.Button(dialog, text="Cancel", command=dialog.destroy, relief="flat", pady=5).pack()

    def _sort_tree(self, col):
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        try:
            items.sort(key=lambda t: float(t[0].replace(",", "").replace("GHS", "").strip()))
        except ValueError:
            items.sort()
        for index, (_, k) in enumerate(items):
            self.tree.move(k, "", index)

    def _clear_form(self):
        for var in self.form_vars.values():
            var.set("")
        self.selected_product_id = None
        self.update_btn.config(state="disabled")
        self.delete_btn.config(state="disabled")
        self.restore_btn.config(state="disabled")
        self.adjust_frame.pack_forget()
        self.times_sold_var.set("Times sold: --")
        self.last_updated_var.set("Last updated: --")
        self._clear_msg()
        self.tree.selection_remove(self.tree.selection())

    def _show_msg(self, msg: str, success: bool):
        self.msg_var.set(msg)
        self.msg_label.config(fg="#27ae60" if success else "#e74c3c")
        self.after(3000, self._clear_msg)

    def _clear_msg(self):
        self.msg_var.set("")

    def _parse_float(self, val: str, default=0.0) -> float:
        try:
            return float(val.strip())
        except (ValueError, AttributeError):
            return default

    def _parse_int(self, val: str, default=0) -> int:
        try:
            return int(val.strip())
        except (ValueError, AttributeError):
            return default