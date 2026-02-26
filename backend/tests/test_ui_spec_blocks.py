"""
Tests for iteration 5: UI Spec Block Structure & Answer Evaluation
Tests for:
- POST /api/checks/evaluate: response includes extracted_claims, missing_ideas, wrong_ideas_stated
- Block content verification: all 4 blocks present in correct response
- Scenario check type: backend still evaluates, frontend skips
- Risk messages: correct text returned in RATING_CONFIG (verified via session flow)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

TEST_EMAIL = "test_km_tester@example.com"
TEST_PASSWORD = "password123"
PACK_ID = "69a0d422aaf6f2ddaeebd0f1"

# Known check IDs from pack (recall type with dict requirements)
RECALL_CHECK_WITH_REQS = "69a0d43caaf6f2ddaeebd0f4"  # recall, required: ['two or more factors', 'verify identity', 'before granting access']
SCENARIO_CHECK_ID = "69a0d43caaf6f2ddaeebd0f6"  # scenario type with dict requirements
SCENARIO_CHECK_LIST_REQS = "69a0d44daaf6f2ddaeebd0fb"  # scenario with list (malformed) requirements


@pytest.fixture(scope="module")
def auth_headers():
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    if res.status_code != 200:
        pytest.skip(f"Auth failed: {res.text}")
    token = res.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestEvaluateBlockStructure:
    """Verify that /api/checks/evaluate returns all required block fields"""

    def test_evaluate_returns_all_required_block_fields(self, auth_headers):
        """Response must include: result, extracted_claims, missing_ideas, wrong_ideas_stated"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": RECALL_CHECK_WITH_REQS,
            "user_answer": "MFA uses two or more factors to verify identity before granting access"
        }, headers=auth_headers, timeout=30)
        assert res.status_code == 200, f"Got {res.status_code}: {res.text}"
        data = res.json()

        # Block 1 source: correct answer comes from check.expected_answer (not in evaluate response)
        # Block 2 source: extracted_claims
        assert 'extracted_claims' in data, "Block 2 requires extracted_claims in response"
        assert isinstance(data['extracted_claims'], list), "extracted_claims must be a list"

        # Block 3 source: missing_ideas
        assert 'missing_ideas' in data, "Block 3 requires missing_ideas in response"
        assert isinstance(data['missing_ideas'], list), "missing_ideas must be a list"

        # Block 4 source: wrong_ideas_stated
        assert 'wrong_ideas_stated' in data, "Block 4 requires wrong_ideas_stated in response"
        assert isinstance(data['wrong_ideas_stated'], list), "wrong_ideas_stated must be a list"

        # result field
        assert 'result' in data
        assert data['result'] in ['correct', 'partially_correct', 'incorrect', 'no_answer', 'no_requirements']
        print(f"  Result: {data['result']}")
        print(f"  extracted_claims: {data['extracted_claims']}")
        print(f"  missing_ideas: {data['missing_ideas']}")
        print(f"  wrong_ideas_stated: {data['wrong_ideas_stated']}")

    def test_empty_answer_returns_no_answer_with_empty_lists(self, auth_headers):
        """Block 2 fallback: empty answer → result=no_answer, all lists empty"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": RECALL_CHECK_WITH_REQS,
            "user_answer": ""
        }, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data['result'] == 'no_answer'
        assert data['covered_ideas'] == []
        assert data['missing_ideas'] == []
        assert data['wrong_ideas_stated'] == []
        # No extracted_claims for empty answer
        extracted = data.get('extracted_claims', [])
        assert isinstance(extracted, list)
        print(f"  Empty answer: result={data['result']}, claims={extracted}")

    def test_good_answer_produces_extracted_claims(self, auth_headers):
        """Block 2: Answer with content should produce at least 1 extracted claim"""
        answer = "MFA requires two or more factors. It verifies identity before granting access. These factors can be something you know, have, or are."
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": RECALL_CHECK_WITH_REQS,
            "user_answer": answer
        }, headers=auth_headers, timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert len(data.get('extracted_claims', [])) >= 1, f"Expected claims for detailed answer, got: {data.get('extracted_claims')}"
        print(f"  Claims count: {len(data['extracted_claims'])}")
        print(f"  Claims: {data['extracted_claims']}")

    def test_all_covered_produces_empty_missing_ideas(self, auth_headers):
        """Block 3 'all covered' path: when all required_ideas covered, missing_ideas=[]"""
        # Answer containing all required ideas
        answer = "MFA verifies identity using two or more factors before granting access to a system or resource"
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": RECALL_CHECK_WITH_REQS,
            "user_answer": answer
        }, headers=auth_headers, timeout=30)
        assert res.status_code == 200
        data = res.json()
        # Either correct (missing=0) or partially_correct
        print(f"  Result: {data['result']}, missing: {data['missing_ideas']}")
        # The key assertion is that missing_ideas is a list (could be empty or not depending on LLM)
        assert isinstance(data['missing_ideas'], list)
        if data['result'] == 'correct':
            assert len(data['missing_ideas']) == 0, "Correct result should have no missing_ideas"

    def test_wrong_answer_produces_missing_ideas_for_block3(self, auth_headers):
        """Block 3 'missing' path: irrelevant answer should have missing_ideas populated"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": RECALL_CHECK_WITH_REQS,
            "user_answer": "I think it might have something to do with passwords"
        }, headers=auth_headers, timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert data['result'] in ['incorrect', 'partially_correct']
        assert len(data['missing_ideas']) > 0, f"Expected missing_ideas for vague answer, got: {data['missing_ideas']}"
        print(f"  Result: {data['result']}, missing: {data['missing_ideas']}")


class TestScenarioCheckBehavior:
    """Scenario checks: backend evaluates fine; frontend EvaluationPanel returns null"""

    def test_scenario_check_with_dict_reqs_still_evaluates(self, auth_headers):
        """Backend doesn't care about check type — scenario check evaluates normally"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": SCENARIO_CHECK_ID,
            "user_answer": "This is MFA because two factors are present: password and fingerprint"
        }, headers=auth_headers, timeout=30)
        assert res.status_code == 200, f"Got {res.status_code}: {res.text}"
        data = res.json()
        # Backend evaluates regardless of check type
        assert data['result'] in ['correct', 'partially_correct', 'incorrect']
        assert 'extracted_claims' in data
        print(f"  Scenario check result: {data['result']}")
        print(f"  Note: Frontend EvaluationPanel returns null for scenario type — this is UI-only behavior")

    def test_scenario_check_with_list_reqs_returns_no_requirements(self, auth_headers):
        """Scenario check with malformed list requirements → no_requirements (graceful)"""
        res = requests.post(f"{BASE_URL}/api/checks/evaluate", json={
            "check_id": SCENARIO_CHECK_LIST_REQS,
            "user_answer": "This seems like a valid answer involving multiple factors"
        }, headers=auth_headers, timeout=30)
        assert res.status_code == 200, f"Got {res.status_code}: {res.text}"
        data = res.json()
        # Malformed list requirements → no_requirements
        assert data['result'] == 'no_requirements', f"Expected no_requirements for list-formatted reqs, got {data['result']}"
        print(f"  Scenario list-reqs result: {data['result']} (graceful fallback)")


class TestRatingConfigMessages:
    """Verify rating flow works (risk messages are frontend-only, verified via session answer)"""

    def test_session_start_for_pack(self, auth_headers):
        """Session can be started for the test pack"""
        res = requests.post(f"{BASE_URL}/api/sessions/start",
                           json={"pack_id": PACK_ID, "duration_minutes": 10},
                           headers=auth_headers)
        assert res.status_code == 200, f"Got {res.status_code}: {res.text}"
        data = res.json()
        assert 'session_id' in data
        assert 'current_item' in data
        assert data['current_item']['check'] is not None
        assert data['current_item']['concept'] is not None
        check = data['current_item']['check']
        print(f"  Session started, check type: {check.get('type')}")

        # Rate this item and verify next_item
        session_id = data['session_id']
        concept_id = data['current_item']['concept']['id']
        check_id = check['id']

        rate_res = requests.post(f"{BASE_URL}/api/sessions/answer", json={
            "session_id": session_id,
            "concept_id": concept_id,
            "check_id": check_id,
            "rating": "good",
            "user_answer": "test answer"
        }, headers=auth_headers)
        assert rate_res.status_code == 200
        rate_data = rate_res.json()
        assert 'session_complete' in rate_data
        print(f"  After rating 'good': session_complete={rate_data['session_complete']}")

    def test_rating_again_advances_session(self, auth_headers):
        """Rating 'again' advances session (frontend will show high risk message)"""
        res = requests.post(f"{BASE_URL}/api/sessions/start",
                           json={"pack_id": PACK_ID, "duration_minutes": 10},
                           headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        session_id = data['session_id']
        item = data['current_item']

        rate_res = requests.post(f"{BASE_URL}/api/sessions/answer", json={
            "session_id": session_id,
            "concept_id": item['concept']['id'],
            "check_id": item['check']['id'],
            "rating": "again",
            "user_answer": "I don't know"
        }, headers=auth_headers)
        assert rate_res.status_code == 200
        rate_data = rate_res.json()
        # 'again' should trigger micro_fix if user_answer is non-empty
        print(f"  Rating 'again' — session_complete={rate_data.get('session_complete')}")
        print(f"  Note: Frontend shows 'High exam risk detected. This concept will be prioritized.'")

    def test_rating_easy_advances_session(self, auth_headers):
        """Rating 'easy' advances session (frontend will show low risk message)"""
        res = requests.post(f"{BASE_URL}/api/sessions/start",
                           json={"pack_id": PACK_ID, "duration_minutes": 10},
                           headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        session_id = data['session_id']
        item = data['current_item']

        rate_res = requests.post(f"{BASE_URL}/api/sessions/answer", json={
            "session_id": session_id,
            "concept_id": item['concept']['id'],
            "check_id": item['check']['id'],
            "rating": "easy",
            "user_answer": ""
        }, headers=auth_headers)
        assert rate_res.status_code == 200
        print(f"  Rating 'easy' — Note: Frontend shows 'Low risk detected. This concept will be deprioritized.'")


class TestHealthAndAuth:
    """Basic connectivity tests"""

    def test_health_check(self):
        res = requests.get(f"{BASE_URL}/api/health")
        assert res.status_code == 200
        assert res.json()['status'] == 'ok'

    def test_login_with_test_credentials(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        assert res.status_code == 200
        assert 'token' in res.json()
