import sqlite3
import glob
import os
import re

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text)
    return text.strip('-')

def clean_title(title):
    title = title.replace(" - Artha Solutions", "")
    title = title.replace(" | Blog | Artha Solutions", "")
    title = title.replace(" | Artha Solutions", "")
    title = title.replace(" | Artha", "")
    return title.strip()

def get_category(title, url):
    title_lower = title.lower()
    url_lower = url.lower()
    if 'cloud' in title_lower or 'cloud' in url_lower:
        return 'Cloud Services'
    elif 'servicenow' in title_lower or 'servicenow' in url_lower:
        return 'ServiceNow'
    elif 'oracle' in title_lower or 'oracle' in url_lower:
        return 'Oracle Services'
    elif 'sap' in title_lower or 'sap' in url_lower:
        return 'SAP Modernization'
    elif 'ai' in title_lower or 'artificial' in title_lower or 'machine learning' in title_lower:
        return 'AI & ML'
    elif 'healthcare' in title_lower or 'patient' in title_lower:
        return 'Healthcare'
    elif 'retail' in title_lower or 'omnichannel' in title_lower:
        return 'Retail'
    elif 'manufacturing' in title_lower:
        return 'Manufacturing'
    return 'Data Solutions'

def parse_and_import():
    scratch_dir = "/Users/amit/.gemini/antigravity-ide/brain/9419e352-8bb6-4571-8c27-ee4acb4b36ff/scratch"
    files = glob.glob(os.path.join(scratch_dir, "blog_*.txt"))
    
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    
    imported_count = 0
    print(f"Scanning for blog files in {scratch_dir}...")
    
    for filepath in files:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        url = ""
        title = ""
        date_str = ""
        content_lines = []
        is_content = False
        
        for line in lines:
            if line.startswith("URL:"):
                url = line.replace("URL:", "").strip()
            elif line.startswith("TITLE:"):
                title = clean_title(line.replace("TITLE:", "").strip())
            elif line.startswith("DATE:"):
                date_str = line.replace("DATE:", "").strip()
            elif line.startswith("CONTENT:"):
                is_content = True
            elif is_content:
                content_lines.append(line)
        
        # Skip utility pages that are not actual articles
        if not title or "Case Studies" in title or "Blogs" in title:
            continue
            
        content_text = "".join(content_lines).strip()
        # Clean menu links that get crawled in the body parser
        # (remove common navigation links at the start)
        paragraphs = [p.strip() for p in content_text.split('\n') if p.strip()]
        cleaned_paragraphs = []
        for p in paragraphs:
            # Skip common menu texts
            if any(x == p for x in ["Skip to content", "Artha Advantage", "Accelerators", "Solutions", "Industries", "Resources", "About Us", "Partners", "Careers", "Contact Us", "Get in Touch"]):
                continue
            if len(p) < 40 and any(x in p.lower() for x in ["accelerators", "data insights", "mdm lite", "customer 360", "dynamic ingestion", "etl tool migration", "digital transformation", "sap migration", "managed services"]):
                continue
            cleaned_paragraphs.append(p)
            
        full_content = "\n\n".join(cleaned_paragraphs)
        
        # Summary is the first 2 sentences
        sentences = re.split(r'(?<=[.!?])\s+', full_content)
        summary = " ".join(sentences[:2]) if len(sentences) > 0 else "Enterprise data insights and integrations."
        if len(summary) > 200:
            summary = summary[:197] + "..."
            
        slug = slugify(title)
        category = get_category(title, url)
        
        # Mock views and SEO parameters
        views = int(35 + (hash(title) % 450)) # 35 to 485 views
        seo_score = int(75 + (hash(slug) % 20)) # 75 to 95 score
        
        # Keywords
        kw_map = {
            'Cloud Services': 'cloud migration, ETL pipelines, retail IT',
            'ServiceNow': 'servicenow integration, ITSM automation, workflow',
            'Oracle Services': 'oracle consulting, database administration, ERP integration',
            'SAP Modernization': 'sap migration, s4hana transition, data quality',
            'AI & ML': 'generative ai, model deployment, data readiness',
            'Healthcare': 'patient deduplication, healthcare records, HIPAA integration',
            'Retail': 'retail streams, omnichannel processing, real-time analytics',
            'Manufacturing': 'manufacturing MDM, IoT diagnostics, plm system',
            'Data Solutions': 'data governance, MDM audit, metadata catalog'
        }
        keywords = kw_map.get(category, 'data solutions, think artha')
        
        meta_desc = summary
        meta_title = title
        
        try:
            # Check if slug exists to avoid duplicates
            cursor.execute("SELECT id FROM posts WHERE slug = ?", (slug,))
            if cursor.fetchone():
                print(f"Slug already exists: {slug}, skipping...")
                continue
                
            cursor.execute('''
            INSERT INTO posts (title, slug, date, category, content, summary, status, meta_title, meta_desc, keywords, seo_score, views)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, slug, date_str, category, full_content, summary, 'Published', meta_title, meta_desc, keywords, seo_score, views))
            imported_count += 1
            print(f"Imported: {title} -> {slug} ({category})")
        except Exception as e:
            print(f"Error importing {title}: {e}")
            
    conn.commit()
    conn.close()
    print(f"Finished seeding database. Imported {imported_count} posts.")

if __name__ == '__main__':
    parse_and_import()
