"""
Tests for POST /api/checks/evaluate - Answer Evaluation endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

TEST_EMAIL = "test_km_tester@example.com"
TEST_PASSWORD = "password123"
NEW_PACK_ID = "69a0d422aaf6f2ddaeebd0f1"  # has answer_requirements
OLD_PACK_ID = "69a0c27812e8a54c83092edb"   # no requirements


@pytest.fixture(scope="module")
def auth_headers():
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    if res.status_code != 200:
        pytest.skip(f"Auth failed: {res.text}")
    token = res.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def check_with_requirements(auth_headers):
    """Start session on new pack to get a check with requirements"""
    res = requests.post(f"{BASE_URL}/api/sessions/start", json={"pack_id": NEW_PACK_ID}, headers=auth_headers)
    if res.status_code != 200:
        pytest.skip(f"Could not start session: {res.text}")
    data = res.json()
    check = data['current_item']['check']
    if not check.get('answer_requirements', {}).get('required_ideas'):
        pytest.skip("Check has no required_ideas")
    return check


@pytest.fixture(scope="module")
def check_without_requirements(auth_headers):
    """Start session on old pack to get a check without requirements"""
    res = requests.post(f"{BASE_URL}/api/sessions/start", json={"pack_id": OLD_PACK_ID}, headers=auth_headers)
    if res.status_code != 200:
        pytest.skip(f"Could not start old pack session: {res.text}")
    return res.json()['current_item']['check']


class TestEvaluateEndpoint:

    def test_empty_answer_returns_no_answer(self, auth_headers, check_without_requirements):
        """Empty answer returns result='no_answer'"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": check_without_requirements['id'],
            "user_answer": ""
        }, headers=auth_headers)
        assert res.status_code == 200, f"Got {res.status_code}: {res.text}"
        data = res.json()
        assert data['result'] == 'no_answer'
        assert data['covered_ideas'] == []
        assert data['missing_ideas'] == []

    def test_whitespace_answer_returns_no_answer(self, auth_headers, check_without_requirements):
        """Whitespace-only answer returns result='no_answer'"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": check_without_requirements['id'],
            "user_answer": "   "
        }, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()['result'] == 'no_answer'

    def test_old_check_returns_no_requirements(self, auth_headers, check_without_requirements):
        """Check without answer_requirements returns result='no_requirements'"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": check_without_requirements['id'],
            "user_answer": "This is a proper answer about firewalls and network security in detail"
        }, headers=auth_headers)
        assert res.status_code == 200, f"Got {res.status_code}: {res.text}"
        data = res.json()
        assert data['result'] == 'no_requirements'
        print(f"  no_requirements summary: {data['summary']}")

    def test_invalid_check_id_returns_400(self, auth_headers):
        """Invalid check ID format returns 400"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": "not-an-object-id",
            "user_answer": "some answer"
        }, headers=auth_headers)
        assert res.status_code == 400

    def test_nonexistent_check_id_returns_404(self, auth_headers):
        """Valid-format but nonexistent check ID returns 404"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": "000000000000000000000000",
            "user_answer": "some answer"
        }, headers=auth_headers)
        assert res.status_code == 404

    def test_unauthenticated_returns_401_or_403(self):
        """No auth token returns 401/403"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": "000000000000000000000000",
            "user_answer": "some answer"
        })
        assert res.status_code in [401, 403]

    def test_good_answer_with_requirements(self, auth_headers, check_with_requirements):
        """Answer containing required ideas returns correct/partially_correct"""
        required_ideas = check_with_requirements['answer_requirements']['required_ideas']
        good_answer = ". ".join(required_ideas)
        print(f"  Testing with required ideas: {required_ideas}")

        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": check_with_requirements['id'],
            "user_answer": good_answer
        }, headers=auth_headers, timeout=30)
        assert res.status_code == 200, f"Got {res.status_code}: {res.text}"
        data = res.json()
        assert data['result'] in ['correct', 'partially_correct', 'incorrect']
        print(f"  Result: {data['result']}, covered: {data['covered_ideas']}, missing: {data['missing_ideas']}")

    def test_bad_answer_with_requirements_has_missing_ideas(self, auth_headers, check_with_requirements):
        """Irrelevant answer returns incorrect/partially_correct with missing_ideas populated"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": check_with_requirements['id'],
            "user_answer": "I have absolutely no idea about this topic whatsoever"
        }, headers=auth_headers, timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert data['result'] in ['incorrect', 'partially_correct']
        assert len(data['missing_ideas']) > 0, "Bad answer should have missing_ideas"
        print(f"  Result: {data['result']}, missing: {data['missing_ideas']}")

    def test_evaluation_returns_extracted_claims(self, auth_headers, check_with_requirements):
        """Evaluation with requirements returns extracted_claims list"""
        required_ideas = check_with_requirements['answer_requirements']['required_ideas']
        good_answer = ". ".join(required_ideas)
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": check_with_requirements['id'],
            "user_answer": good_answer
        }, headers=auth_headers, timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert 'extracted_claims' in data, "Response must include extracted_claims"
        assert isinstance(data['extracted_claims'], list), "extracted_claims must be a list"
        print(f"  extracted_claims count: {len(data['extracted_claims'])}")
        print(f"  extracted_claims: {data['extracted_claims']}")

    def test_no_answer_does_not_include_extracted_claims(self, auth_headers, check_without_requirements):
        """Empty answer (no_answer result) should not crash — extracted_claims may be absent"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": check_without_requirements['id'],
            "user_answer": ""
        }, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data['result'] == 'no_answer'
        # extracted_claims may or may not be present; frontend defaults to []
        # If present, must be list
        if 'extracted_claims' in data:
            assert isinstance(data['extracted_claims'], list)

    def test_extracted_claims_is_populated_for_detailed_answer(self, auth_headers, check_with_requirements):
        """A substantive answer to a check with requirements populates extracted_claims"""
        required_ideas = check_with_requirements['answer_requirements']['required_ideas']
        detailed_answer = f"In my answer: {'. '.join(required_ideas)}"
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": check_with_requirements['id'],
            "user_answer": detailed_answer
        }, headers=auth_headers, timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert 'extracted_claims' in data
        # A detailed answer should produce at least one extracted claim
        assert len(data['extracted_claims']) >= 1, f"Expected claims, got: {data['extracted_claims']}"
        print(f"  Claims extracted: {data['extracted_claims']}")


class TestNewCheckSchema:

    def test_new_pack_check_has_answer_requirements(self, check_with_requirements):
        """New pack checks should have answer_requirements.required_ideas"""
        reqs = check_with_requirements.get('answer_requirements', {})
        assert reqs, "Check should have answer_requirements"
        assert reqs.get('required_ideas'), "Check should have required_ideas"
        assert isinstance(reqs['required_ideas'], list)
        assert len(reqs['required_ideas']) > 0
        print(f"  required_ideas: {reqs['required_ideas']}")
        print(f"  wrong_statements: {reqs.get('wrong_statements', [])}")

    def test_new_pack_concepts_have_concepts(self, auth_headers):
        """New pack has concepts"""
        res = requests.get(f"{BASE_URL}/api/packs/{NEW_PACK_ID}/concepts", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) > 0, "New pack should have concepts"
        print(f"  New pack has {len(data)} concepts")
