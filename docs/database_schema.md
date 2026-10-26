# JobIntel - Database Schema Specification

The JobIntel platform uses a normalized relational schema on **PostgreSQL** (SQLite is used only by the automated tests; the application never falls back to it silently). No schema change was made in the final phases: `interactions` already held everything needed for behavioral personalization.

## Entity Relationship Diagram

```mermaid
erDiagram
    COMPANIES ||--o{ JOBS : "employs"
    JOBS ||--o{ JOB_SKILLS : "requires"
    SKILLS ||--o{ JOB_SKILLS : "identified_in"
    USERS ||--o{ USER_SKILLS : "possesses"
    SKILLS ||--o{ USER_SKILLS : "categorizes"
    USERS ||--o{ INTERACTIONS : "performs"
    JOBS ||--o{ INTERACTIONS : "targeted_by"

    JOBS {
        int id PK
        string job_id UK
        string source
        string title
        string normalized_title
        string role_category
        int company_id FK
        string company_name
        string location_raw
        string city
        string state
        string country
        text description
        text description_cleaned
        string employment_type
        string work_model
        string experience_level
        float min_experience_years
        float max_experience_years
        float salary_min
        float salary_max
        string salary_currency
        string salary_period
        boolean is_salary_predicted
        datetime posted_at
        datetime last_seen_at
        json raw_payload
        datetime created_at
        datetime updated_at
    }

    SKILLS {
        int id PK
        string name UK
        string display_name
        string category
        json aliases
        datetime created_at
        datetime updated_at
    }

    JOB_SKILLS {
        int id PK
        int job_id FK
        int skill_id FK
        string skill_type
        float confidence
        string extraction_method
        datetime created_at
    }

    COMPANIES {
        int id PK
        string name
        string normalized_name
        string industry
        string company_size
        string website
        datetime created_at
    }

    LOCATIONS {
        int id PK
        string raw_name
        string city
        string state
        string country
        string tier
    }

    USERS {
        int id PK
        string email UK
        string full_name
        string headline
        text summary
        string education_level
        string field_of_study
        float experience_years
        string current_location
        string target_role
        json preferred_roles
        json preferred_locations
        json preferred_work_models
        json preferred_employment_types
        float min_salary_preference
        datetime created_at
        datetime updated_at
    }

    USER_SKILLS {
        int id PK
        int user_id FK
        int skill_id FK
        string proficiency_level
        float years_of_experience
    }

    INTERACTIONS {
        int id PK
        int user_id FK
        int job_id FK
        string interaction_type
        float duration_seconds
        json metadata_payload
        datetime created_at
    }

    INGESTION_RUNS {
        int id PK
        string source
        string status
        json query_parameters
        int total_fetched
        int new_inserted
        int duplicates_skipped
        int errors_count
        datetime started_at
        datetime completed_at
        text error_log
    }
```
