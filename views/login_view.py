import tkinter as tk
from tkinter import messagebox
from modules.auth import login
import logging

logger = logging.getLogger(__name__)


class LoginView(tk.Tk):
    def __init__(self, on_success):
        super().__init__()
        self.on_success = on_success
        self.login_attempts = 0
        self.max_attempts = 3

        self.title("POS System - Login")
        self.geometry("440x580")
        self.resizable(True, True)
        self.minsize(440, 580)
        self.configure(bg="#1a1a2e")
        self._center_window()
        self._build_ui()
        self.username_entry.focus()

    def _center_window(self):
        self.update_idletasks()
        w, h = 440, 580
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg="#16213e", pady=24)
        header.pack(fill="x")

        self.icon_label = tk.Label(
            header, text="🛒", font=("Segoe UI Emoji", 36), bg="#16213e", fg="white"
        )
        self.icon_label.pack()
        self.icon_label.bind(
            "<Enter>", lambda e: self.icon_label.config(font=("Segoe UI Emoji", 42))
        )
        self.icon_label.bind(
            "<Leave>", lambda e: self.icon_label.config(font=("Segoe UI Emoji", 36))
        )

        tk.Label(
            header,
            text="Point of Sale",
            font=("Segoe UI", 20, "bold"),
            bg="#16213e",
            fg="white",
        ).pack()
        tk.Label(
            header,
            text="Sign in to continue",
            font=("Segoe UI", 10),
            bg="#16213e",
            fg="#8892b0",
        ).pack(pady=(4, 0))

        # Form card
        card = tk.Frame(self, bg="#16213e", padx=40, pady=20)
        card.pack(fill="both", expand=True, padx=30, pady=10)

        # Username
        tk.Label(
            card,
            text="Username",
            font=("Segoe UI", 10, "bold"),
            bg="#16213e",
            fg="#ccd6f6",
            anchor="w",
        ).pack(fill="x")
        self.username_var = tk.StringVar()
        self.username_entry = tk.Entry(
            card,
            textvariable=self.username_var,
            font=("Segoe UI", 12),
            bg="#0f3460",
            fg="white",
            insertbackground="white",
            relief="flat",
            bd=0,
        )
        self.username_entry.pack(fill="x", ipady=10, pady=(4, 14))

        # Password
        tk.Label(
            card,
            text="Password",
            font=("Segoe UI", 10, "bold"),
            bg="#16213e",
            fg="#ccd6f6",
            anchor="w",
        ).pack(fill="x")
        self.password_var = tk.StringVar()
        self.password_entry = tk.Entry(
            card,
            textvariable=self.password_var,
            font=("Segoe UI", 12),
            show="•",
            bg="#0f3460",
            fg="white",
            insertbackground="white",
            relief="flat",
            bd=0,
        )
        self.password_entry.pack(fill="x", ipady=10, pady=(4, 4))

        # Show password
        self.show_pw = tk.BooleanVar(value=False)
        tk.Checkbutton(
            card,
            text="Show password",
            variable=self.show_pw,
            command=self._toggle_password,
            bg="#16213e",
            fg="#8892b0",
            selectcolor="#16213e",
            activebackground="#16213e",
            activeforeground="#8892b0",
            font=("Segoe UI", 9),
            cursor="hand2",
        ).pack(anchor="w", pady=(0, 8))

        # Error label
        self.error_var = tk.StringVar()
        tk.Label(
            card,
            textvariable=self.error_var,
            font=("Segoe UI", 9),
            bg="#16213e",
            fg="#ff6b6b",
            wraplength=340,
        ).pack(pady=(0, 6))

        # Login button
        self.login_btn = tk.Button(
            card,
            text="Sign In",
            font=("Segoe UI", 12, "bold"),
            bg="#e94560",
            fg="white",
            activebackground="#c73652",
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            pady=10,
            command=self._attempt_login,
        )
        self.login_btn.pack(fill="x")

        self.loading_label = tk.Label(
            card,
            text="Signing in...",
            font=("Segoe UI", 10),
            bg="#16213e",
            fg="#e94560",
        )

        # Remember me
        self.remember_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            card,
            text="Remember me",
            variable=self.remember_var,
            bg="#16213e",
            fg="#8892b0",
            selectcolor="#16213e",
            activebackground="#16213e",
            activeforeground="#8892b0",
            font=("Segoe UI", 9),
            cursor="hand2",
        ).pack(anchor="w", pady=(8, 0))

        self._load_saved_credentials()

        # Footer — compact single line
        footer = tk.Frame(self, bg="#1a1a2e")
        footer.pack(pady=(0, 8))
        tk.Label(
            footer,
            text="admin/[your password]  •  manager/[password]  •  cashier/[password]",
            font=("Segoe UI", 7),
            bg="#1a1a2e",
            fg="#4a4a6a",
        ).pack()
        tk.Label(
            footer,
            text="POS System v1.0",
            font=("Segoe UI", 7),
            bg="#1a1a2e",
            fg="#4a4a6a",
        ).pack(pady=(2, 0))

        self.bind("<Return>", lambda e: self._attempt_login())
        self.bind("<Escape>", lambda e: self._quit_app())

    def _toggle_password(self):
        if self.password_entry.get():
            self.password_entry.config(show="" if self.show_pw.get() else "•")

    def _save_credentials(self, username, password):
        if self.remember_var.get():
            try:
                import json, os

                cred_file = os.path.expanduser("~/.pos_credentials.json")
                with open(cred_file, "w") as f:
                    json.dump(
                        {"username": username, "password": password, "remember": True},
                        f,
                    )
            except Exception as e:
                logger.error("Error saving credentials: %s", e)
        else:
            self._clear_saved_credentials()

    def _load_saved_credentials(self):
        try:
            import json, os

            cred_file = os.path.expanduser("~/.pos_credentials.json")
            if os.path.exists(cred_file):
                with open(cred_file, "r") as f:
                    data = json.load(f)
                    if data.get("remember"):
                        self.username_var.set(data.get("username", ""))
                        self.password_var.set(data.get("password", ""))
                        self.remember_var.set(True)
        except Exception as e:
            logger.error("Error loading credentials: %s", e)

    def _clear_saved_credentials(self):
        try:
            import os

            cred_file = os.path.expanduser("~/.pos_credentials.json")
            if os.path.exists(cred_file):
                os.remove(cred_file)
        except Exception as e:
            logger.error("Error clearing credentials: %s", e)

    def _attempt_login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()

        if not username or not password:
            self.error_var.set("Please enter both username and password.")
            return

        self.login_btn.pack_forget()
        self.loading_label.pack(fill="x", pady=(10, 0))
        self.update()

        try:
            user = login(username, password)
            if user:
                self._save_credentials(username, password)
                logger.info("Successful login: %s (%s)", username, user["role"])
                self.destroy()
                self.on_success(user)
            else:
                self.login_attempts += 1
                remaining = self.max_attempts - self.login_attempts
                if remaining > 0:
                    self.error_var.set(
                        f"Invalid username or password. {remaining} attempt(s) remaining."
                    )
                    logger.warning(
                        "Failed login attempt %d/%d for %s",
                        self.login_attempts,
                        self.max_attempts,
                        username,
                    )
                else:
                    self.error_var.set(
                        "Maximum login attempts exceeded. Please restart."
                    )
                    self.login_btn.config(state="disabled")
                    messagebox.showerror(
                        "Too Many Attempts",
                        "Maximum login attempts exceeded. The application will now close.",
                    )
                    self.after(3000, self._quit_app)
                self.password_var.set("")
                self.password_entry.focus()
        except Exception as e:
            logger.error("Login error: %s", e)
            self.error_var.set(f"An error occurred: {str(e)}")
        finally:
            if self.winfo_exists():
                try:
                    self.loading_label.pack_forget()
                except Exception:
                    pass
                try:
                    self.login_btn.pack(fill="x")
                except Exception:
                    pass
                self.update()

    def _quit_app(self):
        logger.info("Application closed by user")
        self.destroy()

    def on_closing(self):
        if messagebox.askokcancel("Quit", "Do you want to quit the application?"):
            logger.info("Application closed by user")
            self.destroy()
