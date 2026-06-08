import sqlite3
import json
from datetime import datetime

def seed_data():
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()

    # Clear existing rows to support re-seeding/idempotence
    cursor.execute("DELETE FROM industry_microsite_pages WHERE industry = 'artificial-intelligence'")

    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    pages = [
        # Landing Page / Overview
        {
            'industry': 'artificial-intelligence',
            'page_key': 'ai-overview',
            'title': 'Generative AI Consulting & AI Implementation Services',
            'slug': 'artificial-intelligence',
            'url': '/artificial-intelligence',
            'hero_title': 'Getting Ready for AI?',
            'hero_subtitle': 'Turn AI from pilot to production. Clean, connected, governed data that leaders can trust.',
            'body_sections_json': json.dumps({
                'hero_bullets': [
                    'Build the foundation AI won’t outgrow with a structured data foundation',
                    'Evaluate gaps and prioritize investments with a data readiness assessment',
                    'Ship predictive and prescriptive value fast, safely, and at scale'
                ],
                'intro_title': 'Fast forward to AI Adoption',
                'intro_desc': 'Discover how organizations deliver real business value with Artha Solutions by building trusted, governed, and model-ready data platforms.',
                'capabilities_teaser': [
                    {'title': 'AI Data Readiness', 'desc': 'Prepare, clean, and structure databases for semantic ingestion and LLM retrieval.'},
                    {'title': 'Intelligent Decisioning & Insights', 'desc': 'Embed models in operations to optimize forecasting, pricing, and risk management.'},
                    {'title': 'Workflow Automation & Process Optimization', 'desc': 'Automate manual process loops, invoice handling, and ticket triaging.'},
                    {'title': 'Human Engagement & Experience', 'desc': 'Deploy conversational agents and copilots that reference governed knowledge bases.'},
                    {'title': 'Platform & Engineering Services', 'desc': 'Stand up vector stores, container orchestrators, and guardrails to run models securely.'}
                ],
                'analyst_speak_title': 'IDC Analyst Spotlight',
                'analyst_speak_text': 'Miss the next 12 months on data readiness and rivals may be first to lock in AI advantages around speed, accuracy, and customer trust. Success with AI starts with data: metadata unification, quality management, and control - treating data as a product.'
            }),
            'cta_json': json.dumps({
                'primary_cta_text': 'Talk to an AI Data Expert',
                'primary_cta_url': '/contact-us?industry=ai',
                'secondary_cta_text': 'Explore AI ROI Solutions',
                'secondary_cta_url': '/artificial-intelligence/ai-roi-solutions'
            }),
            'faq_json': json.dumps([
                {
                    'q': 'How fast can you enable data readiness for enterprises?',
                    'a': 'Most programs start with a 2–4 week assessment and a 60–90 day roadmap. Initial improvements in data quality, access, and governance can be delivered in the first quarter, with broader readiness scaling over time.'
                },
                {
                    'q': 'What are the engagement models?',
                    'a': 'Flexible models include advisory and assessment, fixed-scope implementation, and managed services. Teams can start small with a readiness audit or run end-to-end programs covering data, AI, and ongoing operations.'
                },
                {
                    'q': 'What kind of business applications can you create using AI?',
                    'a': 'Common applications include forecasting, pricing, risk monitoring, workflow automation, document processing, customer support, and decision copilots across sales, finance, operations, and service functions.'
                },
                {
                    'q': 'How safe is our data while leveraging Large Language Models (LLMs)?',
                    'a': 'We ensure your proprietary data remains safe by establishing private API networks, data masking layers, and secure context retrievers (RAG) that prevent public leakage or training reuse.'
                }
            ]),
            'related_services_json': json.dumps([
                {'title': 'AI Data Readiness', 'url': '/artificial-intelligence/data-readiness'},
                {'title': 'Intelligent Solutions', 'url': '/artificial-intelligence/intelligent-solutions'},
                {'title': 'Platform Engineering', 'url': '/artificial-intelligence/ai-platform-engineering-services'}
            ]),
            'related_case_studies_json': json.dumps([]),
            'seo_title': 'Generative AI Consulting & AI Implementation Services | Artha Solutions',
            'seo_description': 'Unleash business value with Artha Solutions\' Generative AI consulting, custom LLM integrations, workflow automation, and data readiness frameworks.',
            'seo_keywords': 'generative ai consulting, enterprise LLM implementation, ai data readiness, workflow automation, decision intelligence, model-ready data fabric',
            'canonical_url': 'https://www.thinkartha.com/artificial-intelligence/',
            'og_title': 'Generative AI Consulting & AI Implementation Services | Artha Solutions',
            'og_description': 'Turn AI ambition into measurable production outcomes. Modern data, automation, and platform engineering services built for enterprise leaders.',
            'og_image': 'https://www.thinkartha.com/wp-content/uploads/2026/03/What-Is-an-AI-Ready-Data-Foundation-scaled.jpg',
            'ai_summary': 'Artha Solutions provides end-to-end AI consulting and platform engineering. We help organizations build AI-ready data foundations, implement predictive decision models, optimize workflows, deploy conversational agents, and establish secure MLOps pipelines.',
            'genai_entities_json': json.dumps(['Generative AI', 'Large Language Models', 'AI consulting', 'Data readiness', 'Workflow automation', 'Platform engineering', 'B2B integration', 'Enterprise data governance'])
        },
        
        # Subpage 1: Data Readiness
        {
            'industry': 'artificial-intelligence',
            'page_key': 'ai-data-readiness',
            'title': 'AI Data Readiness Services',
            'slug': 'artificial-intelligence/data-readiness',
            'url': '/artificial-intelligence/data-readiness',
            'hero_title': 'Data foundation that turns AI ambition into business results',
            'hero_subtitle': 'Ensuring your data is production-ready for AI on day zero; not just clean, but accessible, explainable, secure, and governed at scale.',
            'body_sections_json': json.dumps({
                'pillars': [
                    {'title': 'Data Readiness & Governance', 'desc': 'A single control plane-catalog, lineage, quality rules, and privacy-so leaders can trace any KPI to source.'},
                    {'title': 'Data Audit & Quality', 'desc': 'Assess, profile, and continuously validate data quality across sources for accuracy, freshness, and bias.'},
                    {'title': 'Data Structure & Integration', 'desc': 'Standardize and integrate data using modern fabric architectures to feed models at decision speed.'},
                    {'title': 'Compliance & Security', 'desc': 'Embed privacy, masking, and access controls directly into pipelines so sensitive info stays secure.'},
                    {'title': 'AI Governance', 'desc': 'Define policies, ownership, and audit registers for AI inputs and outputs to ensure model transparency.'}
                ],
                'audiences': [
                    {
                        'role': 'Data Office',
                        'features': [
                            {'title': 'Data Trust Control Plane', 'desc': 'Executive trust scores with lineage, quality signals, and explainability so decisions are auditable.'},
                            {'title': 'Domain Data Products & SLAs', 'desc': 'Clear ownership and contracts for critical datasets to accelerate AI time-to-value.'},
                            {'title': 'AI Input & Output Lineage', 'desc': 'Full visibility into what data trained, fed, and influenced production AI models.'}
                        ]
                    },
                    {
                        'role': 'Business Functions',
                        'features': [
                            {'title': 'Decision Ready Data Products', 'desc': 'Curate trusted datasets for forecasting, pricing, and risk management so teams act on consistent inputs.'},
                            {'title': 'Real-Time Data Availability', 'desc': 'Deliver fresh, contextual data to workflows at the moment of decision, reducing latency.'},
                            {'title': 'Data to Workflow Integration', 'desc': 'Embed trusted data directly into CRM, ERP, and service tools to automate tasks.'}
                        ]
                    },
                    {
                        'role': 'Engineering Teams',
                        'features': [
                            {'title': 'Data Integration Modernization', 'desc': 'Unify batch, streaming, and federated access to make data usable for models at scale.'},
                            {'title': 'Metadata & Observability Layer', 'desc': 'Monitor pipeline drift and schema changes to flag issues before they impact models.'},
                            {'title': 'Environment Readiness Toolkit', 'desc': 'Prepare dev, testing, and production data environments to reduce model iteration times.'}
                        ]
                    },
                    {
                        'role': 'Executive Team',
                        'features': [
                            {'title': 'AI Readiness Scorecards', 'desc': 'Executive-level dashboard reflecting data trust, risk boundaries, and platform capabilities.'},
                            {'title': 'Value-Linked Prioritization', 'desc': 'Identify which data products drive the most impact to focus investments where ROI is highest.'},
                            {'title': '90-Day Readiness Roadmap', 'desc': 'Practical blueprint showing incremental data improvements, quick wins, and scaling steps.'}
                        ]
                    },
                    {
                        'role': 'Security & Compliance',
                        'features': [
                            {'title': 'Privacy-Aware Pipelines', 'desc': 'Dynamic data masking, tokenization, and hashing built right into model ingestion layers.'},
                            {'title': 'Audit-Ready Lineage', 'desc': 'Maintain absolute traceability for training datasets to comply with rising AI regulations.'},
                            {'title': 'Policy-Driven Controls', 'desc': 'Automate policy enforcement across tables to block unauthorized access by design.'}
                        ]
                    }
                ]
            }),
            'cta_json': json.dumps({
                'primary_cta_text': 'Request Data Audit',
                'primary_cta_url': '/contact-us?interest=data-readiness',
                'secondary_cta_text': 'Download IDC Spotlight',
                'secondary_cta_url': '/events/future-ready-data-foundation-from-ai-pilot-to-production-value'
            }),
            'faq_json': json.dumps([
                {
                    'q': 'What does "data readiness for AI" actually mean?',
                    'a': 'It means your data is accurate, governed, accessible, and timely enough for AI models to train and operate reliably. It includes quality checks, clear ownership, security controls, and consistent definitions across systems.'
                },
                {
                    'q': 'How do we know if our data is ready for AI?',
                    'a': 'A readiness assessment reviews data quality, availability, integration, and governance. It identifies gaps that could affect AI accuracy, risk, or scale, and provides a prioritized plan to address them.'
                },
                {
                    'q': 'Do we need to move all data to the cloud first?',
                    'a': 'Not always. Many organizations start by improving integration, quality, and governance across existing systems. Cloud migration can be part of the roadmap, but readiness can begin with current environments.'
                },
                {
                    'q': 'Will this disrupt our existing systems?',
                    'a': 'Most work is incremental. Data can be improved and governed in phases without replacing core systems, focusing first on high-value use cases.'
                },
                {
                    'q': 'How do you handle privacy and compliance?',
                    'a': 'Data policies, access controls, and audit trails are applied throughout pipelines and AI workflows. Sensitive data can be masked or restricted based on regulatory and internal requirements.'
                }
            ]),
            'related_services_json': json.dumps([
                {'title': 'Intelligent Solutions', 'url': '/artificial-intelligence/intelligent-solutions'},
                {'title': 'Platform Engineering', 'url': '/artificial-intelligence/ai-platform-engineering-services'},
                {'title': 'Data Governance', 'url': '/solutions/data-governance'}
            ]),
            'related_case_studies_json': json.dumps([]),
            'seo_title': 'AI Data Readiness Services for Enterprises | Artha Solutions',
            'seo_description': 'Ensure your data is production-ready for AI on day zero. We build accessible, explainable, secure, and governed data foundations for scalable AI.',
            'seo_keywords': 'ai data readiness, data governance for ai, data quality assessment, data lake cleanup, raw data to ai assets',
            'canonical_url': 'https://www.thinkartha.com/artificial-intelligence/data-readiness/',
            'ai_summary': 'AI Data Readiness services establish a single control plane for metadata tracking, data lineage, policy-driven masking, and automatic profiling to ensure day-zero AI compliance.'
        },

        # Subpage 2: Intelligent Solutions
        {
            'industry': 'artificial-intelligence',
            'page_key': 'ai-intelligent-solutions',
            'title': 'AI for Intelligent Decisions & Insights',
            'slug': 'artificial-intelligence/intelligent-solutions',
            'url': '/artificial-intelligence/intelligent-solutions',
            'hero_title': 'Decisions that move the P&L',
            'hero_subtitle': 'Predictive and prescriptive intelligence turns data into timely, explainable actions, improving forecast accuracy, pricing, and risk signals so revenue grows and surprises shrink.',
            'body_sections_json': json.dumps({
                'pillars': [
                    {'title': 'Decision Copilot', 'desc': 'Ask your business in plain English. Get explainable, source-linked answers you can act on.'},
                    {'title': 'Forecast Studio', 'desc': 'See the quarter before it happens. Unite demand, revenue, and risk to cut planning errors.'},
                    {'title': 'Pricing Optimizer', 'desc': 'Model price elasticity and margins to set winning price bands that protect volume.'},
                    {'title': 'Next-Best-Action Engine', 'desc': 'Serve the right offer, channel, and timing to drive incremental customer lift.'},
                    {'title': 'Scenario Simulator', 'desc': 'Stress-test plans for supply, capacity, and working capital in minutes to find the best path.'},
                    {'title': 'AutoML & Feature Library', 'desc': 'Reuse features and version models to ship production use cases faster with less risk.'}
                ],
                'audiences': [
                    {
                        'role': 'Sales & Revenue',
                        'features': [
                            {'title': 'Sales Copilot', 'desc': 'Natural-language queries over CRM, notes, and emails for instant briefs and obection handling.'},
                            {'title': 'Quote & Price Optimizer', 'desc': 'Real-time discount guardrails and CPQ-ready bundles to protect margins.'},
                            {'title': 'Deal Alert Monitor', 'desc': 'Early risk signals on account inactivity or competitor activities to rescue deals.'}
                        ]
                    },
                    {
                        'role': 'Supply Chain',
                        'features': [
                            {'title': 'Demand & Supply Forecasting', 'desc': 'Unify logs across warehouses, supplier networks, and market indicators to predict stockouts.'},
                            {'title': 'Inventory & Working Capital Optimizer', 'desc': 'Optimize replenishment schedules to free up cash flow while maintaining service SLAs.'},
                            {'title': 'Supply Simulator', 'desc': 'Model sourcing bottlenecks and logistic rate shifts to prepare buffer plans.'}
                        ]
                    },
                    {
                        'role': 'Finance & Ops',
                        'features': [
                            {'title': 'Margin Forecast Studio', 'desc': 'Predict cost shifts and revenue swings tied to live operational signals.'},
                            {'title': 'Cash Flow Optimizer', 'desc': 'Model AP/AR trends to optimize liquidity positioning.'},
                            {'title': 'Capacity Throughput Optimizer', 'desc': 'Determine staffing and scheduling limits to improve operational output.'}
                        ]
                    }
                ]
            }),
            'cta_json': json.dumps({
                'primary_cta_text': 'Talk to a Decision Strategist',
                'primary_cta_url': '/contact-us?interest=intelligent-solutions',
                'secondary_cta_text': 'Claim $1 Feasibility POC',
                'secondary_cta_url': '/intelligent-data-assessment-platform'
            }),
            'faq_json': json.dumps([
                {
                    'q': 'How does Artha use AI to improve enterprise decision-making?',
                    'a': 'Artha applies AI and advanced analytics to unify enterprise data, surface actionable insights, and augment human decision-making across planning, revenue, and risk scenarios.'
                },
                {
                    'q': 'What types of decisions can AI improve using Artha’s approach?',
                    'a': 'We focus on high-impact decisions such as demand forecasting, pricing optimization, risk assessment, customer segmentation, and executive planning.'
                },
                {
                    'q': 'How is this different from traditional BI or dashboards?',
                    'a': 'Unlike static BI, Artha’s AI-driven insights continuously learn from data, predict outcomes, and recommend actions moving from reporting to decision intelligence.'
                },
                {
                    'q': 'Do you need clean or "perfect" data to get started?',
                    'a': 'No. Artha specializes in assessing and improving data readiness for AI, enabling organizations to derive value even from fragmented or imperfect data.'
                },
                {
                    'q': 'How quickly can we see results?',
                    'a': 'Most clients see measurable improvements within 60 – 90 days, starting with targeted decision workflows rather than enterprise-wide disruption.'
                }
            ]),
            'related_services_json': json.dumps([
                {'title': 'AI Data Readiness', 'url': '/artificial-intelligence/data-readiness'},
                {'title': 'Workflow Automation', 'url': '/artificial-intelligence/ai-workflow-automation-process-optimization'},
                {'title': 'Data Science & Analytics', 'url': '/solutions/data-science-analytics'}
            ]),
            'related_case_studies_json': json.dumps([]),
            'seo_title': 'AI Intelligent Decisioning Solutions for Enterprises | Artha Solutions',
            'seo_description': 'Embed predictive analytics and decision copilots into CRM, ERP, and supply chain applications to optimize pricing, demand, and operations.',
            'seo_keywords': 'decision intelligence, predictive forecasting, cash flow optimization, inventory demand forecasting, pricing optimizer, automated decisioning',
            'canonical_url': 'https://www.thinkartha.com/artificial-intelligence/intelligent-solutions/',
            'ai_summary': 'AI for Intelligent Decisions embeds AutoML, forecast studios, pricing engines, and scenario simulators to move the P&L across sales, supply chain, and operations.'
        },

        # Subpage 3: Workflow Automation
        {
            'industry': 'artificial-intelligence',
            'page_key': 'ai-workflow-automation',
            'title': 'AI for Workflow Automation & Process Optimization',
            'slug': 'artificial-intelligence/ai-workflow-automation-process-optimization',
            'url': '/artificial-intelligence/ai-workflow-automation-process-optimization',
            'hero_title': 'Automate the busywork. Improve the work',
            'hero_subtitle': 'Orchestrate tasks across systems with human-in-the-loop only where needed. Cut cycle times and costs while reducing errors across O2C, P2P, service, and operations.',
            'body_sections_json': json.dumps({
                'pillars': [
                    {'title': 'Process Orchestrator', 'desc': 'Run cross-app processes end to end with policy-aware approvals to cut handoffs.'},
                    {'title': 'Document & Email Automation', 'desc': 'Auto-extract and classify invoices, shipping records, and claims, routing data to systems.'},
                    {'title': 'Service Desk Triage', 'desc': 'Auto-route tickets by skills, priority, and SLA, providing agents with immediate context.'},
                    {'title': 'Pre-built Process Blueprints', 'desc': 'Blueprints for O2C, P2P, and HR onboarding to standardize delivery from day one.'},
                    {'title': 'Exception Manager', 'desc': 'Early warning triggers and playbooks to catch process breaks before they breach SLAs.'},
                    {'title': 'RPA & Application Connectors', 'desc': 'Unify ERP, CRM, and custom apps through secure APIs and bots to stop swivel-chair work.'}
                ],
                'audiences': [
                    {
                        'role': 'Orchestration',
                        'features': [
                            {'title': 'Flow Orchestrator', 'desc': 'Stitch steps across CRM, ERP, and custom tools automatically to save cycle time.'},
                            {'title': 'Adaptive Approvals', 'desc': 'Risk-scored parallel approvals with mobile one-click sign-offs.'},
                            {'title': 'Exception Playbooks', 'desc': 'Automated backup routing and alerts when standard paths fail.'}
                        ]
                    },
                    {
                        'role': 'Automation',
                        'features': [
                            {'title': 'Document Automation', 'desc': 'OCR extraction on invoices, receipts, and shipping labels, synced to database records.'},
                            {'title': 'Case Classification', 'desc': 'Automated classification of inbound support emails to trigger response drafts.'},
                            {'title': 'Onboarding Flows', 'desc': 'Provision accounts, security rights, and directory profiles for employees automatically.'}
                        ]
                    },
                    {
                        'role': 'Optimization',
                        'features': [
                            {'title': 'Bottleneck Analyzer', 'desc': 'Track latency across process steps and flag points causing delays.'},
                            {'title': 'Cost to Serve Tracker', 'desc': 'Directly link operational overhead to specific processes and teams.'},
                            {'title': 'Process Variant Analyzer', 'desc': 'Compare task sequences to identify and scale the most efficient path.'}
                        ]
                    }
                ]
            }),
            'cta_json': json.dumps({
                'primary_cta_text': 'Automate My Processes',
                'primary_cta_url': '/contact-us?interest=workflow-automation',
                'secondary_cta_text': 'View Retail Success',
                'secondary_cta_url': '/artificial-intelligence/data-readiness'
            }),
            'faq_json': json.dumps([
                {
                    'q': 'What kinds of processes can be automated with AI?',
                    'a': 'Common processes include order-to-cash (O2C), procure-to-pay (P2P), customer support triaging, invoice/document processing, HR onboarding, and IT ticket routing.'
                },
                {
                    'q': 'Do we need to replace our current legacy systems to automate workflows?',
                    'a': 'No. Artha uses secure APIs and RPA bots to bridge the gap between legacy databases, ERPs, CRMs, and modern cloud orchestrators, preserving your investments.'
                },
                {
                    'q': 'How do you handle exceptions in automated steps?',
                    'a': 'We build "Human-in-the-loop" exception paths. When a model falls below a confidence threshold, the item is sent to a team dashboard with highlighted fields for manual review.'
                },
                {
                    'q': 'How fast can we see results from process automation?',
                    'a': 'Initial pilots can go live in 6 to 8 weeks, with target processes seeing a significant drop in cycle times within the first 90 days.'
                }
            ]),
            'related_services_json': json.dumps([
                {'title': 'Intelligent Solutions', 'url': '/artificial-intelligence/intelligent-solutions'},
                {'title': 'Platform Engineering', 'url': '/artificial-intelligence/ai-platform-engineering-services'},
                {'title': 'Managed Services', 'url': '/solutions/managed-services'}
            ]),
            'related_case_studies_json': json.dumps([]),
            'seo_title': 'AI-Driven Document Automation & Workflow Management | Artha Solutions',
            'seo_description': 'Unify ERP, CRM, and custom apps with end-to-end intelligent orchestration. Auto-extract documents, triage support tickets, and cut processing costs.',
            'seo_keywords': 'workflow automation, intelligent document processing, o2c automation, invoice processing, process orchestration, process optimization',
            'canonical_url': 'https://www.thinkartha.com/artificial-intelligence/ai-workflow-automation-process-optimization/',
            'ai_summary': 'AI Workflow Automation connects cross-application steps using natural language classification, optical character recognition (OCR), and RPA connectors to cut processing overhead.'
        },

        # Subpage 4: Human Engagement
        {
            'industry': 'artificial-intelligence',
            'page_key': 'ai-human-engagement',
            'title': 'AI for Human Engagement & Experience',
            'slug': 'artificial-intelligence/ai-human-engagement-experience',
            'url': '/artificial-intelligence/ai-human-engagement-experience',
            'hero_title': 'AI that serves customers, not scripts',
            'hero_subtitle': 'Virtual agents and agent assist deliver grounded answers, personalized offers, and faster resolutions-raising CX/EX while lowering handling time and support costs.',
            'body_sections_json': json.dumps({
                'pillars': [
                    {'title': 'AI Customer Agent', 'desc': 'Always-on AI agents resolve requests, complete orders, and hand off to humans with full context.'},
                    {'title': 'Agent Assist', 'desc': 'Real-time guidance, summaries, and next-best actions integrated into your CCaaS/CRM.'},
                    {'title': 'Agentic Contact Center', 'desc': 'Plug AI into Nice, Genesys, or Salesforce to guide conversations and automate call wrap-ups.'},
                    {'title': 'Enterprise Search', 'desc': 'Combine search with LLMs to return grounded, source-linked answers from internal files.'},
                    {'title': 'Automated QA & Coaching', 'desc': 'Assess 100% of interactions for sentiment, script compliance, and training opportunities.'},
                    {'title': 'Proactive Outreach', 'desc': 'Orchestrate automated renewal, alert, or scheduling messages tailored to behavior.'}
                ],
                'audiences': [
                    {
                        'role': 'Conversational Care',
                        'features': [
                            {'title': 'Conversational Service Agent', 'desc': 'Secure, authentic chatbot answering FAQs and guiding customers without script errors.'},
                            {'title': 'Transactional Concierge', 'desc': 'Let customers pay bills, check order status, and change dates through chat integrations.'},
                            {'title': 'Proactive Care Alerts', 'desc': 'Notify customers of outages, shipments, or renewal dates with interactive responses.'}
                        ]
                    },
                    {
                        'role': 'Support Quality',
                        'features': [
                            {'title': 'Automated QA Scoring', 'desc': 'Ditch random call sampling. Audit every call transcript for compliance automatically.'},
                            {'title': 'Sentiment & Risk Alerts', 'desc': 'Instantly flag interactions displaying frustration or policy violations.'},
                            {'title': 'Compliance Checker', 'desc': 'Verify disclosures, scripting, and privacy protocols are followed during chats.'}
                        ]
                    }
                ]
            }),
            'cta_json': json.dumps({
                'primary_cta_text': 'Deploy AI Customer Agents',
                'primary_cta_url': '/contact-us?interest=human-engagement',
                'secondary_cta_text': 'Claim Complimentary Audit',
                'secondary_cta_url': '/intelligent-data-assessment-platform'
            }),
            'faq_json': json.dumps([
                {
                    'q': 'How does AI improve customer and employee experiences without feeling automated?',
                    'a': 'Artha applies AI to deliver contextual, timely, and personalized experiences while preserving human empathy and interaction where it matters most.'
                },
                {
                    'q': 'What role do AI agents play in engagement and experience?',
                    'a': 'AI agents assist users by providing relevant insights, recommendations, and next-best actions while seamlessly escalating to humans when needed.'
                },
                {
                    'q': 'How does AI reduce support costs while improving experience quality?',
                    'a': 'By resolving routine inquiries faster and guiding complex cases intelligently, AI reduces effort and cost without sacrificing experience quality.'
                },
                {
                    'q': 'How do you prevent AI driven experiences from becoming inaccurate or risky?',
                    'a': 'All engagement AI is grounded in governed data, approved knowledge sources, and continuous monitoring to ensure accuracy and compliance.'
                },
                {
                    'q': 'Can AI experiences be personalized without violating data privacy?',
                    'a': 'Yes. Artha designs personalization using consent-based data access, role-based controls, and enterprise governance frameworks.'
                }
            ]),
            'related_services_json': json.dumps([
                {'title': 'AI Data Readiness', 'url': '/artificial-intelligence/data-readiness'},
                {'title': 'Intelligent Solutions', 'url': '/artificial-intelligence/intelligent-solutions'},
                {'title': 'Managed Services', 'url': '/solutions/managed-services'}
            ]),
            'related_case_studies_json': json.dumps([]),
            'seo_title': 'AI for Human Engagement & Experience | Artha Solutions',
            'seo_description': 'Deploy secure AI customer agents, real-time agent assist tools, and automated QA systems. Lift CSAT, reduce handling times, and lower support costs.',
            'seo_keywords': 'conversational ai, agent assist copilot, agentic contact center, auto QA scoring, enterprise search, customer experience ai',
            'canonical_url': 'https://www.thinkartha.com/artificial-intelligence/ai-human-engagement-experience/',
            'ai_summary': 'AI for Human Engagement deploys natural-language self-service agents and desktop coaching tools (Agent Assist) to resolve customer needs quickly and securely.'
        },

        # Subpage 5: Platform Engineering
        {
            'industry': 'artificial-intelligence',
            'page_key': 'ai-platform-engineering',
            'title': 'AI for Platform & Engineering Services',
            'slug': 'artificial-intelligence/ai-platform-engineering-services',
            'url': '/artificial-intelligence/ai-platform-engineering-services',
            'hero_title': 'Foundations that make AI safe to scale',
            'hero_subtitle': 'Data products with owners, lineage, and SLAs; secure access and open architectures; MLOps/LLMOps and AIOps to keep quality, privacy, and uptime on track-so innovation can run.',
            'body_sections_json': json.dumps({
                'pillars': [
                    {'title': 'Data Readiness & Governance', 'desc': 'Maintain metadata catalogs, lineage maps, quality checks, and privacy rules from a single pane.'},
                    {'title': 'Data Products & SLAs', 'desc': 'Turn data into reusable, domain-owned products with clear contracts to cut delivery cycles.'},
                    {'title': 'Connectors, CDC & Federation', 'desc': 'Unify sources using real-time CDC and federated access to curb duplicate storage and egress.'},
                    {'title': 'Lakehouse & Open Tables', 'desc': 'Standardize on open table formats like Iceberg to keep datasets portable across engines.'},
                    {'title': 'Feature Store & Model Registry', 'desc': 'Track versioned models, prompt configurations, and training features to reuse assets safely.'},
                    {'title': 'MLOps & LLMOps pipelines', 'desc': 'Automate delivery, bias checks, drift alerts, and safe model rollback in production.'},
                    {'title': 'Governance & Guardrails', 'desc': 'Deploy PII/prompt injection guardrails and role-based access rules across application layers.'}
                ],
                'audiences': [
                    {
                        'role': 'Platform Engineering',
                        'features': [
                            {'title': 'Data Integration Backbone', 'desc': 'Real-time CDC and connectors across cloud, ERP, and databases to speed up pipeline setup.'},
                            {'title': 'Real-Time Data Fabric', 'desc': 'Event-driven ingestion layers delivering fresh metadata and tables to model contexts.'},
                            {'title': 'Platform Observability', 'desc': 'Monitor pipeline load times, data freshness, and service health to head off downstream issues.'}
                        ]
                    },
                    {
                        'role': 'AI/ML Engineering',
                        'features': [
                            {'title': 'Centralized Feature Stores', 'desc': 'Govern feature datasets across training stages to ensure consistent inference results.'},
                            {'title': 'Drift & Explainability Tools', 'desc': 'Automated dashboards tracking model accuracy, prediction drift, and prompt changes.'},
                            {'title': 'LLMOps Pipeline Automation', 'desc': 'Deploy prompt updates, fine-tuning scripts, and vector indexes with CI/CD rigor.'}
                        ]
                    },
                    {
                        'role': 'FinOps & Cost Control',
                        'features': [
                            {'title': 'Cost Visibility Dashboards', 'desc': 'Trace compute, storage, and API token usage per business case, model, and developer.'},
                            {'title': 'Workload Optimizer', 'desc': 'Auto-recommend instance sizing, vector indexing, and caching configurations to optimize spend.'},
                            {'title': 'Budget Guardrails', 'desc': 'Set strict alert thresholds to prevent runaway GPU and cloud bills.'}
                        ]
                    }
                ]
            }),
            'cta_json': json.dumps({
                'primary_cta_text': 'Set Up AI Platform',
                'primary_cta_url': '/contact-us?interest=platform-engineering',
                'secondary_cta_text': 'Schedule MLOps Consultation',
                'secondary_cta_url': '/contact-us'
            }),
            'faq_json': json.dumps([
                {
                    'q': 'Is Artha locked into a specific cloud or model provider?',
                    'a': 'No. Artha is platform-agnostic. We design and build open architectures that support AWS, Azure, GCP, and private server clusters, using open-source formats like Apache Iceberg.'
                },
                {
                    'q': 'How do you ensure platforms are ready for GenAI and Agentic AI?',
                    'a': 'We configure the vector database indexing, dynamic caching, LLM orchestration frameworks (like LangChain/LlamaIndex), and secure API routing required by autonomous agents.'
                },
                {
                    'q': 'Is this about tools or custom engineering?',
                    'a': 'Artha is a services firm. We build on top of your existing investments (Databricks, Snowflake, Talend, etc.), stitching together components using governed architecture patterns.'
                },
                {
                    'q': 'How do you address AI security and compliance at the platform level?',
                    'a': 'We embed PII filters, query guardrails, encryption at rest and in transit, and role-based access rules directly into your data pipelines and model API endpoints.'
                },
                {
                    'q': 'How does Artha use FinOps to control AI and cloud costs?',
                    'a': 'We design caching strategies, optimize embedding pipelines, and establish scale-to-zero compute rules to keep API and compute bills from spiraling.'
                }
            ]),
            'related_services_json': json.dumps([
                {'title': 'AI Data Readiness', 'url': '/artificial-intelligence/data-readiness'},
                {'title': 'Data Governance', 'url': '/solutions/data-governance'},
                {'title': 'Cloud Services', 'url': '/solutions/cloud'}
            ]),
            'related_case_studies_json': json.dumps([]),
            'seo_title': 'AI for Platform & Engineering Services | Artha Solutions',
            'seo_description': 'Establish MLOps/LLMOps pipelines, build lakehouse solutions using open tables, set up vector databases, and integrate FinOps cost visibility.',
            'seo_keywords': 'ai platform engineering, llmops, mlops, apache iceberg, vector database, finops, api gateway, data fabric',
            'canonical_url': 'https://www.thinkartha.com/artificial-intelligence/ai-platform-engineering-services/',
            'ai_summary': 'AI Platform Engineering services deploy feature registries, model registers, MLOps orchestration, security filters, and FinOps metrics to build safe, scalable AI platforms.'
        },

        # Subpage 6: ROI Solutions
        {
            'industry': 'artificial-intelligence',
            'page_key': 'ai-roi-solutions',
            'title': 'AI ROI Solutions',
            'slug': 'artificial-intelligence/ai-roi-solutions',
            'url': '/artificial-intelligence/ai-roi-solutions',
            'hero_title': 'AI built around your ROI. Not ours.',
            'hero_subtitle': 'It’s not about the models we build. It’s about the value they generate. We partner with you to deploy scalable, outcome-driven solutions with guaranteed payback.',
            'body_sections_json': json.dumps({
                'teaser': 'Most AI budgets are bigger than they need to be. Many consulting firms sell multi-million dollar pilots. We build what you need to start, validate, and scale, ensuring your investments yield real operational metrics.',
                'pillars': [
                    {'title': 'AI SniffGuard', 'desc': 'Prevent prompt injections, toxicity, and outbound PII leaks automatically. Our middleware guardrail ensures your models remain safe, compliant, and focused.'},
                    {'title': 'AI Solutions Frameworks', 'desc': 'Skip starting from scratch. Deploy pre-built framework components to ingest data, trigger agents, and orchestrate approvals rapidly.'},
                    {'title': 'MAAC Framework', 'desc': 'The framework runs on MAAC: Master Agents & App Catalog. A modular library of certified connectors and agent behaviors to slash implementation cycle times.'}
                ],
                'metrics': [
                    {'val': '8–16', 'unit': 'Weeks', 'label': 'Deployment time from first conversation to operational release.'},
                    {'val': '<12', 'unit': 'Months', 'label': 'Payback period where savings or revenue lift exceeds setup costs.'},
                    {'val': '~25%', 'unit': 'Cost', 'label': 'Lower implementation overhead compared to traditional custom engineering builds.'}
                ],
                'steps': [
                    {'step': '01', 'title': 'Discovery', 'desc': 'Identify your high-value use cases, profile data readiness, and baseline current operational costs.'},
                    {'step': '02', 'title': 'Proof of Value', 'desc': 'Build a working prototype in 4 to 6 weeks to validate accuracy and calculate expected cost reductions.'},
                    {'step': '03', 'title': 'Delivery', 'desc': 'Package features, configure security policies, connect live ERP/CRM systems, and release to production.'},
                    {'step': '04', 'title': 'Value', 'desc': 'Conduct ongoing QA, monitor cost drift, measure process savings, and share results with business leaders.'}
                ],
                'philosophy': 'We win when you win. Not before. We offer flexible risk-sharing pricing models linked directly to verified process outcomes and SLA achievements.'
            }),
            'cta_json': json.dumps({
                'primary_cta_text': 'Start Your AI ROI Journey',
                'primary_cta_url': '/contact-us?interest=ai-roi',
                'secondary_cta_text': 'Claim $1 Assessment',
                'secondary_cta_url': '/intelligent-data-assessment-platform'
            }),
            'faq_json': json.dumps([]),
            'related_services_json': json.dumps([]),
            'related_case_studies_json': json.dumps([]),
            'seo_title': 'Measurable AI ROI Solutions for Enterprises | Artha Solutions',
            'seo_description': 'Deploy outcome-linked AI solutions in weeks. Leverage pre-built frameworks like MAAC and SniffGuard to lower implementation costs by 25%.',
            'seo_keywords': 'ai roi, master agents and app catalog, ai sniffguard, cost-effective ai pilot, value-linked ai pricing',
            'canonical_url': 'https://www.thinkartha.com/artificial-intelligence/ai-roi-solutions/',
            'ai_summary': 'AI ROI Solutions deploy value-gated execution plans, pre-built accelerators (MAAC, SniffGuard), and value-linked engagement models to deliver payback in under 12 months.'
        },

        # Campaign Page 1: Future-Ready Data Foundation
        {
            'industry': 'artificial-intelligence',
            'page_key': 'ai-campaign-future-ready',
            'title': 'Future Ready Data Foundation Webcast',
            'slug': 'events/future-ready-data-foundation-from-ai-pilot-to-production-value',
            'url': '/events/future-ready-data-foundation-from-ai-pilot-to-production-value',
            'hero_title': 'Future-Ready Data Foundation: From AI Pilot to Production Value',
            'hero_subtitle': 'Watch the on-demand IDC & Artha Solutions webcast. Learn to build a 90-day data readiness roadmap to scale AI without losing trust.',
            'body_sections_json': json.dumps({
                'webcast_teaser': 'Every organization is investing in AI. But most initiatives stall before production. Not because models fail, but because data isn’t ready. Data sits across systems, defined differently, owned by different teams. The result? AI that looks powerful...but lacks trust, consistency, and scale. Learn how to get your data foundation ready by signing up for this webcast.',
                'speakers': [
                    {
                        'name': 'Stewart Bond',
                        'title': 'Research VP, Data Intelligence & Integration - IDC',
                        'bio': 'Stewart Bond leads IDC\'s research into emerging trends in data movement, ingestion, cleansing, mastering, and active metadata catalogs.'
                    },
                    {
                        'name': 'Srinivas Poddutoori',
                        'title': 'Co-founder and COO - Artha Solutions',
                        'bio': 'Srinivas poddutoori drives global data innovation, structuring MDM, active governance, and responsible AI guardrails for enterprise players.'
                    },
                    {
                        'name': 'Madhav Nalla',
                        'title': 'Enterprise Intelligence Architect - Qlik Partner Ambassador',
                        'bio': 'Madhav works at the intersection of data strategy, digital transformation, and advanced analytics, designing AI-ready data products.'
                    },
                    {
                        'name': 'Sidney Drill',
                        'title': 'Product Marketing Director - Qlik',
                        'bio': 'Sidney is a product marketer at Qlik specializing in integration and analytics, solution design, and data-for-good advocacy.'
                    }
                ],
                'offer_title': 'AI Data Readiness Assessment worth $15999 in just $1',
                'offer_desc': 'Know where to begin-and what to fix first in just $1. A structured assessment that profiles your tables, reviews quality signals, outlines gaps, and delivers an actionable 60-90 day roadmap.'
            }),
            'cta_json': json.dumps({
                'primary_cta_text': 'Watch Webcast & Claim Offer',
                'primary_cta_url': '#register-form'
            }),
            'faq_json': json.dumps([
                {'q': 'What will I gain from watching this webcast?', 'a': 'You will get a clear view of why AI pilots stall, what "AI-ready data" means in practice, and how to scale initiatives. You will also get access to our $1 AI Data Readiness assessment (worth $15,999).'},
                {'q': 'Is this relevant if we already have a data warehouse/platform?', 'a': 'Yes. Most organizations have warehouses but struggle with semantic search, metadata tagging, and LLM governance. This webcast focuses on making existing platforms ready for AI.'},
                {'q': 'How is AI readiness different from basic data quality?', 'a': 'Data quality is only one pillar. Readiness includes data ownership contracts, real-time sync, schema lineage tracing, and active security compliance.'}
            ]),
            'related_services_json': json.dumps([]),
            'related_case_studies_json': json.dumps([]),
            'seo_title': 'Future Ready Data Foundation Webcast | IDC & Artha Solutions',
            'seo_description': 'Access the on-demand webcast featuring IDC Research VP. Learn how to build a future-ready data foundation and move AI pilots to production.',
            'seo_keywords': 'idc webcast artha solutions, future ready data foundation, ai pilot to production, data readiness roadmap',
            'canonical_url': 'https://www.thinkartha.com/events/future-ready-data-foundation-from-ai-pilot-to-production-value/'
        },

        # Campaign Page 2: Intelligent Data Assessment Platform
        {
            'industry': 'artificial-intelligence',
            'page_key': 'ai-campaign-data-assessment',
            'title': 'Intelligent Data Assessment Platform',
            'slug': 'intelligent-data-assessment-platform',
            'url': '/intelligent-data-assessment-platform',
            'hero_title': 'ARTHA INTELLIGENT DATA ASSESSMENT PLATFORM',
            'hero_subtitle': 'Assess your current data, governance, and control maturity before AI risk becomes business risk.',
            'body_sections_json': json.dumps({
                'teaser': 'Organizations deploying AI face mounting regulatory scrutiny (EU AI Act, NIST AI RMF, CCPA/GDPR, DPDPA) but lack purpose-built tools to run auditable, multi-stakeholder governance assessments. Artha is a configurable assessment orchestration platform that enables enterprises to run structured, evidence-gated governance assessments across models and databases with full auditability.',
                'features': [
                    {'title': 'Maturity View', 'desc': 'A structured AI readiness assessment that gives leadership a clear view of current data maturity, control strengths, and gaps that could slow adoption.'},
                    {'title': 'Framework Fit', 'desc': 'A flexible assessment model aligned to DCAM, ISO 42001, NIST AI RMF, or your internal standards so readiness is measured against frameworks that matter.'},
                    {'title': 'Decision Insights', 'desc': 'Evidence-based scoring supported by executive dashboards, risk heatmaps, and gap analyses to help CIOs/CDOs prioritize investments.'},
                    {'title': 'Audit Control', 'desc': 'A regulator-defensible audit trail with role-based workflows that brings accountability across business, data, risk, and compliance teams.'}
                ],
                'offer_title': 'Claim Your Assessment of Data Readiness for AI in $1',
                'offer_desc': 'Get a structured data readiness assessment worth $15,999 for just $1. Our team will audit your governance policies, outline data gaps, and design a 60-90 day production roadmap.'
            }),
            'cta_json': json.dumps({
                'primary_cta_text': 'Claim $1 Assessment',
                'primary_cta_url': '#assessment-form'
            }),
            'faq_json': json.dumps([
                {'q': 'What is the AI Data Readiness Assessment?', 'a': 'It is a structured evaluation of your data maturity, cataloging, lineage, and access controls against leading AI frameworks like NIST AI RMF, ISO 42001, and DCAM.'},
                {'q': 'How is this different from a survey?', 'a': 'This is an evidence-gated, workflow-based assessment. You upload logs, schema samples, and policy files, which are validated by certified architects to issue a score.'},
                {'q': 'Who should be involved from my organization?', 'a': 'Typically sponsored by the CIO or CDO, with participation from data governance teams, security managers, and business process owners.'}
            ]),
            'related_services_json': json.dumps([]),
            'related_case_studies_json': json.dumps([]),
            'seo_title': 'Intelligent Data Assessment Platform | Artha Solutions',
            'seo_description': 'Run structured, evidence-gated governance assessments across AI models and databases. Ensure compliance with EU AI Act, NIST AI RMF, and ISO 42001.',
            'seo_keywords': 'intelligent data assessment platform, eu ai act compliance, nist ai rmf audit, dcam assessment, iso 42001 compliance',
            'canonical_url': 'https://www.thinkartha.com/intelligent-data-assessment-platform/'
        }
    ]

    for page in pages:
        # Check if url already exists
        cursor.execute("SELECT id FROM industry_microsite_pages WHERE page_key = ?", (page['page_key'],))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("""
                UPDATE industry_microsite_pages 
                SET industry = ?, title = ?, slug = ?, url = ?, hero_title = ?, hero_subtitle = ?, 
                    body_sections_json = ?, cta_json = ?, faq_json = ?, related_services_json = ?, 
                    related_case_studies_json = ?, seo_title = ?, seo_description = ?, seo_keywords = ?, 
                    canonical_url = ?, og_title = ?, og_description = ?, og_image = ?, schema_json = ?, 
                    ai_summary = ?, genai_entities_json = ?, updated_at = ?
                WHERE page_key = ?
            """, (
                page['industry'], page['title'], page['slug'], page['url'], page['hero_title'], page['hero_subtitle'],
                page['body_sections_json'], page['cta_json'], page['faq_json'], page['related_services_json'],
                page.get('related_case_studies_json', '[]'), page['seo_title'], page['seo_description'], 
                page.get('seo_keywords', ''), page['canonical_url'], page.get('og_title', page['seo_title']),
                page.get('og_description', page['seo_description']), page.get('og_image', ''), 
                page.get('schema_json', ''), page.get('ai_summary', ''), page.get('genai_entities_json', '[]'),
                now, page['page_key']
            ))
        else:
            cursor.execute("""
                INSERT INTO industry_microsite_pages (
                    industry, page_key, title, slug, url, hero_title, hero_subtitle, 
                    body_sections_json, cta_json, faq_json, related_services_json, 
                    related_case_studies_json, seo_title, seo_description, seo_keywords, 
                    canonical_url, og_title, og_description, og_image, schema_json, 
                    ai_summary, genai_entities_json, status, noindex, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Published', 0, ?, ?)
            """, (
                page['industry'], page['page_key'], page['title'], page['slug'], page['url'], page['hero_title'], page['hero_subtitle'],
                page['body_sections_json'], page['cta_json'], page['faq_json'], page['related_services_json'],
                page.get('related_case_studies_json', '[]'), page['seo_title'], page['seo_description'], 
                page.get('seo_keywords', ''), page['canonical_url'], page.get('og_title', page['seo_title']),
                page.get('og_description', page['seo_description']), page.get('og_image', ''), 
                page.get('schema_json', ''), page.get('ai_summary', ''), page.get('genai_entities_json', '[]'),
                now, now
            ))
            
    conn.commit()
    conn.close()
    print("AI pages seeded successfully.")

if __name__ == '__main__':
    seed_data()
