"""Backend tests for Knowledge Memory MVP - Auth, Packs, Concepts, Sessions, Dashboard"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

TEST_EMAIL = "test_km_tester@example.com"
TEST_PASSWORD = "password123"

# ─── Shared State ─────────────────────────────────────────────────────────────
shared = {}


# ─── Health Check ──────────────────────────────────────────────────────────────
class TestHealth:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ─── Auth ──────────────────────────────────────────────────────────────────────
class TestAuth:
    def test_register(self):
        """Register new user - skip if already exists"""
        r = requests.post(f"{BASE_URL}/api/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        if r.status_code == 400 and "already registered" in r.text:
            pytest.skip("User already exists")
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert data["email"] == TEST_EMAIL

    def test_login(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        shared["token"] = data["token"]
        shared["user_id"] = data["user_id"]

    def test_login_invalid(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": "wrongpass"})
        assert r.status_code == 401

    def test_protected_without_token(self):
        r = requests.get(f"{BASE_URL}/api/packs")
        assert r.status_code == 403  # FastAPI HTTPBearer returns 403 when no token

    def test_protected_with_invalid_token(self):
        r = requests.get(f"{BASE_URL}/api/packs", headers={"Authorization": "Bearer badtoken"})
        assert r.status_code == 401


# ─── Study Packs ───────────────────────────────────────────────────────────────
class TestStudyPacks:
    @pytest.fixture(autouse=True)
    def ensure_token(self):
        if "token" not in shared:
            r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
            if r.status_code != 200:
                # Try to register first
                requests.post(f"{BASE_URL}/api/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
                r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
            shared["token"] = r.json()["token"]
        self.headers = {"Authorization": f"Bearer {shared['token']}"}

    def test_create_pack(self):
        r = requests.post(f"{BASE_URL}/api/packs",
                          json={"title": "TEST_Cyber Security Pack", "description": "Testing", "domain": "cybersec"},
                          headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "TEST_Cyber Security Pack"
        assert "id" in data
        shared["pack_id"] = data["id"]

    def test_list_packs(self):
        r = requests.get(f"{BASE_URL}/api/packs", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_get_pack(self):
        pack_id = shared.get("pack_id")
        if not pack_id:
            pytest.skip("No pack_id available")
        r = requests.get(f"{BASE_URL}/api/packs/{pack_id}", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == pack_id


# ─── Upload & AI Concept Extraction ────────────────────────────────────────────
class TestUpload:
    @pytest.fixture(autouse=True)
    def ensure_token(self):
        if "token" not in shared:
            r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
            shared["token"] = r.json()["token"]
        self.headers = {"Authorization": f"Bearer {shared['token']}"}

    def test_upload_text(self):
        """Upload short cyber security text and get concepts"""
        pack_id = shared.get("pack_id")
        if not pack_id:
            pytest.skip("No pack_id available - run TestStudyPacks first")

        cyber_text = (
            "A firewall is a network security device that monitors and filters incoming and outgoing "
            "network traffic based on an organization security policies. At its most basic, a firewall is "
            "essentially the barrier that sits between a private internal network and the public Internet. "
            "A firewall can be hardware, software, software-as-a-service (SaaS) or public or private "
            "cloud (virtual). Firewalls are used to prevent unauthorized internet users from accessing "
            "private networks connected to the internet, especially intranets. All messages entering or "
            "leaving the intranet pass through the firewall, which examines each message and blocks those "
            "that do not meet the specified security criteria."
        )

        r = requests.post(
            f"{BASE_URL}/api/packs/{pack_id}/upload",
            data={"text": cyber_text},
            headers=self.headers,
            timeout=120,
        )
        assert r.status_code == 200, f"Upload failed: {r.text}"
        data = r.json()
        assert "concepts_extracted" in data
        assert data["concepts_extracted"] > 0
        assert len(data["concepts"]) > 0
        # Store first concept_id for subsequent tests
        shared["concept_id"] = data["concepts"][0]["id"]
        print(f"Extracted {data['concepts_extracted']} concepts")

    def test_upload_no_content(self):
        pack_id = shared.get("pack_id")
        if not pack_id:
            pytest.skip("No pack_id available")
        r = requests.post(f"{BASE_URL}/api/packs/{pack_id}/upload", data={}, headers=self.headers, timeout=30)
        assert r.status_code == 400


# ─── Concepts ──────────────────────────────────────────────────────────────────
class TestConcepts:
    @pytest.fixture(autouse=True)
    def ensure_token(self):
        if "token" not in shared:
            r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
            shared["token"] = r.json()["token"]
        self.headers = {"Authorization": f"Bearer {shared['token']}"}

    def test_list_concepts(self):
        pack_id = shared.get("pack_id")
        if not pack_id:
            pytest.skip("No pack_id available")
        r = requests.get(f"{BASE_URL}/api/packs/{pack_id}/concepts", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} concepts")

    def test_update_concept(self):
        concept_id = shared.get("concept_id")
        if not concept_id:
            pytest.skip("No concept_id available")
        r = requests.patch(f"{BASE_URL}/api/concepts/{concept_id}",
                           json={"exam_weight": "high"},
                           headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        assert data["exam_weight_label"] == "high"

    def test_delete_concept(self):
        """Create a temporary concept to delete - use a concept from the list"""
        pack_id = shared.get("pack_id")
        if not pack_id:
            pytest.skip("No pack_id available")
        # Get concepts list and delete the last one (not the one we use for sessions)
        r = requests.get(f"{BASE_URL}/api/packs/{pack_id}/concepts", headers=self.headers)
        concepts = r.json()
        if len(concepts) < 2:
            pytest.skip("Need at least 2 concepts to safely test deletion")
        last_concept_id = concepts[-1]["id"]
        r = requests.delete(f"{BASE_URL}/api/concepts/{last_concept_id}", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        assert data["deleted"] is True


# ─── Sessions ──────────────────────────────────────────────────────────────────
class TestSessions:
    @pytest.fixture(autouse=True)
    def ensure_token(self):
        if "token" not in shared:
            r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
            shared["token"] = r.json()["token"]
        self.headers = {"Authorization": f"Bearer {shared['token']}"}

    def test_start_session(self):
        pack_id = shared.get("pack_id")
        if not pack_id:
            pytest.skip("No pack_id available")
        r = requests.post(f"{BASE_URL}/api/sessions/start",
                          json={"pack_id": pack_id, "duration_minutes": 10},
                          headers=self.headers)
        assert r.status_code == 200, f"Start session failed: {r.text}"
        data = r.json()
        assert "session_id" in data
        assert "current_item" in data
        assert data["current_item"]["check"] is not None
        shared["session_id"] = data["session_id"]
        shared["session_concept_id"] = data["current_item"]["concept"]["id"]
        shared["session_check_id"] = data["current_item"]["check"]["id"]
        print(f"Session started: {data['session_id']}, total: {data['total']}")

    def test_answer_session(self):
        session_id = shared.get("session_id")
        if not session_id:
            pytest.skip("No session_id available")
        r = requests.post(f"{BASE_URL}/api/sessions/answer",
                          json={
                              "session_id": session_id,
                              "concept_id": shared["session_concept_id"],
                              "check_id": shared["session_check_id"],
                              "rating": "good",
                              "user_answer": "test answer",
                          },
                          headers=self.headers)
        assert r.status_code == 200, f"Answer session failed: {r.text}"
        data = r.json()
        assert "session_complete" in data
        assert "stats" in data
        print(f"Session complete: {data['session_complete']}, stats: {data['stats']}")


# ─── Dashboard ─────────────────────────────────────────────────────────────────
class TestDashboard:
    @pytest.fixture(autouse=True)
    def ensure_token(self):
        if "token" not in shared:
            r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
            shared["token"] = r.json()["token"]
        self.headers = {"Authorization": f"Bearer {shared['token']}"}

    def test_dashboard_overview(self):
        r = requests.get(f"{BASE_URL}/api/dashboard/overview", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        assert "avg_risk" in data
        assert "total_concepts" in data
        assert "total_packs" in data
        assert "weakest_concepts" in data
        assert "recent_sessions" in data
        print(f"Dashboard: packs={data['total_packs']}, concepts={data['total_concepts']}, avg_risk={data['avg_risk']}")
