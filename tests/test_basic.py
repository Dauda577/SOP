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
