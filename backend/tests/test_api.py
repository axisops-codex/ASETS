"""The HTTP contract the mobile app depends on.

Field names and shapes here are what ships in the store build — they are
asserted deliberately, not incidentally.
"""
import pytest


class TestAuth:
    async def test_registration_returns_a_token_and_profile(self, api, clean_db):
        resp = await api.post("/api/auth/register",
                              json={"email": "New@Example.com", "password": "secret123", "name": "Dr New"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["access_token"]
        user = body["user"]
        assert user["email"] == "new@example.com"          # normalised
        assert user["bank"]["reference"] == "Please use the invoice number"
        assert user["services"] == []
        assert user["settings"]["theme"] == "system"
        assert "password_hash" not in user

    async def test_duplicate_registration_is_rejected(self, api, user):
        resp = await api.post("/api/auth/register",
                              json={"email": user["email"], "password": "secret123"})
        assert resp.status_code == 409

    async def test_login_is_case_insensitive_on_email(self, api, user):
        resp = await api.post("/api/auth/login",
                              json={"email": user["email"].upper(), "password": "secret123"})
        assert resp.status_code == 200, resp.text

    async def test_wrong_password_is_rejected(self, api, user):
        resp = await api.post("/api/auth/login",
                              json={"email": user["email"], "password": "nope"})
        assert resp.status_code == 401

    async def test_short_password_is_rejected(self, api, clean_db):
        resp = await api.post("/api/auth/register", json={"email": "s@example.com", "password": "abc"})
        assert resp.status_code == 422

    async def test_protected_routes_need_a_token(self, api):
        assert (await api.get("/api/clients")).status_code == 403
        assert (await api.get("/api/clients",
                              headers={"Authorization": "Bearer nonsense"})).status_code == 401


class TestProfile:
    async def test_profile_fields_round_trip(self, api, user):
        resp = await api.put("/api/auth/profile", headers=user["headers"], json={
            "business_name": "Reviewer Psychology", "city": "London", "postcode": "W1G 6AB",
            "utr": "1234567890"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["business_name"] == "Reviewer Psychology"

    async def test_bank_details_are_nested_the_way_the_app_expects(self, api, user):
        resp = await api.put("/api/auth/profile", headers=user["headers"], json={
            "bank": {"bank_name": "Barclays", "account_name": "S R", "sort_code": "20-00-00",
                     "account_number": "12345678", "reference": "Invoice number please"}})
        bank = resp.json()["bank"]
        assert bank["bank_name"] == "Barclays"
        assert bank["reference"] == "Invoice number please"

    async def test_services_replace_wholesale_and_deduplicate(self, api, user):
        await api.put("/api/auth/profile", headers=user["headers"], json={
            "services": [{"name": "CBT session", "price": 95, "unit": "session"},
                         {"name": "cbt SESSION", "price": 99, "unit": "hour"}]})
        resp = await api.get("/api/auth/me", headers=user["headers"])
        services = resp.json()["services"]
        assert len(services) == 1
        assert services[0]["price"] == 99.0

        await api.put("/api/auth/profile", headers=user["headers"], json={"services": []})
        assert (await api.get("/api/auth/me", headers=user["headers"])).json()["services"] == []

    async def test_settings_persist(self, api, user):
        await api.put("/api/auth/profile", headers=user["headers"],
                      json={"settings": {"theme": "dark", "cards": ["hmrc"]}})
        settings = (await api.get("/api/auth/me", headers=user["headers"])).json()["settings"]
        assert settings == {"theme": "dark", "cards": ["hmrc"]}


class TestClients:
    async def test_create_list_update_delete(self, api, user):
        created = await api.post("/api/clients", headers=user["headers"],
                                 json={"name": "Northgate Ltd", "email": "a@b.com", "rate": 95})
        assert created.status_code == 200, created.text
        client_id = created.json()["id"]
        assert created.json()["rate"] == 95.0

        listed = await api.get("/api/clients", headers=user["headers"])
        assert [c["id"] for c in listed.json()] == [client_id]

        updated = await api.put(f"/api/clients/{client_id}", headers=user["headers"],
                                json={"name": "Northgate Wellbeing", "rate": 110})
        assert updated.json()["name"] == "Northgate Wellbeing"

        await api.delete(f"/api/clients/{client_id}", headers=user["headers"])
        assert (await api.get("/api/clients", headers=user["headers"])).json() == []

    async def test_updating_a_missing_client_is_a_404(self, api, user):
        resp = await api.put("/api/clients/00000000-0000-0000-0000-000000000000",
                             headers=user["headers"], json={"name": "Ghost"})
        assert resp.status_code == 404


async def _client_id(api, user, name="Client") -> str:
    resp = await api.post("/api/clients", headers=user["headers"], json={"name": name})
    return resp.json()["id"]


class TestInvoices:
    async def test_numbering_is_sequential_per_user(self, api, user):
        cid = await _client_id(api, user)
        numbers = []
        for _ in range(3):
            resp = await api.post("/api/invoices", headers=user["headers"], json={
                "client_id": cid, "issue_date": "2026-05-01",
                "items": [{"description": "Session", "quantity": 1, "unit_price": 95}]})
            assert resp.status_code == 200, resp.text
            numbers.append(resp.json()["number"])
        assert numbers == ["INV-0001", "INV-0002", "INV-0003"]

    async def test_total_is_computed_from_the_lines(self, api, user):
        cid = await _client_id(api, user)
        resp = await api.post("/api/invoices", headers=user["headers"], json={
            "client_id": cid, "issue_date": "2026-05-01", "due_date": "2026-05-31",
            "items": [{"description": "Session", "quantity": 8, "unit_price": 95},
                      {"description": "Report", "quantity": 1, "unit_price": 180.5}]})
        body = resp.json()
        assert body["total"] == 940.50
        assert body["client_name"] == "Client"
        assert len(body["items"]) == 2
        assert body["items"][0] == {"description": "Session", "quantity": 8.0, "unit_price": 95.0}

    async def test_editing_lines_replaces_them_and_recomputes(self, api, user):
        cid = await _client_id(api, user)
        created = await api.post("/api/invoices", headers=user["headers"], json={
            "client_id": cid, "issue_date": "2026-05-01",
            "items": [{"description": "Session", "quantity": 8, "unit_price": 95}]})
        invoice_id = created.json()["id"]

        updated = await api.put(f"/api/invoices/{invoice_id}", headers=user["headers"], json={
            "items": [{"description": "Session", "quantity": 2, "unit_price": 95}]})
        assert updated.json()["total"] == 190.00
        assert len(updated.json()["items"]) == 1

    async def test_marking_paid_sets_and_clears_the_paid_date(self, api, user):
        cid = await _client_id(api, user)
        created = await api.post("/api/invoices", headers=user["headers"], json={
            "client_id": cid, "issue_date": "2026-05-01",
            "items": [{"description": "Session", "quantity": 1, "unit_price": 95}]})
        invoice_id = created.json()["id"]

        paid = await api.put(f"/api/invoices/{invoice_id}", headers=user["headers"],
                             json={"status": "paid"})
        assert paid.json()["status"] == "paid"
        assert paid.json()["paid_date"] is not None

        reverted = await api.put(f"/api/invoices/{invoice_id}", headers=user["headers"],
                                 json={"status": "sent"})
        assert reverted.json()["paid_date"] is None

    async def test_an_invoice_needs_a_real_client(self, api, user):
        resp = await api.post("/api/invoices", headers=user["headers"], json={
            "client_id": "00000000-0000-0000-0000-000000000000", "issue_date": "2026-05-01",
            "items": [{"description": "x", "quantity": 1, "unit_price": 1}]})
        assert resp.status_code == 404

    async def test_deleted_invoices_disappear_from_the_list(self, api, user):
        cid = await _client_id(api, user)
        created = await api.post("/api/invoices", headers=user["headers"], json={
            "client_id": cid, "issue_date": "2026-05-01",
            "items": [{"description": "Session", "quantity": 1, "unit_price": 95}]})
        await api.delete(f"/api/invoices/{created.json()['id']}", headers=user["headers"])
        assert (await api.get("/api/invoices", headers=user["headers"])).json() == []


class TestExpenses:
    async def test_create_and_list_uses_the_date_field(self, api, user):
        resp = await api.post("/api/expenses", headers=user["headers"], json={
            "category": "Supervision", "description": "Monthly supervision",
            "amount": 120.0, "date": "2026-05-14"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["date"] == "2026-05-14"
        assert body["amount"] == 120.0

        listed = (await api.get("/api/expenses", headers=user["headers"])).json()
        assert listed[0]["category"] == "Supervision"

    async def test_an_unknown_category_is_a_clear_400(self, api, user):
        resp = await api.post("/api/expenses", headers=user["headers"], json={
            "category": "Yachts", "amount": 10000, "date": "2026-05-14"})
        assert resp.status_code == 400
        assert "Yachts" in resp.json()["detail"]

    async def test_delete_removes_it_from_the_list(self, api, user):
        created = await api.post("/api/expenses", headers=user["headers"], json={
            "category": "Software", "amount": 24.0, "date": "2026-05-01"})
        await api.delete(f"/api/expenses/{created.json()['id']}", headers=user["headers"])
        assert (await api.get("/api/expenses", headers=user["headers"])).json() == []


class TestTenantIsolation:
    """The database enforces this; these tests prove the API cannot be
    talked out of it."""

    async def test_one_user_never_sees_anothers_records(self, api, user, other_user):
        cid = await _client_id(api, user, "A's client")
        await api.post("/api/invoices", headers=user["headers"], json={
            "client_id": cid, "issue_date": "2026-05-01",
            "items": [{"description": "Session", "quantity": 1, "unit_price": 95}]})
        await api.post("/api/expenses", headers=user["headers"],
                       json={"category": "Software", "amount": 10, "date": "2026-05-01"})

        assert (await api.get("/api/clients", headers=other_user["headers"])).json() == []
        assert (await api.get("/api/invoices", headers=other_user["headers"])).json() == []
        assert (await api.get("/api/expenses", headers=other_user["headers"])).json() == []

    async def test_guessing_an_id_does_not_help(self, api, user, other_user):
        cid = await _client_id(api, user, "A's client")
        invoice_id = (await api.post("/api/invoices", headers=user["headers"], json={
            "client_id": cid, "issue_date": "2026-05-01",
            "items": [{"description": "Session", "quantity": 1, "unit_price": 95}]})).json()["id"]

        assert (await api.put(f"/api/invoices/{invoice_id}", headers=other_user["headers"],
                              json={"status": "paid"})).status_code == 404
        assert (await api.put(f"/api/clients/{cid}", headers=other_user["headers"],
                              json={"name": "stolen"})).status_code == 404
        # And the original is untouched.
        assert (await api.get("/api/invoices", headers=user["headers"])).json()[0]["status"] == "sent"

    async def test_deleting_an_account_erases_only_that_account(self, api, user, other_user):
        await _client_id(api, user, "A's client")
        await api.post("/api/clients", headers=other_user["headers"], json={"name": "B's client"})

        resp = await api.delete("/api/auth/account", headers=user["headers"])
        assert resp.status_code == 200 and resp.json()["deleted"] is True

        assert (await api.get("/api/auth/me", headers=user["headers"])).status_code == 401
        assert (await api.post("/api/auth/login",
                               json={"email": user["email"], "password": "secret123"})).status_code == 401
        remaining = (await api.get("/api/clients", headers=other_user["headers"])).json()
        assert [c["name"] for c in remaining] == ["B's client"]


class TestReporting:
    @staticmethod
    async def _seed(api, user):
        cid = await _client_id(api, user)
        await api.post("/api/invoices", headers=user["headers"], json={
            "client_id": cid, "issue_date": "2026-05-01", "status": "paid",
            "items": [{"description": "Session", "quantity": 10, "unit_price": 100}]})
        await api.post("/api/invoices", headers=user["headers"], json={
            "client_id": cid, "issue_date": "2026-06-01", "status": "sent",
            "items": [{"description": "Session", "quantity": 5, "unit_price": 100}]})
        await api.post("/api/expenses", headers=user["headers"], json={
            "category": "Supervision", "amount": 300, "date": "2026-05-20"})
        # Outside the window on purpose.
        await api.post("/api/expenses", headers=user["headers"], json={
            "category": "Software", "amount": 999, "date": "2025-01-01"})

    async def test_summary_totals_and_tax(self, api, user):
        await self._seed(api, user)
        resp = await api.get("/api/summary", headers=user["headers"],
                             params={"start": "2026-04-06", "end": "2027-04-05"})
        body = resp.json()
        assert body["sales"] == 1500.0
        assert body["paid"] == 1000.0
        assert body["outstanding"] == 500.0
        assert body["expenses"] == 300.0
        assert body["net"] == 1200.0
        # Under the personal allowance, so no tax is due.
        assert body["tax"]["profit"] == 1200.0
        assert body["tax"]["total_due"] == 0.0
        assert body["expenses_by_category"] == [{"category": "Supervision", "amount": 300.0}]

    async def test_cashflow_buckets_by_month(self, api, user):
        await self._seed(api, user)
        body = (await api.get("/api/summary", headers=user["headers"],
                              params={"start": "2026-04-06", "end": "2027-04-05",
                                      "group": "month"})).json()
        buckets = {c["bucket"]: c for c in body["cashflow"]}
        assert buckets["2026-05"]["income"] == 1000.0
        assert buckets["2026-05"]["expenses"] == 300.0
        assert buckets["2026-06"]["income"] == 500.0

    async def test_tax_estimate_crosses_the_bands(self, api, user):
        cid = await _client_id(api, user)
        await api.post("/api/invoices", headers=user["headers"], json={
            "client_id": cid, "issue_date": "2026-05-01", "status": "paid",
            "items": [{"description": "Assessment", "quantity": 1, "unit_price": 60000}]})
        body = (await api.get("/api/summary", headers=user["headers"],
                              params={"start": "2026-04-06", "end": "2027-04-05"})).json()
        tax = body["tax"]
        # 60,000 profit: 12,570 free, 37,700 at 20%, 9,730 at 40%.
        assert tax["income_tax"] == pytest.approx(7540 + 3892, abs=1)
        # Class 4: 6% between 12,570 and 50,270, then 2% above.
        assert tax["national_insurance"] == pytest.approx(2262 + 194.6, abs=1)

    async def test_csv_export_contains_both_sections(self, api, user):
        await self._seed(api, user)
        body = (await api.get("/api/export/csv", headers=user["headers"],
                              params={"start": "2026-04-06", "end": "2027-04-05"})).json()
        assert body["filename"] == "psybooks_2026-04-06_to_2027-04-05.csv"
        csv = body["csv"]
        assert "INCOME (Invoices)" in csv and "EXPENSES" in csv and "SUMMARY" in csv
        assert "INV-0001" in csv
        assert "Total sales,1500.00" in csv
        assert "999" not in csv          # the out-of-range expense stays out


class TestReceiptStorage:
    """Receipt images live in the database (STORAGE_BACKEND=postgres), so
    they inherit row-level security and account-deletion cascade."""

    @staticmethod
    async def _store(user, path: str, data: bytes = b"\xff\xd8\xff-jpeg-bytes"):
        import server
        return await server.put_object(path, data, "image/jpeg", user["id"])

    async def test_an_image_round_trips(self, api, user):
        import server
        path = f"psybooks/uploads/{user['id']}/receipt-1.jpg"
        await self._store(user, path)
        content, ctype = await server.get_object(path, user["id"])
        assert content == b"\xff\xd8\xff-jpeg-bytes"
        assert ctype == "image/jpeg"

    async def test_the_owner_can_download_it_through_the_api(self, api, user):
        path = f"psybooks/uploads/{user['id']}/receipt-2.jpg"
        await self._store(user, path)
        resp = await api.get(f"/api/files/{path}", headers=user["headers"])
        assert resp.status_code == 200
        assert resp.content == b"\xff\xd8\xff-jpeg-bytes"
        assert resp.headers["content-type"].startswith("image/jpeg")

    async def test_another_user_cannot_download_it(self, api, user, other_user):
        path = f"psybooks/uploads/{user['id']}/receipt-3.jpg"
        await self._store(user, path)
        # The path carries the owner's id, so this is refused before the
        # database is even asked.
        resp = await api.get(f"/api/files/{path}", headers=other_user["headers"])
        assert resp.status_code == 403

    async def test_an_unauthenticated_download_is_refused(self, api, user):
        path = f"psybooks/uploads/{user['id']}/receipt-4.jpg"
        await self._store(user, path)
        assert (await api.get(f"/api/files/{path}")).status_code == 401

    async def test_a_token_query_parameter_works_for_image_tags(self, api, user):
        path = f"psybooks/uploads/{user['id']}/receipt-5.jpg"
        await self._store(user, path)
        resp = await api.get(f"/api/files/{path}", params={"token": user["token"]})
        assert resp.status_code == 200

    async def test_images_go_when_the_account_goes(self, api, user, superuser_url):
        path = f"psybooks/uploads/{user['id']}/receipt-6.jpg"
        await self._store(user, path)

        import asyncpg
        conn = await asyncpg.connect(superuser_url)
        try:
            # Superuser, so row-level security cannot make this pass by
            # simply hiding the row — before and after are both real counts.
            before = await conn.fetchval(
                "SELECT count(*) FROM asets.receipt_files WHERE path = $1", path)
            assert before == 1

            await api.delete("/api/auth/account", headers=user["headers"])

            after = await conn.fetchval(
                "SELECT count(*) FROM asets.receipt_files WHERE path = $1", path)
        finally:
            await conn.close()
        assert after == 0

    async def test_an_oversized_image_is_refused_by_the_database(self, api, user):
        import asyncpg
        with pytest.raises(asyncpg.CheckViolationError):
            await self._store(user, f"psybooks/uploads/{user['id']}/huge.jpg",
                              b"x" * (8 * 1024 * 1024 + 1))


class TestFeatureDegradation:
    """A feature without its credential must report as unavailable rather
    than fail halfway through a request."""

    async def test_health_reports_unconfigured_providers_as_disabled(self, api):
        body = (await api.get("/api/health")).json()
        assert body["receipt_ocr"] == "disabled"
        assert body["hmrc"] == "sandbox"     # the test env sets HMRC credentials

    async def test_naming_a_provider_without_its_key_disables_it(self):
        import server
        assert server._resolve_provider("anthropic", {"anthropic": ""}) == ""
        assert server._resolve_provider("anthropic", {"anthropic": "sk-x"}) == "anthropic"
        assert server._resolve_provider("", {"emergent": "", "resend": "re_x"}) == "resend"
        assert server._resolve_provider("", {"emergent": "", "resend": ""}) == ""

    async def test_receipt_scanning_says_so_when_it_is_off(self, api, user):
        resp = await api.post("/api/expenses/scan", headers=user["headers"],
                              json={"image_base64": "abc"})
        assert resp.status_code == 503
        assert "manually" in resp.json()["detail"]


CATS = [
    {"code": "Office & admin", "hint": "Stationery", "hmrc_field": "adminCosts", "disallowable": False},
    {"code": "Client entertainment", "hint": "Not allowed", "hmrc_field": "businessEntertainmentCosts", "disallowable": True},
    {"code": "Other", "hint": "", "hmrc_field": "otherExpenses", "disallowable": False},
]


class TestReceiptExtraction:
    """The wiring between the scan endpoint and the vision provider.

    This is here because it once broke silently: a refactor left
    `extract_receipt` calling a symbol that no longer existed, and
    `_vision_emergent` calling itself. Nothing failed until a real
    receipt was sent to the live service.
    """

    async def test_the_dispatcher_routes_to_the_configured_provider(self, monkeypatch):
        import server
        calls = []

        async def fake_anthropic(system, prompt, image_b64, schema=None):
            calls.append("anthropic")
            return "{}"

        async def fake_emergent(system, prompt, image_b64, schema=None):
            calls.append("emergent")
            return "{}"

        monkeypatch.setattr(server, "_vision_anthropic", fake_anthropic)
        monkeypatch.setattr(server, "_vision_emergent", fake_emergent)

        monkeypatch.setattr(server, "LLM_PROVIDER", "anthropic")
        await server._vision_extract("s", "p", "img", {})
        monkeypatch.setattr(server, "LLM_PROVIDER", "emergent")
        await server._vision_extract("s", "p", "img", {})
        assert calls == ["anthropic", "emergent"]

    async def test_no_provider_configured_raises_rather_than_recursing(self, monkeypatch):
        import server
        monkeypatch.setattr(server, "LLM_PROVIDER", "")
        with pytest.raises(RuntimeError, match="No vision provider"):
            await server._vision_extract("s", "p", "img", {})

    async def test_a_model_answer_becomes_an_expense(self, monkeypatch):
        import server

        async def fake(system, prompt, image_b64, schema=None):
            return ('```json\n{"amount": 58.76, "currency": "GBP", "date": "2026-08-14", '
                    '"merchant": "Ryman", "description": "Stationery", '
                    '"category": "Office & admin"}\n```')

        monkeypatch.setattr(server, "_vision_extract", fake)
        out = await server.extract_receipt("aW1n", CATS)
        assert out["amount"] == 58.76
        assert out["date"] == "2026-08-14"
        assert out["merchant"] == "Ryman"
        assert out["category"] == "Office & admin"

    async def test_an_unknown_category_falls_back_to_other(self, monkeypatch):
        import server

        async def fake(system, prompt, image_b64, schema=None):
            return '{"amount": 10, "category": "Yachts", "merchant": "X"}'

        monkeypatch.setattr(server, "_vision_extract", fake)
        assert (await server.extract_receipt("aW1n", CATS))["category"] == "Other"

    async def test_unparseable_output_does_not_explode(self, monkeypatch):
        import server

        async def fake(system, prompt, image_b64, schema=None):
            return "I'm sorry, I cannot read this image."

        monkeypatch.setattr(server, "_vision_extract", fake)
        out = await server.extract_receipt("aW1n", CATS)
        assert out["amount"] == 0.0
        assert out["category"] == "Other"


class TestExpenseCategories:
    """One list, in the database. The app, the receipt reader and the
    HMRC submission all read it — they used to keep three copies."""

    VALID_HMRC_FIELDS = {
        "costOfGoods", "paymentsToSubcontractors", "wagesAndStaffCosts",
        "carVanTravelExpenses", "premisesRunningCosts", "maintenanceCosts",
        "adminCosts", "businessEntertainmentCosts", "advertisingCosts",
        "interestOnBankOtherLoans", "financeCharges", "irrecoverableDebts",
        "professionalFees", "depreciation", "otherExpenses",
    }

    async def test_the_app_can_fetch_them(self, api, user):
        body = (await api.get("/api/expense-categories", headers=user["headers"])).json()
        cats = body["categories"]
        assert len(cats) >= 10
        first = cats[0]
        assert set(first) == {"code", "label", "icon", "hint", "hmrc_field", "disallowable"}

    async def test_every_category_maps_to_a_real_hmrc_field(self, api, user):
        cats = (await api.get("/api/expense-categories", headers=user["headers"])).json()["categories"]
        for c in cats:
            assert c["hmrc_field"] in self.VALID_HMRC_FIELDS, c

    async def test_client_entertainment_is_marked_disallowable(self, api, user):
        cats = (await api.get("/api/expense-categories", headers=user["headers"])).json()["categories"]
        entertainment = [c for c in cats if c["disallowable"]]
        assert [c["code"] for c in entertainment] == ["Client entertainment"]
        assert entertainment[0]["hmrc_field"] == "businessEntertainmentCosts"

    async def test_an_expense_can_be_filed_under_every_category(self, api, user):
        """The picker must not offer a category the API then rejects."""
        cats = (await api.get("/api/expense-categories", headers=user["headers"])).json()["categories"]
        for c in cats:
            resp = await api.post("/api/expenses", headers=user["headers"], json={
                "category": c["code"], "amount": 10, "date": "2026-05-01"})
            assert resp.status_code == 200, f'{c["code"]}: {resp.text}'

    async def test_the_old_invented_categories_are_gone(self, api, user):
        cats = (await api.get("/api/expense-categories", headers=user["headers"])).json()["categories"]
        codes = {c["code"] for c in cats}
        # These predated the HMRC alignment and had nowhere sensible to map.
        assert "Office / Rent" not in codes
        assert "Phone / Internet" not in codes
        assert "Insurance" not in codes
