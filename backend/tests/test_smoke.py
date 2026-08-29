"""Harness check: the cluster boots, migrations apply, the app answers."""


async def test_health_reports_a_live_database(api):
    resp = await api.get("/api/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"


async def test_register_and_authenticate(api, clean_db):
    resp = await api.post("/api/auth/register",
                          json={"email": "smoke@example.com", "password": "secret123", "name": "Smoke"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]

    me = await api.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "smoke@example.com"
