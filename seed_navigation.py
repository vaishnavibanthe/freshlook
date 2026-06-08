import sqlite3
from datetime import datetime

def seed_navigation():
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()

    # Clear existing navigation data
    cursor.execute("DELETE FROM navigation_menus")
    cursor.execute("DELETE FROM navigation_items")
    cursor.execute("DELETE FROM navigation_featured_cards")
    cursor.execute("DELETE FROM navigation_ctas")

    now = datetime.utcnow().isoformat()

    # 1. Create Main Menu
    cursor.execute("""
        INSERT INTO navigation_menus (name, location, status, created_at, updated_at, published_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("Main Menu", "header", "Published", now, now, now))
    menu_id = cursor.lastrowid

    # Helper to insert nav item
    def insert_item(label, url=None, parent_id=None, group_label=None, description=None, icon=None, sort_order=0, is_top_level=0, is_featured=0):
        cursor.execute("""
            INSERT INTO navigation_items (
                menu_id, parent_id, label, url, description, icon, group_label, sort_order, is_top_level, is_featured, is_visible, opens_in_new_tab, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
        """, (menu_id, parent_id, label, url, description, icon, group_label, sort_order, is_top_level, is_featured, now, now))
        return cursor.lastrowid

    # 2. Top Level Navigation Items
    adv_id = insert_item("Artha Advantage", url="#", is_top_level=1, sort_order=1)
    sol_id = insert_item("Solutions", url="#", is_top_level=1, sort_order=2)
    ind_id = insert_item("Industries", url="#", is_top_level=1, sort_order=3)
    res_id = insert_item("Resources", url="#", is_top_level=1, sort_order=4)
    abt_id = insert_item("About Us", url="#", is_top_level=1, sort_order=5)

    # 3. Sub-items for "Artha Advantage"
    # Accelerators Group
    insert_item("Data Insights Platform (DIP)", "/artha-advantage/data-insights-platform", parent_id=adv_id, group_label="Accelerators", description="Comprehensive, AI-driven solution to streamline Data Governance", sort_order=1)
    insert_item("MDM Lite", "/artha-advantage/mdm-lite", parent_id=adv_id, group_label="Accelerators", description="Cost-effective, easy-to-use platform to manage and centralize master data", sort_order=2)
    insert_item("Customer 360", "/artha-advantage/customer-360", parent_id=adv_id, group_label="Accelerators", description="A complete customer picture with unified data for actionable insights", sort_order=3)
    insert_item("Dynamic Ingestion Framework", "/artha-advantage/dynamic-ingestion-framework", parent_id=adv_id, group_label="Accelerators", description="Revolutionize Data Ingestion with Metadata-driven ETL", sort_order=4)
    insert_item("ETL Tool Migration", "/artha-advantage/technology-and-data-migration", parent_id=adv_id, group_label="Accelerators", description="Accelerate your ETL Tool Migration to Talend", sort_order=5)

    # Digital Transformation Group
    insert_item("Digital Strategy", "/artha-advantage/digital-transformations", parent_id=adv_id, group_label="Digital Transformation", description="Differentiate digitally, optimize, engage, and succeed", sort_order=1)
    insert_item("Transformation Solutions & Services", "/artha-advantage/digital-transformation-services", parent_id=adv_id, group_label="Digital Transformation", description="Unlock digital potential with innovative solutions and ongoing support", sort_order=2)

    # SAP Modernization Group
    insert_item("Artha Advantage for SAP", "/artha-advantage-for-sap", parent_id=adv_id, group_label="SAP Modernization", description="Comprehensive SAP migration for data quality and accelerated transition", sort_order=1)
    insert_item("B’etl™ – The ETL Migrator", "/artha-advantage/technology-and-data-migration", parent_id=adv_id, group_label="SAP Modernization", description="Modernization doesn't have to be hard. With B’etl™, it isn't.", sort_order=2)

    # 4. Sub-items for "Solutions"
    # Data Solutions Group
    insert_item("Data Strategy", "/solutions/data-strategy", parent_id=sol_id, group_label="Data Solutions", description="Align business goals with data potential", sort_order=1)
    insert_item("Master Data Management", "/solutions/master-data-management", parent_id=sol_id, group_label="Data Solutions", description="Single source of truth for critical entity data", sort_order=2)
    insert_item("Enterprise Data Management", "/solutions/enterprise-data-management", parent_id=sol_id, group_label="Data Solutions", description="Build scalable pipelines and data lakes", sort_order=3)
    insert_item("Data Governance", "/solutions/data-governance", parent_id=sol_id, group_label="Data Solutions", description="Security, quality, and compliance for confidence", sort_order=4)
    insert_item("Big Data", "/solutions/big-data", parent_id=sol_id, group_label="Data Solutions", description="Real-time processing and massive scalability", sort_order=5)
    insert_item("Data Quality", "/industries/data-quality", parent_id=sol_id, group_label="Data Solutions", description="Clean, consistent, and reliable datasets", sort_order=6)
    insert_item("Data Science & Analytics", "/solutions/data-science-analytics", parent_id=sol_id, group_label="Data Solutions", description="AI/ML predictive analytics and visual intelligence", sort_order=7)

    # Artificial Intelligence Group
    insert_item("AI Solutions Hub", "/artificial-intelligence", parent_id=sol_id, group_label="Artificial Intelligence", description="Overview of Artha's Generative AI consulting & engineering", sort_order=1)
    insert_item("AI Data Readiness", "/artificial-intelligence/data-readiness", parent_id=sol_id, group_label="Artificial Intelligence", description="Prepare data foundations for model ingestion & RAG", sort_order=2)
    insert_item("Intelligent Decisions", "/artificial-intelligence/intelligent-solutions", parent_id=sol_id, group_label="Artificial Intelligence", description="AutoML forecasting, pricing engines, and scenario simulations", sort_order=3)
    insert_item("Workflow Automation", "/artificial-intelligence/ai-workflow-automation-process-optimization", parent_id=sol_id, group_label="Artificial Intelligence", description="Orchestrate tasks and automate document processing loops", sort_order=4)
    insert_item("Human Engagement", "/artificial-intelligence/ai-human-engagement-experience", parent_id=sol_id, group_label="Artificial Intelligence", description="Conversational agents, copilots, and CCaaS QA scoring", sort_order=5)
    insert_item("Platform Engineering", "/artificial-intelligence/ai-platform-engineering-services", parent_id=sol_id, group_label="Artificial Intelligence", description="Set up MLOps/LLMOps pipelines, lakehouses, & guardrails", sort_order=6)
    insert_item("AI ROI Solutions", "/artificial-intelligence/ai-roi-solutions", parent_id=sol_id, group_label="Artificial Intelligence", description="Outcome-driven frameworks like MAAC & SniffGuard", sort_order=7)

    # Enterprise Applications Group
    insert_item("SAP Modernization", "/sap", parent_id=sol_id, group_label="Enterprise Applications", description="SAP migration, integration, and platform upgrades", sort_order=1)
    insert_item("ServiceNow Services", "/enterprise-application/service-now", parent_id=sol_id, group_label="Enterprise Applications", description="Optimize IT workflows and enterprise operations", sort_order=2)
    insert_item("Oracle Consulting", "/enterprise-application/oracle", parent_id=sol_id, group_label="Enterprise Applications", description="Upgrade ERP, databases, and financial systems", sort_order=3)
    insert_item("Cloud Services", "/cloud", parent_id=sol_id, group_label="Enterprise Applications", description="Multi-cloud migration, strategy, and architecture", sort_order=4)
    insert_item("Managed Services", "/managed-services", parent_id=sol_id, group_label="Enterprise Applications", description="24/7 proactive data platform administration", sort_order=5)

    # Featured Card for Solutions
    cursor.execute("""
        INSERT INTO navigation_featured_cards (
            menu_id, parent_nav_item_id, title, description, image_path, label, cta_text, cta_url, sort_order, is_visible, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
    """, (
        menu_id,
        sol_id,
        "Future-Ready Data Foundation",
        "Learn how to move from AI pilots to full scale enterprise production value in this IDC Spotlight report.",
        "",
        "Featured Spotlight",
        "Download Report",
        "/events/future-ready-data-foundation-from-ai-pilot-to-production-value",
        1,
        now,
        now
    ))

    # 5. Sub-items for "Industries"
    # Success Stories Group
    insert_item("Enhanced Data Governance", "/case-studies", parent_id=ind_id, group_label="Selected Success Stories", description="Reduced metadata search time by 40% and improved data accuracy by 65% for financial operations.", sort_order=1)
    insert_item("Analytics Modernization", "/case-studies", parent_id=ind_id, group_label="Selected Success Stories", description="Improved data visibility, safeguard data security, and scale data infrastructure for acquisition analytics.", sort_order=2)
    insert_item("Master Data Management", "/case-studies", parent_id=ind_id, group_label="Selected Success Stories", description="Strengthened customer experience, compliance, and decision logic via unified MDM.", sort_order=3)

    # Target Industries Group (with Icons)
    insert_item("Manufacturing", "/industries/manufacturing", parent_id=ind_id, group_label="Target Industries", icon="fas fa-industry", sort_order=1)
    insert_item("BFSI (Banking & Financial Services)", "/industries/bfsi", parent_id=ind_id, group_label="Target Industries", icon="fas fa-landmark", sort_order=2)
    insert_item("Retail & E-Commerce", "/industries/retail", parent_id=ind_id, group_label="Target Industries", icon="fas fa-shopping-cart", sort_order=3)
    insert_item("Healthcare & Life Sciences", "/industries/healthcare", parent_id=ind_id, group_label="Target Industries", icon="fas fa-hospital", sort_order=4)
    insert_item("Utilities & Energy", "/industries/utilities", parent_id=ind_id, group_label="Target Industries", icon="fas fa-tint", sort_order=5)
    insert_item("Hospitality & Travel", "/industries/hospitality", parent_id=ind_id, group_label="Target Industries", icon="fas fa-hotel", sort_order=6)
    insert_item("Telecommunications", "/industries/telecom", parent_id=ind_id, group_label="Target Industries", icon="fas fa-broadcast-tower", sort_order=7)

    # 6. Sub-items for "Resources"
    # Featured Resources Group
    insert_item("Data Quality Guide", "/industries/data-quality", parent_id=res_id, group_label="Featured Resources", description="Clean, consistent, and well-governed data to drive your business success.", sort_order=1)
    insert_item("Master Data Management Frameworks", "/solutions/master-data-management", parent_id=res_id, group_label="Featured Resources", description="Improve data visibility, safeguard data security, and scale data infrastructure.", sort_order=2)
    insert_item("Data Governance Playbook", "/solutions/data-governance", parent_id=res_id, group_label="Featured Resources", description="Establish data quality, security, and compliance for better decision logic.", sort_order=3)

    # Resource Center Group (with Icons)
    insert_item("Events & Summits", "/resources/events", parent_id=res_id, group_label="Resource Center", icon="fas fa-calendar-alt", sort_order=1)
    insert_item("On-Demand Webinars", "/resources/webinars", parent_id=res_id, group_label="Resource Center", icon="fas fa-video", sort_order=2)
    insert_item("Blogs & Insights", "/blogs", parent_id=res_id, group_label="Resource Center", icon="fas fa-book-open", sort_order=3)
    insert_item("Whitepapers & Reports", "/resources/whitepapers", parent_id=res_id, group_label="Resource Center", icon="fas fa-file-alt", sort_order=4)
    insert_item("Case Studies", "/case-studies", parent_id=res_id, group_label="Resource Center", icon="fas fa-clipboard-list", sort_order=5)
    insert_item("On-Demand Workshop", "/resources/on-demand-workshop", parent_id=res_id, group_label="Resource Center", icon="fas fa-tools", sort_order=6)

    # 7. Sub-items for "About Us"
    # Partners Mini Grid
    insert_item("Talend", "/partners/talend", parent_id=abt_id, group_label="Technology Partners", description="Platinum Partner", sort_order=1)
    insert_item("Qlik", "/partners/qlik", parent_id=abt_id, group_label="Technology Partners", description="Active Intelligence", sort_order=2)
    insert_item("Snowflake", "/partners/snowflake", parent_id=abt_id, group_label="Technology Partners", description="Cloud Warehouse", sort_order=3)
    insert_item("AWS Cloud", "/partners/aws-cloud-services", parent_id=abt_id, group_label="Technology Partners", description="Infrastructure", sort_order=4)
    insert_item("Azure Cloud", "/partners/azure-cloud-services", parent_id=abt_id, group_label="Technology Partners", description="Solutions", sort_order=5)
    insert_item("Amurta DIP", "/partners/amurta-data-insights-platform", parent_id=abt_id, group_label="Technology Partners", description="Governance", sort_order=6)
    insert_item("Data Sentinel", "/data-sentinel", parent_id=abt_id, group_label="Technology Partners", description="Privacy & Compliance", sort_order=7)
    insert_item("Alation", "/alation-2", parent_id=abt_id, group_label="Technology Partners", description="Data Catalog", sort_order=8)

    # Company
    insert_item("About Our Team", "/about-us", parent_id=abt_id, group_label="Company", description="Empower businesses with insightful innovations", sort_order=1)
    insert_item("Partners Ecosystem", "/partners", parent_id=abt_id, group_label="Company", description="Strategic alliances catering to all data requirements", sort_order=2)
    insert_item("Careers", "/careers", parent_id=abt_id, group_label="Company", description="Be part of our dynamic enterprise consulting team", sort_order=3)
    insert_item("Request a Demo", "/contact-us", parent_id=abt_id, group_label="Company", description="See our assessment framework in action", sort_order=4)

    # 8. Create CTAs
    cursor.execute("""
        INSERT INTO navigation_ctas (label, url, style, location, is_visible, sort_order, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, ?, ?)
    """, ("Talk to an Expert", "/contact-us", "secondary", "header", 1, now, now))

    cursor.execute("""
        INSERT INTO navigation_ctas (label, url, style, location, is_visible, sort_order, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, ?, ?)
    """, ("Get Data Readiness Assessment", "/data-readiness-assessment", "primary", "header", 2, now, now))

    conn.commit()
    conn.close()
    print("Navigation data seeded successfully.")

if __name__ == '__main__':
    seed_navigation()
