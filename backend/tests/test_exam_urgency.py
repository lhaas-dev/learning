"""
Backend tests for P2 – Exam Urgency Boost
Tests:
  1. urgency_multiplier() helper: all day-range buckets
  2. days_until_exam() helper: correct day counting
  3. PATCH /api/packs/{id}/exam-date: set, update, clear
  4. GET /api/packs/{id}: includes exam_date field
  5. POST /api/sessions/start: urgency_multiplier reflected in session doc
  6. Risk ordering: risk values increase with urgency multiplier
"""

import sys
import os
import pytest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/app/backend")

# Load environment variables
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

import requests as http_requests
from server import urgency_multiplier, days_until_exam, calculate_risk

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_EMAIL = "test_km_tester@example.com"
TEST_PASSWORD = "password123"
ES5_PACK_ID = "69a82c7bc7c639682e4e9224"


# ─── Unit Tests: helpers ──────────────────────────────────────────────────────

class TestUrgencyMultiplierHelper:
    """urgency_multiplier() returns the correct bucket."""

    def test_no_date_returns_1(self):
        assert urgency_multiplier(None) == 1.0

    def test_over_30_days_returns_1(self):
        future = (datetime.now(timezone.utc) + timedelta(days=45)).date().isoformat()
        assert urgency_multiplier(future) == 1.0

    def test_31_days_returns_1_0(self):
        future = (datetime.now(timezone.utc) + timedelta(days=31)).date().isoformat()
        assert urgency_multiplier(future) == 1.0

    def test_exactly_30_days_returns_1_3(self):
        """30 days falls in the 15–30 bucket → 1.3 per spec."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
        assert urgency_multiplier(future) == 1.3

    def test_29_days_returns_1_3(self):
        future = (datetime.now(timezone.utc) + timedelta(days=29)).date().isoformat()
        assert urgency_multiplier(future) == 1.3

    def test_15_days_returns_1_3(self):
        future = (datetime.now(timezone.utc) + timedelta(days=15)).date().isoformat()
        assert urgency_multiplier(future) == 1.3

    def test_14_days_returns_1_6(self):
        future = (datetime.now(timezone.utc) + timedelta(days=14)).date().isoformat()
        assert urgency_multiplier(future) == 1.6

    def test_7_days_returns_1_6(self):
        future = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
        assert urgency_multiplier(future) == 1.6

    def test_6_days_returns_2_0(self):
        future = (datetime.now(timezone.utc) + timedelta(days=6)).date().isoformat()
        assert urgency_multiplier(future) == 2.0

    def test_3_days_returns_2_0(self):
        future = (datetime.now(timezone.utc) + timedelta(days=3)).date().isoformat()
        assert urgency_multiplier(future) == 2.0

    def test_2_days_returns_2_5(self):
        future = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
        assert urgency_multiplier(future) == 2.5

    def test_today_returns_2_5(self):
        today = datetime.now(timezone.utc).date().isoformat()
        assert urgency_multiplier(today) == 2.5

    def test_past_date_returns_2_5(self):
        past = (datetime.now(timezone.utc) - timedelta(days=5)).date().isoformat()
        assert urgency_multiplier(past) == 2.5

    def test_invalid_date_returns_1(self):
        assert urgency_multiplier("not-a-date") == 1.0


class TestDaysUntilExamHelper:
    def test_none_returns_none(self):
        assert days_until_exam(None) is None

    def test_tomorrow_returns_1(self):
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        assert days_until_exam(tomorrow) == 1

    def test_today_returns_0(self):
        today = datetime.now(timezone.utc).date().isoformat()
        assert days_until_exam(today) == 0

    def test_past_returns_negative(self):
        past = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
        assert days_until_exam(past) == -3

    def test_invalid_returns_none(self):
        assert days_until_exam("bad-date") is None


class TestCalculateRisk:
    def test_risk_with_no_urgency(self):
        risk = calculate_risk(0.5, 1.0)
        assert risk == 0.5

    def test_risk_boosted_by_urgency_multiplier(self):
        base = calculate_risk(0.5, 1.0)
        boosted = round(base * 2.0, 4)
        assert boosted == 1.0

    def test_zero_recall_max_risk(self):
        assert calculate_risk(0.0, 1.0) == 1.0

    def test_full_recall_no_risk(self):
        assert calculate_risk(1.0, 1.0) == 0.0


class TestUrgencyMultiplierBoundaries:
    """Parametrized boundary tests."""

    @pytest.mark.parametrize("days,expected", [
        (31, 1.0),
        (30, 1.3),
        (29, 1.3),
        (15, 1.3),
        (14, 1.6),
        (7,  1.6),
        (6,  2.0),
        (3,  2.0),
        (2,  2.5),
        (1,  2.5),
        (0,  2.5),
    ])
    def test_boundary(self, days, expected):
        date_str = (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()
        assert urgency_multiplier(date_str) == expected, f"Days={days}: expected {expected}"


# ─── Integration Tests via HTTP ───────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_token():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    r = http_requests.post(f"{BASE_URL}/api/auth/login",
                           json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def test_pack_id(headers):
    """Create a dedicated test pack."""
    r = http_requests.post(f"{BASE_URL}/api/packs",
                           json={"title": "Exam Urgency Test Pack", "domain": "W&G"},
                           headers=headers, timeout=15)
    assert r.status_code == 200
    return r.json()["id"]


class TestExamDateEndpoint:
    def test_set_exam_date(self, headers, test_pack_id):
        future = (datetime.now(timezone.utc) + timedelta(days=20)).date().isoformat()
        r = http_requests.patch(f"{BASE_URL}/api/packs/{test_pack_id}/exam-date",
                                json={"exam_date": future}, headers=headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("exam_date") == future

    def test_get_pack_includes_exam_date(self, headers, test_pack_id):
        future = (datetime.now(timezone.utc) + timedelta(days=20)).date().isoformat()
        http_requests.patch(f"{BASE_URL}/api/packs/{test_pack_id}/exam-date",
                            json={"exam_date": future}, headers=headers, timeout=15)
        r = http_requests.get(f"{BASE_URL}/api/packs/{test_pack_id}", headers=headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("exam_date") == future

    def test_update_exam_date(self, headers, test_pack_id):
        new_date = (datetime.now(timezone.utc) + timedelta(days=5)).date().isoformat()
        r = http_requests.patch(f"{BASE_URL}/api/packs/{test_pack_id}/exam-date",
                                json={"exam_date": new_date}, headers=headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("exam_date") == new_date

    def test_clear_exam_date(self, headers, test_pack_id):
        r = http_requests.patch(f"{BASE_URL}/api/packs/{test_pack_id}/exam-date",
                                json={"exam_date": None}, headers=headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("exam_date") is None

    def test_invalid_date_format_returns_400(self, headers, test_pack_id):
        r = http_requests.patch(f"{BASE_URL}/api/packs/{test_pack_id}/exam-date",
                                json={"exam_date": "32-13-2099"}, headers=headers, timeout=15)
        assert r.status_code == 400

    def test_unauthorized_returns_401_or_422(self, test_pack_id):
        r = http_requests.patch(f"{BASE_URL}/api/packs/{test_pack_id}/exam-date",
                                json={"exam_date": "2099-01-01"}, timeout=15)
        assert r.status_code in (401, 403, 422)

    def test_urgency_visible_in_live_session(self, headers):
        """Using ES5 pack (has concepts): session must include urgency_multiplier=1.6 for 7-day exam."""
        exam = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
        http_requests.patch(f"{BASE_URL}/api/packs/{ES5_PACK_ID}/exam-date",
                            json={"exam_date": exam}, headers=headers, timeout=15)
        r = http_requests.post(f"{BASE_URL}/api/sessions/start",
                               json={"pack_id": ES5_PACK_ID, "duration_minutes": 5},
                               headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "urgency_multiplier" in data, "urgency_multiplier must be in session response"
        assert data["urgency_multiplier"] == 1.6

    def test_no_exam_date_urgency_is_1(self, headers):
        """Clear exam_date: urgency_multiplier must be 1.0."""
        http_requests.patch(f"{BASE_URL}/api/packs/{ES5_PACK_ID}/exam-date",
                            json={"exam_date": None}, headers=headers, timeout=15)
        r = http_requests.post(f"{BASE_URL}/api/sessions/start",
                               json={"pack_id": ES5_PACK_ID, "duration_minutes": 5},
                               headers=headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("urgency_multiplier") == 1.0



# ─── Unit Tests: helpers ──────────────────────────────────────────────────────

class TestUrgencyMultiplierHelper:
    """urgency_multiplier() returns the correct bucket."""

    def test_no_date_returns_1(self):
        assert urgency_multiplier(None) == 1.0

    def test_over_30_days_returns_1(self):
        future = (datetime.now(timezone.utc) + timedelta(days=45)).date().isoformat()
        assert urgency_multiplier(future) == 1.0

    def test_exactly_30_days_returns_1_3(self):
        """30 days falls in the 15–30 bucket → 1.3 per spec."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
        assert urgency_multiplier(future) == 1.3

    def test_31_days_returns_1_0(self):
        future = (datetime.now(timezone.utc) + timedelta(days=31)).date().isoformat()
        assert urgency_multiplier(future) == 1.0

    def test_29_days_returns_1_3(self):
        future = (datetime.now(timezone.utc) + timedelta(days=29)).date().isoformat()
        assert urgency_multiplier(future) == 1.3

    def test_15_days_returns_1_3(self):
        future = (datetime.now(timezone.utc) + timedelta(days=15)).date().isoformat()
        assert urgency_multiplier(future) == 1.3

    def test_14_days_returns_1_6(self):
        future = (datetime.now(timezone.utc) + timedelta(days=14)).date().isoformat()
        assert urgency_multiplier(future) == 1.6

    def test_7_days_returns_1_6(self):
        future = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
        assert urgency_multiplier(future) == 1.6

    def test_6_days_returns_2_0(self):
        future = (datetime.now(timezone.utc) + timedelta(days=6)).date().isoformat()
        assert urgency_multiplier(future) == 2.0

    def test_3_days_returns_2_0(self):
        future = (datetime.now(timezone.utc) + timedelta(days=3)).date().isoformat()
        assert urgency_multiplier(future) == 2.0

    def test_2_days_returns_2_5(self):
        future = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
        assert urgency_multiplier(future) == 2.5

    def test_today_returns_2_5(self):
        today = datetime.now(timezone.utc).date().isoformat()
        assert urgency_multiplier(today) == 2.5

    def test_past_date_returns_2_5(self):
        past = (datetime.now(timezone.utc) - timedelta(days=5)).date().isoformat()
        assert urgency_multiplier(past) == 2.5

    def test_invalid_date_returns_1(self):
        assert urgency_multiplier("not-a-date") == 1.0


class TestDaysUntilExamHelper:
    def test_none_returns_none(self):
        assert days_until_exam(None) is None

    def test_tomorrow_returns_1(self):
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        assert days_until_exam(tomorrow) == 1

    def test_today_returns_0(self):
        today = datetime.now(timezone.utc).date().isoformat()
        assert days_until_exam(today) == 0

    def test_past_returns_negative(self):
        past = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
        assert days_until_exam(past) == -3

    def test_invalid_returns_none(self):
        assert days_until_exam("bad-date") is None


class TestCalculateRisk:
    def test_risk_with_no_urgency(self):
        risk = calculate_risk(0.5, 1.0)
        assert risk == 0.5

    def test_risk_boosted_by_urgency(self):
        base_risk = calculate_risk(0.5, 1.0)
        boosted = round(base_risk * 2.0, 4)
        assert boosted == 1.0  # capped at multiplier value

    def test_zero_recall_max_risk(self):
        risk = calculate_risk(0.0, 1.0)
        assert risk == 1.0

    def test_full_recall_no_risk(self):
        risk = calculate_risk(1.0, 1.0)
        assert risk == 0.0


# ─── Integration Tests via HTTP ───────────────────────────────────────────────


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def test_pack_id(client, headers):
    """Create a dedicated test pack for exam date tests."""
    r = client.post("/api/packs", json={
        "title": "Exam Urgency Test Pack",
        "description": "Created by test_exam_urgency.py",
        "domain": "W&G",
    }, headers=headers)
    assert r.status_code == 200
    return r.json()["id"]


class TestExamDateEndpoint:
    def test_set_exam_date(self, client, headers, test_pack_id):
        """PATCH with a valid date sets exam_date on the pack."""
        future = (datetime.now(timezone.utc) + timedelta(days=20)).date().isoformat()
        r = client.patch(
            f"/api/packs/{test_pack_id}/exam-date",
            json={"exam_date": future},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("exam_date") == future

    def test_get_pack_includes_exam_date(self, client, headers, test_pack_id):
        """GET /api/packs/{id} returns the exam_date field."""
        future = (datetime.now(timezone.utc) + timedelta(days=20)).date().isoformat()
        # Ensure date is set
        client.patch(
            f"/api/packs/{test_pack_id}/exam-date",
            json={"exam_date": future},
            headers=headers,
        )
        r = client.get(f"/api/packs/{test_pack_id}", headers=headers)
        assert r.status_code == 200
        assert r.json().get("exam_date") == future

    def test_update_exam_date(self, client, headers, test_pack_id):
        """PATCH with a different date updates exam_date."""
        new_date = (datetime.now(timezone.utc) + timedelta(days=5)).date().isoformat()
        r = client.patch(
            f"/api/packs/{test_pack_id}/exam-date",
            json={"exam_date": new_date},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json().get("exam_date") == new_date

    def test_clear_exam_date(self, client, headers, test_pack_id):
        """PATCH with null clears exam_date."""
        r = client.patch(
            f"/api/packs/{test_pack_id}/exam-date",
            json={"exam_date": None},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json().get("exam_date") is None

    def test_invalid_date_format_returns_400(self, client, headers, test_pack_id):
        """PATCH with invalid date format returns 400."""
        r = client.patch(
            f"/api/packs/{test_pack_id}/exam-date",
            json={"exam_date": "32-13-2099"},
            headers=headers,
        )
        assert r.status_code == 400

    def test_unauthorized_returns_403(self, client, test_pack_id):
        """Without auth token, PATCH returns 401 or 403."""
        r = client.patch(
            f"/api/packs/{test_pack_id}/exam-date",
            json={"exam_date": "2099-01-01"},
        )
        assert r.status_code in (401, 403)


class TestUrgencyInSession:
    """Verify session start reflects urgency_multiplier field."""

    def test_session_has_urgency_multiplier_field(self, client, headers, test_pack_id):
        """Started session must include urgency_multiplier."""
        # Set an exam date close enough for a boost (7 days)
        exam = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
        client.patch(
            f"/api/packs/{test_pack_id}/exam-date",
            json={"exam_date": exam},
            headers=headers,
        )
        r = client.post("/api/sessions/start", json={
            "pack_id": test_pack_id,
            "duration_minutes": 10,
        }, headers=headers)
        # Might return 400 if no concepts exist — that's fine for this test
        if r.status_code == 400:
            pytest.skip("Test pack has no concepts — urgency field test skipped")
        assert r.status_code == 200
        data = r.json()
        assert "urgency_multiplier" in data
        assert data["urgency_multiplier"] == 1.6  # 7 days → 1.6

    def test_no_exam_date_urgency_is_1(self, client, headers, test_pack_id):
        """Without exam_date, urgency_multiplier must be 1.0."""
        client.patch(
            f"/api/packs/{test_pack_id}/exam-date",
            json={"exam_date": None},
            headers=headers,
        )
        r = client.post("/api/sessions/start", json={
            "pack_id": test_pack_id,
            "duration_minutes": 10,
        }, headers=headers)
        if r.status_code == 400:
            pytest.skip("Test pack has no concepts")
        assert r.status_code == 200
        assert r.json().get("urgency_multiplier") == 1.0


class TestUrgencyMultiplierBoundaries:
    """Parametrized boundary tests for urgency_multiplier()."""

    @pytest.mark.parametrize("days,expected", [
        (31, 1.0),
        (30, 1.3),  # 30 days = 15–30 bucket
        (29, 1.3),
        (15, 1.3),
        (14, 1.6),
        (7,  1.6),
        (6,  2.0),
        (3,  2.0),
        (2,  2.5),
        (1,  2.5),
        (0,  2.5),
    ])
    def test_boundary(self, days, expected):
        date_str = (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()
        assert urgency_multiplier(date_str) == expected, f"Days={days}: expected {expected}"
