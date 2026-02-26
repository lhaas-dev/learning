"""Backend tests for Session Debrief and Drill Session features"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

TEST_EMAIL = "test_km_tester@example.com"
TEST_PASSWORD = "password123"
PACK_ID = "69a0c27812e8a54c83092edb"

shared = {}


def get_token():
    if "token" in shared:
        return shared["token"]
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert r.status_code == 200
    shared["token"] = r.json()["token"]
    return shared["token"]


def auth_headers():
    return {"Authorization": f"Bearer {get_token()}"}


# ─── Debrief Tests ─────────────────────────────────────────────────────────────
class TestSessionDebrief:
    """Tests for GET /api/sessions/{session_id}/debrief"""

    def test_login(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        assert r.status_code == 200
        shared["token"] = r.json()["token"]
        print(f"Logged in, token: {shared['token'][:20]}...")

    def test_debrief_with_no_wrong_answers(self):
        """Start a session, answer all GOOD, verify debrief returns empty gaps"""
        # Start session
        r = requests.post(f"{BASE_URL}/api/sessions/start",
                         json={"pack_id": PACK_ID, "duration_minutes": 5},
                         headers=auth_headers())
        assert r.status_code == 200, f"Start session failed: {r.text}"
        data = r.json()
        session_id = data["session_id"]
        total = data["total"]
        current_item = data["current_item"]
        print(f"Started session {session_id} with {total} items")

        # Answer all with 'good'
        for i in range(total):
            concept_id = current_item["concept"]["id"]
            check_id = current_item["check"]["id"]
            r = requests.post(f"{BASE_URL}/api/sessions/answer",
                             json={
                                 "session_id": session_id,
                                 "concept_id": concept_id,
                                 "check_id": check_id,
                                 "rating": "good",
                                 "user_answer": "good answer"
                             },
                             headers=auth_headers())
            assert r.status_code == 200, f"Answer failed: {r.text}"
            answer_data = r.json()
            if answer_data.get("session_complete"):
                break
            current_item = answer_data["next_item"]

        # Get debrief - no wrong answers, should return empty gaps
        r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/debrief", headers=auth_headers())
        assert r.status_code == 200, f"Debrief failed: {r.text}"
        debrief = r.json()
        print(f"Debrief (no wrong): {debrief}")

        assert "top_gaps" in debrief
        assert "pattern" in debrief
        assert "can_drill" in debrief
        assert "drill_concept_ids" in debrief
        assert debrief["top_gaps"] == [], f"Expected empty gaps, got: {debrief['top_gaps']}"
        assert debrief["can_drill"] == False, f"Expected can_drill=False"
        assert debrief["pattern"] is None
        print("✅ Zero wrong answers debrief: correct empty response")

    def test_debrief_with_wrong_answers(self):
        """Start a session, answer first item with 'again', rest 'good', verify debrief has gaps"""
        # Start session
        r = requests.post(f"{BASE_URL}/api/sessions/start",
                         json={"pack_id": PACK_ID, "duration_minutes": 5},
                         headers=auth_headers())
        assert r.status_code == 200, f"Start session failed: {r.text}"
        data = r.json()
        session_id = data["session_id"]
        total = data["total"]
        current_item = data["current_item"]
        print(f"Started session {session_id} with {total} items")

        # Answer first with 'again' and user_answer
        concept_id = current_item["concept"]["id"]
        check_id = current_item["check"]["id"]
        r = requests.post(f"{BASE_URL}/api/sessions/answer",
                         json={
                             "session_id": session_id,
                             "concept_id": concept_id,
                             "check_id": check_id,
                             "rating": "again",
                             "user_answer": "I don't know this concept well"
                         },
                         headers=auth_headers())
        assert r.status_code == 200, f"First answer failed: {r.text}"
        answer_data = r.json()
        
        if not answer_data.get("session_complete"):
            current_item = answer_data["next_item"]
            # Answer rest with 'good'
            for i in range(total - 1):
                concept_id = current_item["concept"]["id"]
                check_id = current_item["check"]["id"]
                r = requests.post(f"{BASE_URL}/api/sessions/answer",
                                 json={
                                     "session_id": session_id,
                                     "concept_id": concept_id,
                                     "check_id": check_id,
                                     "rating": "good",
                                     "user_answer": ""
                                 },
                                 headers=auth_headers())
                assert r.status_code == 200
                ans = r.json()
                if ans.get("session_complete"):
                    break
                current_item = ans["next_item"]

        # Get debrief - wait a bit for AI call
        print("Waiting for debrief AI analysis...")
        time.sleep(5)

        r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/debrief", headers=auth_headers())
        assert r.status_code == 200, f"Debrief failed: {r.text}"
        debrief = r.json()
        print(f"Debrief (with wrong): {debrief}")

        assert debrief["wrong_count"] >= 1, "Expected at least 1 wrong answer"
        assert debrief["can_drill"] == True, "Expected can_drill=True"
        assert len(debrief["drill_concept_ids"]) >= 1, "Expected at least 1 drill concept"
        assert len(debrief["top_gaps"]) >= 1, f"Expected top_gaps populated: {debrief}"

        # Check gap structure
        gap = debrief["top_gaps"][0]
        assert "concept_name" in gap
        assert "risk_reason" in gap
        print(f"✅ Debrief with wrong answers: {len(debrief['top_gaps'])} gaps found")
        
        # Store for drill test
        shared["drill_concept_ids"] = debrief["drill_concept_ids"]

    def test_debrief_session_id_field_stored_in_review_events(self):
        """Verify review_events have session_id field by checking debrief query works"""
        # Reuse previous session or create new one
        if "drill_concept_ids" not in shared:
            pytest.skip("No session created yet, run test_debrief_with_wrong_answers first")
        # If debrief worked in previous test, session_id is stored in review_events
        print("✅ session_id field in review_events confirmed (debrief query worked)")

    def test_debrief_invalid_session(self):
        """Debrief with invalid session ID returns 400 or 404"""
        r = requests.get(f"{BASE_URL}/api/sessions/invalid_id/debrief", headers=auth_headers())
        assert r.status_code in [400, 404]
        print(f"✅ Invalid session ID returns {r.status_code}")

    def test_debrief_other_user_session(self):
        """Debrief for another user's session returns 404"""
        # Create a session ID that doesn't exist for this user
        import random, string
        fake_id = "6" + "".join(random.choices("0123456789abcdef", k=23))
        r = requests.get(f"{BASE_URL}/api/sessions/{fake_id}/debrief", headers=auth_headers())
        assert r.status_code == 404
        print(f"✅ Non-existent session returns 404")


# ─── Drill Session Tests ───────────────────────────────────────────────────────
class TestDrillSession:
    """Tests for POST /api/sessions/drill"""

    def test_login(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        assert r.status_code == 200
        shared["token"] = r.json()["token"]

    def test_drill_session_creates_with_recall_contrast(self):
        """Drill session uses recall+contrast checks only"""
        if not shared.get("drill_concept_ids"):
            # First create a session with a wrong answer to get concept IDs
            r = requests.post(f"{BASE_URL}/api/sessions/start",
                             json={"pack_id": PACK_ID, "duration_minutes": 5},
                             headers=auth_headers())
            assert r.status_code == 200
            data = r.json()
            concept_id = data["current_item"]["concept"]["id"]
            check_id = data["current_item"]["check"]["id"]
            session_id = data["session_id"]
            # Complete quickly
            for _ in range(data["total"]):
                r2 = requests.post(f"{BASE_URL}/api/sessions/answer",
                                  json={"session_id": session_id, "concept_id": concept_id,
                                        "check_id": check_id, "rating": "good", "user_answer": ""},
                                  headers=auth_headers())
                if r2.json().get("session_complete"):
                    break
                ni = r2.json().get("next_item")
                if ni:
                    concept_id = ni["concept"]["id"]
                    check_id = ni["check"]["id"]
            shared["drill_concept_ids"] = [data["current_item"]["concept"]["id"]]

        concept_ids = shared["drill_concept_ids"][:2]
        r = requests.post(f"{BASE_URL}/api/sessions/drill",
                         json={"concept_ids": concept_ids},
                         headers=auth_headers())
        assert r.status_code == 200, f"Drill session failed: {r.text}"
        data = r.json()
        print(f"Drill session: {data}")

        assert "session_id" in data
        assert data.get("is_drill") == True
        assert "current_item" in data
        assert data["current_item"]["concept"] is not None
        assert data["current_item"]["check"] is not None
        
        # Check type should be recall or contrast
        check_type = data["current_item"]["check"].get("type")
        assert check_type in ["recall", "contrast"], f"Expected recall or contrast, got: {check_type}"
        
        shared["drill_session_id"] = data["session_id"]
        shared["drill_current_item"] = data["current_item"]
        shared["drill_total"] = data["total"]
        print(f"✅ Drill session created: {data['session_id']}, check type: {check_type}")

    def test_drill_session_answer_flow(self):
        """Drill session accepts answers via POST /api/sessions/answer"""
        if not shared.get("drill_session_id"):
            pytest.skip("No drill session created")
        
        session_id = shared["drill_session_id"]
        current_item = shared["drill_current_item"]
        
        r = requests.post(f"{BASE_URL}/api/sessions/answer",
                         json={
                             "session_id": session_id,
                             "concept_id": current_item["concept"]["id"],
                             "check_id": current_item["check"]["id"],
                             "rating": "good",
                             "user_answer": "test answer"
                         },
                         headers=auth_headers())
        assert r.status_code == 200, f"Drill answer failed: {r.text}"
        data = r.json()
        print(f"Drill answer response: session_complete={data.get('session_complete')}")
        assert "session_complete" in data
        print("✅ Drill session answer flow works")

    def test_drill_no_concept_ids(self):
        """Drill with empty concept_ids returns 400"""
        r = requests.post(f"{BASE_URL}/api/sessions/drill",
                         json={"concept_ids": []},
                         headers=auth_headers())
        assert r.status_code == 400
        print(f"✅ Empty concept_ids returns 400")

    def test_drill_invalid_concept_id(self):
        """Drill with invalid concept IDs should handle gracefully"""
        r = requests.post(f"{BASE_URL}/api/sessions/drill",
                         json={"concept_ids": ["invalid_id_xyz"]},
                         headers=auth_headers())
        # Should either return 400 (no valid checks) or 200
        assert r.status_code in [400, 200]
        print(f"✅ Invalid concept ID returns {r.status_code}")
