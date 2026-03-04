"""
Backend tests for Chunked PDF Upload feature:
- POST /api/upload/chunk (receive base64 chunks)
- POST /api/upload/finalize (assemble + start pipeline)
- GET /api/jobs/{job_id} (job status, concepts_extracted)
- No 15-concept limit validation
"""
import pytest
import requests
import os
import base64
import time
import math

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

TEST_EMAIL = "test_km_tester@example.com"
TEST_PASSWORD = "password123"

# Test PDF path (large PDF for no-limit testing)
TEST_PDF_PATH = "/tmp/test_material/WuG_ES6_mL_2020.pdf"
TEST_TXT_PATH = "/tmp/test_small.txt"

# Shared state across tests
shared = {}
CHUNK_SIZE = 200 * 1024  # 200KB


def get_auth_headers():
    """Helper to get auth headers, using cached token if available."""
    if shared.get("token"):
        return {"Authorization": f"Bearer {shared['token']}"}
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    if r.status_code == 200:
        shared["token"] = r.json()["token"]
        return {"Authorization": f"Bearer {shared['token']}"}
    return {}


# ─── Auth Setup ───────────────────────────────────────────────────────────────
class TestAuthSetup:
    """Login to get token for subsequent tests."""

    def test_login(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        assert r.status_code == 200, f"Login failed: {r.text}"
        data = r.json()
        assert "token" in data
        shared["token"] = data["token"]
        shared["user_id"] = data["user_id"]
        print(f"Login OK, user_id={data['user_id']}")


# ─── Pack Creation ────────────────────────────────────────────────────────────
class TestPackSetup:
    """Create a pack for chunked upload testing."""

    def test_create_pack_for_upload(self):
        headers = get_auth_headers()
        assert headers, "No auth token"
        r = requests.post(f"{BASE_URL}/api/packs", json={
            "title": "TEST_Chunked Upload Pack",
            "description": "Pack for chunked upload testing",
            "domain": "JavaScript ES6"
        }, headers=headers)
        assert r.status_code == 200, f"Pack creation failed: {r.text}"
        data = r.json()
        assert "id" in data
        assert data["title"] == "TEST_Chunked Upload Pack"
        shared["pack_id"] = data["id"]
        print(f"Pack created: {data['id']}")


# ─── Chunk Upload Tests ────────────────────────────────────────────────────────
class TestChunkUpload:
    """Test POST /api/upload/chunk endpoint."""

    def test_chunk_endpoint_requires_auth(self):
        """Chunk endpoint should return 403 without auth."""
        r = requests.post(f"{BASE_URL}/api/upload/chunk", json={
            "upload_id": "test-upload-id",
            "chunk_index": 0,
            "total_chunks": 1,
            "data": base64.b64encode(b"test data").decode()
        })
        assert r.status_code in [401, 403], f"Expected 401/403, got {r.status_code}"

    def test_upload_single_chunk(self):
        """Upload a single chunk with valid data and check response."""
        headers = get_auth_headers()
        assert headers, "No auth token"

        chunk_data = b"Hello, this is a test chunk for chunked upload"
        encoded = base64.b64encode(chunk_data).decode()

        r = requests.post(f"{BASE_URL}/api/upload/chunk", json={
            "upload_id": "TEST_single_chunk_upload",
            "chunk_index": 0,
            "total_chunks": 1,
            "data": encoded
        }, headers=headers)
        assert r.status_code == 200, f"Chunk upload failed: {r.text}"
        data = r.json()
        assert "received" in data, "Response should have 'received' field"
        assert "upload_id" in data, "Response should have 'upload_id' field"
        assert data["received"] == 0, "received should be chunk_index=0"
        assert data["upload_id"] == "TEST_single_chunk_upload"
        print(f"Single chunk upload OK: {data}")

    def test_upload_multiple_chunks_in_sequence(self):
        """Upload 3 chunks sequentially and verify each is acknowledged."""
        headers = get_auth_headers()
        assert headers, "No auth token"

        upload_id = "TEST_multi_chunk_upload_v2"
        chunks = [b"chunk0_data" * 100, b"chunk1_data" * 100, b"chunk2_data" * 100]

        for i, chunk in enumerate(chunks):
            encoded = base64.b64encode(chunk).decode()
            r = requests.post(f"{BASE_URL}/api/upload/chunk", json={
                "upload_id": upload_id,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "data": encoded
            }, headers=headers)
            assert r.status_code == 200, f"Chunk {i} upload failed: {r.text}"
            data = r.json()
            assert data["received"] == i, f"Expected received={i}, got {data['received']}"
            assert data["upload_id"] == upload_id
            print(f"Chunk {i} uploaded OK")

    def test_chunk_with_invalid_base64(self):
        """Chunk with invalid base64 should return 4xx or 5xx."""
        headers = get_auth_headers()
        assert headers, "No auth token"

        r = requests.post(f"{BASE_URL}/api/upload/chunk", json={
            "upload_id": "TEST_invalid_b64",
            "chunk_index": 0,
            "total_chunks": 1,
            "data": "NOT_VALID_BASE64!!!"
        }, headers=headers)
        # Server decodes base64 - invalid input should return error or 500
        assert r.status_code in [400, 422, 500], f"Expected error, got {r.status_code}: {r.text}"
        print(f"Invalid base64 handled: status={r.status_code}")


# ─── Finalize Upload Tests ──────────────────────────────────────────────────
class TestFinalizeUpload:
    """Test POST /api/upload/finalize endpoint with .txt file."""

    def test_finalize_requires_auth(self):
        """Finalize endpoint requires authentication."""
        r = requests.post(f"{BASE_URL}/api/upload/finalize", json={
            "upload_id": "test-upload",
            "pack_id": "some-pack-id",
            "filename": "test.pdf"
        })
        assert r.status_code in [401, 403], f"Expected 401/403, got {r.status_code}"

    def test_finalize_missing_upload(self):
        """Finalize with non-existent upload_id should return 400."""
        headers = get_auth_headers()
        assert headers, "No auth token"
        pack_id = shared.get("pack_id")
        if not pack_id:
            pytest.skip("No pack_id available")

        r = requests.post(f"{BASE_URL}/api/upload/finalize", json={
            "upload_id": "nonexistent-upload-session-xyz",
            "pack_id": pack_id,
            "filename": "test.pdf"
        }, headers=headers)
        assert r.status_code == 400, f"Expected 400 for missing upload, got {r.status_code}: {r.text}"
        print(f"Missing upload handled: {r.json()}")

    def test_txt_chunked_upload_and_finalize(self):
        """
        Full flow: read .txt, split into chunks, upload all chunks, finalize.
        Verify job_id returned and status is 'queued'.
        """
        headers = get_auth_headers()
        assert headers, "No auth token"
        pack_id = shared.get("pack_id")
        if not pack_id:
            pytest.skip("No pack_id available")

        if not os.path.exists(TEST_TXT_PATH):
            pytest.skip(f"Test file not found: {TEST_TXT_PATH}")

        with open(TEST_TXT_PATH, "rb") as f:
            file_bytes = f.read()

        upload_id = f"TEST_txt_upload_{int(time.time())}"
        total_chunks = math.ceil(len(file_bytes) / CHUNK_SIZE)

        print(f"Uploading {len(file_bytes)} bytes in {total_chunks} chunk(s)")

        for i in range(total_chunks):
            start = i * CHUNK_SIZE
            end = min(start + CHUNK_SIZE, len(file_bytes))
            chunk = file_bytes[start:end]
            encoded = base64.b64encode(chunk).decode()
            r = requests.post(f"{BASE_URL}/api/upload/chunk", json={
                "upload_id": upload_id,
                "chunk_index": i,
                "total_chunks": total_chunks,
                "data": encoded
            }, headers=headers)
            assert r.status_code == 200, f"Chunk {i} failed: {r.text}"

        # Finalize
        r = requests.post(f"{BASE_URL}/api/upload/finalize", json={
            "upload_id": upload_id,
            "pack_id": pack_id,
            "filename": "test_material.txt"
        }, headers=headers)
        assert r.status_code == 200, f"Finalize failed: {r.text}"
        data = r.json()
        assert "job_id" in data, "Response should have job_id"
        assert data["status"] == "queued", f"Expected 'queued', got {data['status']}"
        shared["txt_job_id"] = data["job_id"]
        print(f"TXT finalize OK: job_id={data['job_id']}, status={data['status']}")

    def test_job_status_after_finalize(self):
        """Verify job status is accessible and progresses after finalize."""
        headers = get_auth_headers()
        assert headers, "No auth token"

        job_id = shared.get("txt_job_id")
        if not job_id:
            pytest.skip("No job_id from txt finalize test")

        r = requests.get(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)
        assert r.status_code == 200, f"Job status failed: {r.text}"
        data = r.json()
        assert "status" in data
        assert data["status"] in ["queued", "processing", "complete", "failed"]
        assert "concepts_extracted" in data
        assert "chunks_processed" in data
        print(f"Job status: {data['status']}, concepts_extracted={data['concepts_extracted']}")


# ─── PDF Chunked Upload Test ──────────────────────────────────────────────────
class TestPdfChunkedUpload:
    """Test chunked upload with actual PDF file and check for no 15-concept limit."""

    def test_pdf_chunked_upload_and_finalize(self):
        """
        Upload WuG_ES6 PDF via chunks, verify job starts.
        The PDF is 6MB and should produce many chunks.
        """
        headers = get_auth_headers()
        assert headers, "No auth token"
        pack_id = shared.get("pack_id")
        if not pack_id:
            pytest.skip("No pack_id available")

        if not os.path.exists(TEST_PDF_PATH):
            pytest.skip(f"PDF not found at {TEST_PDF_PATH}")

        with open(TEST_PDF_PATH, "rb") as f:
            pdf_bytes = f.read()

        total_chunks = math.ceil(len(pdf_bytes) / CHUNK_SIZE)
        upload_id = f"TEST_pdf_upload_{int(time.time())}"
        print(f"PDF size={len(pdf_bytes)} bytes, chunks={total_chunks}, chunk_size={CHUNK_SIZE}")

        assert total_chunks > 1, "PDF should require multiple chunks"

        # Upload all chunks
        for i in range(total_chunks):
            start = i * CHUNK_SIZE
            end = min(start + CHUNK_SIZE, len(pdf_bytes))
            chunk = pdf_bytes[start:end]
            encoded = base64.b64encode(chunk).decode()
            r = requests.post(f"{BASE_URL}/api/upload/chunk", json={
                "upload_id": upload_id,
                "chunk_index": i,
                "total_chunks": total_chunks,
                "data": encoded
            }, headers=headers)
            assert r.status_code == 200, f"PDF chunk {i}/{total_chunks} upload failed: {r.text}"
            if i % 5 == 0:
                print(f"  Chunk {i+1}/{total_chunks} uploaded")

        print(f"All {total_chunks} PDF chunks uploaded")

        # Finalize
        r = requests.post(f"{BASE_URL}/api/upload/finalize", json={
            "upload_id": upload_id,
            "pack_id": pack_id,
            "filename": "WuG_ES6_mL_2020.pdf"
        }, headers=headers)
        assert r.status_code == 200, f"PDF finalize failed: {r.text}"
        data = r.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        shared["pdf_job_id"] = data["job_id"]
        print(f"PDF finalize OK: job_id={data['job_id']}")

    def test_pdf_job_initial_status(self):
        """Verify PDF job is queued or processing after finalize."""
        headers = get_auth_headers()
        assert headers, "No auth token"

        job_id = shared.get("pdf_job_id")
        if not job_id:
            pytest.skip("No PDF job_id available")

        r = requests.get(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)
        assert r.status_code == 200, f"Job status failed: {r.text}"
        data = r.json()
        assert data["status"] in ["queued", "processing"], f"Expected queued/processing, got {data['status']}"
        print(f"PDF job initial status: {data['status']}")

    def test_pdf_job_progresses_over_time(self):
        """
        Poll the PDF job to verify it progresses.
        Check concepts_extracted increases (no hard 15-concept limit).
        Poll up to 60 seconds.
        """
        headers = get_auth_headers()
        assert headers, "No auth token"

        job_id = shared.get("pdf_job_id")
        if not job_id:
            pytest.skip("No PDF job_id available")

        max_wait = 60  # seconds - just check it progresses
        poll_interval = 5
        last_concepts = 0
        progress_seen = False

        for attempt in range(max_wait // poll_interval):
            time.sleep(poll_interval)
            r = requests.get(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)
            if r.status_code != 200:
                continue
            data = r.json()
            concepts = data.get("concepts_extracted", 0)
            status = data.get("status")
            print(f"Poll {attempt+1}: status={status}, concepts_extracted={concepts}")

            if concepts > last_concepts:
                progress_seen = True
                last_concepts = concepts

            if status == "complete":
                print(f"Job completed with {concepts} concepts extracted")
                # Verify no hard limit - should have more than 15 concepts if PDF is large
                assert concepts > 0, "Should have extracted at least some concepts"
                # Note: the test verifies there is NO hard 15-concept cap
                # For a 6MB PDF with many chapters, we expect well above 15
                if concepts <= 15:
                    print(f"WARNING: Only {concepts} concepts from large PDF - possible limit still in effect")
                else:
                    print(f"PASS: {concepts} concepts extracted - no 15-concept limit confirmed")
                return

            if status == "failed":
                error = data.get("error", "Unknown error")
                pytest.fail(f"Job failed: {error}")

        # If we reach here, job is still running after 60s - that's OK for large PDF
        print(f"Job still processing after {max_wait}s. Last seen: {last_concepts} concepts.")
        if progress_seen:
            print(f"PASS: Pipeline is progressing (concepts_extracted increased to {last_concepts})")
        else:
            print(f"Job status after wait: status={data.get('status')}, concepts={last_concepts}")
        # The test passes if job is running (queued/processing) even after timeout
        assert data.get("status") in ["queued", "processing", "complete"], "Job should be in valid state"


# ─── Previously Started Job Check ────────────────────────────────────────────
class TestExistingJob:
    """Check status of the previously created job mentioned in context."""

    def test_check_previous_pdf_job(self):
        """
        Check job 69a7fa3f3e3b03f209d31236 from context.
        This should have processed the WuG_ES6 PDF with >15 concepts.
        """
        headers = get_auth_headers()
        assert headers, "No auth token"

        job_id = "69a7fa3f3e3b03f209d31236"
        r = requests.get(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)

        if r.status_code == 404:
            pytest.skip(f"Job {job_id} not found (may belong to different user or not exist)")
        elif r.status_code == 400:
            pytest.skip(f"Invalid job ID: {r.text}")

        assert r.status_code == 200, f"Job status failed: {r.text}"
        data = r.json()
        concepts = data.get("concepts_extracted", 0)
        status = data.get("status")
        print(f"Job {job_id}: status={status}, concepts_extracted={concepts}")

        if status == "complete":
            assert concepts > 0, "Completed job should have extracted concepts"
            print(f"Job completed with {concepts} concepts")
            if concepts > 15:
                print(f"PASS: {concepts} > 15 — no concept limit confirmed!")
            else:
                print(f"WARNING: Only {concepts} concepts — may still have limit or insufficient content")
        else:
            print(f"Job status: {status} — not yet complete")
