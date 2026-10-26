"""
JobIntel - Jobs API Endpoint Tests
"""

def test_create_and_list_jobs(client):
    job_payload = {
        "job_id": "jobvetta_api_test_01",
        "source": "jobvetta",
        "title": "Machine Learning Engineer",
        "company_name": "AI Labs India",
        "city": "Bengaluru",
        "state": "Karnataka",
        "country": "India",
        "description": "We are seeking a Machine Learning Engineer proficient in Python and PyTorch.",
        "employment_type": "Full-time",
        "work_model": "Remote",
        "experience_level": "Mid-level",
        "salary_min": 1200000.0,
        "salary_max": 1800000.0,
    }

    # 1. Create Job
    create_res = client.post("/api/v1/jobs/", json=job_payload)
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["job_id"] == "jobvetta_api_test_01"
    assert created_data["title"] == "Machine Learning Engineer"

    # 2. List Jobs
    list_res = client.get("/api/v1/jobs/")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(j["job_id"] == "jobvetta_api_test_01" for j in list_data["items"])

    # 3. Filter by city
    filter_res = client.get("/api/v1/jobs/?city=Bengaluru")
    assert filter_res.status_code == 200
    assert len(filter_res.json()["items"]) >= 1

    # 4. Detail endpoint
    job_id = created_data["id"]
    detail_res = client.get(f"/api/v1/jobs/{job_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == job_id
