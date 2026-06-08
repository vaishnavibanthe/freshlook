import sqlite3
import json

db_path = 'blog.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Case Study ID 14 - Enterprise Data Governance and Master Data Management (MDM)
metrics_14 = [
    {"value": "40%", "label": "Reduction in compliance reporting time"},
    {"value": "80%", "label": "Improvement in active data reconciliation accuracy"},
    {"value": "95%", "label": "Automated data validation scoring achieved"},
    {"value": "12", "label": "Separate legacy platforms consolidated"}
]

# Case Study ID 29 - Automated Bing Ads Campaign Ingestion
metrics_29 = [
    {"value": "80%", "label": "Reduction in manual effort by automating campaign reporting"},
    {"value": "Real-time", "label": "Campaign insights availability for faster decisions"},
    {"value": "Improved", "label": "Data extraction accuracy, minimizing retrieval errors"}
]

cursor.execute(
    "UPDATE case_studies SET key_metrics = ? WHERE id = ?",
    (json.dumps(metrics_14), 14)
)

cursor.execute(
    "UPDATE case_studies SET key_metrics = ? WHERE id = ?",
    (json.dumps(metrics_29), 29)
)

conn.commit()

# Verify updates
cursor.execute("SELECT id, title, key_metrics FROM case_studies WHERE id IN (14, 29)")
rows = cursor.fetchall()
print("Updated Case Studies in DB:")
for r in rows:
    print(f"ID: {r[0]}")
    print(f"Title: {r[1]}")
    print(f"Metrics: {r[2]}")
    print("-" * 50)

conn.close()
print("Database metrics updated successfully.")
