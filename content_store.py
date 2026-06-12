# ThinkArtha Website Content Store - Static Data Registry

SOLUTIONS_DATA = {
    'data-strategy': {
        'title': 'Data Strategy Consulting',
        'tagline': 'Chart a clear, actionable path from raw data to business success.',
        'icon': 'chess',
        'description': 'In today\'s digital era, having a robust data strategy is no longer optional. Artha Solutions works with small businesses to Fortune 500 enterprises to evaluate legacy infrastructure, identify data gaps, and design blueprints for modern AI adoption.',
        'features': [
            {'title': 'Maturity Assessments', 'desc': 'A comprehensive 2-4 week audit of your data maturity, cataloging assets, and defining clear improvement paths.'},
            {'title': 'Technology Selection', 'desc': 'Unbiased advisory on selecting the right cloud, warehousing, and ETL engines (Snowflake, Databricks, Talend, Qlik).'},
            {'title': 'Business Alignment', 'desc': 'Bridging the gap between corporate goals and engineering pipelines to guarantee high ROI on data investments.'}
        ],
        'stats': [{'val': '40%', 'label': 'Implementation Speedup'}, {'val': '2-4 Wk', 'label': 'Initial Assessment'}],
        'case_study': {'title': 'Financial Operations Strategy', 'desc': 'Artha helped a global banking corporation structure their data modernization blueprint, reducing metadata search times by 40%.', 'slug': 'metadata-driven-etl-framework'}
    },
    'master-data-management': {
        'title': 'Master Data Management (MDM)',
        'tagline': 'Establish a single, governed golden record across your enterprise.',
        'icon': 'sitemap',
        'description': 'Eliminate siloed information, duplicate accounts, and inconsistent naming conventions. Our MDM solutions bridge CRM, ERP, and operations data to build a complete 360-degree view of your business.',
        'features': [
            {'title': 'Golden Record Creation', 'desc': 'Define customized matching and merging rules to create a singular, trusted profile for customers and products.'},
            {'title': 'MDM Lite Accelerator', 'desc': 'Our proprietary lightweight framework to get MDM running in under 45 days, saving up to 40% in implementation costs.'},
            {'title': 'Identity Resolution', 'desc': 'Real-time matching algorithms to connect data points dynamically across systems.'}
        ],
        'stats': [{'val': '40%', 'label': 'Reduction in Setup Cost'}, {'val': '65%', 'label': 'Deduplication Accuracy'}],
        'case_study': {'title': 'Fastest MDM Rollout', 'desc': 'Carhartt Inc. partnered with Artha for an automated MDM deployment, unifying customer records and accelerating supply chains.', 'slug': 'rapid-talend-mdm-deployment'}
    },
    'enterprise-data-management': {
        'title': 'Enterprise Data Management',
        'tagline': 'Scale and secure your databases throughout their lifecycle.',
        'icon': 'boxes-packing',
        'description': 'Manage growing volumes of data without sacrificing performance. We help you design data lakes, structure indexes, migrate files, and automate archives while maintaining security standards.',
        'features': [
            {'title': 'Data Lifecycle Management', 'desc': 'Automate data storage policies to transition cold files to cheap storage, minimizing costs.'},
            {'title': 'Database Optimization', 'desc': 'Tuning indices, queries, and replication structures for real-time applications.'},
            {'title': 'Platform Migrations', 'desc': 'Seamless transitions between database architectures with zero downtime and strict data security.'}
        ],
        'stats': [{'val': '300+', 'label': 'Projects Delivered'}, {'val': '24/7', 'label': 'Support Exposure'}],
        'case_study': {'title': 'Healthcare Platform Migration', 'desc': 'Migrated legacy patient systems for a health distributor, automating data verification checks for 90% accuracy.', 'slug': 'healthcare-member-provider-data-platform'}
    },
    'data-governance': {
        'title': 'Data Governance & Compliance',
        'tagline': 'Ensure data is trustworthy, compliant, and easy to find.',
        'icon': 'gavel',
        'description': 'Establish active stewardship and metadata management. Our governance frameworks automate cataloging, ensure data lineage visibility, and implement privacy compliance for GDPR, HIPAA, and CCPA.',
        'features': [
            {'title': 'Active Cataloging', 'desc': 'Discover, index, and organize data assets across multi-cloud environments automatically.'},
            {'title': 'Lineage Tracking', 'desc': 'Visual maps of how data flows from source ingestion to final dashboard reports.'},
            {'title': 'Privacy & Consent', 'desc': 'Enforce data masking, role-based access, and compliance checks dynamically.'}
        ],
        'stats': [{'val': '40%', 'label': 'Search Time Reduction'}, {'val': '100%', 'label': 'Compliance Audit Readiness'}],
        'case_study': {'title': 'Adira Financial Governance', 'desc': 'Enhanced governance and metadata search for Adira, reducing compliance audit preparation times by 65%.', 'slug': 'enterprise-data-governance-mdm'}
    },
    'bigdata': {
        'title': 'Big Data Analytics',
        'tagline': 'Process petabyte-scale data lakes with speed and agility.',
        'icon': 'database',
        'description': 'Unlock the value of unstructured and semi-structured logs. We deploy Big Data platforms using Databricks, Snowflake, and Spark to handle complex processing pipelines at scale.',
        'features': [
            {'title': 'Data Lakes & Meshes', 'desc': 'Architect modern data lakes to store raw events, logs, and transactional records in open formats.'},
            {'title': 'Distributed Engine Tuning', 'desc': 'Optimize Spark, Hadoop, and SQL warehouses to execute queries in seconds, not hours.'},
            {'title': 'Real-time Log Ingestion', 'desc': 'Stream millions of events per second with schema validation and error-quarantine queues.'}
        ],
        'stats': [{'val': '3×', 'label': 'Faster Query Speeds'}, {'val': '26', 'label': 'Countries Served'}],
        'case_study': {'title': 'Telecom Scale Ingestion', 'desc': 'Implemented a distributed ingestion pipeline for a telecom provider to process millions of diagnostic events in real-time.', 'slug': 'enterprise-big-data-integration'}
    },
    'data-quality': {
        'title': 'Data Quality Management',
        'tagline': 'Clean, consistent, and well-governed data for business success.',
        'icon': 'shield-heart',
        'description': 'Poor data quality leads to poor business decisions. We design automated validation checks, syntax corrections, and active profiling structures to keep your analytics engines reliable.',
        'features': [
            {'title': 'Automated Profiling', 'desc': 'Scan landing zones for anomalies, out-of-range parameters, or missing values immediately.'},
            {'title': 'Cleansing Rules', 'desc': 'Implement standardized transformations for addresses, dates, and account tags.'},
            {'title': 'Data Reconciliation', 'desc': 'Active verification scripts to cross-reference data integrity across sources.'}
        ],
        'stats': [{'val': '80%', 'label': 'Data Reliability'}, {'val': '85%', 'label': 'Validation Accuracy'}],
        'case_study': {'title': 'Automated Quality Checking', 'desc': 'Partnered with a retail bank to automate metadata checks, boosting data validation accuracy to 85%.', 'slug': 'automated-data-quality-audits-talend'}
    },
    'data-science-analytics': {
        'title': 'Data Science & Analytics',
        'tagline': 'Predict trends, optimize operations, and discover hidden insights.',
        'icon': 'chart-line',
        'description': 'Move from historical reporting to predictive intelligence. We build custom machine learning models, forecasting engines, and executive dashboards to drive business strategies.',
        'features': [
            {'title': 'Predictive Modeling', 'desc': 'Custom forecasting models for sales demand, staff scheduling, and customer churn.'},
            {'title': 'Business Intelligence', 'desc': 'Responsive dashboards utilizing Qlik, Tableau, and PowerBI for real-time visibility.'},
            {'title': 'Feature Engineering', 'desc': 'Clean and transform raw data signals into highly predictive input matrices for ML pipelines.'}
        ],
        'stats': [{'val': '3×', 'label': 'Faster Decision Speeds'}, {'val': '75%', 'label': 'Error Rate Reduction'}],
        'case_study': {'title': 'Staffing Demand Prediction', 'desc': 'Developed an AI staffing forecast engine for a healthcare distributor, matching employee schedules with patient spikes.', 'slug': 'healthcare-resource-predictive-forecasting'}
    },
    'servicenow-2': {
        'title': 'ServiceNow Services',
        'tagline': 'Automate IT workflows and streamline employee service delivery.',
        'icon': 'server',
        'description': 'Deliver modern IT and employee experiences. We help you design, configure, and integrate ServiceNow modules to unify workflows, automate ticket routing, and reduce support overheads.',
        'features': [
            {'title': 'IT Service Management (ITSM)', 'desc': 'Optimize incident, problem, change, and asset management in a single platform.'},
            {'title': 'IT Operations Management (ITOM)', 'desc': 'Automate infrastructure discovery, map dependencies, and predict service outages.'},
            {'title': 'Custom Integration Hub', 'desc': 'Connect ServiceNow with CRMs, ERPs, and database platforms seamlessly.'}
        ],
        'stats': [{'val': '80%', 'label': 'Steps Automated'}, {'val': '24/7', 'label': 'Support Coverage'}],
        'case_study': {'title': 'Workplace Workflow Automation', 'desc': 'Automated IT ticketing routing for a global manufacturing firm, slashing ticket resolution times by 40%.', 'slug': 'premises-to-cloud-it-transition'}
    },
    'oracle-services': {
        'title': 'Oracle Services & Consulting',
        'tagline': 'Optimize your enterprise resource planning and database applications.',
        'icon': 'database',
        'description': 'Unlock the potential of your Oracle database engines and cloud business applications. We provide database administration, performance tuning, architecture migration, and managed services.',
        'features': [
            {'title': 'Database Administration', 'desc': '24/7 DBA support, backup management, patching, replication, and query optimization.'},
            {'title': 'Oracle Cloud Migration', 'desc': 'Assess and transition legacy Oracle databases to the OCI (Oracle Cloud Infrastructure).'},
            {'title': 'ERP Application Support', 'desc': 'Managed functional support for Oracle E-Business Suite and cloud applications.'}
        ],
        'stats': [{'val': '300+', 'label': 'Expert Engineers'}, {'val': '26', 'label': 'Countries Served'}],
        'case_study': {'title': 'Global ERP Synchronization', 'desc': 'Managed database replication and query tuning for a global retail network, stabilizing order processing.', 'slug': 'ecommerce-gateway-integration'}
    },
    'sap': {
        'title': 'Artha Advantage for SAP',
        'tagline': 'Comprehensive S/4HANA migrations with minimal downtime.',
        'icon': 'gear',
        'description': 'Migrating to S/4HANA doesn\'t have to be complex. We automate data conversion mapping, validate database schemas, and reconcile data integrity to accelerate your SAP modernizations.',
        'features': [
            {'title': 'Data Migration Automation', 'desc': 'Standardized convert routines to migrate legacy ERP files to S/4HANA structures.'},
            {'title': 'Data Integrity Checks', 'desc': 'Automate reconciliation during landing, ensuring zero transaction loss.'},
            {'title': 'Pre-Migration Profiling', 'desc': 'Clean and purge redundant client database records before migration to save memory.'}
        ],
        'stats': [{'val': '90%', 'label': 'Automated Mapping'}, {'val': '70%', 'label': 'Faster Timelines'}],
        'case_study': {'title': 'Commonwealth Care SAP Upgrade', 'desc': 'Assisted in validating data integrity for an ERP upgrade, recognized with Talend\'s Data Masters award.', 'slug': 'sap-s4hana-cloud-migration-talend'}
    },
    'cloud': {
        'title': 'Cloud Services & Consulting',
        'tagline': 'One-stop shop for all your cloud architecture and migration needs.',
        'icon': 'cloud',
        'description': 'Empower your business with scalable, secure cloud environments. We provide consulting and managed support for AWS, Azure, and multi-cloud strategies, minimizing operating overheads.',
        'features': [
            {'title': 'Cloud Architecture Design', 'desc': 'Establish secure VPCs, identity controls, and load balancing configurations.'},
            {'title': 'Migration & Modernization', 'desc': 'Lift and shift legacy servers or refactor applications into cloud-native microservices.'},
            {'title': 'Cost Optimization (FinOps)', 'desc': 'Monitor cloud resources to scale down idle nodes, slashing monthly cloud invoices.'}
        ],
        'stats': [{'val': '40%', 'label': 'Overhead Cost Savings'}, {'val': '24/7', 'label': 'Active Monitoring'}],
        'case_study': {'title': 'Cloud Migration Challenges Solved', 'desc': 'Helped a health services provider transition local server logs to Azure, structuring secure and HIPAA-compliant partitions.', 'slug': 'premises-to-cloud-it-transition'}
    },
    'managed-services': {
        'title': 'Managed IT & Data Services',
        'tagline': 'Strategic approach guaranteeing smooth operations around the clock.',
        'icon': 'headset',
        'description': 'Focus on your business while our team manages the tech. With over 300 certified engineers globally, we provide 24/7 monitoring, database administration, cloud ops, and application support.',
        'features': [
            {'title': '24/7 Operations Monitoring', 'desc': 'Network operations center tracking server health, logs, and security alerts in real-time.'},
            {'title': 'Database & ETL Support', 'desc': 'Manage pipelines, schedules, patches, and errors across Talend, Qlik, and SQL engines.'},
            {'title': 'Service Level Agreements (SLAs)', 'desc': 'Guaranteed response times, incident escalation channels, and transparent reporting.'}
        ],
        'stats': [{'val': '300+', 'label': 'Expert Engineers'}, {'val': '12+ Yrs', 'label': 'Partnership Legacy'}],
        'case_study': {'title': 'Health Alliance Support', 'desc': 'Partnered with Commonwealth Care Alliance to deliver ongoing 24/7 support for data pipelines and reporting engines.', 'slug': 'managed-services-operations-optimization'}
    }
}

INDUSTRIES_DATA = {
    'bfsi': {
        'title': 'BFSI (Banking & Financial Services)',
        'tagline': 'Secure, compliant, and data-driven financial operations.',
        'description': 'In today\'s highly regulated banking landscape, managing fragmented data silos is critical. Artha Solutions builds secure compliance pipelines, real-time fraud monitoring, and automated deduplication systems.',
        'stats': [{'val': '80%', 'label': 'Data Reliability'}, {'val': '75%', 'label': 'Stewardship Speedup'}, {'val': '85%', 'label': 'Validation Accuracy'}],
        'demands': [
            {'title': 'Personalized Banking', 'desc': 'Deliver targeted recommendations using real-time user behavior logs.'},
            {'title': 'Regulatory Compliance', 'desc': 'Automate tracking for financial audits, GDPR, and anti-money laundering regulations.'},
            {'title': 'Fraud Prevention', 'desc': 'Identify transaction anomalies in real-time with machine learning models.'}
        ],
        'case_study': {'title': 'Deduplication in Retail Banking', 'desc': 'Helped a bank deploy an ML deduplication engine on consumer accounts, reducing profile duplicates by 65%.', 'slug': 'real-time-customer-matching-fraud-prevention'}
    },
    'healthcare': {
        'title': 'Healthcare & Life Sciences',
        'tagline': 'Unified records and analytics for better patient outcomes.',
        'description': 'Patient records must be accurate, secure, and accessible. We assist hospital networks and life science distributors in modernizing data lakes, deduplicating patient profiles, and predicting demand.',
        'stats': [{'val': '40%', 'label': 'AI Adoption Speedup'}, {'val': '100%', 'label': 'HIPAA Compliance'}],
        'demands': [
            {'title': 'Patient Profile Deduplication', 'desc': 'Clean duplicate records using custom matching rules to prevent medical errors.'},
            {'title': 'Supply Chain Optimization', 'desc': 'Forecasting medical supply requirements with predictive analytics.'},
            {'title': 'Regulatory Guardrails', 'desc': 'Establish secure, governed data partitions ensuring strict HIPAA audit trails.'}
        ],
        'case_study': {'title': 'Patient Deduplication in Care', 'desc': 'Implemented an AI deduplication algorithm for diabetes care profiles, enhancing record validation.', 'slug': 'ml-deduplication-patient-identity-resolution'}
    },
    'retail': {
        'title': 'Retail & E-Commerce',
        'tagline': 'Real-time retail data optimization for lasting success.',
        'description': 'Deliver the personalized experience today\'s consumers expect. We help retailers unify customer touchpoints, process real-time transaction streaming, and optimize logistics.',
        'stats': [{'val': '40%', 'label': 'Implementation Speedup'}, {'val': '300+', 'label': 'Global Projects'}],
        'demands': [
            {'title': 'Omnichannel Integration', 'desc': 'Unify logs from brick-and-mortar sales, web shopping carts, and loyalty apps.'},
            {'title': 'Streaming Analytics', 'desc': 'Track and process checkout transactions in real-time to adjust pricing dynamically.'},
            {'title': 'Supply Chain Visibility', 'desc': 'Optimize store inventories using automated warehouse stock reports.'}
        ],
        'case_study': {'title': 'Streaming Data Processing', 'desc': 'Introduced real-time transaction streaming for a sportswear brand, providing store managers with instant sales metrics.', 'slug': 'ecommerce-gateway-integration'}
    },
    'manufacturing': {
        'title': 'Manufacturing',
        'tagline': 'Boost industrial efficiency and supply chain visibility.',
        'description': 'Optimize production lines and stabilize component sourcing. We deploy big data analytics, automated reporting, and predictive maintenance engines to minimize factory downtime.',
        'stats': [{'val': '80%', 'label': 'Mapping Efficiency'}, {'val': '24/7', 'label': 'Operational Monitoring'}],
        'demands': [
            {'title': 'Predictive Maintenance', 'desc': 'Process sensor feeds to flag machinery anomalies before failures occur.'},
            {'title': 'Supply Chain Tracking', 'desc': 'Unify component tracking from supplier shipping docks to final assembly lines.'},
            {'title': 'Operational Dashboards', 'desc': 'Provide floor supervisors with real-time analytics on production cycle times.'}
        ],
        'case_study': {'title': 'Factory Logistics Modernization', 'desc': 'Helped a heavy manufacturing firm unify local supplier inventory databases, boosting tracking speed.', 'slug': 'real-time-logistics-analytics-etl'}
    },
    'utilities': {
        'title': 'Utilities & Telecom',
        'tagline': 'Streamline data governance for reliable operations.',
        'description': 'Ensure uptime and track network infrastructure. We deploy metadata catalogs, data security guardrails, and real-time streaming analytics to monitor energy grids and telecom grids.',
        'stats': [{'val': '40%', 'label': 'Search Time Reduction'}, {'val': '3×', 'label': 'Query Speeds'}],
        'demands': [
            {'title': 'Grid & Network Monitoring', 'desc': 'Process millions of sensor events per second to isolate failures.'},
            {'title': 'Compliance Governance', 'desc': 'Ensure adherence to government utility operations policies.'},
            {'title': 'Customer Support Copilots', 'desc': 'Deploy conversational assistants to handle outages reporting.'}
        ],
        'case_study': {'title': 'Grid Sensor Log Processing', 'desc': 'Built a Spark-driven log processing pipeline for an electrical utility, accelerating diagnostic analytics.', 'slug': 'premises-to-cloud-it-transition'}
    },
    'hospitality': {
        'title': 'Hospitality & Travel',
        'tagline': 'Data-driven insights for guest loyalty and operational success.',
        'description': 'Build personalized guest relationships. We help hotels, airlines, and travel agencies aggregate loyalty points, booking histories, and survey reviews into unified guest profiles.',
        'stats': [{'val': '40%', 'label': 'Implementation Speedup'}, {'val': '26', 'label': 'Countries Exposed'}],
        'demands': [
            {'title': 'Guest Profile Consolidation', 'desc': 'Merge booking engine databases with customer loyalty profiles.'},
            {'title': 'Dynamic Pricing Analytics', 'desc': 'Predict room demand trends to maximize booking revenues.'},
            {'title': 'Feedback Sentiment Analysis', 'desc': 'Scan reviews and surveys automatically to resolve issues.'}
        ],
        'case_study': {'title': 'Hotel Customer 360 Rollout', 'desc': 'Unified guest profile databases across a luxury resort brand, feeding CRM platforms with direct preferences.', 'slug': 'consolidating-guest-data-personalized-experiences'}
    },
    'telecom': {
        'title': 'Telecommunications',
        'tagline': 'Data insights for telecom network optimization and billing accuracy.',
        'description': 'Manage high volumes of call, message, and diagnostic logs. We deploy Big Data platforms to optimize network bandwidth allocation and resolve billing discrepancies.',
        'stats': [{'val': '3×', 'label': 'Faster Query Speeds'}, {'val': '24/7', 'label': 'NOC Managed Support'}],
        'demands': [
            {'title': 'Bandwidth Optimization', 'desc': 'Analyze cellular tower event traffic to dynamically routing bandwidth.'},
            {'title': 'Billing Reconciliation', 'desc': 'Automate order-to-billing validation checks to isolate errors.'},
            {'title': 'Churn Prediction', 'desc': 'Identify customer accounts showing declining call patterns to target promotions.'}
        ],
        'case_study': {'title': 'Cellular Log Ingestion', 'desc': 'Implemented a metadata-driven ingestion framework for a mobile carrier, processing billions of log events daily.', 'slug': 'data-management-platform-mdm-bigdata'}
    }
}

PARTNERS_DATA = {
    'talend': {
        'title': 'Qlik Talend Partner',
        'tagline': 'Premier Global Platinum Partner of Talend.',
        'icon': 'cube',
        'description': 'With over 12 years of partnership, Artha Solutions is a recognized Talend Partner of the Year. We assist enterprises in modernizing data pipelines, automating ETL migrations, and implementing data quality controls.',
        'highlights': [
            'Recognized Partner of the Year 6 times in a row since 2018',
            'Over 100+ certified Talend engineers globally',
            'Creators of B’etl™: the automated ETL tool migration accelerator'
        ]
    },
    'qlik': {
        'title': 'Qlik Active Intelligence Partner',
        'tagline': 'Transforming raw data into Active, Real-time Intelligence.',
        'icon': 'bolt',
        'description': 'We collaborate with Qlik to design active intelligence environments. Integrate real-time data streaming, dynamic BI visualizations, and custom analytics alerts to make smart business decisions.',
        'highlights': [
            'Qlik Best Enabled Partner of the Year 2023',
            'APAC Reseller of the Year award winner',
            'Expertise in Qlik Sense dashboards and real-time CDC (Change Data Capture) setups'
        ]
    },
    'aws-cloud-services': {
        'title': 'AWS Cloud Services',
        'tagline': 'Scalable, secure, and cost-effective Amazon Cloud solutions.',
        'icon': 'aws',
        'icon_type': 'fab',
        'description': 'We help you harness the full capacity of AWS. From launching secure VPCs, database setups on RDS/Redshift, to managing serverless lambda configurations, we build scalable architectures.',
        'highlights': [
            'Specialists in Amazon Redshift and EMR tuning',
            'FinOps auditing to slash idle compute nodes and storage',
            'Secure AWS IAM permissions architectures'
        ]
    },
    'azure-cloud-services': {
        'title': 'Microsoft Azure Solution Partner',
        'tagline': 'Solution Partner for Data and AI workloads on Azure.',
        'icon': 'microsoft',
        'icon_type': 'fab',
        'description': 'Leverage Microsoft Azure for enterprise analytics. We design and manage Azure Synapse, Data Factory, and cognitive AI setups, aligning with Microsoft enterprise agreements.',
        'highlights': [
            'Azure Solution Partner certification for Data & AI',
            'Enterprise architecture alignment using Azure Synapse pipelines',
            'Secure HIPAA-compliant configurations in Azure GovCloud'
        ]
    },
    'alation': {
        'title': 'Alation Data Catalog Partner',
        'tagline': 'Discover, understand, and govern enterprise data assets.',
        'icon': 'book-open',
        'description': 'Empower your teams to find the data they need. We help implement Alation data catalogs to organize database metadata, record data lineages, and document data vocabularies.',
        'highlights': [
            'Design active metadata harvesting configurations',
            'Establish user friendly data glossaries for business teams',
            'Integration of catalog systems directly with data governance policies'
        ]
    },
    'data-sentinel': {
        'title': 'Data Sentinel Privacy Partner',
        'tagline': 'Simplifying data privacy compliance across the enterprise.',
        'icon': 'lock',
        'description': 'Automate data privacy governance. We partner with Data Sentinel to implement continuous data mapping, detect personal identifiable information (PII), and trace privacy leakage.',
        'highlights': [
            'Real-time PII and PHI discovery audits',
            'Automated compliance reporting for GDPR, CCPA, and HIPAA',
            'Integrates privacy safeguards directly into cloud loading docks'
        ]
    },
    'snowflake': {
        'title': 'Snowflake Data Cloud Partner',
        'tagline': 'Experience the power of a modern cloud data warehouse.',
        'icon': 'snowflake',
        'description': 'Unify your data storage on Snowflake. We help architect multi-cluster SQL warehouses, configure secure data shares, and set up dynamic compute structures to optimize analytic processing.',
        'highlights': [
            'Snowflake data pipeline optimization using Snowpipe',
            'Secure, governed zero-copy data sharing configurations',
            'Performance tuning for large scale concurrent query workloads'
        ]
    },
    'databricks': {
        'title': 'Databricks Lakehouse Partner',
        'tagline': 'Unlocking the power of Data and AI with Databricks.',
        'icon': 'fire-alt',
        'description': 'Unify data engineering, data science, and analytics on a single Lakehouse platform. We design Databricks Delta Lake architectures to execute Spark workloads and run machine learning models.',
        'highlights': [
            'Delta Lake storage optimization and data engineering',
            'MLflow configuration for machine learning model registries',
            'Integrating Databricks with BI engines like Qlik and Tableau'
        ]
    },
    'amurta-data-insights-platform': {
        'title': 'Amurta Data Insights Platform',
        'tagline': 'Establish end-to-end lineage and business dictionary controls.',
        'icon': 'database',
        'description': 'We partner with Amurta to implement their Data Insights Platform (DIP). DIP provides active data cataloging, business metadata mapping, and executive dashboard metrics tracking.',
        'highlights': [
            'Automate metadata harvesting across diverse database platforms',
            'Define custom KPI metrics formulas for standard financial audits',
            'Interactive dashboard widgets supporting real-time alerts'
        ]
    }
}

ADVANTAGE_DATA = {
    'accelerators-1': {
        'title': 'B2B Integration Accelerators',
        'tagline': 'Pre-built mapping libraries and schemas to cut development time by 40%.',
        'icon': 'rocket',
        'description': 'Artha Solutions provides pre-built accelerators for common integration endpoints, including ERP, CRM, and supply chain APIs. These assets skip manual mapping phases and bring immediate compatibility.',
        'features': [
            {'title': 'Standardized Schemas', 'desc': 'Pre-mapped JSON and XML definitions for SAP, Salesforce, ServiceNow, and Qlik Talend.'},
            {'title': 'Error Handling Templates', 'desc': 'Pre-configured validation loops and quarantine structures for instant deployment.'},
            {'title': 'API Gateway Configurations', 'desc': 'Secure proxy rules, rate-limiting frameworks, and OAuth handlers.'}
        ],
        'stats': [{'val': '40%', 'label': 'Implementation Speedup'}, {'val': '100+', 'label': 'Pre-built Templates'}]
    },
    'data-insights-platform': {
        'title': 'Data Insights Platform (DIP)',
        'tagline': 'A unified ecosystem connecting ETL, database, and business intelligence.',
        'icon': 'chart-pie',
        'description': 'DIP acts as the single entry point for all organizational reporting and pipeline monitoring, offering centralized data catalogs, lineage tracing, and interactive executive charts.',
        'features': [
            {'title': 'Centralized KPI Catalog', 'desc': 'A standard data dictionary defining all business formulas and dashboard metrics.'},
            {'title': 'Interactive Executive Dashboards', 'desc': 'High-performance Qlik-powered views displaying financial and operating performance.'},
            {'title': 'Pipeline Health Monitoring', 'desc': 'Real-time alert systems tracking database uptime, memory spikes, and sync delays.'}
        ],
        'stats': [{'val': '3×', 'label': 'Faster Report Loading'}, {'val': '100%', 'label': 'Lineage Visibility'}]
    },
    'mdm-lite': {
        'title': 'MDM Lite Framework',
        'tagline': 'A lightweight, rapid-deployment approach to master data management.',
        'icon': 'bolt',
        'description': 'MDM Lite is our proprietary framework that enables SMEs and enterprise subdivisions to deploy a singular customer, product, or supplier golden record in under 45 days, saving significant initial license costs.',
        'features': [
            {'title': 'Rapid Identity Matching', 'desc': 'De-duplicate customer profiles using lightweight SQL heuristics and scoring models.'},
            {'title': 'Flexible Schema Support', 'desc': 'Extend database records dynamically to include custom attribute mappings.'},
            {'title': 'Fast Data Stewardship Portal', 'desc': 'Easy-to-use review grids for data owners to approve or reject profile merges.'}
        ],
        'stats': [{'val': '45 Days', 'label': 'Deployment Speed'}, {'val': '40%', 'label': 'Lower Setup Expenses'}]
    },
    'customer-360': {
        'title': 'Customer 360 Solutions',
        'tagline': 'Unify customer touchpoints across all transactional and operations platforms.',
        'icon': 'user-gear',
        'description': 'Customer 360 links records from Salesforce, SAP ERP, Zendesk, and billing databases to establish a singular, verified customer profile. This enables real-time personalization and precise support.',
        'features': [
            {'title': 'Multi-System Integration', 'desc': 'Synchronize billing transaction logs with CRM customer service profiles.'},
            {'title': 'Activity Stream Consolidation', 'desc': 'Compile purchases, support cases, and web portal visits into a chronological timeline.'},
            {'title': 'Predictive Churn Scoring', 'desc': 'Feed unified data profiles into AI models to identify retention risks early.'}
        ],
        'stats': [{'val': '65%', 'label': 'Profile Accuracy Boost'}, {'val': '25%', 'label': 'Support Call Speedup'}]
    },
    'dynamic-ingestion-framework': {
        'title': 'Dynamic Ingestion Framework (DIF)',
        'tagline': 'Streamline multi-source data loading with automated schema harvesting.',
        'icon': 'network-wired',
        'description': 'DIF is an ingestion pipeline accelerator designed to automate database synchronization, schema conversions, and file loading from hundreds of local servers to a central cloud data lake.',
        'features': [
            {'title': 'Automated Schema Harvesting', 'desc': 'Detect source database table structure changes and update cloud tables automatically.'},
            {'title': 'CDC Ingestion Integration', 'desc': 'Capture and load transaction edits instantly with zero database query stress.'},
            {'title': 'Error Recovery Queues', 'desc': 'Quarantine corrupt data records automatically while keeping main loaders active.'}
        ],
        'stats': [{'val': '80%', 'label': 'Manual Ingestion Reduction'}, {'val': 'Real-Time', 'label': 'Ingestion Latency'}]
    },
    'technology-and-data-migration': {
        'title': 'Technology & Data Migration Services',
        'tagline': 'Seamless, zero-downtime database and system transitions.',
        'icon': 'truck-ramp-box',
        'description': 'Artha Solutions manages complex database migrations, transitioning legacy mainframes and databases into modern cloud warehouses (like Snowflake or AWS Redshift) with full validation.',
        'features': [
            {'title': 'Pre-Migration Profiling', 'desc': 'Identify and isolate duplicate, corrupted, or cold archive records before migrating.'},
            {'title': 'Conversion Mapping Automation', 'desc': 'Translate database schemas, stored procedures, and tables into modern SQL.'},
            {'title': 'Data Reconciliation Audits', 'desc': 'Validate transaction totals at destination to verify 100% data integrity.'}
        ],
        'stats': [{'val': '70%', 'label': 'Migration Timeline Reduction'}, {'val': 'Zero', 'label': 'Business Interruption'}]
    },
    'digital-transformations': {
        'title': 'Digital Transformation Strategy',
        'tagline': 'Re-engineer operating models and tech stacks for scalable growth.',
        'icon': 'arrows-spin',
        'description': 'We help enterprises modernize operational software, transition legacy IT to agile architectures, and build automated reporting systems that empower executive decision makers.',
        'features': [
            {'title': 'Workplace Automation audits', 'desc': 'Analyze employee operations logs to replace manual tasks with API automation.'},
            {'title': 'Architecture Modernization', 'desc': 'Refactor legacy code bases into scalable microservices and Docker modules.'},
            {'title': 'Enterprise Capability Scaling', 'desc': 'Provide certified developers and engineers to execute large transformation programs.'}
        ],
        'stats': [{'val': '300+', 'label': 'Enterprise Programs'}, {'val': '24/7', 'label': 'Managed Operations'}]
    },
    'digital-strategy': {
        'title': 'Digital Strategy & Advisory',
        'tagline': 'Align technical investments with corporate growth objectives.',
        'icon': 'chess-knight',
        'description': 'Leverage our consulting architects to audit current system bottlenecks, evaluate vendor platforms, and design a multi-year modernization blueprint with clear ROI metrics.',
        'features': [
            {'title': 'Tech Stack Auditing', 'desc': 'Identify license overlaps and database performance bottlenecks across business units.'},
            {'title': 'Vendor Selection Advisory', 'desc': 'Provide independent, unbiased comparisons between database, cloud, and AI tools.'},
            {'title': 'Multi-Year Roadmapping', 'desc': 'Structure clear phases for system migrations, data cleanups, and AI deployments.'}
        ],
        'stats': [{'val': '2-4 Wk', 'label': 'Assessment Timelines'}, {'val': '35%', 'label': 'Licensing Optimization'}]
    },
    'digital-transformation-services': {
        'title': 'Digital Transformation Services',
        'tagline': 'Execute complex system modernizations with high agility.',
        'icon': 'cogs',
        'description': 'From technical blueprints to continuous cloud operations support, we provide the full lifecycle of software engineering, system integration, and data management services.',
        'features': [
            {'title': 'Cloud Application Engineering', 'desc': 'Develop and deploy modern, secure portals and APIs matching corporate guidelines.'},
            {'title': 'Legacy Code Modernization', 'desc': 'Refactor COBOL or older Java programs into modern, microservice-based Python code.'},
            {'title': 'Staffing & Support Expansion', 'desc': 'Certified developers and systems architects integrated directly into your agile teams.'}
        ],
        'stats': [{'val': '12+ Yrs', 'label': 'Consulting Legacy'}, {'val': '100%', 'label': 'Project Delivery SLA'}]
    }
}

SAP_PAGES_DATA = {
    'sap-data-integration': {
        'title': 'SAP Data Integration Services',
        'tagline': 'High-performance connectivity between SAP databases and modern cloud lakes.',
        'icon': 'circle-nodes',
        'description': 'Break down the silos of SAP ECC and S/4HANA. We deploy robust, certified pipelines using Talend and CDC engines to synchronize material ledgers, customer masters, and financial records with cloud data warehouses safely, with zero source system degradation.',
        'features': [
            {'title': 'Certified RFC and BAPI Connectors', 'desc': 'Eliminate custom ABAP development. Leverage certified SAP interfaces to securely extract data from transparent, cluster, and pooled tables.'},
            {'title': 'Core Data Services (CDS) Views', 'desc': 'Leverage SAP\'s virtual data model (VDM) layer to perform pushdown logic, extracting pre-aggregated business entities directly.'},
            {'title': 'Multi-Cloud Lakehouse Targets', 'desc': 'Push clean, schema-mapped SAP records into Databricks Delta Lake, Snowflake, or AWS Redshift with automatic schema evolution.'}
        ],
        'stats': [
            {'val': '95%', 'label': 'Extraction Automation'},
            {'val': 'Sub-Minute', 'label': 'Data Latency'},
            {'val': '4.5x', 'label': 'Faster Reports'}
        ],
        'architecture': [
            {'title': 'Zero-Impact Extraction', 'desc': 'Utilizes SAP\'s native RFC/OData interface layer with throttling controls to safeguard production transactional performance (OLTP).'},
            {'title': 'Incremental Ingestion', 'desc': 'Applies log-based tracking on SAP application layers to stream changes without repetitive full table scans.'},
            {'title': 'Metadata Translation', 'desc': 'Automatically maps complex SAP table naming conventions (e.g., KNA1, MARA, ACDOCA) and raw data types to readable, enterprise-ready schemas.'}
        ],
        'business_value': [
            {'title': 'Accelerated Decision Making', 'desc': 'Real-time data availability enables business teams to run daily financial audits and active inventory tracking without lag.'},
            {'title': 'Infrastructure Cost Optimization', 'desc': 'By moving heavy query workloads to cloud warehouses, you reduce costly MIPS/HANA RAM overhead on the primary ERP.'},
            {'title': 'Silo Elimination', 'desc': 'Unifies proprietary SAP transaction records with Salesforce CRM, web analytics, and external market logs in a single lakehouse.'}
        ]
    },
    'sap-data-migration': {
        'title': 'SAP S/4HANA Data Migration',
        'tagline': 'Migrate legacy ERP files to S/4HANA with absolute compliance.',
        'icon': 'truck-fast',
        'description': 'Transitioning to S/4HANA requires restructuring your entire data model. Artha\'s migration framework automates legacy-to-target mapping, validates balance records, and cleans material files before cutover, ensuring a risk-free go-live.',
        'features': [
            {'title': 'Universal Journal Mapping (ACDOCA)', 'desc': 'Seamlessly aggregate and map legacy FI/CO records, general ledgers, and asset databases into S/4HANA\'s single source of truth.'},
            {'title': 'Business Partner (BP) Consolidation', 'desc': 'Automatically transform and merge legacy vendor and customer files (KNA1/LFA1) into S/4HANA\'s modern Business Partner structure.'},
            {'title': 'Pre-Migration Readiness Profiling', 'desc': 'Scan, isolate, and archive stale transactional history to minimize HANA in-memory database footprint and licensing costs.'}
        ],
        'stats': [
            {'val': '65%', 'label': 'Timeline Acceleration'},
            {'val': '100%', 'label': 'Reconciliation Match'},
            {'val': '40%', 'label': 'RAM Cost Savings'}
        ],
        'architecture': [
            {'title': 'Staged ETL Pipelines', 'desc': 'Leverages a multi-stage loading architecture (Extract -> Profile -> Cleanse -> Reconcile -> Load) using Talend pipelines.'},
            {'title': 'Validation Enclaves', 'desc': 'Standardizes target S/4HANA tables in a secure staging zone to validate foreign keys, configuration checks, and schema errors before import.'},
            {'title': 'Balance Reconciliation', 'desc': 'Run automated checksums on ledger records and inventory quantities during migrations to ensure perfect alignment between old and new systems.'}
        ],
        'business_value': [
            {'title': 'Mitigated Transition Risks', 'desc': 'Ensures zero business disruption during migration cutovers, preserving critical supply-chain schedules and accounting files.'},
            {'title': 'Reduced Licensing Costs', 'desc': 'Shrinking the migrated dataset size via profiling saves hundreds of thousands in HANA in-memory database RAM licenses.'},
            {'title': 'Future-Ready Operations', 'desc': 'Establishes clean, high-performance customer and material master databases to power post-upgrade analytics from Day 1.'}
        ]
    },
    'advanced-data-matching': {
        'title': 'Advanced Data Matching for SAP',
        'tagline': 'Unify customer and material codes using machine learning heuristics.',
        'icon': 'copy',
        'description': 'Clean and consolidate duplicate master records before or after your SAP transition. Our AI-driven matching algorithms group duplicate vendor files, standardize customer registries, and eliminate code redundancy automatically.',
        'features': [
            {'title': 'Semantic Material Master Match', 'desc': 'Deduplicate spare parts and supply materials by analyzing unstructured description fields, technical parameters, and category standards.'},
            {'title': 'Fuzzy Address & Legal Name Matching', 'desc': 'Resolve multilingual variations in customer names, billing addresses, and tax registry IDs into single profiles.'},
            {'title': 'Dynamic Stewardship Worklists', 'desc': 'Provide data stewards with an intuitive interface to verify matching suggestions, set thresholds, and execute automated merges.'}
        ],
        'stats': [
            {'val': '88%', 'label': 'Duplication Clean Rate'},
            {'val': '99.2%', 'label': 'Match Accuracy Score'},
            {'val': '45%', 'label': 'Faster Procurement'}
        ],
        'architecture': [
            {'title': 'ML Similarity Pipelines', 'desc': 'Utilizes natural language processing (NLP) and similarity distance algorithms (Levenshtein, Jaro-Winkler, Cosine) on unstructured text columns.'},
            {'title': 'Blocking & Indexing', 'desc': 'Implements highly optimized blocking keys (e.g., Double Metaphone) to run comparisons over million-row databases efficiently.'},
            {'title': 'Feedback Stewardship Integration', 'desc': 'Syncs human override decisions directly back to the model to refine weights and confidence scores continuously.'}
        ],
        'business_value': [
            {'title': 'Procurement Savings', 'desc': 'Consolidating duplicate material codes reveals volume purchasing opportunities and prevents duplicate inventory acquisitions.'},
            {'title': 'Accurate Customer 360', 'desc': 'Unifies duplicate client listings to build single records, improving marketing accuracy and client service logs.'},
            {'title': 'Clean S/4HANA Upgrade', 'desc': 'Prevents migrating "garbage records" to the new ERP system, lowering indexing time and operational delays.'}
        ]
    },
    'change-data-capture': {
        'title': 'Change Data Capture (CDC) for SAP',
        'tagline': 'Replicate SAP transactions to Snowflake in real time with zero database stress.',
        'icon': 'bolt',
        'description': 'Traditional batch extraction can slow down production ERP databases and fail to support real-time decisions. Our CDC services capture database table updates directly from SAP log files, keeping data warehouses fresh.',
        'features': [
            {'title': 'Log-Based Capture', 'desc': 'Extract data modifications from transaction logs, bypassing the database execution layer.'},
            {'title': 'Schema Drift Detection & Auto-Mapping', 'desc': 'Detect structural table changes in SAP and automatically sync target tables without breaking pipeline ingestion.'},
            {'title': 'Snowflake Ingestion Optimization', 'desc': 'Leverage Snowflake Snowpipe or Databricks Autoloader to ingest updates continuously with micro-batch optimization.'}
        ],
        'stats': [
            {'val': '<1.5s', 'label': 'Ingestion Latency'},
            {'val': '0%', 'label': 'Core DB Impact'},
            {'val': '12M+', 'label': 'Daily Events'}
        ],
        'architecture': [
            {'title': 'Triggerless Replication', 'desc': 'Reads binary database logs (e.g., Oracle REDO, HANA transaction logs) directly to record modifications without query loads.'},
            {'title': 'Operational Data Provisioning (ODP)', 'desc': 'Utilizes SAP ODP queues to extract delta queues safely at the application layer when direct log access is restricted.'},
            {'title': 'Micro-Batch Streamers', 'desc': 'Encapsulates delta changes into encrypted JSON/Parquet packets, streaming them into target cloud warehouses.'}
        ],
        'business_value': [
            {'title': 'Real-Time Insights', 'desc': 'Streams sales billing, inventory movements, and shipping updates to dashboards as they occur, enabling dynamic decisions.'},
            {'title': 'Zero System Interruption', 'desc': 'Prevents reports queries from competing for resources with critical transactional operations, keeping the ERP stable.'},
            {'title': 'Reduced Compute Overhead', 'desc': 'Replicating only delta changes eliminates massive batch updates, slashing cloud warehouse compute invoices.'}
        ]
    },
    'clean-data-for-sap': {
        'title': 'Clean Data for SAP',
        'tagline': 'Establish data quality guardrails before upgrading your ERP system.',
        'icon': 'broom',
        'description': 'Do not migrate legacy garbage to S/4HANA. Our data profiling and cleansing software identifies corrupt postal addresses, duplicate vendor records, and missing fields to ensure your database starts clean.',
        'features': [
            {'title': 'Postal Validation APIs', 'desc': 'Verify customer and vendor physical addresses against global postal databases in real-time.'},
            {'title': 'Database Purging Programs', 'desc': 'Archive or delete transaction records over 7 years old to save S/4HANA memory costs.'},
            {'title': 'Active Validation Triggers', 'desc': 'Enforce validation standards at the CRM/ERP input screens to keep dirty data out.'}
        ],
        'stats': [
            {'val': '98%', 'label': 'Master Data Cleanliness'},
            {'val': '35%', 'label': 'Reduction in RAM Cost'},
            {'val': '15x', 'label': 'Faster Audit Prep'}
        ],
        'architecture': [
            {'title': 'Continuous Profiling Scans', 'desc': 'Executes background analysis rules across key tables to measure completeness, uniqueness, and consistency.'},
            {'title': 'API Address Standardization', 'desc': 'Interfaces directly with certified global location services (e.g., USPS, Loqate) to normalize street addresses.'},
            {'title': 'Archiving Segregation', 'desc': 'Implements data tiering rules (Hot, Warm, Cold) to offload legacy files safely into low-cost cloud storage.'}
        ],
        'business_value': [
            {'title': 'Minimized Logistics Failures', 'desc': 'Normalizing physical addresses avoids shipping delays, delivery returns, and billing disputes.'},
            {'title': 'Optimized HANA Performance', 'desc': 'Purging cold archive records before migration reduces the required RAM, lowering hardware infrastructure expenses.'},
            {'title': 'Trustworthy Analytics', 'desc': 'Ensures that corporate dashboards are fed with standardized, complete records, preventing misleading KPI reports.'}
        ]
    },
    'sap-test-data-management': {
        'title': 'SAP Test Data Management',
        'tagline': 'Provision light, masked developer databases dynamically.',
        'icon': 'shield-halved',
        'description': 'Developers need realistic datasets for testing without exposing private customer information. We slice and mask production SAP tables to create secure, compact developer databases while maintaining referential integrity.',
        'features': [
            {'title': 'Referentially Intact Slicing', 'desc': 'Extract a complete transaction history slice (e.g., specific company codes or time ranges) while maintaining full foreign-key structures.'},
            {'title': 'Deterministic PII Masking', 'desc': 'Anonymize or scramble credit card records, tax details, employee data, and customer identities deterministically.'},
            {'title': 'Dynamic Sandbox Refreshing', 'desc': 'Automate sandbox restores from updated production baselines via CLI scripts, slashing server storage costs.'}
        ],
        'stats': [
            {'val': '92%', 'label': 'Sandbox Refresh Speedup'},
            {'val': '100%', 'label': 'Compliance Guarantee'},
            {'val': '80%', 'label': 'Lower Storage Costs'}
        ],
        'architecture': [
            {'title': 'Metadata Relationship Mapping', 'desc': 'Maps complex foreign key relationships across hundreds of SAP tables to ensure data consistency during slicing.'},
            {'title': 'In-Flight Anonymization Engine', 'desc': 'Applies masking rules (scrambling, padding, tokenization) during the extraction process so sensitive data never hits dev disks.'},
            {'title': 'Automation Orchestration', 'desc': 'Connects with database backup and virtualization utilities to spin up fresh clones on-demand.'}
        ],
        'business_value': [
            {'title': 'Absolute Regulatory Compliance', 'desc': 'Protect customer data privacy and complies with GDPR, HIPAA, and CCPA standards during development.'},
            {'title': 'Accelerated Development Cycles', 'desc': 'Developers get access to high-fidelity data subsets instantly, eliminating delay tickets for sandbox refreshes.'},
            {'title': 'Infrastructure Storage Savings', 'desc': 'Slicing production terabytes into 10% clones saves massive hosting costs on non-production servers.'}
        ]
    },
    'data-reconciliation': {
        'title': 'SAP Data Reconciliation Services',
        'tagline': 'Automate transaction and ledger reconciliation across databases.',
        'icon': 'scale-balanced',
        'description': 'Avoid financial discrepancies and ledger imbalances during S/4HANA transitions. We deploy automated validation checks to reconcile every ledger entry, inventory balance, and transaction record in real time.',
        'features': [
            {'title': 'Cross-Database Ledger Balance Matching', 'desc': 'Automatically cross-reference and verify general ledgers against system transactions across systems (e.g., SAP vs. Salesforce billing).'},
            {'title': 'Real-Time Exception Routing', 'desc': 'Route matching discrepancies and imbalance alerts to finance team dashboards for fast dispute resolution.'},
            {'title': 'Multi-Currency & Tax Audit Support', 'desc': 'Reconcile intercompany transfers, foreign currency evaluations, and local tax filings to ensure full statutory compliance.'}
        ],
        'stats': [
            {'val': '100%', 'label': 'Reconciliation Accuracy'},
            {'val': '5x', 'label': 'Faster Auditing Speeds'},
            {'val': '90%', 'label': 'Fewer Manual Adjustments'}
        ],
        'architecture': [
            {'title': 'Parallel Ledgers Matching Engines', 'desc': 'Compares ledgers across external systems and SAP GL (General Ledger) using high-performance SQL hash queries.'},
            {'title': 'Steward Audit Trails', 'desc': 'Tracks all reconciling activities, anomaly reports, resolution details, and steward signatures in an immutable database audit log.'},
            {'title': 'Active Reconciliation Hub', 'desc': 'Intercepts transaction streams to execute checks at ledger interfaces before posting ledger entries.'}
        ],
        'business_value': [
            {'title': 'Fast Ledger Closures', 'desc': 'Accelerates monthly and quarterly financial book closures by eliminating manual excel reconciliation loops.'},
            {'title': 'Audit-Ready Financials', 'desc': 'Provides clear, automated validation records to external auditors, reducing audit times and preparation workloads.'},
            {'title': 'Early Fraud Detection', 'desc': 'Catches billing and cash adjustments immediately, minimizing revenue leakage and payment errors.'}
        ]
    }
}

ENTERPRISE_APP_DATA = {
    'service-now': {
        'title': 'ServiceNow Consulting & Integration',
        'tagline': 'Automate IT workflows and connect ITSM logs to corporate analytics.',
        'icon': 'gears',
        'description': 'ServiceNow tracks critical operational events, but these insights are often siloed. We integrate ServiceNow incident, asset, and change logs with central data warehouses to evaluate SLAs.',
        'features': [
            {'title': 'ServiceNow REST API Sync', 'desc': 'Stream ticket creation and escalation logs in real-time to operational alert maps.'},
            {'title': 'Configuration Management (CMDB)', 'desc': 'Reconcile infrastructure assets with purchasing databases to identify licensing gaps.'},
            {'title': 'Custom Integration Hub Flows', 'desc': 'Connect ServiceNow alerts to third-party databases, CRMs, and email gateways.'}
        ],
        'stats': [{'val': '40%', 'label': 'Incident Resolution Speedup'}, {'val': '100%', 'label': 'SLA Audit Visibility'}]
    },
    'oracle': {
        'title': 'Oracle Database Integration & Tuning',
        'tagline': 'Extract maximum value from your transactional Oracle platforms.',
        'icon': 'database',
        'description': 'Optimize Oracle ERP and database performance. We design real-time database replication pipelines, capture transaction edits via CDC, and tune queries to eliminate database bottlenecks.',
        'features': [
            {'title': 'Performance Tuning audits', 'desc': 'Analyze execution plans and tune indexes to speed up sluggish transaction reports.'},
            {'title': 'Oracle Cloud Migrations', 'desc': 'Transition databases to Oracle Cloud Infrastructure (OCI) with zero transaction losses.'},
            {'title': 'Real-Time Talend ETL Sync', 'desc': 'Capture and replicate Oracle transaction logs to cloud data lakes in seconds.'}
        ],
        'stats': [{'val': '3×', 'label': 'Faster Query Execution'}, {'val': '24/7', 'label': 'Managed Database Support'}]
    }
}

AI_PAGES_DATA = {
    'machine-learning': {
        'title': 'Machine Learning Solutions',
        'tagline': 'Build, train, and scale classification and forecasting models.',
        'icon': 'brain',
        'description': 'Transition from static reporting to predictive analytics. We help you design machine learning pipelines to forecast sales demand, identify anomalous transaction alerts, and model customer retention.',
        'features': [
            {'title': 'Predictive Forecasting', 'desc': 'Forecast sales demand and inventory needs to optimize logistics supply lines.'},
            {'title': 'Anomalous Transaction Alerts', 'desc': 'Train classification models to detect billing anomalies and security risks.'},
            {'title': 'Model Registry & Governance', 'desc': 'Deploy MLflow modules to manage version controls and audit algorithmic logic.'}
        ],
        'stats': [{'val': '75%', 'label': 'Error Rate Reduction'}, {'val': '3×', 'label': 'Faster Analytics Decisions'}]
    },
    'generative-ai': {
        'title': 'Generative AI Consulting',
        'tagline': 'Deploy secure LLM applications and custom RAG databases.',
        'icon': 'wand-magic-sparkles',
        'description': 'Generative AI can revolutionize productivity, but public models present security risks. We build secure, custom LLM solutions using Retrieval-Augmented Generation (RAG) to reference internal manuals.',
        'features': [
            {'title': 'Retrieval-Augmented Generation', 'desc': 'Connect LLMs to secure corporate databases for factual, context-specific answers.'},
            {'title': 'Open Source Model Fine-Tuning', 'desc': 'Customize Llama and Mistral models on proprietary manuals for specialized tasks.'},
            {'title': 'Middleware Data Guardrails', 'desc': 'Prevent prompt injection, filter out toxicity, and block outbound PII leaks.'}
        ],
        'stats': [{'val': '100%', 'label': 'Data Privacy Protection'}, {'val': '40%', 'label': 'Operations Speedup'}]
    },
    'intelligent-solutions': {
        'title': 'Intelligent Business Solutions',
        'tagline': 'Embed AI models into operations pipelines to automate tasks.',
        'icon': 'microchip',
        'description': 'Go beyond chatbots. We integrate classification and translation models directly into business logic pipelines, automating document classification, contract reviews, and ticketing routing.',
        'features': [
            {'title': 'Document Classification APIs', 'desc': 'Parse and categorize invoices, shipping slips, and emails automatically.'},
            {'title': 'Automated Contract Auditing', 'desc': 'Deploy text-matching algorithms to highlight non-compliant clauses in seconds.'},
            {'title': 'Customer Support Routing', 'desc': 'Process ticket text sentiments to route urgent issues to managers instantly.'}
        ],
        'stats': [{'val': '80%', 'label': 'Manual Processing Cut'}, {'val': '24/7', 'label': 'Continuous Processing'}]
    },
    'data-readiness': {
        'title': 'AI Data Readiness Services',
        'tagline': 'Prepare, clean, and structure data lakes for AI adoption.',
        'icon': 'shield-check',
        'description': 'AI models are only as good as their data inputs. We cleanse database records, de-duplicate customer tables, and tag dataset schemas to ensure your files are ready for LLM indexing.',
        'features': [
            {'title': 'Metadata Auto-Tagging', 'desc': 'Tag dataset fields automatically to build search indexes for AI retrievers.'},
            {'title': 'Profile De-duplication', 'desc': 'Consolidate multiple vendor records into a singular, verified master profile.'},
            {'title': 'Data Lineage Tracing', 'desc': 'Trace data sources to ensure training inputs are audit-ready and legally compliant.'}
        ],
        'stats': [{'val': '90%', 'label': 'Cleansed Data Input'}, {'val': '2-4 Wk', 'label': 'Readiness Assessment'}]
    }
}

EVENTS_DATA = {
    'barc-north-america-event': {
        'title': 'BARC North America Conference 2026',
        'date': 'October 14, 2026',
        'location': 'Chicago, IL',
        'summary': 'Artha Solutions is sponsoring the BARC North America conference, detailing best practices for master data management and cloud warehousing.',
        'description': 'Join Artha Solutions at BARC North America 2026. We will host panel discussions with enterprise CIOs on modernizing risk models, deploying AI readiness pipelines, and structuring active metadata catalogues.'
    },
    'sap-data-modernization-webinar-india': {
        'title': 'SAP Data Modernization Summit - India',
        'date': 'July 18, 2026',
        'location': 'Bengaluru, KA (Hybrid)',
        'summary': 'A comprehensive summit on accelerating SAP migrations to S/4HANA with zero transaction loss.',
        'description': 'Discuss data integration, change data capture, and master data cleanup with our team of certified SAP data engineers. Learn how heavy manufacturing firms cut S/4HANA in-memory costs by 45%.'
    },
    'sap-data-governance-and-migration-to-s-4hana-webinar-indonesia': {
        'title': 'SAP Data Governance and Migration Seminar - Indonesia',
        'date': 'June 25, 2026',
        'location': 'Jakarta (Virtual)',
        'summary': 'Tackle compliance and migration risks in the Indonesian enterprise market.',
        'description': 'Our ASEAN consulting directors showcase local case studies on validating data schemas, establishing active data stewardship, and complying with regional data sovereignty guidelines.'
    },
    'compliance-customer-centricity-optimizing-data-for-retail-industry': {
        'title': 'Compliance & Customer Centricity in Omnichannel Retail',
        'date': 'August 08, 2026',
        'location': 'New York, NY',
        'summary': 'Optimize retail checkout pipelines, unify POS events, and ensure data privacy compliance.',
        'description': 'Explore retail data engineering patterns. Learn how leading retail networks integrate payment gateway checkouts, POS logs, and shipping systems to establish a Customer 360 view.'
    },
    'qlik-ai-reality-tour-delhi-sponsored': {
        'title': 'Qlik AI Reality Tour - Delhi NCR',
        'date': 'November 12, 2026',
        'location': 'New Delhi (Sponsored)',
        'summary': 'Explore active intelligence and real-time visualization dashboards in action.',
        'description': 'As a premier Qlik partner, Artha Solutions is proud to sponsor the Delhi tour. See live demonstrations of streaming CDC pipelines, real-time analytics alerts, and automated ETL pipelines.'
    },
    'data-governance-best-practices-for-bfsi': {
        'title': 'Data Governance & Metadata Management in Banking',
        'date': 'September 22, 2026',
        'location': 'Toronto, ON (Virtual)',
        'summary': 'Ensure compliance with strict financial audits and data privacy rules.',
        'description': 'A masterclass for BFSI risk officers. We outline metadata harvesting, role-based access management, and automated CCPA/GDPR auditing setups.'
    },
    'taming-the-data-deluge-in-banking-sector': {
        'title': 'Taming the Data Deluge in Retail Banking',
        'date': 'June 10, 2026',
        'location': 'London, UK',
        'summary': 'Handle petabyte-scale transaction logs with speed and security.',
        'description': 'Analyze cellular app checkouts, ATM logs, and card transactions in real-time. Learn to deploy distributed Spark clusters to isolate fraud patterns in milliseconds.'
    },
    'from-siloed-to-strategic-data-transformation': {
        'title': 'From Siloed to Strategic: Data Foundations Masterclass',
        'date': 'May 15, 2026',
        'location': 'San Francisco, CA',
        'summary': 'Re-engineer operating databases and align tech investments with corporate growth.',
        'description': 'An executive round-table on data maturity. Learn how to audit database bottlenecks, purge redundant data, and define metadata catalog rules to prepare your business for AI.'
    },
    'learn-about-data-protection-dpdp-act-by-goi': {
        'title': 'DPDP Act Compliance and Data Governance',
        'date': 'April 20, 2026',
        'location': 'Mumbai, MH (Virtual)',
        'summary': 'Audit readiness guidelines for the Digital Personal Data Protection Act of India.',
        'description': 'Align database storage with new GOI compliance rules. Learn how to implement consent managers, automated PII indexing, and secure data masking.'
    }
}

WEBINARS_DATA = {
    '100-days-to-agile-data-governance-by-talend-artha': {
        'title': '100 Days to Agile Data Governance',
        'host': 'Artha Solutions & Talend',
        'duration': '45 min',
        'summary': 'Learn the rapid deployment framework to establish a fully compliant metadata catalog and lineage map in under 100 days.',
        'description': 'Enterprise data governance does not have to take years. Our directors detail the step-by-step blueprint to connect Talend catalogs, automate data harvesting, and establish active data steward teams in 100 days.'
    },
    'sap-data-governance-in-s-4hana': {
        'title': 'Active Data Governance in SAP S/4HANA',
        'host': 'Artha Enterprise Consulting',
        'duration': '50 min',
        'summary': 'How to maintain database cleanliness and enforce data policies inside your S/4HANA environment.',
        'description': 'Avoid post-migration database degradation. We showcase validation rules, real-time address cleanups, and automated material code audits integrated directly into the SAP creation portals.'
    },
    'sap-data-modernization-and-s-4hana-migration': {
        'title': 'SAP Data Modernization and S/4HANA Migration Blueprint',
        'host': 'Artha SAP Practice',
        'duration': '60 min',
        'summary': 'A technical deep-dive into automated conversion mapping and zero-downtime cutover strategies.',
        'description': 'Watch a simulated migration cutover. Our architects demonstrate conversion routines, transactional balance checks, and change data capture log streaming to Snowflake during active migrations.'
    },
    'sap-data-migration-in-age-of-industry-4-0': {
        'title': 'SAP Data Migration for Smart Manufacturing',
        'host': 'Artha Solutions Industrial Practice',
        'duration': '45 min',
        'summary': 'Connect PLM, SAP ERP, and shop-floor IoT sensors using a unified master record.',
        'description': 'Industry 4.0 requires clean part registries. We show how to synchronize Bill of Materials (BOM) changes automatically from design databases into SAP inventory codes.'
    },
    'customer-360-accelerate-customer-engagement-and-personalization-indonesia': {
        'title': 'Accelerate Customer Engagement with Customer 360 - Indonesia',
        'host': 'Artha Solutions ASEAN',
        'duration': '55 min',
        'summary': 'Build unified buyer profiles across local retail, mobile, and web channels.',
        'description': 'A localized webinar showing how retail networks de-duplicate customer files, track payment checkpoints, and feed CRM analytics to boost marketing ROI.'
    },
    'balancing-modernization-with-business-risk-in-the-financial-service-industry': {
        'title': 'Modernization vs. Risk in BFSI Data Warehousing',
        'host': 'Artha BFSI Advisory Group',
        'duration': '60 min',
        'summary': 'Migrate sensitive transaction data to multi-cloud data lakes without violating security policies.',
        'description': 'How to manage risk. Learn about tokenizing PII records, establishing HIPAA/GDPR enclaves, and auditing data lineages to guarantee compliance during migrations.'
    },
    'future-ready-data-foundation-from-ai-pilot-to-production-value': {
        'title': 'Future-Ready Data Foundation: From AI Pilot to Production Value',
        'host': 'Artha Solutions, IDC & Qlik',
        'duration': '45 min',
        'summary': 'Watch the IDC & Qlik webcast to learn how to build a trusted, scalable, and AI-ready data foundation.',
        'description': 'Every organization is investing in AI, but most initiatives stall before production because data isn’t ready. This on-demand webcast featuring IDC Research VP Stewart Bond explores how organizations can overcome these challenges by building a future-ready data foundation that enables trusted, scalable, and AI-ready data.'
    }
}

WHITEPAPERS_DATA = {
    'accountable-care-organizations': {
        'title': 'Data Foundations for Accountable Care Organizations (ACOs)',
        'author': 'Artha Healthcare Advisory Group',
        'pages': '18 Pages',
        'summary': 'Explore data management and profile deduplication strategies designed to optimize patient care and ensure compliance.',
        'description': 'Healthcare networks struggle with fragmented patient files. This whitepaper outlines a technical framework to unify records across clinics, manage database security, and use predictive models to improve outcomes.'
    },
    'ai-and-data-modernization-enterprise-readiness-and-value-realization': {
        'title': 'AI and Data Modernization: Enterprise Readiness and Value Realization',
        'author': 'IDC Analyst Connection',
        'pages': '6 Pages',
        'pdf_url': '/static/docs/IDC-Analyst-Connect-US54108025.pdf',
        'summary': 'An IDC Analyst Connection detailing the critical link between data modernization, enterprise readiness, and business value realization in the AI era.',
        'description': 'This IDC Analyst Connection document explores the business value and technological requirements of building an AI-ready data foundation. It outlines strategies to modernize data pipelines, eliminate data silos, establish robust governance, and scale GenAI from pilot to production-grade value.'
    },
    'future-ready-data-foundation-from-ai-pilot-to-production-value': {
        'title': 'Future-Ready Data Foundation: From AI Pilot to Production Value',
        'author': 'IDC Spotlight Paper',
        'pages': '8 Pages',
        'pdf_url': '/static/docs/IDC-Spotlight-Paper-US54106825.pdf',
        'summary': 'An IDC Spotlight Paper detailing how organizations can overcome key data challenges and build a future-ready data foundation that enables trusted, scalable AI.',
        'description': 'AI is available to everyone, but the real competitive advantage comes from how quickly and confidently you can build on the right data foundation. This IDC Spotlight Paper outlines how to transition from AI pilots to production value by establishing a strong, governed data readiness framework.'
    }
}

JOBS_DATA = {
    'php-developer': {
        'title': 'Senior PHP / Laravel Developer',
        'location': 'Bengaluru, India (Hybrid)',
        'department': 'Enterprise Applications',
        'type': 'Full-Time',
        'description': 'We are looking for a Senior PHP Developer with extensive experience in Laravel, database replication, and API integrations to support our enterprise client projects.',
        'requirements': [
            '5+ years of PHP software engineering experience',
            'Strong proficiency in Laravel framework and MySQL query optimization',
            'Experience building and consuming RESTful and SOAP APIs',
            'Knowledge of containerization (Docker) and AWS deployment is a plus'
        ]
    },
    'php-developer-2': {
        'title': 'PHP / Integration Engineer',
        'location': 'Jakarta, Indonesia (Hybrid)',
        'department': 'Enterprise Applications',
        'type': 'Full-Time',
        'description': 'Support integration mapping and API gateway setup using PHP and modern Laravel frameworks for our regional ASEAN enterprise applications.',
        'requirements': [
            '3+ years of professional backend software development experience',
            'Hands-on experience with Laravel, REST APIs, and database migrations',
            'Understanding of data mapping rules and data quality standards',
            'Fluency in English and Bahasa Indonesia is preferred'
        ]
    },
    'project-manager': {
        'title': 'Enterprise Data Project Manager',
        'location': 'New Jersey, USA (Hybrid)',
        'department': 'Consulting Services',
        'type': 'Full-Time',
        'description': 'Manage enterprise-scale data migration, master data management, and data governance programs from initial maturity assessments to final cutover.',
        'requirements': [
            '6+ years managing data warehouse, MDM, or ERP migration projects',
            'PMP or Agile Scrum Master certification is highly preferred',
            'Excellent communication and client relationship management skills',
            'Familiarity with Talend, Qlik, Snowflake, or SAP migrations is a major plus'
        ]
    },
    'project-manager-2': {
        'title': 'Agile Data Project Manager',
        'location': 'Bengaluru, India (Hybrid)',
        'department': 'Delivery Center',
        'type': 'Full-Time',
        'description': 'Coordinate data engineering sprints, track deliverables, and manage resources across our Talend integration and AI readiness programs.',
        'requirements': [
            '4+ years of project coordination experience in software or data consulting',
            'Hands-on experience with Jira, Confluence, and Agile methodologies',
            'Ability to translate technical data specifications into project timeline tasks',
            'Certified Scrum Master (CSM) is preferred'
        ]
    },
    'project-manager-3': {
        'title': 'SAP Migration Project Manager',
        'location': 'Singapore (On-site)',
        'department': 'SAP Practice Group',
        'type': 'Full-Time',
        'description': 'Lead regional S/4HANA data migration programs, managing timelines, data reconciliation checkpoints, and technical conversion audits.',
        'requirements': [
            '8+ years of project management experience, focusing on SAP ERP migrations',
            'Track record of delivering complex conversions with minimal operational disruption',
            'Experience coordinating cross-border consulting teams and client stakeholders',
            'Familiarity with SAP S/4HANA balance reconciliation and migration enclaves'
        ]
    },
    'project-manager-4': {
        'title': 'Technical Project Manager - AI & Analytics',
        'location': 'Bengaluru, India (Hybrid)',
        'department': 'AI CoE',
        'type': 'Full-Time',
        'description': 'Guide Generative AI implementation, retrieval-augmented generation pipelines, and machine learning models from sandbox prototypes to production systems.',
        'requirements': [
            '5+ years managing technical data science or machine learning development loops',
            'Background in python coding, database schemas, and AI pipeline orchestration',
            'Ability to bridge the gap between business analyst objectives and model training routines',
            'Strong alignment with software version control and model governance rules'
        ]
    }
}
