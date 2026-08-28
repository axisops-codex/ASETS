import os
import pytest
import requests
import time
import uuid

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://freelance-finance-35.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def test_user(api):
    email = f"qa_{uuid.uuid4().hex[:10]}@psybooks.com"
    r = api.post(f"{API}/auth/register", json={"email": email, "password": "secret123", "name": "Dr QA"})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"email": email, "password": "secret123", "token": data["access_token"], "user": data["user"]}


@pytest.fixture(scope="session")
def auth_headers(test_user):
    return {"Authorization": f"Bearer {test_user['token']}", "Content-Type": "application/json"}
