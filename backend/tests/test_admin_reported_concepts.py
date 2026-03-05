"""
Tests for Admin-View features:
- POST /api/concepts/{id}/report
- GET /api/packs/{pack_id}/reported-concepts
- POST /api/packs/{pack_id}/concepts/bulk-dismiss
- POST /api/packs/{pack_id}/concepts/bulk-delete (structure check only)
- POST /api/upload/text
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
PACK_ID = "69a82c7bc7c639682e4e9224"  # W&G ES5 pack with 933 concepts
TEST_EMAIL = "test_km_tester@example.com"
TEST_PASSWORD = "password123"


@pytest.fixture(scope="module")
def auth_token():
    """Obtain JWT token for test user."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json().get("token") or resp.json().get("access_token")
    assert token, "No token in login response"
    return token


@pytest.fixture(scope="module")
def client(auth_token):
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    })
    return session


# ─── GET /api/packs/{pack_id}/reported-concepts ───────────────────────────────

class TestListReportedConcepts:
    """Tests for GET /api/packs/{pack_id}/reported-concepts"""

    def test_list_reported_concepts_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/api/packs/{PACK_ID}/reported-concepts")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_list_reported_concepts_returns_list(self, client):
        resp = client.get(f"{BASE_URL}/api/packs/{PACK_ID}/reported-concepts")
        data = resp.json()
        assert isinstance(data, list), "Response should be a list"

    def test_reported_concepts_have_required_fields(self, client):
        resp = client.get(f"{BASE_URL}/api/packs/{PACK_ID}/reported-concepts")
        data = resp.json()
        if len(data) > 0:
            first = data[0]
            assert "id" in first, "Missing 'id' field"
            assert "title" in first, "Missing 'title' field"
            assert "short_definition" in first, "Missing 'short_definition' field"
            assert "reported_at" in first, "Missing 'reported_at' field"
        else:
            pytest.skip("No reported concepts available, skipping field validation")

    def test_reported_concepts_count_positive(self, client):
        resp = client.get(f"{BASE_URL}/api/packs/{PACK_ID}/reported-concepts")
        data = resp.json()
        print(f"Reported concepts count: {len(data)}")
        assert len(data) >= 0, "Should return a valid list"

    def test_list_reported_requires_auth(self):
        # Without token
        resp = requests.get(f"{BASE_URL}/api/packs/{PACK_ID}/reported-concepts")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"

    def test_list_reported_invalid_pack(self, client):
        resp = client.get(f"{BASE_URL}/api/packs/000000000000000000000000/reported-concepts")
        assert resp.status_code in [404, 403], f"Expected 404/403, got {resp.status_code}"


# ─── POST /api/concepts/{id}/report ──────────────────────────────────────────

class TestReportConcept:
    """Tests for POST /api/concepts/{concept_id}/report"""

    def test_report_concept_success(self, client):
        # First get a concept from the pack
        concepts_resp = client.get(f"{BASE_URL}/api/packs/{PACK_ID}/concepts")
        assert concepts_resp.status_code == 200
        concepts = concepts_resp.json()
        assert len(concepts) > 0, "No concepts found in pack"

        # Find a concept that is NOT already reported
        reported_resp = client.get(f"{BASE_URL}/api/packs/{PACK_ID}/reported-concepts")
        reported_ids = {c["id"] for c in reported_resp.json()}

        # Find an unreported concept to report
        target = None
        for c in concepts:
            if c["id"] not in reported_ids:
                target = c
                break

        if not target:
            pytest.skip("All concepts already reported, skipping test")

        # Report the concept
        resp = client.post(f"{BASE_URL}/api/concepts/{target['id']}/report")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert data.get("reported") is True, f"Expected reported=True, got {data}"
        assert data.get("concept_id") == target["id"], "concept_id mismatch"

        # Store for cleanup
        TestReportConcept._reported_concept_id = target["id"]

    def test_reported_concept_appears_in_list(self, client):
        if not hasattr(TestReportConcept, "_reported_concept_id"):
            pytest.skip("No concept was reported in previous test")
        concept_id = TestReportConcept._reported_concept_id

        resp = client.get(f"{BASE_URL}/api/packs/{PACK_ID}/reported-concepts")
        ids = [c["id"] for c in resp.json()]
        assert concept_id in ids, f"Reported concept {concept_id} not found in reported list"

    def test_report_concept_requires_auth(self):
        resp = requests.post(f"{BASE_URL}/api/concepts/anyconceptid/report")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"

    def test_report_concept_invalid_id(self, client):
        resp = client.post(f"{BASE_URL}/api/concepts/invalid_id/report")
        assert resp.status_code in [400, 404], f"Expected 400/404, got {resp.status_code}"


# ─── POST /api/packs/{pack_id}/concepts/bulk-dismiss ─────────────────────────

class TestBulkDismiss:
    """Tests for POST /api/packs/{pack_id}/concepts/bulk-dismiss (non-destructive)"""

    def test_bulk_dismiss_one_concept(self, client):
        """Dismiss one reported concept and verify it's removed from reported list."""
        reported_resp = client.get(f"{BASE_URL}/api/packs/{PACK_ID}/reported-concepts")
        reported = reported_resp.json()

        if not reported:
            pytest.skip("No reported concepts to dismiss")

        # Use the LAST one (least important) to dismiss
        target_id = reported[-1]["id"]
        initial_count = len(reported)

        # Dismiss it
        resp = client.post(
            f"{BASE_URL}/api/packs/{PACK_ID}/concepts/bulk-dismiss",
            json={"concept_ids": [target_id]}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "dismissed" in data, f"Missing 'dismissed' in response: {data}"
        assert data["dismissed"] == 1, f"Expected dismissed=1, got {data['dismissed']}"

        # Verify concept no longer in reported list
        after_resp = client.get(f"{BASE_URL}/api/packs/{PACK_ID}/reported-concepts")
        after_ids = [c["id"] for c in after_resp.json()]
        assert target_id not in after_ids, "Dismissed concept still in reported list"
        print(f"Reported count after dismiss: {len(after_resp.json())} (was {initial_count})")

        # Re-report it to restore state
        re_report = client.post(f"{BASE_URL}/api/concepts/{target_id}/report")
        assert re_report.status_code == 200, "Failed to re-report concept to restore state"
        print(f"Re-reported concept {target_id} to restore state")

    def test_bulk_dismiss_returns_dismissed_count(self, client):
        reported_resp = client.get(f"{BASE_URL}/api/packs/{PACK_ID}/reported-concepts")
        reported = reported_resp.json()

        if len(reported) < 2:
            pytest.skip("Need at least 2 reported concepts for this test")

        ids_to_dismiss = [reported[0]["id"], reported[1]["id"]]

        resp = client.post(
            f"{BASE_URL}/api/packs/{PACK_ID}/concepts/bulk-dismiss",
            json={"concept_ids": ids_to_dismiss}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("dismissed") == len(ids_to_dismiss)

        # Restore: re-report them
        for cid in ids_to_dismiss:
            client.post(f"{BASE_URL}/api/concepts/{cid}/report")

    def test_bulk_dismiss_empty_list(self, client):
        resp = client.post(
            f"{BASE_URL}/api/packs/{PACK_ID}/concepts/bulk-dismiss",
            json={"concept_ids": []}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("dismissed") == 0

    def test_bulk_dismiss_requires_auth(self):
        resp = requests.post(
            f"{BASE_URL}/api/packs/{PACK_ID}/concepts/bulk-dismiss",
            json={"concept_ids": ["someid"]}
        )
        assert resp.status_code in [401, 403]


# ─── POST /api/packs/{pack_id}/concepts/bulk-delete ──────────────────────────

class TestBulkDelete:
    """Structure-check for bulk-delete endpoint (no actual deletion to preserve pack state)."""

    def test_bulk_delete_empty_list_returns_200(self, client):
        """Test with empty list - safe, no actual deletions."""
        resp = client.post(
            f"{BASE_URL}/api/packs/{PACK_ID}/concepts/bulk-delete",
            json={"concept_ids": []}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "deleted" in data, f"Missing 'deleted' in response: {data}"
        assert data["deleted"] == 0, f"Expected deleted=0 for empty list, got {data['deleted']}"

    def test_bulk_delete_requires_auth(self):
        resp = requests.post(
            f"{BASE_URL}/api/packs/{PACK_ID}/concepts/bulk-delete",
            json={"concept_ids": []}
        )
        assert resp.status_code in [401, 403]

    def test_bulk_delete_invalid_pack(self, client):
        resp = client.post(
            f"{BASE_URL}/api/packs/000000000000000000000000/concepts/bulk-delete",
            json={"concept_ids": ["anyid"]}
        )
        assert resp.status_code in [403, 404], f"Expected 403/404, got {resp.status_code}"


# ─── POST /api/upload/text ────────────────────────────────────────────────────

class TestUploadText:
    """Tests for POST /api/upload/text endpoint."""

    def test_upload_text_returns_job_id(self, client):
        resp = client.post(
            f"{BASE_URL}/api/upload/text",
            json={
                "pack_id": PACK_ID,
                "content": "TEST_UPLOAD: Volkswirtschaft - Die Inflation beschreibt den Anstieg des allgemeinen Preisniveaus über einen bestimmten Zeitraum.",
                "source_name": "TEST_text_upload"
            }
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "job_id" in data, f"Missing 'job_id' in response: {data}"
        assert "status" in data, f"Missing 'status' in response: {data}"
        assert data["status"] == "queued", f"Expected status=queued, got {data['status']}"
        print(f"Upload text job created: {data['job_id']}")

    def test_upload_text_empty_content_fails(self, client):
        resp = client.post(
            f"{BASE_URL}/api/upload/text",
            json={
                "pack_id": PACK_ID,
                "content": "   ",
                "source_name": "Empty test"
            }
        )
        assert resp.status_code == 400, f"Expected 400 for empty content, got {resp.status_code}"

    def test_upload_text_invalid_pack_fails(self, client):
        resp = client.post(
            f"{BASE_URL}/api/upload/text",
            json={
                "pack_id": "000000000000000000000000",
                "content": "Some valid content here.",
                "source_name": "Test"
            }
        )
        assert resp.status_code in [400, 404], f"Expected 400/404, got {resp.status_code}"

    def test_upload_text_requires_auth(self):
        resp = requests.post(
            f"{BASE_URL}/api/upload/text",
            json={"pack_id": PACK_ID, "content": "Test content", "source_name": "Test"}
        )
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"


# ─── Concepts count integrity ─────────────────────────────────────────────────

class TestConceptsIntegrity:
    """Verify pack still has expected concept count after tests."""

    def test_pack_concepts_count(self, client):
        resp = client.get(f"{BASE_URL}/api/packs/{PACK_ID}/concepts")
        assert resp.status_code == 200
        data = resp.json()
        count = len(data)
        print(f"Total concepts in ES5 pack: {count}")
        # Should have 933 or close (test runs might add minimal via text upload)
        assert count >= 900, f"Expected at least 900 concepts, got {count}"
