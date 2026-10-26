"""
JobIntel - User Profile & Interaction API Tests
"""

def test_user_creation_and_interaction(client):
    user_payload = {
        "email": "test.engineer@jobintel.ai",
        "full_name": "Priya Patel",
        "headline": "Full Stack & Python Developer",
        "experience_years": 2.0,
        "target_role": "Software Engineering",
        "preferred_locations": ["Pune", "Mumbai"],
        "preferred_work_models": ["Hybrid"],
        "skills": [
            {"skill_name": "python", "proficiency_level": "advanced", "years_of_experience": 2.0},
            {"skill_name": "react", "proficiency_level": "intermediate", "years_of_experience": 1.5},
        ]
    }

    # 1. Create User
    create_res = client.post("/api/v1/users/", json=user_payload)
    assert create_res.status_code == 201
    user_data = create_res.json()
    user_id = user_data["id"]
    assert user_data["email"] == "test.engineer@jobintel.ai"
    assert len(user_data["skills"]) == 2

    # 2. Fetch User Profile
    get_res = client.get(f"/api/v1/users/{user_id}")
    assert get_res.status_code == 200
    assert get_res.json()["full_name"] == "Priya Patel"

    # 3. Create a dummy job to interact with
    job_res = client.post("/api/v1/jobs/", json={
        "job_id": "test_interaction_job_1",
        "title": "React Python Developer",
        "company_name": "Tech Hub Pune",
        "city": "Pune",
        "description": "Building modern web platforms using Python and React.",
    })
    job_id = job_res.json()["id"]

    # 4. Log Interaction
    inter_res = client.post("/api/v1/users/interactions", json={
        "user_id": user_id,
        "job_id": job_id,
        "interaction_type": "save",
        "duration_seconds": 15.0,
        "metadata_payload": {"source_page": "explorer"}
    })
    assert inter_res.status_code == 201
    assert inter_res.json()["interaction_type"] == "save"
