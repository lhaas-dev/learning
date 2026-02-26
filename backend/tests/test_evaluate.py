"""
Tests for POST /api/checks/evaluate - Answer Evaluation endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "test_km_tester@example.com"
TEST_PASSWORD = "password123"

# Pack IDs from test context
NEW_PACK_ID = "69a0d422aaf6f2ddaeebd0f1"   # has answer_requirements
OLD_PACK_ID = "69a0c27812e8a54c83092edb"    # no requirements


@pytest.fixture(scope="module")
def auth_token():
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    if res.status_code != 200:
        pytest.skip(f"Auth failed: {res.text}")
    return res.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def check_with_requirements(auth_headers):
    """Get a check from the new pack that has answer_requirements"""
    res = requests.get(f"{BASE_URL}/api/packs/{NEW_PACK_ID}/concepts", headers=auth_headers)
    if res.status_code != 200:
        pytest.skip("Could not fetch concepts from new pack")
    concepts = res.json()
    if not concepts:
        pytest.skip("No concepts in new pack")
    # Get checks for first concept
    concept_id = concepts[0]['id']
    res2 = requests.get(f"{BASE_URL}/api/concepts/{concept_id}/checks", headers=auth_headers)
    if res2.status_code != 200:
        pytest.skip("Could not fetch checks")
    checks = res2.json()
    # Find check with answer_requirements
    for c in checks:
        reqs = c.get('answer_requirements', {})
        if reqs and reqs.get('required_ideas'):
            return c
    pytest.skip("No check with answer_requirements found in new pack")


@pytest.fixture(scope="module")
def check_without_requirements(auth_headers):
    """Get a check from the old pack that has no answer_requirements"""
    res = requests.get(f"{BASE_URL}/api/packs/{OLD_PACK_ID}/concepts", headers=auth_headers)
    if res.status_code != 200:
        pytest.skip("Could not fetch concepts from old pack")
    concepts = res.json()
    if not concepts:
        pytest.skip("No concepts in old pack")
    concept_id = concepts[0]['id']
    res2 = requests.get(f"{BASE_URL}/api/concepts/{concept_id}/checks", headers=auth_headers)
    if res2.status_code != 200:
        pytest.skip("Could not fetch checks")
    checks = res2.json()
    if not checks:
        pytest.skip("No checks in old pack concept")
    return checks[0]


class TestEvaluateEndpoint:

    def test_empty_answer_returns_no_answer(self, auth_headers, check_without_requirements):
        """Empty answer should return result='no_answer'"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": check_without_requirements['id'],
            "user_answer": ""
        }, headers=auth_headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data['result'] == 'no_answer'
        assert 'summary' in data
        assert data['covered_ideas'] == []
        assert data['missing_ideas'] == []

    def test_whitespace_only_answer_returns_no_answer(self, auth_headers, check_without_requirements):
        """Whitespace-only answer should also return result='no_answer'"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": check_without_requirements['id'],
            "user_answer": "   "
        }, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data['result'] == 'no_answer'

    def test_old_check_no_requirements_returns_no_requirements(self, auth_headers, check_without_requirements):
        """Check without answer_requirements returns result='no_requirements'"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": check_without_requirements['id'],
            "user_answer": "This is a proper answer about firewalls and network security"
        }, headers=auth_headers)
        assert res.status_code == 200, f"Got {res.status_code}: {res.text}"
        data = res.json()
        assert data['result'] == 'no_requirements'
        assert 'summary' in data

    def test_invalid_check_id_returns_400(self, auth_headers):
        """Invalid check ID returns 400"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": "not-an-object-id",
            "user_answer": "some answer"
        }, headers=auth_headers)
        assert res.status_code == 400

    def test_nonexistent_check_id_returns_404(self, auth_headers):
        """Nonexistent (but valid format) check ID returns 404"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": "000000000000000000000000",
            "user_answer": "some answer"
        }, headers=auth_headers)
        assert res.status_code == 404

    def test_unauthenticated_request_returns_403(self):
        """No auth token returns 403"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": "000000000000000000000000",
            "user_answer": "some answer"
        })
        assert res.status_code in [401, 403]

    def test_good_answer_with_requirements_returns_result(self, auth_headers, check_with_requirements):
        """Good answer returns result with covered_ideas"""
        # Use required ideas from the check itself as good answer
        req_ideas = check_with_requirements.get('answer_requirements', {}).get('required_ideas', [])
        if not req_ideas:
            pytest.skip("No required ideas")
        good_answer = ". ".join(req_ideas)  # concatenate required ideas as answer

        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": check_with_requirements['id'],
            "user_answer": good_answer
        }, headers=auth_headers, timeout=30)
        assert res.status_code == 200, f"Got {res.status_code}: {res.text}"
        data = res.json()
        assert data['result'] in ['correct', 'partially_correct', 'incorrect']
        assert 'covered_ideas' in data
        assert 'missing_ideas' in data
        assert 'wrong_ideas_stated' in data
        print(f"Good answer result: {data['result']}, covered: {len(data['covered_ideas'])}, missing: {len(data['missing_ideas'])}")

    def test_bad_answer_with_requirements_has_missing_ideas(self, auth_headers, check_with_requirements):
        """Nonsense answer for check with requirements should have missing_ideas"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": check_with_requirements['id'],
            "user_answer": "I have no idea about this topic at all"
        }, headers=auth_headers, timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert data['result'] in ['incorrect', 'partially_correct']
        print(f"Bad answer result: {data['result']}, missing: {data['missing_ideas']}")


class TestNewCheckSchema:

    def test_new_pack_checks_have_answer_requirements(self, auth_headers):
        """New pack checks should have answer_requirements.required_ideas"""
        res = requests.get(f"{BASE_URL}/api/packs/{NEW_PACK_ID}/concepts", headers=auth_headers)
        assert res.status_code == 200
        concepts = res.json()
        assert len(concepts) > 0, "New pack should have concepts"

        found_with_reqs = 0
        for concept in concepts[:3]:  # check first 3 concepts
            res2 = requests.get(f"{BASE_URL}/api/concepts/{concept['id']}/checks", headers=auth_headers)
            if res2.status_code == 200:
                for check in res2.json():
                    reqs = check.get('answer_requirements', {})
                    if reqs and reqs.get('required_ideas'):
                        found_with_reqs += 1

        print(f"Found {found_with_reqs} checks with required_ideas in new pack")
        assert found_with_reqs > 0, "New pack should have checks with answer_requirements"
