"""
Migration script: Create Careers Module tables in blog.db
Run once: python3 migrate_careers.py
"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'blog.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # -- career_jobs table --
    c.execute("""
        CREATE TABLE IF NOT EXISTS career_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            department TEXT NOT NULL,
            location TEXT NOT NULL,
            job_type TEXT NOT NULL DEFAULT 'Full-Time',
            summary TEXT,
            description TEXT,
            responsibilities TEXT,
            requirements TEXT,
            additional_info TEXT,
            status TEXT NOT NULL DEFAULT 'published',
            posted_date TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # -- career_applications table --
    c.execute("""
        CREATE TABLE IF NOT EXISTS career_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            job_title TEXT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            linkedin_url TEXT,
            cover_letter TEXT,
            resume_filename TEXT,
            resume_path TEXT,
            consent_given INTEGER DEFAULT 0,
            status TEXT DEFAULT 'new',
            notes TEXT,
            submitted_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (job_id) REFERENCES career_jobs(id)
        )
    """)

    conn.commit()
    print("Career tables created successfully.")

    # Seed sample jobs using json.dumps for safe string serialization
    sample_jobs = [
        {
            "slug": "senior-data-engineer",
            "title": "Senior Data Engineer",
            "department": "Delivery",
            "location": "USA (Remote)",
            "job_type": "Full-Time",
            "summary": "Design and build scalable data pipelines and ETL frameworks using Talend, Snowflake, and cloud-native tools for Fortune 500 clients.",
            "description": "We are seeking a Senior Data Engineer to join our growing Delivery team. In this role, you will design, build, and optimize data pipelines and ETL workflows that serve enterprise data management programs.",
            "responsibilities": json.dumps([
                "Design and implement enterprise-grade ETL/ELT pipelines",
                "Architect data lake and data warehouse solutions on Snowflake and AWS",
                "Collaborate with clients to gather requirements and define data models",
                "Ensure data quality through automated validation frameworks",
                "Mentor junior engineers and participate in code reviews",
                "Lead technical discovery sessions with enterprise clients"
            ]),
            "requirements": json.dumps([
                "5+ years of data engineering experience",
                "Expert-level proficiency in Talend Studio or Talend Cloud",
                "Hands-on experience with Snowflake, AWS Redshift, or Azure Synapse",
                "Strong SQL skills with query optimization expertise",
                "Experience with Python scripting for data transformation",
                "Familiarity with Agile/Scrum delivery methodologies"
            ]),
            "additional_info": "ThinkArtha is an equal opportunity employer. We offer competitive compensation, remote-first flexibility, health benefits, and professional development sponsorship.",
            "status": "published",
            "posted_date": "2026-05-15"
        },
        {
            "slug": "sap-s4hana-consultant",
            "title": "SAP S/4HANA Data Migration Consultant",
            "department": "SAP Practice",
            "location": "New Jersey, USA (Hybrid)",
            "job_type": "Full-Time",
            "summary": "Lead SAP S/4HANA data migration programs, managing data extraction, transformation, reconciliation, and cutover for large enterprise clients.",
            "description": "As an SAP S/4HANA Data Migration Consultant, you will serve as a subject matter expert for enterprise ERP migrations. You will oversee data profiling, cleansing, transformation, and migration activities during S/4HANA implementations.",
            "responsibilities": json.dumps([
                "Lead data migration workstreams for SAP S/4HANA greenfield and brownfield projects",
                "Perform data assessment, profiling, and gap analysis",
                "Design migration objects using SAP Data Services and LSMW",
                "Conduct data reconciliation and balance validation",
                "Coordinate with functional teams for master data and transactional data cutover",
                "Present migration status to client executive stakeholders"
            ]),
            "requirements": json.dumps([
                "7+ years of SAP data migration project experience",
                "Deep knowledge of SAP LSMW, BAPI, IDocs, and Data Services",
                "Experience with S/4HANA migration cockpit (LTMC/LTMOM)",
                "Understanding of FICO, MM, SD data objects",
                "Excellent written and verbal communication skills",
                "SAP certification is highly preferred"
            ]),
            "additional_info": "Travel up to 25% to client sites may be required. Candidates must be eligible to work in the United States.",
            "status": "published",
            "posted_date": "2026-05-20"
        },
        {
            "slug": "data-governance-analyst",
            "title": "Data Governance Analyst",
            "department": "Delivery",
            "location": "Bengaluru, India (Hybrid)",
            "job_type": "Full-Time",
            "summary": "Support enterprise data governance programs by defining data standards, managing metadata catalogs, and driving data quality initiatives.",
            "description": "We are looking for a Data Governance Analyst to help our clients define and operationalize their data governance frameworks. You will work closely with business and technical stakeholders to catalog data assets, define data quality rules, and drive governance adoption.",
            "responsibilities": json.dumps([
                "Develop and maintain enterprise data dictionaries and metadata catalogs",
                "Define data quality KPIs and implement monitoring dashboards",
                "Facilitate data stewardship programs across business units",
                "Assist in selecting and implementing data catalog tools (Alation, Collibra)",
                "Produce governance maturity assessment reports",
                "Conduct training sessions for business data stewards"
            ]),
            "requirements": json.dumps([
                "3+ years of experience in data governance or data management",
                "Working knowledge of Alation, Collibra, or similar data catalog tools",
                "Understanding of DAMA DMBOK framework",
                "Experience in data lineage documentation",
                "Strong stakeholder communication and facilitation skills",
                "Bachelor degree in Computer Science, Information Systems, or related field"
            ]),
            "additional_info": "Candidates based in Bengaluru preferred. Flexible work-from-home policy available.",
            "status": "published",
            "posted_date": "2026-05-25"
        },
        {
            "slug": "qlik-bi-developer",
            "title": "Qlik Sense / QlikView BI Developer",
            "department": "Delivery",
            "location": "USA (Remote)",
            "job_type": "Full-Time",
            "summary": "Build enterprise analytics dashboards and self-service BI solutions using Qlik Sense for Fortune 500 retail, BFSI, and manufacturing clients.",
            "description": "As a Qlik BI Developer at ThinkArtha, you will design and deliver high-impact analytics solutions using Qlik Sense and QlikView. You will transform raw data into actionable executive dashboards and collaborate with data engineering teams to ensure reliable data pipelines.",
            "responsibilities": json.dumps([
                "Design and develop Qlik Sense dashboards and NPrinting reports",
                "Build QVDs, data models, and set analysis expressions",
                "Work with clients to define KPIs and reporting requirements",
                "Integrate Qlik with data sources including Snowflake, SQL Server, and SAP",
                "Maintain and optimize existing QlikView applications",
                "Conduct end-user training and adoption workshops"
            ]),
            "requirements": json.dumps([
                "4+ years of Qlik Sense or QlikView development experience",
                "Strong understanding of associative data modeling",
                "Proficiency in set analysis, extensions, and Qlik APIs",
                "Experience with Qlik NPrinting for automated reporting",
                "SQL proficiency and knowledge of data warehousing concepts",
                "Qlik certification is a plus"
            ]),
            "additional_info": "This is a 100% remote position. Occasional travel to client offices or ThinkArtha HQ may be required.",
            "status": "published",
            "posted_date": "2026-06-01"
        },
        {
            "slug": "enterprise-solutions-executive",
            "title": "Enterprise Solutions Executive",
            "department": "Sales",
            "location": "New York, USA",
            "job_type": "Full-Time",
            "summary": "Drive new business development for data management, cloud, and AI solutions at the C-suite level across enterprise accounts in North America.",
            "description": "We are seeking a high-energy Enterprise Solutions Executive to join our North America sales team. You will own the full sales cycle from prospecting through contract close, engaging C-level decision-makers at Fortune 1000 companies.",
            "responsibilities": json.dumps([
                "Identify and develop new enterprise accounts in target verticals (BFSI, Retail, Healthcare)",
                "Lead executive presentations and discovery workshops",
                "Manage pipeline in Salesforce and forecast accurately",
                "Collaborate with solution architects to craft winning proposals",
                "Negotiate contracts and SOWs with legal and procurement teams",
                "Achieve and exceed quarterly revenue targets"
            ]),
            "requirements": json.dumps([
                "8+ years of enterprise software/services sales experience",
                "Proven track record of $2M+ annual quota attainment",
                "Experience selling data management, cloud, or analytics solutions",
                "Strong executive presence and consultative selling skills",
                "Familiarity with SAP, Snowflake, Qlik, or AWS ecosystems is a strong plus",
                "Bachelor degree required; MBA preferred"
            ]),
            "additional_info": "Uncapped commission structure with accelerators above 100% quota. Comprehensive benefits package including equity options.",
            "status": "published",
            "posted_date": "2026-06-01"
        },
        {
            "slug": "ai-ml-engineer",
            "title": "AI / ML Engineer",
            "department": "AI CoE",
            "location": "Bengaluru, India (Hybrid)",
            "job_type": "Full-Time",
            "summary": "Design and deploy production-grade machine learning models, RAG pipelines, and LLM-powered applications for enterprise use cases.",
            "description": "Join our AI Center of Excellence and work at the forefront of enterprise AI adoption. You will design, train, evaluate, and deploy machine learning models and generative AI applications that deliver measurable business outcomes for our clients.",
            "responsibilities": json.dumps([
                "Develop and deploy ML models for classification, forecasting, and anomaly detection",
                "Build RAG pipelines using LangChain, LlamaIndex, and vector databases",
                "Implement and fine-tune LLMs for domain-specific enterprise applications",
                "Collaborate with data engineers to build reliable feature pipelines",
                "Conduct model performance monitoring and continuous improvement",
                "Document AI solutions and present results to client stakeholders"
            ]),
            "requirements": json.dumps([
                "3+ years of ML engineering or applied AI experience",
                "Proficiency in Python, PyTorch or TensorFlow, and scikit-learn",
                "Experience with OpenAI, Anthropic, or open-source LLM APIs",
                "Hands-on knowledge of vector databases (Pinecone, Weaviate, pgvector)",
                "Understanding of MLOps tools (MLflow, Kubeflow, or similar)",
                "Master degree in Computer Science, AI, or related field preferred"
            ]),
            "additional_info": "This role includes access to enterprise GPU clusters and cutting-edge AI research budget.",
            "status": "published",
            "posted_date": "2026-06-03"
        }
    ]

    inserted = 0
    for job in sample_jobs:
        try:
            c.execute("""
                INSERT OR IGNORE INTO career_jobs
                (slug, title, department, location, job_type, summary, description,
                 responsibilities, requirements, additional_info, status, posted_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job["slug"], job["title"], job["department"], job["location"],
                job["job_type"], job["summary"], job["description"],
                job["responsibilities"], job["requirements"],
                job["additional_info"], job["status"], job["posted_date"]
            ))
            inserted += 1
        except Exception as e:
            print(f"  Skipped {job['slug']}: {e}")

    conn.commit()
    conn.close()
    print(f"Seeded {inserted} sample jobs.")

if __name__ == '__main__':
    migrate()
