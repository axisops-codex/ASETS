"""Guarantees the database makes on its own, independent of the API.

If any of these break, no amount of careful application code saves the
books.
"""
import asyncpg
import pytest
import pytest_asyncio

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"


@pytest_asyncio.fixture(loop_scope="session")
async def admin(superuser_url):
    conn = await asyncpg.connect(superuser_url)
    async with conn.transaction():
        await conn.execute("SELECT set_config('asets.allow_audit_purge','on',true)")
        await conn.execute("TRUNCATE asets.users CASCADE")
    await conn.execute(
        """INSERT INTO asets.users (id, email, password_hash, name) VALUES
             ($1, 'schema_a@example.com', 'x', 'A'),
             ($2, 'schema_b@example.com', 'x', 'B')""", USER_A, USER_B)
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture(loop_scope="session")
async def app_conn(app_url):
    conn = await asyncpg.connect(app_url)
    try:
        yield conn
    finally:
        await conn.close()


class TestMoneyAndTotals:
    async def test_invoice_total_is_maintained_by_the_database(self, admin):
        client_id = await admin.fetchval(
            "INSERT INTO asets.clients (user_id, name) VALUES ($1,'C') RETURNING id", USER_A)
        invoice_id = await admin.fetchval(
            """INSERT INTO asets.invoices (user_id, client_id, number, issue_date)
               VALUES ($1,$2,'INV-0001', DATE '2026-05-01') RETURNING id""", USER_A, client_id)

        await admin.execute(
            """INSERT INTO asets.invoice_items (invoice_id,user_id,position,description,quantity,unit_price)
               VALUES ($1,$2,1,'Session',8,95.00), ($1,$2,2,'Report',1,180.50)""",
            invoice_id, USER_A)
        assert await admin.fetchval("SELECT total FROM asets.invoices WHERE id=$1", invoice_id) == 940.50

        await admin.execute("DELETE FROM asets.invoice_items WHERE invoice_id=$1 AND position=2",
                            invoice_id)
        assert await admin.fetchval("SELECT total FROM asets.invoices WHERE id=$1", invoice_id) == 760.00

    async def test_line_total_rounds_to_pennies(self, admin):
        client_id = await admin.fetchval(
            "INSERT INTO asets.clients (user_id, name) VALUES ($1,'C2') RETURNING id", USER_A)
        invoice_id = await admin.fetchval(
            """INSERT INTO asets.invoices (user_id, client_id, number, issue_date)
               VALUES ($1,$2,'INV-0002', DATE '2026-05-01') RETURNING id""", USER_A, client_id)
        # 1.5 hours at 33.333 would be 49.9995 in float; NUMERIC keeps it exact.
        await admin.execute(
            """INSERT INTO asets.invoice_items (invoice_id,user_id,position,quantity,unit_price)
               VALUES ($1,$2,1,1.5,33.33)""", invoice_id, USER_A)
        assert await admin.fetchval("SELECT total FROM asets.invoices WHERE id=$1", invoice_id) == 50.00


class TestConstraints:
    async def test_paid_invoice_requires_a_paid_date(self, admin):
        client_id = await admin.fetchval(
            "INSERT INTO asets.clients (user_id, name) VALUES ($1,'C') RETURNING id", USER_A)
        with pytest.raises(asyncpg.CheckViolationError):
            await admin.execute(
                """INSERT INTO asets.invoices (user_id, client_id, number, issue_date, status)
                   VALUES ($1,$2,'INV-9001', DATE '2026-05-01','paid')""", USER_A, client_id)

    async def test_due_date_cannot_precede_issue_date(self, admin):
        client_id = await admin.fetchval(
            "INSERT INTO asets.clients (user_id, name) VALUES ($1,'C') RETURNING id", USER_A)
        with pytest.raises(asyncpg.CheckViolationError):
            await admin.execute(
                """INSERT INTO asets.invoices (user_id, client_id, number, issue_date, due_date)
                   VALUES ($1,$2,'INV-9002', DATE '2026-05-01', DATE '2026-04-01')""",
                USER_A, client_id)

    async def test_invoice_numbers_are_unique_per_user(self, admin):
        client_id = await admin.fetchval(
            "INSERT INTO asets.clients (user_id, name) VALUES ($1,'C') RETURNING id", USER_A)
        await admin.execute(
            """INSERT INTO asets.invoices (user_id, client_id, number, issue_date)
               VALUES ($1,$2,'INV-7000', DATE '2026-05-01')""", USER_A, client_id)
        with pytest.raises(asyncpg.UniqueViolationError):
            await admin.execute(
                """INSERT INTO asets.invoices (user_id, client_id, number, issue_date)
                   VALUES ($1,$2,'INV-7000', DATE '2026-06-01')""", USER_A, client_id)

    async def test_expense_category_must_exist(self, admin):
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await admin.execute(
                """INSERT INTO asets.expenses (user_id, category, amount, expense_date)
                   VALUES ($1,'Bananas',5,DATE '2026-05-01')""", USER_A)

    async def test_negative_amounts_are_rejected(self, admin):
        with pytest.raises(asyncpg.CheckViolationError):
            await admin.execute(
                """INSERT INTO asets.expenses (user_id, category, amount, expense_date)
                   VALUES ($1,'Software',-5,DATE '2026-05-01')""", USER_A)

    async def test_email_uniqueness_ignores_case(self, admin):
        with pytest.raises(asyncpg.UniqueViolationError):
            await admin.execute(
                "INSERT INTO asets.users (email, password_hash) VALUES ('Schema_A@Example.com','x')")

    async def test_invoice_line_cannot_belong_to_another_users_invoice(self, admin):
        client_id = await admin.fetchval(
            "INSERT INTO asets.clients (user_id, name) VALUES ($1,'C') RETURNING id", USER_A)
        invoice_id = await admin.fetchval(
            """INSERT INTO asets.invoices (user_id, client_id, number, issue_date)
               VALUES ($1,$2,'INV-8000', DATE '2026-05-01') RETURNING id""", USER_A, client_id)
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await admin.execute(
                """INSERT INTO asets.invoice_items (invoice_id,user_id,position,quantity,unit_price)
                   VALUES ($1,$2,1,1,10)""", invoice_id, USER_B)


class TestRowLevelSecurity:
    async def test_without_a_tenant_nothing_is_visible(self, admin, app_conn):
        await admin.execute("INSERT INTO asets.clients (user_id, name) VALUES ($1,'Hidden')", USER_A)
        assert await app_conn.fetchval("SELECT count(*) FROM asets.clients") == 0

    async def test_each_tenant_sees_only_its_own_rows(self, admin, app_conn):
        await admin.execute("INSERT INTO asets.clients (user_id, name) VALUES ($1,'Only A')", USER_A)
        await admin.execute("INSERT INTO asets.clients (user_id, name) VALUES ($1,'Only B')", USER_B)

        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('asets.user_id', $1, true)", USER_A)
            names = [r["name"] for r in await app_conn.fetch("SELECT name FROM asets.clients")]
        assert names == ["Only A"]

    async def test_a_tenant_cannot_write_rows_owned_by_another(self, app_conn):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with app_conn.transaction():
                await app_conn.execute("SELECT set_config('asets.user_id', $1, true)", USER_A)
                await app_conn.execute(
                    "INSERT INTO asets.clients (user_id, name) VALUES ($1,'Sneaky')", USER_B)

    async def test_a_tenant_cannot_update_another_tenants_row(self, admin, app_conn):
        client_id = await admin.fetchval(
            "INSERT INTO asets.clients (user_id, name) VALUES ($1,'B only') RETURNING id", USER_B)
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('asets.user_id', $1, true)", USER_A)
            result = await app_conn.execute(
                "UPDATE asets.clients SET name='hacked' WHERE id=$1", client_id)
        assert result == "UPDATE 0"
        assert await admin.fetchval("SELECT name FROM asets.clients WHERE id=$1", client_id) == "B only"

    async def test_the_application_role_cannot_change_the_schema(self, app_conn):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await app_conn.execute("CREATE TABLE asets.nope (i int)")

    async def test_the_application_role_cannot_edit_reference_data(self, app_conn):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await app_conn.execute(
                "INSERT INTO asets.expense_categories (code,label,position,hmrc_field) "
                "VALUES ('X','X',99,'x')")


class TestAuditTrail:
    async def _submission(self, admin, status="accepted"):
        return await admin.fetchval(
            """INSERT INTO asets.hmrc_submissions
                 (user_id, submission_type, status, endpoint)
               VALUES ($1,'quarterly_update',$2::asets.hmrc_submission_status,'PUT /x')
               RETURNING id""", USER_A, status)

    async def test_a_finalised_submission_cannot_be_altered(self, admin):
        submission_id = await self._submission(admin, "accepted")
        with pytest.raises(asyncpg.RaiseError, match="final"):
            await admin.execute(
                "UPDATE asets.hmrc_submissions SET http_status = 200 WHERE id=$1", submission_id)

    async def test_a_pending_submission_may_be_completed_once(self, admin):
        submission_id = await self._submission(admin, "pending")
        await admin.execute(
            """UPDATE asets.hmrc_submissions
                  SET status='accepted', http_status=200, completed_at=now() WHERE id=$1""",
            submission_id)
        with pytest.raises(asyncpg.RaiseError):
            await admin.execute(
                "UPDATE asets.hmrc_submissions SET http_status=500 WHERE id=$1", submission_id)

    async def test_submissions_cannot_be_deleted(self, admin):
        submission_id = await self._submission(admin)
        with pytest.raises(asyncpg.RaiseError, match="append-only"):
            await admin.execute("DELETE FROM asets.hmrc_submissions WHERE id=$1", submission_id)

    async def test_the_purge_flag_does_not_survive_its_transaction(self, admin):
        """The capability is transaction-scoped, so a pooled connection
        cannot carry it into an unrelated request."""
        submission_id = await self._submission(admin)
        async with admin.transaction():
            await admin.execute("SELECT set_config('asets.allow_audit_purge','on',true)")
        with pytest.raises(asyncpg.RaiseError, match="append-only"):
            await admin.execute("DELETE FROM asets.hmrc_submissions WHERE id=$1", submission_id)

    async def test_account_erasure_may_purge_the_audit_trail(self, admin):
        await self._submission(admin)
        async with admin.transaction():
            await admin.execute("SELECT set_config('asets.allow_audit_purge','on',true)")
            await admin.execute("DELETE FROM asets.users WHERE id=$1", USER_A)
        assert await admin.fetchval(
            "SELECT count(*) FROM asets.hmrc_submissions WHERE user_id=$1", USER_A) == 0


class TestPoolResilience:
    """Cloud Run scales to zero and the pooler can reject a single
    connection; neither should take the service down."""

    async def test_connect_retries_before_giving_up(self, monkeypatch, app_url):
        """A pooler that rejects one connection must not kill the container."""
        import asyncpg
        from db import pool as pool_module

        calls = {"n": 0}
        real_create = pool_module._create

        async def flaky(url, min_size, max_size):
            calls["n"] += 1
            if calls["n"] < 3:
                raise asyncpg.InvalidPasswordError("stale pooler credentials")
            return await real_create(url, min_size, max_size)

        # monkeypatch restores the module's shared pool on teardown.
        monkeypatch.setattr(pool_module, "_create", flaky)
        monkeypatch.setattr(pool_module, "_pool", None)

        created = await pool_module.connect(app_url, max_size=2, base_delay=0)
        assert calls["n"] == 3
        await created.close()

    async def test_it_eventually_gives_up_with_a_clear_message(self, monkeypatch):
        import asyncpg
        import pytest as _pytest
        from db import pool as pool_module

        async def always_fails(*_):
            raise asyncpg.InvalidPasswordError("nope")

        monkeypatch.setattr(pool_module, "_create", always_fails)
        monkeypatch.setattr(pool_module, "_pool", None)

        with _pytest.raises(RuntimeError, match="could not reach the database"):
            await pool_module.connect("postgresql://nowhere/db", attempts=3, base_delay=0)
