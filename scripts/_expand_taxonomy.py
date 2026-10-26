"""One-off: append new skills to nlp/dictionaries/skills_taxonomy.json (existing entries untouched)."""
import json, os
P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nlp", "dictionaries", "skills_taxonomy.json")
d = json.load(open(P, encoding="utf-8"))
have = {s["name"] for s in d["skills"]} | {a.lower() for s in d["skills"] for a in s.get("aliases", [])}
NEW = [
 # name, display, category, aliases
 ("golang", "Go (Golang)", "Programming Languages", []),
 ("rust", "Rust", "Programming Languages", []),
 ("kotlin", "Kotlin", "Programming Languages", []),
 ("swift", "Swift", "Programming Languages", []),
 ("php", "PHP", "Programming Languages", []),
 ("ruby", "Ruby", "Programming Languages", ["ruby on rails"]),
 ("bash", "Bash / Shell", "Programming Languages", ["shell scripting"]),
 ("html", "HTML", "Web Frameworks", ["html5"]),
 ("css", "CSS", "Web Frameworks", ["css3"]),
 ("angular", "Angular", "Web Frameworks", ["angularjs"]),
 ("vue", "Vue.js", "Web Frameworks", ["vue.js", "vuejs"]),
 ("next.js", "Next.js", "Web Frameworks", ["nextjs"]),
 ("spring boot", "Spring Boot", "Web Frameworks", ["spring framework"]),
 ("rest api", "REST APIs", "Web Frameworks", ["rest apis", "restful", "restful apis"]),
 ("graphql", "GraphQL", "Web Frameworks", []),
 ("microservices", "Microservices", "Web Frameworks", ["microservice"]),
 ("postgresql", "PostgreSQL", "Databases & Query", ["postgres"]),
 ("mysql", "MySQL", "Databases & Query", []),
 ("mongodb", "MongoDB", "Databases & Query", []),
 ("redis", "Redis", "Databases & Query", []),
 ("elasticsearch", "Elasticsearch", "Databases & Query", []),
 ("sql server", "SQL Server", "Databases & Query", ["mssql"]),
 ("snowflake", "Snowflake", "Data Engineering", []),
 ("bigquery", "BigQuery", "Data Engineering", []),
 ("redshift", "Redshift", "Data Engineering", []),
 ("airflow", "Airflow", "Data Engineering", ["apache airflow"]),
 ("kafka", "Kafka", "Data Engineering", ["apache kafka"]),
 ("hadoop", "Hadoop", "Data Engineering", []),
 ("hive", "Hive", "Data Engineering", ["apache hive"]),
 ("dbt", "dbt", "Data Engineering", []),
 ("data engineering", "Data Engineering", "Domain / Field", []),
 ("data analysis", "Data Analysis", "Domain / Field", ["data analytics"]),
 ("business intelligence", "Business Intelligence", "Business Intelligence & Analytics", ["bi tools"]),
 ("looker", "Looker", "Business Intelligence & Analytics", []),
 ("qlik", "Qlik", "Business Intelligence & Analytics", ["qlikview", "qlik sense"]),
 ("google analytics", "Google Analytics", "Business Intelligence & Analytics", []),
 ("power query", "Power Query", "Business Intelligence & Analytics", []),
 ("vba", "VBA", "Business Intelligence & Analytics", ["excel vba"]),
 ("matplotlib", "Matplotlib", "Data Science & Analytics", []),
 ("seaborn", "Seaborn", "Data Science & Analytics", []),
 ("xgboost", "XGBoost", "AI & Machine Learning", []),
 ("computer vision", "Computer Vision", "AI & Machine Learning", []),
 ("time series", "Time Series", "AI & Machine Learning", ["time-series"]),
 ("feature engineering", "Feature Engineering", "AI & Machine Learning", []),
 ("mlops", "MLOps", "AI & Machine Learning", []),
 ("llm", "Large Language Models", "AI & Machine Learning", ["llms", "large language models", "large language model"]),
 ("langchain", "LangChain", "AI & Machine Learning", []),
 ("recommendation systems", "Recommendation Systems", "AI & Machine Learning", ["recommender systems", "recommendation engines"]),
 ("data mining", "Data Mining", "Data Science & Analytics", []),
 ("terraform", "Terraform", "Cloud & DevOps", []),
 ("ansible", "Ansible", "Cloud & DevOps", []),
 ("jenkins", "Jenkins", "Cloud & DevOps", []),
 ("ci/cd", "CI/CD", "Cloud & DevOps", ["cicd", "ci cd", "continuous integration"]),
 ("linux", "Linux", "Cloud & DevOps", []),
 ("system design", "System Design", "Software Engineering Practices", []),
 ("unit testing", "Unit Testing", "Software Engineering Practices", ["test automation"]),
 ("selenium", "Selenium", "Software Engineering Practices", []),
 ("jira", "Jira", "Tools & Methodology", []),
 ("figma", "Figma", "Tools & Methodology", []),
 ("project management", "Project Management", "Tools & Methodology", []),
 ("stakeholder management", "Stakeholder Management", "Soft Skills", []),
 ("leadership", "Leadership", "Soft Skills", []),
 ("financial analysis", "Financial Analysis", "Finance & Domain", []),
 ("financial reporting", "Financial Reporting", "Finance & Domain", []),
 ("budgeting", "Budgeting", "Finance & Domain", []),
 ("sap", "SAP", "Finance & Domain", []),
 ("seo", "SEO", "Marketing", ["search engine optimization"]),
 ("content marketing", "Content Marketing", "Marketing", []),
 ("crm", "CRM", "Marketing", []),
]
added = 0
for name, disp, cat, aliases in NEW:
    if name in have:
        continue
    d["skills"].append({"name": name, "display_name": disp, "category": cat, "aliases": [a for a in aliases if a not in have]})
    have |= {name} | set(aliases)
    added += 1
json.dump(d, open(P, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("added", added, "total", len(d["skills"]))
