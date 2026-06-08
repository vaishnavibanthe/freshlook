import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def create_pdf(filename, title, content_dict):
    doc = SimpleDocTemplate(filename, pagesize=letter,
                            rightMargin=54, leftMargin=54,
                            topMargin=54, bottomMargin=54)
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=15
    )
    
    section_title_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#2563eb'),
        spaceBefore=12,
        spaceAfter=6
    )
    
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#334155'),
        spaceAfter=10
    )
    
    meta_label_style = ParagraphStyle(
        'MetaLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#475569')
    )
    
    meta_val_style = ParagraphStyle(
        'MetaVal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#0f172a')
    )
    
    quote_style = ParagraphStyle(
        'QuoteStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#1e3a8a'),
        leftIndent=15,
        spaceBefore=10,
        spaceAfter=10
    )

    story = []
    
    # Title
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 10))
    
    # Metadata block as a table
    meta_data = [
        [Paragraph("Client Profile:", meta_label_style), Paragraph(content_dict.get('client', ''), meta_val_style),
         Paragraph("Industry:", meta_label_style), Paragraph(content_dict.get('industry', ''), meta_val_style)],
        [Paragraph("Region:", meta_label_style), Paragraph(content_dict.get('region', ''), meta_val_style),
         Paragraph("Solution Area:", meta_label_style), Paragraph(content_dict.get('solution_area', ''), meta_val_style)],
        [Paragraph("Technologies:", meta_label_style), Paragraph(content_dict.get('technologies', ''), meta_val_style),
         Paragraph("Date:", meta_label_style), Paragraph(content_dict.get('date', ''), meta_val_style)]
    ]
    
    t = Table(meta_data, colWidths=[90, 160, 90, 160])
    t.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('INNERGRID', (0,0), (-1,-1), 0.25, colors.HexColor('#e2e8f0')),
    ]))
    
    story.append(t)
    story.append(Spacer(1, 15))
    
    # Sections
    sections = [
        ("Business Challenge", 'challenge'),
        ("Solution Delivered", 'solution'),
        ("Implementation Approach", 'approach'),
        ("Business Outcomes", 'outcomes'),
        ("Key Result Metrics", 'metrics')
    ]
    
    for sec_title, key in sections:
        story.append(Paragraph(sec_title, section_title_style))
        story.append(Paragraph(content_dict.get(key, ''), body_style))
        story.append(Spacer(1, 5))
        
    if 'quote' in content_dict:
        story.append(Paragraph("Executive Quote", section_title_style))
        story.append(Paragraph(f'"{content_dict["quote"]}"', quote_style))
        
    doc.build(story)
    print(f"Generated PDF: {filename}")

def main():
    target_dir = './CaseStudies'
    os.makedirs(target_dir, exist_ok=True)
    
    # 1. Talend Case Study
    talend_data = {
        'client': 'A Leading Commercial Bank in North America',
        'industry': 'BFSI',
        'region': 'North America',
        'solution_area': 'Master Data Management (MDM) & Data Governance',
        'technologies': 'Talend Data Fabric, Snowflake, AWS S3, Apache Spark',
        'date': 'May 2026',
        'challenge': (
            'The client, a major commercial bank with operations spanning retail and commercial lending, '
            'struggled with decentralized customer records. Due to legacy acquisitions, customer records were '
            'scattered across 12 source systems. This fragmentation resulted in severe data inconsistencies '
            '(e.g., duplicated profiles, divergent credit scores), compliance issues with KYC/AML audits, '
            'and significant manual reconciliation overhead. Business analysts spent over 40% of their time '
            'manually compiling customer summaries for reporting.'
        ),
        'solution': (
            'Artha Solutions designed and deployed an active Data Governance and Master Data Management (MDM) '
            'framework using Talend Data Fabric. The solution ingested customer metadata in real-time, '
            'matching and merging duplicates into a single golden record in a secure Snowflake data warehouse. '
            'Talend Data Stewardship was integrated, allowing business curators to resolve matching exceptions '
            'via custom interactive workflows.'
        ),
        'approach': (
            'The implementation followed a three-phase approach: first, mapping metadata properties and '
            'establishing survivorship rules; second, deploying Talend pipelines to clean and standardise names, '
            'emails, and tax IDs; and third, implementing active data reconciliation triggers that push live updates '
            'to downstream systems on AWS S3.'
        ),
        'outcomes': (
            'The Talend MDM solution successfully established a unified customer directory, eliminating '
            'duplicate records across systems. Regulatory audit preparation time was reduced from weeks to '
            'a single click. The data repository now serves as a trusted foundation for active intelligence '
            'and localized AI analytics.'
        ),
        'metrics': (
            'The implementation delivered quantifiable improvements: achieved a 40% reduction in compliance '
            'reporting time, improved active data reconciliation accuracy by 80%, accomplished 95% automated '
            'data validation scoring, and successfully consolidated customer data from 12 separate legacy platforms.'
        ),
        'quote': (
            'Artha Solutions transformed our customer data landscape, bringing order to our compliance pipelines '
            'and delivering a trusted data repository that underpins our modern banking applications.'
        )
    }
    create_pdf(os.path.join(target_dir, 'Talend_Data_Governance_BFSI.pdf'), 
               "Enterprise Data Governance and Master Data Management (MDM) with Talend", 
               talend_data)
               
    # 2. Qlik Case Study
    qlik_data = {
        'client': 'Global Automotive Parts Manufacturer',
        'industry': 'Manufacturing',
        'region': 'Global / Europe',
        'solution_area': 'Real-time Logistics Analytics & ETL Modernization',
        'technologies': 'Qlik Cloud, Qlik Replicate, Qlik Compose, Snowflake, Microsoft Azure',
        'date': 'April 2026',
        'challenge': (
            'A global manufacturer of automotive assemblies suffered from severe inventory latency. '
            'Logistics and inventory events from legacy databases took over 24 hours to sync to the executive '
            'BI system. This latency led to frequent delays, stockouts, shipping bottle-necks, and a total lack '
            'of real-time tracking for hot orders. The manual ETL pipelines in place required frequent '
            'overnight maintenance, causing data outages.'
        ),
        'solution': (
            'Artha Solutions migrated the legacy ETL workflows to Qlik Cloud, designing a modern Change Data '
            'Capture (CDC) streaming pipeline. Using Qlik Replicate, transaction logs are read in real-time '
            'and streamed directly to a Snowflake warehouse hosted on Microsoft Azure. Qlik Compose was utilized '
            'to dynamically model warehouse schemas and automate data mart creations without writing complex SQL.'
        ),
        'approach': (
            'We audited 150 legacy ETL pipelines and mapped target schemas. We then deployed Qlik Replicate CDC '
            'tasks, set up automated schema generation in Qlik Compose, and designed live dashboards displaying '
            'key warehousing indicators, shipping statuses, and inventory routing metrics.'
        ),
        'outcomes': (
            'Logistics latency dropped from 24 hours to under 2 minutes, enabling active intelligence. '
            'Operations managers can now dynamically redirect shipments to avoid delays. The system automatically '
            'handles pipeline exceptions, resulting in zero overnight maintenance outages.'
        ),
        'metrics': (
            'Key project milestones include: 65% faster inventory reporting cycles, 90% automated ETL code '
            'migration from legacy systems, 30 million database transactions replicated daily, and over '
            'USD 1.2 million in annual logistics savings achieved by eliminating shipping delays.'
        ),
        'quote': (
            'By transitioning our pipelines to Qlik Cloud, Artha enabled real-time logistics analytics '
            'that saved millions in shipping delays and completely eliminated overnight pipeline overhead.'
        )
    }
    create_pdf(os.path.join(target_dir, 'Qlik_Cloud_Modernization_Manufacturing.pdf'), 
               "ETL Modernization and Live Logistics Analytics with Qlik Cloud", 
               qlik_data)

if __name__ == '__main__':
    main()
