"""HMRC Making Tax Digital integration.

HMRC itself is replaced by an httpx MockTransport that records every
request, so these tests assert on exactly what would go over the wire:
the URL, the API version, the fraud prevention headers and the payload.
"""
import base64
import json
from datetime import date

import asyncpg
import pytest
import pytest_asyncio
import httpx

from hmrc import client as hmrc_client
from hmrc import mapping


DEVICE = base64.urlsafe_b64encode(json.dumps({
    "deviceId": "beec798b-b366-47fa-b1f8-92cede14a1ce",
    "timezone": "UTC+01:00",
    "localIps": ["10.1.2.3", "fc00::1"],
    "localIpsTimestamp": "2026-08-28T14:30:05.123Z",
    "screens": {"width": 375, "height": 812, "scalingFactor": 3, "colourDepth": 32},
    "windowSize": {"width": 375, "height": 812},
    "os": {"family": "iOS", "version": "26.1", "manufacturer": "Apple", "model": "iPhone17,2"},
    "appVersion": "1.0.0",
}).encode()).decode().rstrip("=")

DEVICE_HEADERS = {"X-ASETS-Device": DEVICE, "X-Forwarded-For": "198.51.100.7"}


class FakeHMRC:
    """Records requests and replies with whatever the test queued."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.responses: dict[str, tuple[int, dict]] = {}
        self.default = (200, {})

    def reply(self, path_fragment: str, status: int, body):
        self.responses[path_fragment] = (status, body)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for fragment, (status, body) in self.responses.items():
            if fragment in str(request.url):
                return httpx.Response(status, json=body,
                                      headers={"X-CorrelationId": "corr-123"})
        return httpx.Response(*self.default, headers={"X-CorrelationId": "corr-123"})

    def last(self, fragment: str) -> httpx.Request:
        for request in reversed(self.requests):
            if fragment in str(request.url):
                return request
        raise AssertionError(f"no request matching {fragment!r} in "
                             f"{[str(r.url) for r in self.requests]}")


@pytest.fixture
def hmrc():
    fake = FakeHMRC()
    fake.reply("/oauth/token", 200, {
        "access_token": "access-1", "refresh_token": "refresh-1",
        "expires_in": 14400, "scope": "read:self-assessment write:self-assessment"})
    hmrc_client.set_client_factory(
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    yield fake
    hmrc_client.set_client_factory(None)


async def _connect(api, user, hmrc, *, nino="QQ123456C", business="XAIS12345678910"):
    """Walk the real OAuth flow, then set NINO and business."""
    start = await api.post("/api/hmrc/connect", headers=user["headers"])
    assert start.status_code == 200, start.text
    state = start.json()["state"]

    callback = await api.get("/api/hmrc/callback", params={"code": "auth-code", "state": state})
    assert callback.status_code in (307, 302)
    assert "status=connected" in callback.headers["location"]

    if nino:
        resp = await api.post("/api/hmrc/nino", headers=user["headers"], json={"nino": nino})
        assert resp.status_code == 200, resp.text
    if business:
        resp = await api.post("/api/hmrc/business", headers=user["headers"],
                              json={"business_id": business})
        assert resp.status_code == 200, resp.text


class TestConnection:
    async def test_status_before_connecting(self, api, user, hmrc):
        body = (await api.get("/api/hmrc/status",
                              headers={**user["headers"], **DEVICE_HEADERS})).json()
        assert body["configured"] is True
        assert body["connected"] is False
        assert body["environment"] == "sandbox"
        assert body["missing_fraud_headers"] == []

    async def test_authorization_url_carries_the_right_parameters(self, api, user, hmrc):
        body = (await api.post("/api/hmrc/connect", headers=user["headers"])).json()
        url = httpx.URL(body["authorization_url"])
        assert url.host == "test-api.service.hmrc.gov.uk"
        assert url.path == "/oauth/authorize"
        params = dict(url.params)
        assert params["client_id"] == "test-client-id"
        assert params["response_type"] == "code"
        assert params["scope"] == "read:self-assessment write:self-assessment"
        assert params["state"] == body["state"]

    async def test_callback_exchanges_the_code_and_connects(self, api, user, hmrc):
        await _connect(api, user, hmrc)
        status = (await api.get("/api/hmrc/status", headers=user["headers"])).json()
        assert status["connected"] is True
        assert status["nino_set"] is True
        assert status["business_id"] == "XAIS12345678910"

        token_request = hmrc.last("/oauth/token")
        form = dict(pair.split("=", 1) for pair in token_request.content.decode().split("&"))
        assert form["grant_type"] == "authorization_code"
        assert form["client_secret"] == "test-client-secret"

    async def test_a_state_token_works_only_once(self, api, user, hmrc):
        state = (await api.post("/api/hmrc/connect", headers=user["headers"])).json()["state"]
        first = await api.get("/api/hmrc/callback", params={"code": "c", "state": state})
        assert "status=connected" in first.headers["location"]
        second = await api.get("/api/hmrc/callback", params={"code": "c", "state": state})
        assert "status=error" in second.headers["location"]
        assert "expired_link" in second.headers["location"]

    async def test_an_unknown_state_is_refused(self, api, user, hmrc):
        resp = await api.get("/api/hmrc/callback", params={"code": "c", "state": "made-up"})
        assert "status=error" in resp.headers["location"]

    async def test_user_denial_is_reported_back_to_the_app(self, api, user, hmrc):
        resp = await api.get("/api/hmrc/callback",
                             params={"error": "access_denied", "error_description": "User denied"})
        assert "status=denied" in resp.headers["location"]

    async def test_tokens_are_not_readable_in_the_database(self, api, user, hmrc, superuser_url):
        await _connect(api, user, hmrc)
        conn = await asyncpg.connect(superuser_url)
        try:
            row = await conn.fetchrow(
                "SELECT access_token, nino_encrypted FROM asets.hmrc_connections WHERE user_id=$1",
                user["id"])
        finally:
            await conn.close()
        assert b"access-1" not in bytes(row["access_token"])
        assert b"QQ123456C" not in bytes(row["nino_encrypted"])

    async def test_disconnect_removes_the_grant(self, api, user, hmrc):
        await _connect(api, user, hmrc)
        await api.post("/api/hmrc/disconnect", headers=user["headers"])
        assert (await api.get("/api/hmrc/status", headers=user["headers"])).json()["connected"] is False

    async def test_a_malformed_nino_is_rejected(self, api, user, hmrc):
        await _connect(api, user, hmrc, nino=None, business=None)
        resp = await api.post("/api/hmrc/nino", headers=user["headers"], json={"nino": "NOTANINO"})
        assert resp.status_code == 400
        assert "National Insurance" in resp.json()["detail"]

    async def test_calls_before_connecting_are_a_409(self, api, user, hmrc):
        resp = await api.get("/api/hmrc/obligations", headers=user["headers"])
        assert resp.status_code == 409


class TestFraudPreventionHeaders:
    async def test_every_expected_header_reaches_hmrc(self, api, user, hmrc):
        await _connect(api, user, hmrc)
        hmrc.reply("/obligations/details", 200, {"obligations": []})
        await api.get("/api/hmrc/obligations", headers={**user["headers"], **DEVICE_HEADERS})

        sent = hmrc.last("/obligations/details").headers
        assert sent["Gov-Client-Connection-Method"] == "MOBILE_APP_VIA_SERVER"
        assert sent["Gov-Client-Device-ID"] == "beec798b-b366-47fa-b1f8-92cede14a1ce"
        assert sent["Gov-Client-Timezone"] == "UTC+01:00"
        assert sent["Gov-Client-Public-IP"] == "198.51.100.7"
        assert sent["Gov-Client-Screens"] == "width=375&height=812&scaling-factor=3&colour-depth=32"
        assert sent["Gov-Client-User-Agent"] == (
            "os-family=iOS&os-version=26.1&device-manufacturer=Apple&device-model=iPhone17%2C2")
        assert sent["Gov-Vendor-Public-IP"] == "203.0.113.6"
        assert "asets-app=1.0.0" in sent["Gov-Vendor-Version"]
        assert sent["Gov-Client-User-IDs"] == f"asets={user['id']}"
        # IPv6 must be percent-encoded.
        assert sent["Gov-Client-Local-IPs"] == "10.1.2.3,fc00%3A%3A1"

    async def test_a_missing_device_header_is_reported_not_faked(self, api, user, hmrc):
        body = (await api.get("/api/hmrc/status", headers=user["headers"])).json()
        assert "Gov-Client-Device-ID" in body["missing_fraud_headers"]
        assert "Gov-Client-Screens" in body["missing_fraud_headers"]

    async def test_the_api_version_is_pinned_per_endpoint(self, api, user, hmrc):
        await _connect(api, user, hmrc)
        hmrc.reply("/obligations/details", 200, {"obligations": []})
        hmrc.reply("/individuals/business/details", 200, {"listOfBusinesses": []})

        await api.get("/api/hmrc/obligations", headers={**user["headers"], **DEVICE_HEADERS})
        assert hmrc.last("/obligations/details").headers["Accept"] == "application/vnd.hmrc.3.0+json"

        await api.get("/api/hmrc/businesses", headers={**user["headers"], **DEVICE_HEADERS})
        assert hmrc.last("/individuals/business/details").headers["Accept"] == \
            "application/vnd.hmrc.2.0+json"


class TestTokenRefresh:
    async def test_an_expired_access_token_is_refreshed_transparently(self, api, user, hmrc,
                                                                     superuser_url):
        await _connect(api, user, hmrc)
        conn = await asyncpg.connect(superuser_url)
        try:
            await conn.execute(
                "UPDATE asets.hmrc_connections SET access_expires_at = now() - interval '1 hour' "
                "WHERE user_id=$1", user["id"])
        finally:
            await conn.close()

        hmrc.reply("/oauth/token", 200, {"access_token": "access-2", "refresh_token": "refresh-2",
                                         "expires_in": 14400, "scope": "read:self-assessment"})
        hmrc.reply("/obligations/details", 200, {"obligations": []})
        resp = await api.get("/api/hmrc/obligations", headers={**user["headers"], **DEVICE_HEADERS})
        assert resp.status_code == 200, resp.text

        refresh = hmrc.last("/oauth/token")
        assert "grant_type=refresh_token" in refresh.content.decode()
        assert hmrc.last("/obligations/details").headers["Authorization"] == "Bearer access-2"


class TestQuarterlySubmission:
    @staticmethod
    async def _books(api, user):
        cid = (await api.post("/api/clients", headers=user["headers"],
                              json={"name": "Northgate"})).json()["id"]
        # Two invoices inside Q1 of 2026-27, one after it.
        for issue, amount in (("2026-04-10", 950), ("2026-06-20", 1200), ("2026-08-01", 400)):
            await api.post("/api/invoices", headers=user["headers"], json={
                "client_id": cid, "issue_date": issue, "status": "sent",
                "items": [{"description": "Sessions", "quantity": 1, "unit_price": amount}]})
        for category, amount, when in (("Supervision", 120, "2026-05-02"),
                                       ("Travel", 45.5, "2026-06-11"),
                                       ("Software", 24, "2026-04-30"),
                                       ("Client entertainment", 83.43, "2026-05-20"),
                                       ("Software", 24, "2026-09-01")):
            await api.post("/api/expenses", headers=user["headers"],
                           json={"category": category, "amount": amount, "date": when})

    async def test_preview_shows_the_cumulative_figures(self, api, user, hmrc):
        await self._books(api, user)
        body = (await api.get("/api/hmrc/quarter-preview", headers=user["headers"],
                              params={"tax_year": "2026-27", "quarter": 1})).json()

        assert body["quarter"]["period_start"] == "2026-04-06"
        assert body["quarter"]["period_end"] == "2026-07-05"
        payload = body["payload"]
        assert payload["periodIncome"]["turnover"] == 2150.0        # 950 + 1200
        assert payload["periodExpenses"] == {
            "adminCosts": 24.0,                      # Software
            "businessEntertainmentCosts": 83.43,     # the pub dinner
            "carVanTravelExpenses": 45.5,            # Travel
            "professionalFees": 120.0,               # Supervision
        }
        # HMRC does not allow client entertainment, so it is declared and
        # then added straight back.
        assert payload["periodDisallowableExpenses"] == {
            "businessEntertainmentCostsDisallowable": 83.43}
        assert body["summary"]["disallowable_total"] == 83.43
        assert body["summary"]["profit"] == 1960.5   # unchanged: 83.43 out, 83.43 back

    async def test_submission_is_refused_without_confirmation(self, api, user, hmrc):
        await _connect(api, user, hmrc)
        resp = await api.post("/api/hmrc/submit-quarter", headers=user["headers"],
                              json={"tax_year": "2026-27", "quarter": 1})
        assert resp.status_code == 400
        assert "Confirm" in resp.json()["detail"]

    async def test_a_confirmed_submission_goes_to_the_cumulative_endpoint(self, api, user, hmrc):
        await _connect(api, user, hmrc)
        await self._books(api, user)
        hmrc.reply("/cumulative/", 200, {})

        resp = await api.post("/api/hmrc/submit-quarter",
                              headers={**user["headers"], **DEVICE_HEADERS},
                              json={"tax_year": "2026-27", "quarter": 1, "confirm": True})
        assert resp.status_code == 200, resp.text
        assert resp.json()["submitted"] is True

        sent = hmrc.last("/cumulative/")
        assert sent.method == "PUT"
        assert str(sent.url).endswith(
            "/individuals/business/self-employment/QQ123456C/XAIS12345678910/cumulative/2026-27")
        assert sent.headers["Accept"] == "application/vnd.hmrc.5.0+json"
        body = json.loads(sent.content)
        assert body["periodDates"] == {"periodStartDate": "2026-04-06",
                                       "periodEndDate": "2026-07-05"}
        assert body["periodIncome"]["turnover"] == 2150.0

    async def test_the_audit_trail_records_what_was_sent(self, api, user, hmrc):
        await _connect(api, user, hmrc)
        await self._books(api, user)
        hmrc.reply("/cumulative/", 200, {})
        await api.post("/api/hmrc/submit-quarter", headers={**user["headers"], **DEVICE_HEADERS},
                       json={"tax_year": "2026-27", "quarter": 1, "confirm": True})

        submissions = (await api.get("/api/hmrc/submissions",
                                     headers=user["headers"])).json()["submissions"]
        quarterly = [s for s in submissions if s["type"] == "quarterly_update"]
        assert len(quarterly) == 1
        record = quarterly[0]
        assert record["status"] == "accepted"
        assert record["http_status"] == 200
        assert record["tax_year"] == "2026-27"
        assert record["period_start"] == "2026-04-06"
        assert record["correlation_id"] == "corr-123"

    async def test_an_hmrc_rejection_is_explained_and_recorded(self, api, user, hmrc):
        await _connect(api, user, hmrc)
        await self._books(api, user)
        hmrc.reply("/cumulative/", 400, {
            "code": "INVALID_REQUEST", "message": "Invalid request",
            "errors": [{"code": "RULE_TAX_YEAR_NOT_SUPPORTED",
                        "message": "The tax year specified does not lie within the supported range"}]})

        resp = await api.post("/api/hmrc/submit-quarter",
                              headers={**user["headers"], **DEVICE_HEADERS},
                              json={"tax_year": "2026-27", "quarter": 1, "confirm": True})
        assert resp.status_code == 400
        assert "RULE_TAX_YEAR_NOT_SUPPORTED" in resp.json()["detail"]

        submissions = (await api.get("/api/hmrc/submissions",
                                     headers=user["headers"])).json()["submissions"]
        rejected = [s for s in submissions if s["type"] == "quarterly_update"][0]
        assert rejected["status"] == "rejected"
        assert rejected["http_status"] == 400

    async def test_a_transport_failure_is_recorded_as_an_error(self, api, user, hmrc):
        await _connect(api, user, hmrc)

        def explode(request):
            hmrc.requests.append(request)
            if "/cumulative/" in str(request.url):
                raise httpx.ConnectError("network down")
            return httpx.Response(200, json={})

        hmrc_client.set_client_factory(
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(explode)))
        with pytest.raises(httpx.ConnectError):
            await api.post("/api/hmrc/submit-quarter",
                           headers={**user["headers"], **DEVICE_HEADERS},
                           json={"tax_year": "2026-27", "quarter": 1, "confirm": True})

        hmrc_client.set_client_factory(
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(hmrc.handler)))
        submissions = (await api.get("/api/hmrc/submissions",
                                     headers=user["headers"])).json()["submissions"]
        assert [s for s in submissions if s["type"] == "quarterly_update"][0]["status"] == "error"


class TestObligationsAndCalculations:
    async def test_obligations_are_scoped_to_the_tax_year_and_business(self, api, user, hmrc):
        await _connect(api, user, hmrc)
        hmrc.reply("/obligations/details", 200, {"obligations": [{"businessId": "XAIS12345678910"}]})
        resp = await api.get("/api/hmrc/obligations", headers={**user["headers"], **DEVICE_HEADERS},
                             params={"tax_year": "2026-27"})
        assert resp.status_code == 200
        assert resp.json()["tax_year"] == "2026-27"

        params = dict(hmrc.last("/obligations/details").url.params)
        assert params["typeOfBusiness"] == "self-employment"
        assert params["fromDate"] == "2026-04-06"
        assert params["toDate"] == "2027-04-05"
        assert params["businessId"] == "XAIS12345678910"

    async def test_triggering_a_calculation_returns_its_id(self, api, user, hmrc):
        await _connect(api, user, hmrc)
        hmrc.reply("/trigger/", 200, {"calculationId": "calc-abc"})
        resp = await api.post("/api/hmrc/calculation", headers={**user["headers"], **DEVICE_HEADERS},
                              params={"tax_year": "2026-27"})
        assert resp.status_code == 200
        assert resp.json()["calculationId"] == "calc-abc"
        assert str(hmrc.last("/trigger/").url).endswith(
            "/individuals/calculations/QQ123456C/self-assessment/2026-27/trigger/in-year")


class TestTaxCalendar:
    def test_the_tax_year_turns_over_on_6_april(self):
        assert mapping.tax_year_for(date(2026, 4, 5)) == "2025-26"
        assert mapping.tax_year_for(date(2026, 4, 6)) == "2026-27"

    def test_quarters_are_cumulative_from_6_april(self):
        quarters = mapping.quarters("2026-27")
        assert [q["period_end"] for q in quarters] == [
            "2026-07-05", "2026-10-05", "2027-01-05", "2027-04-05"]
        assert {q["period_start"] for q in quarters} == {"2026-04-06"}

    def test_a_malformed_tax_year_is_rejected(self):
        with pytest.raises(ValueError):
            mapping.tax_year_bounds("2026-28")


class TestExpiredGrant:
    """HMRC authorisations last 18 months, and users can revoke them.
    Either way the app has to say 'reconnect', not 'server error'."""

    async def test_an_expired_grant_asks_the_user_to_reconnect(self, api, user, hmrc,
                                                               superuser_url):
        await _connect(api, user, hmrc)
        conn = await asyncpg.connect(superuser_url)
        try:
            await conn.execute(
                "UPDATE asets.hmrc_connections SET access_expires_at = now() - interval '1 hour' "
                "WHERE user_id = $1", user["id"])
        finally:
            await conn.close()

        hmrc.reply("/oauth/token", 400, {
            "error": "invalid_grant",
            "error_description": "The refresh token is invalid or has expired"})

        resp = await api.get("/api/hmrc/obligations",
                             headers={**user["headers"], **DEVICE_HEADERS})
        assert resp.status_code == 409
        assert "Reconnect" in resp.json()["detail"]

    async def test_the_reason_is_visible_on_the_status_screen(self, api, user, hmrc,
                                                              superuser_url):
        await _connect(api, user, hmrc)
        conn = await asyncpg.connect(superuser_url)
        try:
            await conn.execute(
                "UPDATE asets.hmrc_connections SET access_expires_at = now() - interval '1 hour' "
                "WHERE user_id = $1", user["id"])
        finally:
            await conn.close()
        hmrc.reply("/oauth/token", 400, {"error": "invalid_grant"})
        await api.get("/api/hmrc/obligations", headers={**user["headers"], **DEVICE_HEADERS})

        status = (await api.get("/api/hmrc/status", headers=user["headers"])).json()
        assert "expired or been withdrawn" in (status["last_error"] or "")

    async def test_hmrc_being_unwell_is_not_mistaken_for_an_expired_grant(self, api, user, hmrc,
                                                                         superuser_url):
        await _connect(api, user, hmrc)
        conn = await asyncpg.connect(superuser_url)
        try:
            await conn.execute(
                "UPDATE asets.hmrc_connections SET access_expires_at = now() - interval '1 hour' "
                "WHERE user_id = $1", user["id"])
        finally:
            await conn.close()

        hmrc.reply("/oauth/token", 503, {"error": "server_error"})
        resp = await api.get("/api/hmrc/obligations",
                             headers={**user["headers"], **DEVICE_HEADERS})
        # A 502 tells the user to try again; a 409 would send them off to
        # reconnect an account that is perfectly fine.
        assert resp.status_code == 502
