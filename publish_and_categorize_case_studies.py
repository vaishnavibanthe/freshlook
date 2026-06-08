import sqlite3
import os
import re

db_path = 'blog.db'
conn = sqlite3.connect(f'file:{db_path}?nolock=1', uri=True)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get all case studies
cursor.execute("SELECT id, title, slug, pdf_file_path FROM case_studies")
rows = cursor.fetchall()

print(f"Loaded {len(rows)} case studies from database.")

updated = 0
by_industry = {}

for row in rows:
    study_id = row['id']
    title = row['title']
    pdf_path = row['pdf_file_path']
    if not pdf_path:
        continue
        
    filename = os.path.basename(pdf_path).lower()
    
    industry = "Technology"
    tags_list = ["case-study"]
    
    # Healthcare
    if any(k in filename for k in ['cca', 'healthcare', 'fastmed', 'hcsc', 'diabetes', 'schein', 'shein', 'nupco', 'reliant']):
        industry = "Healthcare & Life Sciences"
        tags_list.extend(['healthcare', 'life-sciences'])
        if 'claims' in filename: tags_list.append('claims')
        if 'governance' in filename or 'dg' in filename: tags_list.append('data-governance')
        if 'talend' in filename: tags_list.append('talend')
        if 'azure' in filename: tags_list.append('azure')
        if 'ai' in filename or 'artificial' in filename: tags_list.append('artificial-intelligence')
        if 'edm' in filename: tags_list.append('enterprise-data-management')
    
    # BFSI
    elif any(k in filename for k in ['baf', 'bfi', 'danamon', 'mandiri', 'banking', 'dbs', 'generali', 'insurance', 'financial', 'security bank', 'bfsi']):
        industry = "BFSI"
        tags_list.extend(['bfsi', 'banking', 'finance'])
        if 'insurance' in filename or 'generali' in filename: tags_list.append('insurance')
        if 'governance' in filename or 'dg' in filename: tags_list.append('data-governance')
        if 'mdm' in filename: tags_list.append('master-data-management')
        if 'ml' in filename or 'deduplication' in filename: tags_list.extend(['machine-learning', 'deduplication'])
        if 'dq' in filename: tags_list.append('data-quality')
        if 'dip' in filename: tags_list.append('data-insights-platform')
        
    # Retail
    elif any(k in filename for k in ['aldo', 'carhartt', 'carhatt', 'retail', 'dominos', 'este', 'lowe', 'e-commerce']):
        industry = "Retail & E-Commerce"
        tags_list.extend(['retail', 'e-commerce'])
        if 'mdm' in filename: tags_list.append('master-data-management')
        if 'dq' in filename or 'quality' in filename: tags_list.append('data-quality')
        if 'talend' in filename: tags_list.append('talend')
        if 'aws' in filename: tags_list.append('aws')
        if 'integration' in filename: tags_list.append('data-integration')
        if 'customer' in filename: tags_list.append('customer-360')
        if 'supply' in filename: tags_list.append('supply-chain')
        if 'deduplication' in filename: tags_list.append('deduplication')
        if 'dominos' in filename: tags_list.append('digital-transformation')
        
    # Manufacturing
    elif any(k in filename for k in ['manufacturing', 'iff', 'clark', 'qlik']):
        industry = "Manufacturing"
        tags_list.extend(['manufacturing', 'industrial'])
        if 'sap' in filename: tags_list.append('sap')
        if 'qlik' in filename: tags_list.append('qlik')
        if 'mdm' in filename: tags_list.append('master-data-management')
        if 'modernization' in filename: tags_list.append('data-modernization')
        
    # Utilities
    elif any(k in filename for k in ['utilities', 'homeserve', 'irving']):
        industry = "Utilities & Energy"
        tags_list.extend(['utilities', 'energy'])
        if 'talend' in filename: tags_list.append('talend')
        if 'cloud' in filename: tags_list.append('cloud-migration')
        if 'salesforce' in filename: tags_list.append('salesforce')
        if 'governance' in filename or 'dg' in filename: tags_list.append('data-governance')
        if 'mdm' in filename: tags_list.append('master-data-management')
        
    # Telecom
    elif any(k in filename for k in ['maxis', 'telecom', 'smart']):
        industry = "Telecommunications"
        tags_list.extend(['telecom', 'connectivity'])
        if 'strategy' in filename: tags_list.append('data-strategy')
        if 'integration' in filename: tags_list.append('data-integration')
        if 'insights' in filename: tags_list.append('data-insights-platform')
        
    # Hospitality
    elif any(k in filename for k in ['hilton', 'carribean', 'iata']):
        industry = "Hospitality & Travel"
        tags_list.extend(['hospitality', 'travel', 'leisure'])
        if 'gdpr' in filename or 'compliance' in filename: tags_list.extend(['gdpr', 'compliance'])
        if 'governance' in filename: tags_list.append('data-governance')
        if 'customer' in filename: tags_list.append('customer-360')
        if 'cloud' in filename: tags_list.append('cloud-solutions')

    # Fallback/Additional check based on title text
    if industry == "Technology":
        title_lower = title.lower()
        if any(w in title_lower for w in ['healthcare', 'eligibility', 'payments', 'health', 'patient']):
            industry = "Healthcare & Life Sciences"
            tags_list.extend(['healthcare', 'life-sciences'])
        elif any(w in title_lower for w in ['banking', 'financial', 'payment', 'credit', 'mortgage', 'bank', 'insurance']):
            industry = "BFSI"
            tags_list.extend(['bfsi', 'banking', 'finance'])
        elif any(w in title_lower for w in ['retail', 'e-commerce', 'store', 'onboarding', 'inventory', 'sku', 'loyalty']):
            industry = "Retail & E-Commerce"
            tags_list.extend(['retail', 'e-commerce'])
        elif any(w in title_lower for w in ['manufacturing', 'factory', 'production', 'erp', 'sap', 'industrial']):
            industry = "Manufacturing"
            tags_list.extend(['manufacturing', 'industrial'])
        elif any(w in title_lower for w in ['utility', 'utilities', 'energy', 'water', 'power', 'oil', 'gas']):
            industry = "Utilities & Energy"
            tags_list.extend(['utilities', 'energy'])
        elif any(w in title_lower for w in ['telecom', 'telecommunications', 'mobile', 'cellular']):
            industry = "Telecommunications"
            tags_list.extend(['telecom', 'connectivity'])
        elif any(w in title_lower for w in ['hotel', 'travel', 'hospitality', 'cruise', 'flight']):
            industry = "Hospitality & Travel"
            tags_list.extend(['hospitality', 'travel', 'leisure'])

    # Format tags list to match lower case and unique list
    tags_list = list(dict.fromkeys([t.strip().lower() for t in tags_list]))
    tags = ", ".join(tags_list)
    
    # Update this record in the DB to set industry, tags, and status = 'Published'
    cursor.execute("""
        UPDATE case_studies
        SET industry = ?, tags = ?, status = 'Published'
        WHERE id = ?
    """, (industry, tags, study_id))
    
    by_industry[industry] = by_industry.get(industry, 0) + 1
    updated += 1

conn.commit()
conn.close()

print(f"Updated and published {updated} case studies successfully.")
print("Breakdown by Industry:")
for ind, count in by_industry.items():
    print(f"  - {ind}: {count}")
