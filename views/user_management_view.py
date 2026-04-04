import tkinter as tk
from tkinter import ttk, messagebox
from modules.auth import (
    get_all_users,
    create_user,
    update_user,
    deactivate_user,
    activate_user,
    reset_password,
    delete_user,
    get_role_permissions,
)
import logging

logger = logging.getLogger(__name__)


class UserManagementView(tk.Toplevel):
    ROLE_COLORS = {
        "admin": "#e94560",
        "manager": "#0f3460",
        "cashier": "#1b4332",
    }

    def __init__(self, parent, current_user: dict):
        super().__init__(parent)
        self.parent = parent
        self.current_user = current_user
        self.selected_user_id = None

        if current_user.get("role") != "admin":
            messagebox.showerror("Access Denied", "Only administrators can manage user accounts.")
            self.destroy()
            return

        self.title("User Management — Admin")
        self.geometry("1200x700")
        self.configure(bg="#f0f2f5")
        self.resizable(True, True)
        self.minsize(1050, 620)
        self._center_window()
        self._build_ui()
        self._load_users()

    def _center_window(self):
        self.update_idletasks()
        w, h = 1200, 700
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        topbar = tk.Frame(self, bg="#1a1a2e", pady=12)
        topbar.pack(fill="x")

        tk.Label(topbar, text="  👥  User Management",
                 font=("Segoe UI", 14, "bold"), bg="#1a1a2e", fg="white").pack(side="left", padx=10)

        tk.Label(topbar, text=f"Logged in as: {self.current_user['full_name']}  (admin)",
                 font=("Segoe UI", 9), bg="#1a1a2e", fg="#8892b0").pack(side="right", padx=16)

        self.show_inactive_var = tk.BooleanVar(value=False)
        tk.Checkbutton(topbar, text="Show Inactive Users", variable=self.show_inactive_var,
                       command=self._load_users, bg="#1a1a2e", fg="#8892b0",
                       selectcolor="#1a1a2e", activebackground="#1a1a2e",
                       font=("Segoe UI", 9)).pack(side="right", padx=10)

        body = tk.Frame(self, bg="#f0f2f5")
        body.pack(fill="both", expand=True, padx=16, pady=12)

        self._build_left_panel(body)
        self._build_right_panel(body)

    def _build_left_panel(self, parent):
        left = tk.Frame(parent, bg="#f0f2f5")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        search_row = tk.Frame(left, bg="#f0f2f5")
        search_row.pack(fill="x", pady=(0, 8))

        tk.Label(search_row, text="Search:", bg="#f0f2f5", font=("Segoe UI", 10)).pack(side="left")

        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *a: self._on_search())
        tk.Entry(search_row, textvariable=self.search_var, font=("Segoe UI", 11),
                 relief="flat", bd=4).pack(side="left", fill="x", expand=True, padx=(6, 8))

        tk.Button(search_row, text="⟳ Refresh", font=("Segoe UI", 9), relief="flat",
                  bg="#e94560", fg="white", cursor="hand2",
                  command=self._load_users).pack(side="left")

        cols = ("ID", "Username", "Full Name", "Role", "Status", "Created")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")

        col_widths = {"ID": 40, "Username": 120, "Full Name": 180,
                      "Role": 90, "Status": 80, "Created": 140}
        for col in cols:
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_tree(c))
            self.tree.column(col, width=col_widths[col], anchor="center")
        self.tree.column("Full Name", anchor="w")
        self.tree.column("Username", anchor="w")

        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        self.tree.tag_configure("inactive", background="#f5f5f5", foreground="#95a5a6")
        self.tree.tag_configure("admin", background="#fde8ec", foreground="#c0392b")
        self.tree.tag_configure("manager", background="#e8f0fe", foreground="#1a56db")
        self.tree.tag_configure("cashier", background="#f0fdf4", foreground="#166534")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)

        self.status_var = tk.StringVar(value="")
        tk.Label(left, textvariable=self.status_var, bg="#f0f2f5",
                 font=("Segoe UI", 9), fg="#555").pack(anchor="w", pady=(4, 0))

    def _build_right_panel(self, parent):
        # Outer container with fixed width
        right_outer = tk.Frame(parent, bg="white", relief="flat", bd=1, width=400)
        right_outer.pack(side="right", fill="y")
        right_outer.pack_propagate(False)

        # Scrollable canvas inside
        canvas = tk.Canvas(right_outer, bg="white", highlightthickness=0)
        scrollbar = tk.Scrollbar(right_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Inner frame that holds all content
        right = tk.Frame(canvas, bg="white", padx=20, pady=20)
        canvas_window = canvas.create_window((0, 0), window=right, anchor="nw")

        def on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(e):
            canvas.itemconfig(canvas_window, width=e.width)

        right.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        # Mouse wheel scrolling
        def on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        tk.Label(right, text="User Details", font=("Segoe UI", 13, "bold"),
                 bg="white", fg="#1a1a2e").pack(anchor="w", pady=(0, 14))

        form_fields = [("Username *", "username"), ("Full Name *", "full_name")]
        self.form_vars = {}
        self.form_entries = {}

        for label, key in form_fields:
            tk.Label(right, text=label, font=("Segoe UI", 9, "bold"),
                     bg="white", fg="#333", anchor="w").pack(fill="x")
            var = tk.StringVar()
            self.form_vars[key] = var
            entry = tk.Entry(right, textvariable=var, font=("Segoe UI", 11),
                             relief="flat", bd=3, bg="#f7f8fa")
            entry.pack(fill="x", ipady=6, pady=(2, 10))
            self.form_entries[key] = entry

        # Role selector
        tk.Label(right, text="Role *", font=("Segoe UI", 9, "bold"),
                 bg="white", fg="#333", anchor="w").pack(fill="x")
        self.role_var = tk.StringVar(value="cashier")
        role_frame = tk.Frame(right, bg="white")
        role_frame.pack(fill="x", pady=(2, 10))

        for role in ("cashier", "manager", "admin"):
            color = self.ROLE_COLORS[role]
            tk.Radiobutton(role_frame, text=role.capitalize(), variable=self.role_var,
                           value=role, font=("Segoe UI", 10), bg="white",
                           activebackground="white", cursor="hand2",
                           fg=color, selectcolor="white").pack(side="left", padx=(0, 16))

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=(4, 10))

        tk.Label(right, text="Password (required for new users)",
                 font=("Segoe UI", 9, "bold"), bg="white", fg="#333", anchor="w").pack(fill="x")

        self.form_vars["password"] = tk.StringVar()
        self.pw_entry = tk.Entry(right, textvariable=self.form_vars["password"],
                                  show="•", font=("Segoe UI", 11), relief="flat", bd=3, bg="#f7f8fa")
        self.pw_entry.pack(fill="x", ipady=6, pady=(2, 4))

        tk.Label(right, text="Confirm Password", font=("Segoe UI", 9, "bold"),
                 bg="white", fg="#333", anchor="w").pack(fill="x")
        self.form_vars["confirm_pw"] = tk.StringVar()
        self.confirm_pw_entry = tk.Entry(right, textvariable=self.form_vars["confirm_pw"],
                                          show="•", font=("Segoe UI", 11), relief="flat", bd=3, bg="#f7f8fa")
        self.confirm_pw_entry.pack(fill="x", ipady=6, pady=(2, 10))

        self.show_pw_var = tk.BooleanVar(value=False)
        tk.Checkbutton(right, text="Show passwords", variable=self.show_pw_var,
                       command=self._toggle_pw_visibility, bg="white", fg="#8892b0",
                       selectcolor="white", activebackground="white",
                       font=("Segoe UI", 9), cursor="hand2").pack(anchor="w", pady=(0, 12))

        btn_cfg = dict(font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2", pady=9)

        self.create_btn = tk.Button(right, text="➕  Create User", bg="#27ae60", fg="white",
                                     command=self._create_user, **btn_cfg)
        self.create_btn.pack(fill="x", pady=(4, 4))

        self.update_btn = tk.Button(right, text="✏️  Update Details", bg="#2980b9", fg="white",
                                     command=self._update_user, state="disabled", **btn_cfg)
        self.update_btn.pack(fill="x", pady=4)

        self.reset_pw_btn = tk.Button(right, text="🔑  Reset Password", bg="#f39c12", fg="white",
                                       command=self._reset_password, state="disabled", **btn_cfg)
        self.reset_pw_btn.pack(fill="x", pady=4)

        self.toggle_btn = tk.Button(right, text="🚫  Deactivate User", bg="#e67e22", fg="white",
                                     command=self._toggle_active, state="disabled", **btn_cfg)
        self.toggle_btn.pack(fill="x", pady=4)

        self.delete_btn = tk.Button(right, text="🗑️  Delete Permanently", bg="#e74c3c", fg="white",
                                     command=self._delete_user, state="disabled", **btn_cfg)
        self.delete_btn.pack(fill="x", pady=4)

        tk.Button(right, text="✖  Clear Form", bg="#95a5a6", fg="white",
                  command=self._clear_form, **btn_cfg).pack(fill="x", pady=(12, 4))

        self.perms_frame = tk.LabelFrame(right, text="Role Permissions Preview",
                                          bg="white", fg="#333", font=("Segoe UI", 9))
        self.perms_frame.pack(fill="x", pady=(8, 0))
        self.perms_text = tk.Text(self.perms_frame, height=6, font=("Courier New", 8),
                                   bg="#f7f8fa", relief="flat", state="disabled")
        self.perms_text.pack(fill="x", padx=5, pady=5)

        self.role_var.trace("w", lambda *a: self._update_perms_preview())
        self._update_perms_preview()

        self.msg_var = tk.StringVar()
        self.msg_label = tk.Label(right, textvariable=self.msg_var, font=("Segoe UI", 9),
                                   bg="white", wraplength=340)
        self.msg_label.pack(pady=(10, 0))

    def _load_users(self, users=None):
        self.tree.delete(*self.tree.get_children())
        if users is None:
            users = get_all_users(include_inactive=self.show_inactive_var.get())

        keyword = self.search_var.get().strip().lower()
        if keyword:
            users = [u for u in users if keyword in u["username"].lower()
                     or keyword in u["full_name"].lower() or keyword in u["role"].lower()]

        for u in users:
            is_active = u.get("is_active", 1) == 1
            tag = u["role"] if is_active else "inactive"
            self.tree.insert("", "end", iid=str(u["user_id"]), tags=(tag,),
                             values=(u["user_id"], u["username"], u["full_name"],
                                     u["role"].capitalize(),
                                     "Active" if is_active else "Inactive",
                                     u.get("created_at", "")[:16]))

        total = len(users)
        active_count = sum(1 for u in users if u.get("is_active", 1) == 1)
        self.status_var.set(f"{total} user(s) — {active_count} active, {total - active_count} inactive")

    def _on_search(self):
        self._load_users()

    def _on_select(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return

        self.selected_user_id = int(selected[0])
        values = self.tree.item(selected[0])["values"]
        is_active = values[4] == "Active"
        is_self = self.selected_user_id == self.current_user["user_id"]

        self.form_vars["username"].set(values[1])
        self.form_vars["full_name"].set(values[2])
        self.role_var.set(values[3].lower())
        self.form_vars["password"].set("")
        self.form_vars["confirm_pw"].set("")
        self.form_entries["username"].config(state="readonly")

        self.update_btn.config(state="normal")
        self.reset_pw_btn.config(state="normal")
        self.delete_btn.config(state="disabled" if is_self else "normal")

        if is_active:
            self.toggle_btn.config(text="🚫  Deactivate User", bg="#e67e22",
                                    state="disabled" if is_self else "normal")
        else:
            self.toggle_btn.config(text="✅  Activate User", bg="#27ae60", state="normal")

        self._update_perms_preview()
        self._clear_msg()

    def _on_double_click(self, event=None):
        self.form_entries["full_name"].focus()

    def _create_user(self):
        username = self.form_vars["username"].get().strip()
        full_name = self.form_vars["full_name"].get().strip()
        role = self.role_var.get()
        password = self.form_vars["password"].get()
        confirm_pw = self.form_vars["confirm_pw"].get()

        if not username:
            self._show_msg("Username is required.", success=False); return
        if not full_name:
            self._show_msg("Full name is required.", success=False); return
        if not password:
            self._show_msg("Password is required for new users.", success=False); return
        if password != confirm_pw:
            self._show_msg("Passwords do not match.", success=False); return
        if len(password) < 8:
            self._show_msg("Password must be at least 8 characters.", success=False); return

        ok, msg = create_user(username, password, full_name, role)
        if ok:
            self._show_msg(msg, success=True)
            self._clear_form()
            self._load_users()
            logger.info("User '%s' created by admin '%s'", username, self.current_user["full_name"])
        else:
            self._show_msg(msg, success=False)

    def _update_user(self):
        if not self.selected_user_id:
            return
        full_name = self.form_vars["full_name"].get().strip()
        role = self.role_var.get()
        if not full_name:
            self._show_msg("Full name cannot be empty.", success=False); return
        if self.selected_user_id == self.current_user["user_id"] and role != "admin":
            if not messagebox.askyesno("Warning",
                "You are about to change your own role away from admin.\nYou will lose admin access. Proceed?"):
                return
        ok, msg = update_user(self.selected_user_id, full_name=full_name, role=role)
        if ok:
            self._show_msg(msg, success=True)
            self._load_users()
        else:
            self._show_msg(msg, success=False)

    def _reset_password(self):
        if not self.selected_user_id:
            return
        password = self.form_vars["password"].get()
        confirm_pw = self.form_vars["confirm_pw"].get()
        if not password:
            self._show_msg("Enter a new password.", success=False); return
        if password != confirm_pw:
            self._show_msg("Passwords do not match.", success=False); return
        if len(password) < 8:
            self._show_msg("Password must be at least 8 characters.", success=False); return
        username = self.form_vars["username"].get()
        if not messagebox.askyesno("Confirm Reset", f"Reset password for '{username}'?"):
            return
        ok, msg = reset_password(self.selected_user_id, password)
        if ok:
            self._show_msg(msg, success=True)
            self.form_vars["password"].set("")
            self.form_vars["confirm_pw"].set("")
        else:
            self._show_msg(msg, success=False)

    def _toggle_active(self):
        if not self.selected_user_id:
            return
        username = self.form_vars["username"].get()
        values = self.tree.item(str(self.selected_user_id))["values"]
        is_active = values[4] == "Active"
        action = "deactivate" if is_active else "reactivate"
        if not messagebox.askyesno(f"Confirm {action.capitalize()}",
                                    f"{action.capitalize()} account for '{username}'?"):
            return
        ok, msg = deactivate_user(self.selected_user_id) if is_active else activate_user(self.selected_user_id)
        if ok:
            self._show_msg(msg, success=True)
            self._clear_form()
            self._load_users()
        else:
            self._show_msg(msg, success=False)

    def _delete_user(self):
        if not self.selected_user_id:
            return
        if self.selected_user_id == self.current_user["user_id"]:
            self._show_msg("You cannot delete your own account.", success=False); return
        username = self.form_vars["username"].get()
        if not messagebox.askyesno("Confirm Permanent Delete",
                                    f"Permanently delete '{username}'?\nThis cannot be undone."):
            return
        ok, msg = delete_user(self.selected_user_id)
        if ok:
            self._show_msg(msg, success=True)
            self._clear_form()
            self._load_users()
        else:
            self._show_msg(msg, success=False)

    def _update_perms_preview(self):
        role = self.role_var.get()
        perms = get_role_permissions(role)
        lines = [f" {'✓' if v else '✗'}  {k.replace('_', ' ').title()}" for k, v in perms.items()]
        self.perms_text.config(state="normal")
        self.perms_text.delete("1.0", tk.END)
        self.perms_text.insert("1.0", "\n".join(lines))
        self.perms_text.config(state="disabled")

    def _toggle_pw_visibility(self):
        show = "" if self.show_pw_var.get() else "•"
        self.pw_entry.config(show=show)
        self.confirm_pw_entry.config(show=show)

    def _clear_form(self):
        for var in self.form_vars.values():
            var.set("")
        self.role_var.set("cashier")
        self.selected_user_id = None
        self.form_entries["username"].config(state="normal")
        self.update_btn.config(state="disabled")
        self.reset_pw_btn.config(state="disabled")
        self.toggle_btn.config(text="🚫  Deactivate User", bg="#e67e22", state="disabled")
        self.delete_btn.config(state="disabled")
        self._update_perms_preview()
        self._clear_msg()
        self.tree.selection_remove(self.tree.selection())

    def _show_msg(self, msg: str, success: bool):
        self.msg_var.set(msg)
        self.msg_label.config(fg="#27ae60" if success else "#e74c3c")
        self.after(4000, self._clear_msg)

    def _clear_msg(self):
        self.msg_var.set("")

    def _sort_tree(self, col):
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        try:
            items.sort(key=lambda t: float(t[0]))
        except ValueError:
            items.sort()
        for index, (_, k) in enumerate(items):
            self.tree.move(k, "", index)