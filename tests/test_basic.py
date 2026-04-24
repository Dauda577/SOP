"""
Test suite for POS System.

Uses an isolated temporary database file for every test session so
the live pos_system.db is never touched during testing.
"""
import os
import tempfile
import pytest

# Set env vars before any app module is imported
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "AdminPass123"
os.environ["DEFAULT_MANAGER_PASSWORD"] = "ManagerPass123"
os.environ["DEFAULT_CASHIER_PASSWORD"] = "CashierPass123"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def db_conn():
    """
    Session-scoped temporary database.

    Uses a real temp file instead of sqlite:/// (in-memory) because
    in-memory SQLite databases are per-connection — each module that
    calls get_connection() would get a separate empty database.
    A shared temp file lets all connections see the same schema and data.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp.name}"

    from database.db import initialize_database, get_connection

    initialize_database()

    conn = get_connection()
    yield conn
    conn.close()

    try:
        os.unlink(tmp.name)
    except OSError:
        pass


@pytest.fixture
def sample_product(db_conn):
    """Insert a sample product + inventory row, clean up after the test."""
    import uuid

    cursor = db_conn.cursor()
    # Unique barcode per test run so retries never hit a UNIQUE constraint
    barcode = f"TEST-{uuid.uuid4().hex[:8].upper()}"
    cursor.execute(
        "INSERT INTO products (product_name, category, price, barcode) VALUES (?,?,?,?)",
        ("Test Widget", "Electronics", 49.99, barcode),
    )
    product_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO inventory (product_id, quantity, low_stock_alert) VALUES (?,?,?)",
        (product_id, 100, 5),
    )
    db_conn.commit()
    yield {
        "product_id": product_id,
        "product_name": "Test Widget",
        "price": 49.99,
        "quantity": 100,
    }
    # Delete child rows first to satisfy FK constraints
    cursor.execute(
        "DELETE FROM inventory_transactions WHERE product_id = ?", (product_id,)
    )
    cursor.execute("DELETE FROM inventory WHERE product_id = ?", (product_id,))
    cursor.execute("DELETE FROM products WHERE product_id = ?", (product_id,))
    db_conn.commit()


# ── Database tests ────────────────────────────────────────────────────────────


class TestDatabase:
    def test_connection(self, db_conn):
        """Basic connectivity check."""
        cursor = db_conn.cursor()
        cursor.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1

    def test_all_tables_exist(self, db_conn):
        """All expected tables must be present."""
        expected = {
            "users",
            "products",
            "inventory",
            "inventory_transactions",
            "customers",
            "sales",
            "sale_items",
            "payments",
        }
        cursor = db_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        actual = {row[0] for row in cursor.fetchall()}
        assert expected.issubset(actual), f"Missing tables: {expected - actual}"

    def test_foreign_keys_enabled(self, db_conn):
        """PRAGMA foreign_keys must be ON."""
        cursor = db_conn.cursor()
        cursor.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1


# ── Password hashing tests ────────────────────────────────────────────────────


class TestPasswordHashing:
    def test_hash_differs_from_plaintext(self):
        from database.db import hash_password

        assert hash_password("secret") != "secret"

    def test_correct_password_verifies(self):
        from database.db import hash_password, verify_password

        hashed = hash_password("correct_password")
        assert verify_password("correct_password", hashed) is True

    def test_wrong_password_fails(self):
        from database.db import hash_password, verify_password

        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_each_hash_is_unique(self):
        """bcrypt must generate a new salt every call."""
        from database.db import hash_password

        assert hash_password("same") != hash_password("same")

    def test_legacy_sha256_still_verifies(self):
        """Old SHA-256 hashes must still work during migration window."""
        import hashlib
        from database.db import verify_password

        legacy = hashlib.sha256("legacy_pass".encode()).hexdigest()
        assert verify_password("legacy_pass", legacy) is True

    def test_legacy_hash_detected(self):
        from database.db import hash_password, is_legacy_hash

        assert is_legacy_hash("a" * 64) is True  # looks like SHA-256
        assert is_legacy_hash(hash_password("x")) is False  # bcrypt


# ── Auth / login tests ────────────────────────────────────────────────────────


class TestAuth:
    def test_valid_login_returns_user(self):
        from modules.auth import login

        user = login("admin", "AdminPass123")
        assert user is not None
        assert user["username"] == "admin"
        assert user["role"] == "admin"

    def test_wrong_password_returns_none(self):
        from modules.auth import login

        assert login("admin", "wrongpassword") is None

    def test_unknown_user_returns_none(self):
        from modules.auth import login

        assert login("ghost", "anything") is None

    def test_role_permissions_cashier(self):
        from modules.auth import get_role_permissions

        perms = get_role_permissions("cashier")
        assert perms["process_sale"] is True
        assert perms["manage_users"] is False
        assert perms["manage_products"] is False

    def test_role_permissions_manager(self):
        from modules.auth import get_role_permissions

        perms = get_role_permissions("manager")
        assert perms["manage_products"] is True
        assert perms["view_reports"] is True
        assert perms["manage_users"] is False

    def test_role_permissions_admin(self):
        from modules.auth import get_role_permissions

        perms = get_role_permissions("admin")
        assert all(perms.values()), "Admin should have all permissions"

    def test_has_permission_hierarchy(self):
        from modules.auth import has_permission

        assert has_permission("admin", "cashier") is True
        assert has_permission("manager", "cashier") is True
        assert has_permission("cashier", "manager") is False
        assert has_permission("cashier", "admin") is False

    def test_create_user_invalid_role(self):
        from modules.auth import create_user

        ok, msg = create_user("newuser", "Pass1234!", "New User", "superadmin")
        assert ok is False
        assert "role" in msg.lower()

    def test_create_user_short_password(self):
        from modules.auth import create_user

        ok, msg = create_user("newuser", "short", "New User", "cashier")
        assert ok is False
        assert "8" in msg

    def test_auth_class_login_logout(self):
        from modules.auth import Auth

        auth = Auth()
        ok, msg = auth.login("admin", "AdminPass123")
        assert ok is True
        assert auth.get_current_user() is not None
        ok, _ = auth.logout()
        assert ok is True
        assert auth.get_current_user() is None


# ── Inventory tests ───────────────────────────────────────────────────────────


class TestInventory:
    def test_update_inventory_add(self, sample_product):
        from database.db import update_inventory, get_product_with_inventory

        pid = sample_product["product_id"]
        result = update_inventory(pid, 10, "restock", user_id=None)
        assert result is True
        updated = get_product_with_inventory(pid)
        assert updated["quantity"] == 110

    def test_update_inventory_remove(self, sample_product):
        from database.db import update_inventory, get_product_with_inventory

        pid = sample_product["product_id"]
        result = update_inventory(pid, -5, "sale", user_id=None)
        assert result is True
        updated = get_product_with_inventory(pid)
        assert updated["quantity"] == 95

    def test_inventory_cannot_go_negative(self, sample_product):
        from database.db import update_inventory

        pid = sample_product["product_id"]
        result = update_inventory(pid, -99999, "bad adjustment", user_id=None)
        assert result is False

    def test_get_product_with_inventory(self, sample_product):
        from database.db import get_product_with_inventory

        pid = sample_product["product_id"]
        product = get_product_with_inventory(pid)
        assert product is not None
        assert product["product_name"] == "Test Widget"
        assert "quantity" in product
        assert "low_stock_alert" in product

    def test_get_low_stock_products(self, db_conn, sample_product):
        from database.db import get_low_stock_products

        """A product with quantity <= low_stock_alert should appear in low stock."""

        pid = sample_product["product_id"]
        # Drive quantity to 3 (below alert of 5)
        cursor = db_conn.cursor()
        cursor.execute("UPDATE inventory SET quantity = 3 WHERE product_id = ?", (pid,))
        db_conn.commit()
        low = get_low_stock_products()
        ids = [p["product_id"] for p in low]
        assert pid in ids


class TestSales:
    def test_generate_receipt_without_payment_row(self, sample_product):
        from modules.sales import cart_add_item, generate_receipt, process_sale

        cart = []
        cart, ok, _ = cart_add_item(cart, sample_product, 1)
        assert ok is True

        ok, sale_id, change, msg = process_sale(
            cart=cart,
            user_id=1,
            payment_method="momo",
            amount_paid=sample_product["price"],
        )

        assert ok is True, msg
        assert change == 0

        receipt = generate_receipt(sale_id)

        assert "Receipt #" in receipt
        assert "Amount Paid:" in receipt
        assert f"GHS{sample_product['price']:>7.2f}" in receipt


class TestMoMoPayments:
    def test_validate_ghana_phone_detects_provider(self):
        from utils.momo_payments import validate_ghana_phone

        valid, normalized, provider = validate_ghana_phone("+233 24 123 4567")
        assert valid is True
        assert normalized == "0241234567"
        assert provider == "mtn"

    def test_initialize_momo_checkout_creates_pending_payment(
        self, db_conn, sample_product, monkeypatch
    ):
        from modules.sales import cart_add_item, process_sale
        from utils.momo_payments import initialize_momo_checkout

        cart = []
        cart, ok, _ = cart_add_item(cart, sample_product, 1)
        assert ok is True

        ok, sale_id, _, msg = process_sale(
            cart=cart,
            user_id=1,
            payment_method="momo",
            amount_paid=sample_product["price"],
        )
        assert ok is True, msg

        monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_xxx")
        monkeypatch.setattr(
            "utils.momo_payments._paystack_request",
            lambda method, path, payload=None: {
                "status": True,
                "message": "Authorization URL created",
                "data": {
                    "authorization_url": "https://checkout.paystack.test/mock",
                    "reference": "PSK-CHK-001",
                },
            },
        )
        monkeypatch.setattr(
            "utils.momo_payments._build_reference", lambda sale_id: "PSK-CHK-001"
        )

        success, reference, checkout_url, message = initialize_momo_checkout(
            amount=sample_product["price"],
            sale_id=sale_id,
            customer_phone="0241234567",
        )

        assert success is True
        assert reference == "PSK-CHK-001"
        assert checkout_url == "https://checkout.paystack.test/mock"
        assert "Authorization URL created" in message

        cursor = db_conn.cursor()
        cursor.execute(
            "SELECT status, provider FROM payments WHERE reference = ?",
            (reference,),
        )
        payment = cursor.fetchone()
        assert payment is not None
        assert payment[0] == "pending"
        assert payment[1] == "checkout"

    def test_paystack_momo_initiate_and_verify_updates_payment_row(
        self, db_conn, sample_product, monkeypatch
    ):
        from modules.sales import cart_add_item, process_sale
        from utils.momo_payments import initiate_momo_payment, verify_momo_payment

        cart = []
        cart, ok, _ = cart_add_item(cart, sample_product, 1)
        assert ok is True

        ok, sale_id, _, msg = process_sale(
            cart=cart,
            user_id=1,
            payment_method="momo",
            amount_paid=sample_product["price"],
        )
        assert ok is True, msg

        responses = [
            {
                "status": True,
                "message": "Charge attempted",
                "data": {"status": "pending", "reference": "PSK-REF-001"},
            },
            {
                "status": True,
                "message": "Verification successful",
                "data": {
                    "status": "success",
                    "amount": int(sample_product["price"] * 100),
                    "fees": 25,
                    "gateway_response": "Approved",
                    "metadata": {"local_provider": "mtn"},
                },
            },
        ]

        monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_xxx")

        def fake_paystack_request(method, path, payload=None):
            response = responses.pop(0)
            if path == "/charge":
                assert method == "POST"
                assert payload["currency"] == "GHS"
                assert payload["mobile_money"]["provider"] == "mtn"
            return response

        monkeypatch.setattr(
            "utils.momo_payments._paystack_request", fake_paystack_request
        )
        monkeypatch.setattr(
            "utils.momo_payments._build_reference", lambda sale_id: "PSK-REF-001"
        )

        success, reference, message = initiate_momo_payment(
            phone="0241234567",
            amount=sample_product["price"],
            sale_id=sale_id,
            provider="mtn",
        )
        assert success is True
        assert reference == "PSK-REF-001"
        assert "Charge" in message or "Payment" in message

        cursor = db_conn.cursor()
        cursor.execute("SELECT status FROM payments WHERE reference = ?", (reference,))
        payment = cursor.fetchone()
        assert payment is not None
        assert payment[0] == "pending"

        success, status, message = verify_momo_payment(reference)
        assert success is True
        assert status == "success"
        assert "Approved" in message

        cursor.execute(
            "SELECT status, amount_paid, fee FROM payments WHERE reference = ?",
            (reference,),
        )
        updated = cursor.fetchone()
        assert updated[0] == "completed"
        assert float(updated[1]) == sample_product["price"]
        assert float(updated[2]) == 0.25
