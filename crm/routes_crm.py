from flask import render_template, request, redirect, url_for, flash, jsonify, g, session
from datetime import datetime, timedelta
import json
from crm import crm_bp
from crm.auth import crm_login_required, role_required
from crm.models import db_query, db_query_one, db_execute, log_timeline_activity, get_or_create_account_and_contact
from crm.utils import calculate_meddic_score

# Helper to get visibility filter based on user role
def get_visibility_where_clause(table_prefix=""):
    role = g.crm_user.get('role')
    user_id = g.crm_user.get('id')
    group_id = g.crm_user.get('group_id')
    
    p = f"{table_prefix}." if table_prefix else ""
    
    if role == 'Platform Admin':
        return "1=1", []
    elif role in ('Group Admin', 'Sales Head'):
        return f"{p}group_id = ?", [group_id]
    elif role == 'Manager / Sales Manager':
        # See own records + team members where manager_id = user_id
        # Subquery to fetch team user ids
        return f"({p}owner_id = ? OR {p}owner_id IN (SELECT id FROM crm_users WHERE manager_id = ?))", [user_id, user_id]
    elif role in ('Sales User', 'Read-Only User'):
        return f"{p}owner_id = ?", [user_id]
    elif role == 'Telecaller':
        # Telecaller has no general CRM leads access unless permitted, restrict to none
        return "1=0", []
    else:
        return "1=0", []

# ----------------------------------------------------
# CRM Dashboard
# ----------------------------------------------------
@crm_bp.route('/crm')
@crm_bp.route('/crm/dashboard')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager', 'Sales User', 'Read-Only User')
def crm_dashboard():
    user = g.crm_user
    where_clause, params = get_visibility_where_clause()
    where_clause_o, params_o = get_visibility_where_clause(table_prefix="o")
    
    # Local helper for website leads visibility
    def get_website_leads_visibility_clause(table_prefix="wl"):
        role = g.crm_user.get('role')
        user_id = g.crm_user.get('id')
        group_id = g.crm_user.get('group_id')
        p = f"{table_prefix}." if table_prefix else ""
        if role == 'Platform Admin':
            return "1=1", []
        elif role in ('Group Admin', 'Sales Head'):
            return f"({p}assigned_owner_id IS NULL OR {p}assigned_owner_id IN (SELECT id FROM crm_users WHERE group_id = ?))", [group_id]
        elif role == 'Manager / Sales Manager':
            return f"({p}assigned_owner_id = ? OR {p}assigned_owner_id IN (SELECT id FROM crm_users WHERE manager_id = ?) OR ({p}assigned_owner_id IS NULL AND {p}geography IN (SELECT geography FROM crm_users WHERE id = ?)))", [user_id, user_id, user_id]
        elif role == 'Sales User':
            return f"{p}assigned_owner_id = ?", [user_id]
        else:
            return "1=0", []
            
    where_clause_wl, params_wl = get_website_leads_visibility_clause("wl")
    
    # 1. Staging leads counts
    website_leads_count = db_query_one(f"SELECT COUNT(*) as cnt FROM website_leads wl WHERE {where_clause_wl}", params_wl)['cnt']
    new_website_leads = db_query_one(f"SELECT COUNT(*) as cnt FROM website_leads wl WHERE wl.status = 'New' AND {where_clause_wl}", params_wl)['cnt']
    unassigned_website_leads = db_query_one(f"SELECT COUNT(*) as cnt FROM website_leads wl WHERE wl.assigned_owner_id IS NULL AND {where_clause_wl}", params_wl)['cnt']
    pending_review_leads = db_query_one(f"SELECT COUNT(*) as cnt FROM website_leads wl WHERE wl.status IN ('New', 'Reviewed', 'Assigned') AND {where_clause_wl}", params_wl)['cnt']
    
    # Converted today / this week
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    week_ago_str = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    
    converted_today = db_query_one(f"SELECT COUNT(*) as cnt FROM website_leads wl WHERE wl.status = 'Converted to Contact' AND DATE(wl.converted_at) = DATE(?) AND {where_clause_wl}", params_wl + [today_str])['cnt']
    converted_this_week = db_query_one(f"SELECT COUNT(*) as cnt FROM website_leads wl WHERE wl.status = 'Converted to Contact' AND wl.converted_at >= ? AND {where_clause_wl}", params_wl + [week_ago_str])['cnt']
    rejected_spam_leads = db_query_one(f"SELECT COUNT(*) as cnt FROM website_leads wl WHERE wl.status IN ('Rejected', 'Spam') AND {where_clause_wl}", params_wl)['cnt']
    
    # Conversion rate
    total_captured = db_query_one(f"SELECT COUNT(*) as cnt FROM website_leads wl WHERE {where_clause_wl}", params_wl)['cnt']
    total_converted = db_query_one(f"SELECT COUNT(*) as cnt FROM website_leads wl WHERE wl.status = 'Converted to Contact' AND {where_clause_wl}", params_wl)['cnt']
    conversion_rate = round((total_converted / total_captured * 100.0), 1) if total_captured > 0 else 0.0
    
    # 2. Opportunities counts & values
    opp_stats = db_query_one(f'''
        SELECT COUNT(*) as cnt, SUM(estimated_value) as total_val 
        FROM opportunities 
        WHERE status = 'Open' AND {where_clause}
    ''', params)
    opp_count = opp_stats['cnt']
    opp_value = opp_stats['total_val'] or 0.0
    
    # 3. Tasks today & overdue
    today_date = datetime.utcnow().strftime('%Y-%m-%d')
    task_stats = db_query_one(f'''
        SELECT 
            SUM(CASE WHEN due_date = ? AND status != 'Completed' THEN 1 ELSE 0 END) as today_cnt,
            SUM(CASE WHEN due_date < ? AND status != 'Completed' THEN 1 ELSE 0 END) as overdue_cnt
        FROM crm_tasks
        WHERE assigned_to = ?
    ''', (today_date, today_date, user['id']))
    
    tasks_today = task_stats['today_cnt'] or 0
    tasks_overdue = task_stats['overdue_cnt'] or 0
    
    # 4. Website Leads by source form
    leads_by_source = db_query(f'''
        SELECT source_form as label, COUNT(*) as value 
        FROM website_leads wl
        WHERE {where_clause_wl} 
        GROUP BY source_form 
        ORDER BY value DESC LIMIT 5
    ''', params_wl)
    
    # 5. Opportunity value by stage
    opps_by_stage = db_query(f'''
        SELECT stage as label, SUM(estimated_value) as value 
        FROM opportunities 
        WHERE status = 'Open' AND {where_clause} 
        GROUP BY stage
    ''', params)
    
    # 6. Pipeline by partner
    pipeline_by_partner = db_query(f'''
        SELECT p.name as label, SUM(o.estimated_value) as value 
        FROM opportunities o
        JOIN partners p ON o.partner_id = p.id
        WHERE o.status = 'Open' AND {where_clause_o} 
        GROUP BY p.name
    ''', params_o)

    # 7. Pipeline by product/solution
    pipeline_by_product = db_query(f'''
        SELECT ps.name as label, SUM(o.estimated_value) as value 
        FROM opportunities o
        JOIN product_solutions ps ON o.primary_product_solution_id = ps.id
        WHERE o.status = 'Open' AND {where_clause_o} 
        GROUP BY ps.name
    ''', params_o)

    # 8. Website Leads by Product interest (breakdown)
    leads_by_product = db_query(f'''
        SELECT product_solution_interest as label, COUNT(*) as value
        FROM website_leads wl
        WHERE product_solution_interest != '' AND {where_clause_wl}
        GROUP BY product_solution_interest
        ORDER BY value DESC LIMIT 5
    ''', params_wl)

    # Recent Website Leads pending review
    recent_website_leads = db_query(f'''
        SELECT wl.*, u.name as owner_name 
        FROM website_leads wl
        LEFT JOIN crm_users u ON wl.assigned_owner_id = u.id
        WHERE wl.status IN ('New', 'Reviewed', 'Assigned') AND {where_clause_wl}
        ORDER BY wl.id DESC LIMIT 5
    ''', params_wl)
    
    # Upcoming Tasks
    upcoming_tasks = db_query('''
        SELECT t.*, o.opportunity_name 
        FROM crm_tasks t
        LEFT JOIN opportunities o ON t.opportunity_id = o.id
        WHERE t.assigned_to = ? AND t.status != 'Completed'
        ORDER BY t.due_date ASC, t.due_time ASC LIMIT 5
    ''', (user['id'],))
    
    return render_template(
        'crm/dashboard.html',
        website_leads_count=website_leads_count,
        new_website_leads=new_website_leads,
        unassigned_website_leads=unassigned_website_leads,
        pending_review_leads=pending_review_leads,
        converted_today=converted_today,
        converted_this_week=converted_this_week,
        rejected_spam_leads=rejected_spam_leads,
        conversion_rate=conversion_rate,
        opp_count=opp_count,
        opp_value=opp_value,
        tasks_today=tasks_today,
        tasks_overdue=tasks_overdue,
        leads_by_source=leads_by_source,
        opps_by_stage=opps_by_stage,
        pipeline_by_partner=pipeline_by_partner,
        pipeline_by_product=pipeline_by_product,
        leads_by_product=leads_by_product,
        recent_leads=recent_website_leads,
        upcoming_tasks=upcoming_tasks,
        active_page='crm_dashboard'
    )

# ----------------------------------------------------
# CRM Leads Listing & Filters
# ----------------------------------------------------
@crm_bp.route('/crm/leads')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager', 'Sales User', 'Read-Only User')
def crm_leads():
    where_clause, params = get_visibility_where_clause(table_prefix="l")
    
    # Capture filter query params
    status = request.args.get('status')
    source = request.args.get('source')
    geography = request.args.get('geography')
    industry = request.args.get('industry')
    lead_list_id = request.args.get('lead_list_id')
    product_id = request.args.get('product_id')
    partner_id = request.args.get('partner_id')
    owner_id = request.args.get('owner_id')
    meddic_range = request.args.get('meddic_range') # Weak, Developing, Strong
    unassigned = request.args.get('unassigned')
    no_activity = request.args.get('no_activity')
    overdue_task = request.args.get('overdue_task')
    
    filters = []
    
    # Dynamic Custom Fields filters
    custom_filterable_fields = db_query("SELECT * FROM crm_custom_fields WHERE entity_type = 'lead' AND is_filterable = 1")
    custom_filter_values = {}
    for cf in custom_filterable_fields:
        val = request.args.get(f"cf_{cf['field_name']}")
        if val:
            custom_filter_values[cf['field_name']] = val
            filters.append("EXISTS (SELECT 1 FROM crm_custom_field_values cfv WHERE cfv.entity_id = l.id AND cfv.custom_field_id = ? AND cfv.field_value = ?)")
            params.append(cf['id'])
            params.append(val)
            
    # Append filters dynamically
    if status:
        filters.append("l.status = ?")
        params.append(status)
    if source:
        filters.append("l.lead_source = ?")
        params.append(source)
    if geography:
        filters.append("l.geography = ?")
        params.append(geography)
    if industry:
        filters.append("l.industry = ?")
        params.append(industry)
    if lead_list_id:
        filters.append("l.lead_list_id = ?")
        params.append(int(lead_list_id))
    if product_id:
        filters.append("l.primary_product_solution_id = ?")
        params.append(int(product_id))
    if partner_id:
        filters.append("l.partner_id = ?")
        params.append(int(partner_id))
    if owner_id:
        filters.append("l.owner_id = ?")
        params.append(int(owner_id))
    if unassigned == '1':
        filters.append("l.owner_id IS NULL")
        
    if meddic_range:
        if meddic_range == 'Weak':
            filters.append("l.meddic_score BETWEEN 0 AND 39")
        elif meddic_range == 'Developing':
            filters.append("l.meddic_score BETWEEN 40 AND 69")
        elif meddic_range == 'Strong':
            filters.append("l.meddic_score BETWEEN 70 AND 100")
            
    if no_activity == '1':
        # No activities in last 14 days
        two_weeks_ago = (datetime.utcnow() - timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
        filters.append("l.id NOT IN (SELECT entity_id FROM timeline_activities WHERE entity_type = 'lead' AND created_at >= ?)")
        params.append(two_weeks_ago)
        
    if overdue_task == '1':
        today_date = datetime.utcnow().strftime('%Y-%m-%d')
        filters.append("l.id IN (SELECT lead_id FROM crm_tasks WHERE status != 'Completed' AND due_date < ?)")
        params.append(today_date)
        
    # Combine standard security clause and filters
    full_where = where_clause
    if filters:
        full_where += " AND " + " AND ".join(filters)
        
    query = f'''
        SELECT l.*, u.name as owner_name, p.name as partner_name, ps.name as product_name, lst.name as list_name
        FROM leads l
        LEFT JOIN crm_users u ON l.owner_id = u.id
        LEFT JOIN partners p ON l.partner_id = p.id
        LEFT JOIN product_solutions ps ON l.primary_product_solution_id = ps.id
        LEFT JOIN lead_lists lst ON l.lead_list_id = lst.id
        WHERE {full_where}
        ORDER BY l.id DESC
    '''
    leads = db_query(query, params)
    
    # Fetch lists for filters dropdown
    lists = db_query("SELECT id, name FROM lead_lists WHERE is_active = 1")
    products_list = db_query("SELECT id, name FROM product_solutions WHERE is_active = 1")
    partners_list = db_query("SELECT id, name FROM partners WHERE is_active = 1")
    owners = db_query("SELECT id, name FROM crm_users WHERE is_active = 1 AND role != 'Telecaller'")
    
    return render_template(
        'leads/list.html',
        leads=leads,
        lists=lists,
        products=products_list,
        partners=partners_list,
        owners=owners,
        custom_filterable_fields=custom_filterable_fields,
        custom_filter_values=custom_filter_values,
        active_page='crm_leads'
    )

# ----------------------------------------------------
# Manual Lead Creation
# ----------------------------------------------------
@crm_bp.route('/crm/leads/new', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager', 'Sales User')
def new_lead():
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        full_name = f"{first_name or ''} {last_name or ''}".strip()
        company = request.form.get('company')
        email = request.form.get('email')
        phone = request.form.get('phone')
        job_title = request.form.get('job_title')
        geography = request.form.get('geography')
        country = request.form.get('country')
        industry = request.form.get('industry')
        website = request.form.get('website')
        linkedin_profile = request.form.get('linkedin_profile')
        primary_product_id = request.form.get('primary_product_solution_id')
        partner_id = request.form.get('partner_id')
        partner_influence = request.form.get('partner_influence_type', 'None')
        notes = request.form.get('notes')
        
        # Validation
        if not full_name or not email:
            flash("Full Name and Email are mandatory fields.", "error")
            return redirect(url_for('crm.new_lead'))
            
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        owner_id = g.crm_user['id']
        group_id = g.crm_user['group_id']
        
        # Find Lead List for manual entry
        lead_list = db_query_one("SELECT id FROM lead_lists WHERE name = 'Manually Added Leads'")
        lead_list_id = lead_list['id'] if lead_list else None
        
        lead_id = db_execute('''
            INSERT INTO leads (
                first_name, last_name, full_name, company, email, phone, job_title, geography, country, industry, website, linkedin_profile,
                lead_source, lead_list_id, owner_id, group_id, status, primary_product_solution_id, partner_id, partner_influence_type, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            first_name, last_name, full_name, company, email, phone, job_title, geography, country, industry, website, linkedin_profile,
            'Manual', lead_list_id, owner_id, group_id, 'New', primary_product_id, partner_id, partner_influence, notes, now_str, now_str
        ))
        
        # Initialize empty MEDDIC profile
        db_execute('''
            INSERT INTO meddic_qualifications (entity_type, entity_id, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        ''', ('lead', lead_id, now_str, now_str))
        
        log_timeline_activity('lead', lead_id, 'Lead created', f"Lead {full_name} manually created", f"Company: {company}", owner_id)
        flash("Lead created successfully!", "success")
        return redirect(url_for('crm.crm_lead_detail', lead_id=lead_id))
        
    products_list = db_query("SELECT id, name FROM product_solutions WHERE is_active = 1")
    partners_list = db_query("SELECT id, name FROM partners WHERE is_active = 1")
    return render_template('leads/new.html', products=products_list, partners=partners_list)

# ----------------------------------------------------
# Lead Details & Tabs
# ----------------------------------------------------
@crm_bp.route('/crm/leads/<int:lead_id>', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager', 'Sales User', 'Read-Only User')
def crm_lead_detail(lead_id):
    where_clause, params = get_visibility_where_clause(table_prefix="l")
    
    # 1. Fetch Lead (checking visibility)
    full_params = [lead_id] + params
    lead = db_query_one(f'''
        SELECT l.*, u.name as owner_name, lst.name as list_name, ps.name as product_name, p.name as partner_name
        FROM leads l
        LEFT JOIN crm_users u ON l.owner_id = u.id
        LEFT JOIN lead_lists lst ON l.lead_list_id = lst.id
        LEFT JOIN product_solutions ps ON l.primary_product_solution_id = ps.id
        LEFT JOIN partners p ON l.partner_id = p.id
        WHERE l.id = ? AND {where_clause}
    ''', full_params)
    
    if not lead:
        flash("Lead not found or access denied.", "error")
        return redirect(url_for('crm.crm_leads'))
        
    # Handle Updates (details, status, MEDDIC, tasks, emails)
    if request.method == 'POST':
        action = request.form.get('action')
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        if action == 'update_details':
            # Lead parameters
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            full_name = f"{first_name or ''} {last_name or ''}".strip()
            company = request.form.get('company')
            email = request.form.get('email')
            phone = request.form.get('phone')
            job_title = request.form.get('job_title')
            geography = request.form.get('geography')
            country = request.form.get('country')
            industry = request.form.get('industry')
            website = request.form.get('website')
            linkedin_profile = request.form.get('linkedin_profile')
            primary_product_id = request.form.get('primary_product_solution_id')
            partner_id = request.form.get('partner_id')
            partner_influence = request.form.get('partner_influence_type')
            notes = request.form.get('notes')
            status = request.form.get('status')
            owner_id = request.form.get('owner_id')
            
            # Reassignment log
            previous_owner_id = lead['owner_id']
            new_owner_id = int(owner_id) if owner_id else None
            if previous_owner_id != new_owner_id:
                db_execute('''
                    INSERT INTO lead_assignment_history (lead_id, previous_owner_id, new_owner_id, changed_by, reason, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (lead_id, previous_owner_id, new_owner_id, g.crm_user['id'], 'Manual reassignment', now_str))
                log_timeline_activity('lead', lead_id, 'Lead reassigned', f"Lead reassigned", f"Changed from owner ID {previous_owner_id} to {new_owner_id}", g.crm_user['id'])
                
            db_execute('''
                UPDATE leads 
                SET first_name=?, last_name=?, full_name=?, company=?, email=?, phone=?, job_title=?, geography=?, country=?, industry=?, 
                    website=?, linkedin_profile=?, primary_product_solution_id=?, partner_id=?, partner_influence_type=?, notes=?, status=?, owner_id=?, updated_at=?
                WHERE id=?
            ''', (
                first_name, last_name, full_name, company, email, phone, job_title, geography, country, industry,
                website, linkedin_profile, primary_product_id, partner_id, partner_influence, notes, status, new_owner_id, now_str, lead_id
            ))
            
            log_timeline_activity('lead', lead_id, 'Lead updated', "Lead details updated", f"Status updated to: {status}", g.crm_user['id'])
            
            # Save custom field values
            custom_fields = db_query("SELECT * FROM crm_custom_fields WHERE entity_type = 'lead'")
            for cf in custom_fields:
                val = request.form.get(f"cf_{cf['field_name']}")
                db_execute('''
                    INSERT INTO crm_custom_field_values (custom_field_id, entity_id, field_value, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(custom_field_id, entity_id) DO UPDATE SET field_value = excluded.field_value, updated_at = excluded.updated_at
                ''', (cf['id'], lead_id, val, now_str, now_str))
                
            flash("Lead details updated.", "success")
            return redirect(url_for('crm.crm_lead_detail', lead_id=lead_id))
            
        elif action == 'update_meddic':
            # MEDDIC details
            metrics_identified = 1 if request.form.get('metrics_identified') == 'yes' else 0
            metrics_note = request.form.get('metrics_note')
            estimated_impact = request.form.get('estimated_impact')
            success_metric = request.form.get('success_metric')
            economic_buyer_identified = 1 if request.form.get('economic_buyer_identified') == 'yes' else 0
            economic_buyer_name = request.form.get('economic_buyer_name')
            economic_buyer_title = request.form.get('economic_buyer_title')
            economic_buyer_access_level = request.form.get('economic_buyer_access_level')
            decision_criteria = request.form.get('decision_criteria')
            technical_criteria = request.form.get('technical_criteria')
            business_criteria = request.form.get('business_criteria')
            compliance_criteria = request.form.get('compliance_criteria')
            decision_process_known = 1 if request.form.get('decision_process_known') == 'yes' else 0
            decision_timeline = request.form.get('decision_timeline')
            approval_process = request.form.get('approval_process')
            procurement_involved = 1 if request.form.get('procurement_involved') == 'yes' else 0
            target_decision_date = request.form.get('target_decision_date')
            primary_pain = request.form.get('primary_pain')
            business_challenge = request.form.get('business_challenge')
            pain_severity = request.form.get('pain_severity')
            pain_validated = 1 if request.form.get('pain_validated') == 'yes' else 0
            champion_identified = 1 if request.form.get('champion_identified') == 'yes' else 0
            champion_name = request.form.get('champion_name')
            champion_role = request.form.get('champion_role')
            champion_strength = request.form.get('champion_strength')
            competitor = request.form.get('competitor_or_alternative')
            current_sol = request.form.get('current_solution')
            diff_note = request.form.get('differentiation_note')
            
            meddic_dict = {
                'metrics_identified': metrics_identified,
                'economic_buyer_identified': economic_buyer_identified,
                'decision_criteria': decision_criteria,
                'technical_criteria': technical_criteria,
                'business_criteria': business_criteria,
                'decision_process_known': decision_process_known,
                'pain_validated': pain_validated,
                'champion_identified': champion_identified
            }
            score, label = calculate_meddic_score(meddic_dict)
            
            # Check if exists, update or insert
            db_execute('''
                INSERT INTO meddic_qualifications (
                    entity_type, entity_id, metrics_identified, metrics_note, estimated_impact, success_metric,
                    economic_buyer_identified, economic_buyer_name, economic_buyer_title, economic_buyer_access_level,
                    decision_criteria, technical_criteria, business_criteria, compliance_criteria,
                    decision_process_known, decision_timeline, approval_process, procurement_involved, target_decision_date,
                    primary_pain, business_challenge, pain_severity, pain_validated,
                    champion_identified, champion_name, champion_role, champion_strength,
                    competitor_or_alternative, current_solution, differentiation_note, score, updated_by, created_at, updated_at
                ) VALUES ('lead', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                    metrics_identified=excluded.metrics_identified, metrics_note=excluded.metrics_note, estimated_impact=excluded.estimated_impact, success_metric=excluded.success_metric,
                    economic_buyer_identified=excluded.economic_buyer_identified, economic_buyer_name=excluded.economic_buyer_name, economic_buyer_title=excluded.economic_buyer_title, economic_buyer_access_level=excluded.economic_buyer_access_level,
                    decision_criteria=excluded.decision_criteria, technical_criteria=excluded.technical_criteria, business_criteria=excluded.business_criteria, compliance_criteria=excluded.compliance_criteria,
                    decision_process_known=excluded.decision_process_known, decision_timeline=excluded.decision_timeline, approval_process=excluded.approval_process, procurement_involved=excluded.procurement_involved, target_decision_date=excluded.target_decision_date,
                    primary_pain=excluded.primary_pain, business_challenge=excluded.business_challenge, pain_severity=excluded.pain_severity, pain_validated=excluded.pain_validated,
                    champion_identified=excluded.champion_identified, champion_name=excluded.champion_name, champion_role=excluded.champion_role, champion_strength=excluded.champion_strength,
                    competitor_or_alternative=excluded.competitor_or_alternative, current_solution=excluded.current_solution, differentiation_note=excluded.differentiation_note,
                    score=excluded.score, updated_by=excluded.updated_by, updated_at=excluded.updated_at
            ''', (
                lead_id, metrics_identified, metrics_note, estimated_impact, success_metric,
                economic_buyer_identified, economic_buyer_name, economic_buyer_title, economic_buyer_access_level,
                decision_criteria, technical_criteria, business_criteria, compliance_criteria,
                decision_process_known, decision_timeline, approval_process, procurement_involved, target_decision_date,
                primary_pain, business_challenge, pain_severity, pain_validated,
                champion_identified, champion_name, champion_role, champion_strength,
                competitor, current_sol, diff_note, score, g.crm_user['id'], now_str, now_str
            ))
            
            # Sync score to Lead table
            db_execute("UPDATE leads SET meddic_score = ? WHERE id = ?", (score, lead_id))
            
            log_timeline_activity('lead', lead_id, 'MEDDIC updated', f"MEDDIC updated - Score: {score} ({label})", "", g.crm_user['id'])
            flash("MEDDIC qualifications updated.", "success")
            return redirect(url_for('crm.crm_lead_detail', lead_id=lead_id))
            
        elif action == 'add_task':
            title = request.form.get('task_title')
            task_type = request.form.get('task_type')
            due_date = request.form.get('due_date')
            due_time = request.form.get('due_time')
            priority = request.form.get('priority', 'Medium')
            desc = request.form.get('task_description')
            
            task_id = db_execute('''
                INSERT INTO crm_tasks (title, description, task_type, related_entity_type, related_entity_id, lead_id, assigned_to, created_by, due_date, due_time, priority, status, created_at, updated_at)
                VALUES (?, ?, ?, 'lead', ?, ?, ?, ?, ?, ?, ?, 'Open', ?, ?)
            ''', (title, desc, task_type, lead_id, lead_id, lead['owner_id'] or g.crm_user['id'], g.crm_user['id'], due_date, due_time, priority, now_str, now_str))
            
            log_timeline_activity('lead', lead_id, 'Task created', f"Task Created: {title}", f"Type: {task_type}, Due: {due_date} {due_time or ''}", g.crm_user['id'], related_task_id=task_id)
            flash("Task added successfully.", "success")
            return redirect(url_for('crm.crm_lead_detail', lead_id=lead_id))
            
        elif action == 'log_email':
            # Sends/logs plain email to the lead
            to_email = request.form.get('to_email')
            cc = request.form.get('cc')
            subject = request.form.get('subject')
            body = request.form.get('body')
            
            db_execute('''
                INSERT INTO crm_email_logs (entity_type, entity_id, lead_id, sender_user_id, to_email, cc, subject, body, status, sent_at, created_at)
                VALUES ('lead', ?, ?, ?, ?, ?, ?, ?, 'Sent', ?, ?)
            ''', (lead_id, lead_id, g.crm_user['id'], to_email, cc, subject, body, now_str, now_str))
            
            log_timeline_activity('lead', lead_id, 'Email sent', f"Email Sent: {subject}", body[:150], g.crm_user['id'])
            flash("Email logged and sent.", "success")
            return redirect(url_for('crm.crm_lead_detail', lead_id=lead_id))

    # Fetch dependent details
    meddic = db_query_one("SELECT * FROM meddic_qualifications WHERE entity_type = 'lead' AND entity_id = ?", (lead_id,))
    if not meddic:
        # Create empty meddic profile if not exists
        db_execute("INSERT OR IGNORE INTO meddic_qualifications (entity_type, entity_id, created_at, updated_at) VALUES ('lead', ?, ?, ?)", (lead_id, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
        meddic = db_query_one("SELECT * FROM meddic_qualifications WHERE entity_type = 'lead' AND entity_id = ?", (lead_id,))
        
    meddic_score_label = "Weak"
    if meddic:
        score = meddic.get('score', 0)
        if score >= 70:
            meddic_score_label = "Strong"
        elif score >= 40:
            meddic_score_label = "Developing"
            
    timeline = db_query("SELECT t.*, u.name as user_name FROM timeline_activities t LEFT JOIN crm_users u ON t.created_by = u.id WHERE t.lead_id = ? ORDER BY t.id DESC", (lead_id,))
    tasks = db_query("SELECT t.*, u.name as assigned_name FROM crm_tasks t LEFT JOIN crm_users u ON t.assigned_to = u.id WHERE t.lead_id = ? ORDER BY t.due_date ASC, t.id DESC", (lead_id,))
    emails = db_query("SELECT e.*, u.name as sender_name FROM crm_email_logs e LEFT JOIN crm_users u ON e.sender_user_id = u.id WHERE e.lead_id = ? ORDER BY e.id DESC", (lead_id,))
    
    products_list = db_query("SELECT id, name FROM product_solutions WHERE is_active = 1")
    partners_list = db_query("SELECT id, name FROM partners WHERE is_active = 1")
    owners = db_query("SELECT id, name FROM crm_users WHERE is_active = 1 AND role != 'Telecaller'")
    
    custom_fields = db_query("SELECT * FROM crm_custom_fields WHERE entity_type = 'lead'")
    custom_values = db_query("SELECT custom_field_id, field_value FROM crm_custom_field_values WHERE entity_id = ?", (lead_id,))
    custom_values_dict = {val['custom_field_id']: val['field_value'] for val in custom_values}
    
    return render_template(
        'leads/detail.html',
        lead=lead,
        meddic=meddic,
        meddic_label=meddic_score_label,
        timeline=timeline,
        tasks=tasks,
        emails=emails,
        products=products_list,
        partners=partners_list,
        owners=owners,
        custom_fields=custom_fields,
        custom_values=custom_values_dict,
        active_page='crm_leads'
    )

# ----------------------------------------------------
# Convert Lead to Opportunity
# ----------------------------------------------------
@crm_bp.route('/crm/leads/<int:lead_id>/convert-to-opportunity', methods=['POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager', 'Sales User')
def convert_lead(lead_id):
    where_clause, params = get_visibility_where_clause()
    lead = db_query_one(f"SELECT * FROM leads WHERE id = ? AND {where_clause}", [lead_id] + params)
    
    if not lead:
        flash("Lead not found or access denied.", "error")
        return redirect(url_for('crm.crm_leads'))
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    # 1. Map or Create Account and Contact
    account_id, contact_id = get_or_create_account_and_contact(
        company_name=lead['company'],
        email=lead['email'],
        phone=lead['phone'],
        first_name=lead['first_name'],
        last_name=lead['last_name'],
        job_title=lead['job_title'],
        geography=lead['geography'],
        country=lead['country'],
        industry=lead['industry'],
        website=lead['website'],
        linkedin_profile=lead['linkedin_profile'],
        source='Lead Conversion',
        owner_id=lead['owner_id'] or g.crm_user['id']
    )
    
    # Update Lead status & mappings
    db_execute("UPDATE leads SET status='Converted to Opportunity', account_id=?, contact_id=?, updated_at=? WHERE id=?", (account_id, contact_id, now_str, lead_id))
    
    # 2. Create Opportunity
    opp_name = f"{lead['company'] or 'New Account'} - {lead['full_name']} Opportunity"
    estimated_value = float(request.form.get('estimated_value', 0.0))
    close_date = request.form.get('expected_close_date')
    
    opp_id = db_execute('''
        INSERT INTO opportunities (
            lead_id, account_id, contact_id, opportunity_name, company, primary_contact_name, primary_contact_email,
            owner_id, group_id, industry, geography, primary_product_solution_id, partner_id, partner_influence_type,
            estimated_value, currency, expected_close_date, stage, bucket, probability, meddic_score, status, sql_source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'USD', ?, 'Prospecting', 'Prospecting', 10, ?, 'Open', 'CRM', ?, ?)
    ''', (
        lead_id, account_id, contact_id, opp_name, lead['company'], lead['full_name'], lead['email'],
        lead['owner_id'] or g.crm_user['id'], lead['group_id'], lead['industry'], lead['geography'],
        lead['primary_product_solution_id'], lead['partner_id'], lead['partner_influence_type'],
        estimated_value, close_date, lead['meddic_score'], now_str, now_str
    ))
    
    # Carry forward MEDDIC qualification
    meddic = db_query_one("SELECT * FROM meddic_qualifications WHERE entity_type = 'lead' AND entity_id = ?", (lead_id,))
    if meddic:
        # Create opportunity MEDDIC clone
        db_execute('''
            INSERT INTO meddic_qualifications (
                entity_type, entity_id, metrics_identified, metrics_note, estimated_impact, success_metric,
                economic_buyer_identified, economic_buyer_name, economic_buyer_title, economic_buyer_access_level,
                decision_criteria, technical_criteria, business_criteria, compliance_criteria,
                decision_process_known, decision_timeline, approval_process, procurement_involved, target_decision_date,
                primary_pain, business_challenge, pain_severity, pain_validated,
                champion_identified, champion_name, champion_role, champion_strength,
                competitor_or_alternative, current_solution, differentiation_note, score, updated_by, created_at, updated_at
            ) VALUES ('opportunity', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_type, entity_id) DO UPDATE SET score = excluded.score
        ''', (
            opp_id, meddic['metrics_identified'], meddic['metrics_note'], meddic['estimated_impact'], meddic['success_metric'],
            meddic['economic_buyer_identified'], meddic['economic_buyer_name'], meddic['economic_buyer_title'], meddic['economic_buyer_access_level'],
            meddic['decision_criteria'], meddic['technical_criteria'], meddic['business_criteria'], meddic['compliance_criteria'],
            meddic['decision_process_known'], meddic['decision_timeline'], meddic['approval_process'], meddic['procurement_involved'], meddic['target_decision_date'],
            meddic['primary_pain'], meddic['business_challenge'], meddic['pain_severity'], meddic['pain_validated'],
            meddic['champion_identified'], meddic['champion_name'], meddic['champion_role'], meddic['champion_strength'],
            meddic['competitor_or_alternative'], meddic['current_solution'], meddic['differentiation_note'], meddic['score'], g.crm_user['id'], now_str, now_str
        ))
        
    # Link all timeline entries from Lead to the Opportunity
    db_execute("UPDATE timeline_activities SET opportunity_id = ? WHERE lead_id = ?", (opp_id, lead_id))
    db_execute("UPDATE crm_tasks SET opportunity_id = ? WHERE lead_id = ?", (opp_id, lead_id))
    db_execute("UPDATE crm_email_logs SET opportunity_id = ? WHERE lead_id = ?", (opp_id, lead_id))
    
    # Log timeline conversions
    log_timeline_activity('lead', lead_id, 'Lead converted', "Lead converted to Opportunity", f"Opportunity ID: {opp_id}", g.crm_user['id'])
    log_timeline_activity('opportunity', opp_id, 'Opportunity created', "Opportunity created from Lead conversion", f"Lead ID: {lead_id}", g.crm_user['id'])
    
    # Auto task for Rep: follow-up
    tomorrow_str = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%d')
    task_id = db_execute('''
        INSERT INTO crm_tasks (title, description, task_type, related_entity_type, related_entity_id, opportunity_id, assigned_to, created_by, due_date, due_time, priority, status, created_at, updated_at)
        VALUES (?, ?, ?, 'opportunity', ?, ?, ?, ?, ?, ?, ?, 'Open', ?, ?)
    ''', ("Follow up on new Opportunity", "Lead has been successfully converted to this Opportunity. Run discovery call.", 'Follow-up', opp_id, opp_id, lead['owner_id'] or g.crm_user['id'], g.crm_user['id'], tomorrow_str, '10:00', 'High', now_str, now_str))
    
    # Update lead converted mapping
    db_execute("UPDATE leads SET converted_opportunity_id = ? WHERE id = ?", (opp_id, lead_id))
    
    flash("Lead converted to Opportunity successfully!", "success")
    return redirect(url_for('crm.crm_opportunity_detail', opp_id=opp_id))

# ----------------------------------------------------
# CRM Opportunity Listing
# ----------------------------------------------------
@crm_bp.route('/crm/opportunities')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager', 'Sales User', 'Read-Only User')
def crm_opportunities():
    where_clause, params = get_visibility_where_clause(table_prefix="o")
    
    # Stage groups mapping
    stage_buckets = {
        'Prospecting': ['Prospecting', 'Discovery'],
        'Qualifying': ['Solution Fit'],
        'Proposal': ['Proposal'],
        'Negotiating': ['Negotiation'],
        'Closing': ['Closing', 'Closed Won', 'Closed Lost']
    }
    
    # Fetch list of opportunities
    query = f'''
        SELECT o.*, u.name as owner_name, a.account_name as company_name, p.name as partner_name, ps.name as product_name
        FROM opportunities o
        LEFT JOIN crm_users u ON o.owner_id = u.id
        LEFT JOIN accounts a ON o.account_id = a.id
        LEFT JOIN partners p ON o.partner_id = p.id
        LEFT JOIN product_solutions ps ON o.primary_product_solution_id = ps.id
        WHERE {where_clause}
        ORDER BY o.id DESC
    '''
    opps = db_query(query, params)
    
    # Group into buckets for Kanban
    kanban_opps = {bucket: [] for bucket in stage_buckets.keys()}
    for opp in opps:
        # Map bucket
        opp_bucket = opp.get('bucket', 'Prospecting')
        if opp_bucket in kanban_opps:
            kanban_opps[opp_bucket].append(opp)
            
    return render_template(
        'opportunities/list.html',
        opportunities=opps,
        kanban_opportunities=kanban_opps,
        active_page='crm_opportunities'
    )

# ----------------------------------------------------
# Opportunity Detail & Updates
# ----------------------------------------------------
@crm_bp.route('/crm/opportunities/<int:opp_id>', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager', 'Sales User', 'Read-Only User')
def crm_opportunity_detail(opp_id):
    where_clause, params = get_visibility_where_clause(table_prefix="o")
    full_params = [opp_id] + params
    
    opp = db_query_one(f'''
        SELECT o.*, u.name as owner_name, sm.name as manager_name, a.account_name as company_name, a.website, c.full_name as contact_name, c.email as contact_email, c.phone as contact_phone, p.name as partner_name, ps.name as product_name
        FROM opportunities o
        LEFT JOIN crm_users u ON o.owner_id = u.id
        LEFT JOIN crm_users sm ON o.sales_manager_id = sm.id
        LEFT JOIN accounts a ON o.account_id = a.id
        LEFT JOIN contacts c ON o.contact_id = c.id
        LEFT JOIN partners p ON o.partner_id = p.id
        LEFT JOIN product_solutions ps ON o.primary_product_solution_id = ps.id
        WHERE o.id = ? AND {where_clause}
    ''', full_params)
    
    if not opp:
        flash("Opportunity not found or access denied.", "error")
        return redirect(url_for('crm.crm_opportunities'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        if action == 'update_details':
            estimated_value = float(request.form.get('estimated_value', 0.0))
            expected_close_date = request.form.get('expected_close_date')
            stage = request.form.get('stage')
            probability = int(request.form.get('probability', 10))
            owner_id = request.form.get('owner_id')
            sales_manager_id = request.form.get('sales_manager_id')
            primary_product_id = request.form.get('primary_product_solution_id')
            partner_id = request.form.get('partner_id')
            partner_influence = request.form.get('partner_influence_type')
            partner_contact = request.form.get('partner_contact_name')
            partner_notes = request.form.get('partner_notes')
            closed_reason = request.form.get('closed_reason')
            
            # Map stages to pipeline buckets
            # buckets: Prospecting, Qualifying, Proposal, Negotiating, Closing
            bucket = 'Prospecting'
            if stage in ('Prospecting', 'Discovery'):
                bucket = 'Prospecting'
            elif stage in ('Solution Fit',):
                bucket = 'Qualifying'
            elif stage in ('Proposal',):
                bucket = 'Proposal'
            elif stage in ('Negotiation',):
                bucket = 'Negotiating'
            elif stage in ('Closing', 'Closed Won', 'Closed Lost'):
                bucket = 'Closing'
                
            closed_at = now_str if 'Closed' in stage else None
            
            # Reassignment logging
            prev_owner = opp['owner_id']
            new_owner = int(owner_id) if owner_id else None
            if prev_owner != new_owner:
                db_execute('''
                    INSERT INTO lead_assignment_history (opportunity_id, previous_owner_id, new_owner_id, changed_by, reason, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (opp_id, prev_owner, new_owner, g.crm_user['id'], 'Opportunity owner change', now_str))
                log_timeline_activity('opportunity', opp_id, 'Opportunity reassigned', "Opportunity reassigned", f"Assigned to user ID {new_owner}", g.crm_user['id'])
                
            db_execute('''
                UPDATE opportunities 
                SET estimated_value=?, expected_close_date=?, stage=?, bucket=?, probability=?, owner_id=?, sales_manager_id=?, 
                    primary_product_solution_id=?, partner_id=?, partner_influence_type=?, partner_contact_name=?, partner_notes=?, closed_reason=?, closed_at=?, updated_at=?
                WHERE id=?
            ''', (
                estimated_value, expected_close_date, stage, bucket, probability, new_owner, sales_manager_id,
                primary_product_id, partner_id, partner_influence, partner_contact, partner_notes, closed_reason, closed_at, now_str, opp_id
            ))
            
            log_timeline_activity('opportunity', opp_id, 'Opportunity updated', f"Stage changed to {stage}", f"Value: {estimated_value} USD", g.crm_user['id'])
            flash("Opportunity updated successfully.", "success")
            return redirect(url_for('crm.crm_opportunity_detail', opp_id=opp_id))
            
        elif action == 'update_meddic':
            # MEDDIC details
            metrics_identified = 1 if request.form.get('metrics_identified') == 'yes' else 0
            metrics_note = request.form.get('metrics_note')
            estimated_impact = request.form.get('estimated_impact')
            success_metric = request.form.get('success_metric')
            economic_buyer_identified = 1 if request.form.get('economic_buyer_identified') == 'yes' else 0
            economic_buyer_name = request.form.get('economic_buyer_name')
            economic_buyer_title = request.form.get('economic_buyer_title')
            economic_buyer_access_level = request.form.get('economic_buyer_access_level')
            decision_criteria = request.form.get('decision_criteria')
            technical_criteria = request.form.get('technical_criteria')
            business_criteria = request.form.get('business_criteria')
            compliance_criteria = request.form.get('compliance_criteria')
            decision_process_known = 1 if request.form.get('decision_process_known') == 'yes' else 0
            decision_timeline = request.form.get('decision_timeline')
            approval_process = request.form.get('approval_process')
            procurement_involved = 1 if request.form.get('procurement_involved') == 'yes' else 0
            target_decision_date = request.form.get('target_decision_date')
            primary_pain = request.form.get('primary_pain')
            business_challenge = request.form.get('business_challenge')
            pain_severity = request.form.get('pain_severity')
            pain_validated = 1 if request.form.get('pain_validated') == 'yes' else 0
            champion_identified = 1 if request.form.get('champion_identified') == 'yes' else 0
            champion_name = request.form.get('champion_name')
            champion_role = request.form.get('champion_role')
            champion_strength = request.form.get('champion_strength')
            competitor = request.form.get('competitor_or_alternative')
            current_sol = request.form.get('current_solution')
            diff_note = request.form.get('differentiation_note')
            
            meddic_dict = {
                'metrics_identified': metrics_identified,
                'economic_buyer_identified': economic_buyer_identified,
                'decision_criteria': decision_criteria,
                'technical_criteria': technical_criteria,
                'business_criteria': business_criteria,
                'decision_process_known': decision_process_known,
                'pain_validated': pain_validated,
                'champion_identified': champion_identified
            }
            score, label = calculate_meddic_score(meddic_dict)
            
            db_execute('''
                INSERT INTO meddic_qualifications (
                    entity_type, entity_id, metrics_identified, metrics_note, estimated_impact, success_metric,
                    economic_buyer_identified, economic_buyer_name, economic_buyer_title, economic_buyer_access_level,
                    decision_criteria, technical_criteria, business_criteria, compliance_criteria,
                    decision_process_known, decision_timeline, approval_process, procurement_involved, target_decision_date,
                    primary_pain, business_challenge, pain_severity, pain_validated,
                    champion_identified, champion_name, champion_role, champion_strength,
                    competitor_or_alternative, current_solution, differentiation_note, score, updated_by, created_at, updated_at
                ) VALUES ('opportunity', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                    metrics_identified=excluded.metrics_identified, metrics_note=excluded.metrics_note, estimated_impact=excluded.estimated_impact, success_metric=excluded.success_metric,
                    economic_buyer_identified=excluded.economic_buyer_identified, economic_buyer_name=excluded.economic_buyer_name, economic_buyer_title=excluded.economic_buyer_title, economic_buyer_access_level=excluded.economic_buyer_access_level,
                    decision_criteria=excluded.decision_criteria, technical_criteria=excluded.technical_criteria, business_criteria=excluded.business_criteria, compliance_criteria=excluded.compliance_criteria,
                    decision_process_known=excluded.decision_process_known, decision_timeline=excluded.decision_timeline, approval_process=excluded.approval_process, procurement_involved=excluded.procurement_involved, target_decision_date=excluded.target_decision_date,
                    primary_pain=excluded.primary_pain, business_challenge=excluded.business_challenge, pain_severity=excluded.pain_severity, pain_validated=excluded.pain_validated,
                    champion_identified=excluded.champion_identified, champion_name=excluded.champion_name, champion_role=excluded.champion_role, champion_strength=excluded.champion_strength,
                    competitor_or_alternative=excluded.competitor_or_alternative, current_solution=excluded.current_solution, differentiation_note=excluded.differentiation_note,
                    score=excluded.score, updated_by=excluded.updated_by, updated_at=excluded.updated_at
            ''', (
                opp_id, metrics_identified, metrics_note, estimated_impact, success_metric,
                economic_buyer_identified, economic_buyer_name, economic_buyer_title, economic_buyer_access_level,
                decision_criteria, technical_criteria, business_criteria, compliance_criteria,
                decision_process_known, decision_timeline, approval_process, procurement_involved, target_decision_date,
                primary_pain, business_challenge, pain_severity, pain_validated,
                champion_identified, champion_name, champion_role, champion_strength,
                competitor, current_sol, diff_note, score, g.crm_user['id'], now_str, now_str
            ))
            
            # Sync score to Opp table
            db_execute("UPDATE opportunities SET meddic_score = ? WHERE id = ?", (score, opp_id))
            
            log_timeline_activity('opportunity', opp_id, 'MEDDIC updated', f"MEDDIC updated - Score: {score} ({label})", "", g.crm_user['id'])
            flash("MEDDIC qualifications updated.", "success")
            return redirect(url_for('crm.crm_opportunity_detail', opp_id=opp_id))
            
        elif action == 'add_task':
            title = request.form.get('task_title')
            task_type = request.form.get('task_type')
            due_date = request.form.get('due_date')
            due_time = request.form.get('due_time')
            priority = request.form.get('priority', 'Medium')
            desc = request.form.get('task_description')
            
            task_id = db_execute('''
                INSERT INTO crm_tasks (title, description, task_type, related_entity_type, related_entity_id, opportunity_id, assigned_to, created_by, due_date, due_time, priority, status, created_at, updated_at)
                VALUES (?, ?, ?, 'opportunity', ?, ?, ?, ?, ?, ?, ?, 'Open', ?, ?)
            ''', (title, desc, task_type, opp_id, opp_id, opp['owner_id'] or g.crm_user['id'], g.crm_user['id'], due_date, due_time, priority, now_str, now_str))
            
            log_timeline_activity('opportunity', opp_id, 'Task created', f"Task Created: {title}", f"Type: {task_type}, Due: {due_date}", g.crm_user['id'], related_task_id=task_id)
            flash("Task added successfully.", "success")
            return redirect(url_for('crm.crm_opportunity_detail', opp_id=opp_id))
            
        elif action == 'log_email':
            to_email = request.form.get('to_email')
            cc = request.form.get('cc')
            subject = request.form.get('subject')
            body = request.form.get('body')
            
            db_execute('''
                INSERT INTO crm_email_logs (entity_type, entity_id, opportunity_id, sender_user_id, to_email, cc, subject, body, status, sent_at, created_at)
                VALUES ('opportunity', ?, ?, ?, ?, ?, ?, ?, 'Sent', ?, ?)
            ''', (opp_id, opp_id, g.crm_user['id'], to_email, cc, subject, body, now_str, now_str))
            
            log_timeline_activity('opportunity', opp_id, 'Email sent', f"Email Sent: {subject}", body[:150], g.crm_user['id'])
            flash("Email logged and sent.", "success")
            return redirect(url_for('crm.crm_opportunity_detail', opp_id=opp_id))

    meddic = db_query_one("SELECT * FROM meddic_qualifications WHERE entity_type = 'opportunity' AND entity_id = ?", (opp_id,))
    if not meddic:
        db_execute("INSERT OR IGNORE INTO meddic_qualifications (entity_type, entity_id, created_at, updated_at) VALUES ('opportunity', ?, ?, ?)", (opp_id, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
        meddic = db_query_one("SELECT * FROM meddic_qualifications WHERE entity_type = 'opportunity' AND entity_id = ?", (opp_id,))
        
    meddic_score_label = "Weak"
    if meddic:
        score = meddic.get('score', 0)
        if score >= 70:
            meddic_score_label = "Strong"
        elif score >= 40:
            meddic_score_label = "Developing"
            
    timeline = db_query("SELECT t.*, u.name as user_name FROM timeline_activities t LEFT JOIN crm_users u ON t.created_by = u.id WHERE t.opportunity_id = ? ORDER BY t.id DESC", (opp_id,))
    tasks = db_query("SELECT t.*, u.name as assigned_name FROM crm_tasks t LEFT JOIN crm_users u ON t.assigned_to = u.id WHERE t.opportunity_id = ? ORDER BY t.due_date ASC, t.id DESC", (opp_id,))
    emails = db_query("SELECT e.*, u.name as sender_name FROM crm_email_logs e LEFT JOIN crm_users u ON e.sender_user_id = u.id WHERE e.opportunity_id = ? ORDER BY e.id DESC", (opp_id,))
    
    products_list = db_query("SELECT id, name FROM product_solutions WHERE is_active = 1")
    partners_list = db_query("SELECT id, name FROM partners WHERE is_active = 1")
    owners = db_query("SELECT id, name FROM crm_users WHERE is_active = 1 AND role != 'Telecaller'")
    managers = db_query("SELECT id, name FROM crm_users WHERE is_active = 1 AND role IN ('Manager / Sales Manager', 'Sales Head', 'Platform Admin')")
    
    return render_template(
        'opportunities/detail.html',
        opp=opp,
        meddic=meddic,
        meddic_label=meddic_score_label,
        timeline=timeline,
        tasks=tasks,
        emails=emails,
        products=products_list,
        partners=partners_list,
        owners=owners,
        managers=managers,
        active_page='crm_opportunities'
    )

# Quick opportunity stage update endpoint
@crm_bp.route('/api/crm/opportunities/<int:opp_id>/stage', methods=['POST'])
@crm_login_required
def update_opportunity_stage(opp_id):
    where_clause, params = get_visibility_where_clause()
    opp = db_query_one(f"SELECT id, stage FROM opportunities WHERE id = ? AND {where_clause}", [opp_id] + params)
    
    if not opp:
        return jsonify({'status': 'error', 'message': 'Opportunity not found or access denied.'}), 404
        
    data = request.get_json()
    stage = data.get('stage')
    
    # Map buckets
    bucket = 'Prospecting'
    if stage in ('Prospecting', 'Discovery'):
        bucket = 'Prospecting'
    elif stage in ('Solution Fit',):
        bucket = 'Qualifying'
    elif stage in ('Proposal',):
        bucket = 'Proposal'
    elif stage in ('Negotiation',):
        bucket = 'Negotiating'
    elif stage in ('Closing', 'Closed Won', 'Closed Lost'):
        bucket = 'Closing'
        
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    closed_at = now_str if 'Closed' in stage else None
    
    db_execute("UPDATE opportunities SET stage = ?, bucket = ?, closed_at = ?, updated_at = ? WHERE id = ?", (stage, bucket, closed_at, now_str, opp_id))
    log_timeline_activity('opportunity', opp_id, 'Opportunity stage updated', f"Stage updated to: {stage}", f"Updated via pipeline board.", g.crm_user['id'])
    
    return jsonify({'status': 'success', 'stage': stage, 'bucket': bucket})

# ----------------------------------------------------
# CRM Tasks Listing
# ----------------------------------------------------
@crm_bp.route('/crm/tasks', methods=['GET', 'POST'])
@crm_login_required
def crm_tasks():
    user = g.crm_user
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    if request.method == 'POST':
        title = request.form.get('title')
        task_type = request.form.get('task_type')
        due_date = request.form.get('due_date')
        due_time = request.form.get('due_time')
        priority = request.form.get('priority', 'Medium')
        desc = request.form.get('description')
        assigned_to = request.form.get('assigned_to') or user['id']
        
        task_id = db_execute('''
            INSERT INTO crm_tasks (title, description, task_type, assigned_to, created_by, due_date, due_time, priority, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Open', ?, ?)
        ''', (title, desc, task_type, assigned_to, user['id'], due_date, due_time, priority, now_str, now_str))
        
        flash("Task created successfully.", "success")
        return redirect(url_for('crm.crm_tasks'))
        
    # Read tasks visible to user
    role = user['role']
    if role == 'Platform Admin':
        tasks = db_query('''
            SELECT t.*, u.name as assigned_name, creator.name as creator_name, l.full_name as lead_name, o.opportunity_name 
            FROM crm_tasks t 
            LEFT JOIN crm_users u ON t.assigned_to = u.id 
            LEFT JOIN crm_users creator ON t.created_by = creator.id 
            LEFT JOIN leads l ON t.lead_id = l.id 
            LEFT JOIN opportunities o ON t.opportunity_id = o.id 
            ORDER BY t.due_date ASC, t.id DESC
        ''')
    elif role in ('Group Admin', 'Sales Head'):
        tasks = db_query('''
            SELECT t.*, u.name as assigned_name, creator.name as creator_name, l.full_name as lead_name, o.opportunity_name 
            FROM crm_tasks t 
            LEFT JOIN crm_users u ON t.assigned_to = u.id 
            LEFT JOIN crm_users creator ON t.created_by = creator.id 
            LEFT JOIN leads l ON t.lead_id = l.id 
            LEFT JOIN opportunities o ON t.opportunity_id = o.id 
            WHERE u.group_id = ?
            ORDER BY t.due_date ASC, t.id DESC
        ''', (user['group_id'],))
    elif role == 'Manager / Sales Manager':
        tasks = db_query('''
            SELECT t.*, u.name as assigned_name, creator.name as creator_name, l.full_name as lead_name, o.opportunity_name 
            FROM crm_tasks t 
            LEFT JOIN crm_users u ON t.assigned_to = u.id 
            LEFT JOIN crm_users creator ON t.created_by = creator.id 
            LEFT JOIN leads l ON t.lead_id = l.id 
            LEFT JOIN opportunities o ON t.opportunity_id = o.id 
            WHERE t.assigned_to = ? OR t.assigned_to IN (SELECT id FROM crm_users WHERE manager_id = ?)
            ORDER BY t.due_date ASC, t.id DESC
        ''', (user['id'], user['id']))
    else:
        tasks = db_query('''
            SELECT t.*, u.name as assigned_name, creator.name as creator_name, l.full_name as lead_name, o.opportunity_name 
            FROM crm_tasks t 
            LEFT JOIN crm_users u ON t.assigned_to = u.id 
            LEFT JOIN crm_users creator ON t.created_by = creator.id 
            LEFT JOIN leads l ON t.lead_id = l.id 
            LEFT JOIN opportunities o ON t.opportunity_id = o.id 
            WHERE t.assigned_to = ? 
            ORDER BY t.due_date ASC, t.id DESC
        ''', (user['id'],))
        
    owners = db_query("SELECT id, name FROM crm_users WHERE is_active = 1 AND role != 'Telecaller'")
    return render_template('tasks.html', tasks=tasks, owners=owners, active_page='crm_tasks')

@crm_bp.route('/api/crm/tasks/<int:task_id>/complete', methods=['POST'])
@crm_login_required
def complete_task(task_id):
    user = g.crm_user
    task = db_query_one("SELECT * FROM crm_tasks WHERE id = ?", (task_id,))
    if not task:
        return jsonify({'status': 'error', 'message': 'Task not found.'}), 404
        
    # Check permissions (only assigned user, manager, or admin)
    if user['role'] != 'Platform Admin' and task['assigned_to'] != user['id']:
        # check manager
        assigned_user = db_query_one("SELECT manager_id FROM crm_users WHERE id = ?", (task['assigned_to'],))
        if not assigned_user or assigned_user['manager_id'] != user['id']:
            return jsonify({'status': 'error', 'message': 'Access denied.'}), 403
            
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    db_execute("UPDATE crm_tasks SET status = 'Completed', completed_at = ?, updated_at = ? WHERE id = ?", (now_str, now_str, task_id))
    
    # Log to timeline if linked
    if task['lead_id']:
        log_timeline_activity('lead', task['lead_id'], 'Task completed', f"Task completed: {task['title']}", "", user['id'], related_task_id=task_id)
    elif task['opportunity_id']:
        log_timeline_activity('opportunity', task['opportunity_id'], 'Task completed', f"Task completed: {task['title']}", "", user['id'], related_task_id=task_id)
    elif task['telecrm_contact_id']:
        log_timeline_activity('telecrm_contact', task['telecrm_contact_id'], 'Task completed', f"Task completed: {task['title']}", "", user['id'], related_task_id=task_id)
        
    return jsonify({'status': 'success'})

# ============================================================
#  WEBSITE LEADS ROUTES
# ============================================================

@crm_bp.route('/crm/website-leads')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager', 'Sales User', 'Read-Only User')
def crm_website_leads():
    # Visibility helper
    def get_website_leads_visibility_clause(table_prefix="wl"):
        role = g.crm_user.get('role')
        user_id = g.crm_user.get('id')
        group_id = g.crm_user.get('group_id')
        p = f"{table_prefix}." if table_prefix else ""
        if role == 'Platform Admin':
            return "1=1", []
        elif role in ('Group Admin', 'Sales Head'):
            return f"({p}assigned_owner_id IS NULL OR {p}assigned_owner_id IN (SELECT id FROM crm_users WHERE group_id = ?))", [group_id]
        elif role == 'Manager / Sales Manager':
            return f"({p}assigned_owner_id = ? OR {p}assigned_owner_id IN (SELECT id FROM crm_users WHERE manager_id = ?) OR ({p}assigned_owner_id IS NULL AND {p}geography IN (SELECT geography FROM crm_users WHERE id = ?)))", [user_id, user_id, user_id]
        elif role == 'Sales User':
            return f"{p}assigned_owner_id = ?", [user_id]
        else:
            return "1=0", []

    where_clause, params = get_website_leads_visibility_clause("wl")
    
    # Filters
    status = request.args.get('status')
    source_form = request.args.get('source_form')
    source_page = request.args.get('source_page')
    industry = request.args.get('industry')
    geography = request.args.get('geography')
    product = request.args.get('product')
    partner = request.args.get('partner')
    utm_campaign = request.args.get('utm_campaign')
    duplicate_status = request.args.get('duplicate_status')
    owner_id = request.args.get('owner_id')
    unassigned = request.args.get('unassigned')
    converted = request.args.get('converted')
    rejected = request.args.get('rejected')
    spam = request.args.get('spam')
    
    # Search
    search = request.args.get('search', '').strip()
    
    filters = []
    if status:
        filters.append("wl.status = ?")
        params.append(status)
    if source_form:
        filters.append("wl.source_form = ?")
        params.append(source_form)
    if source_page:
        filters.append("wl.source_page LIKE ?")
        params.append(f"%{source_page}%")
    if industry:
        filters.append("wl.industry = ?")
        params.append(industry)
    if geography:
        filters.append("wl.geography = ?")
        params.append(geography)
    if product:
        filters.append("wl.product_solution_interest LIKE ?")
        params.append(f"%{product}%")
    if partner:
        filters.append("wl.partner_interest LIKE ?")
        params.append(f"%{partner}%")
    if utm_campaign:
        filters.append("wl.utm_campaign = ?")
        params.append(utm_campaign)
    if duplicate_status:
        filters.append("wl.duplicate_status = ?")
        params.append(duplicate_status)
    if owner_id:
        filters.append("wl.assigned_owner_id = ?")
        params.append(int(owner_id))
    if unassigned == '1':
        filters.append("wl.assigned_owner_id IS NULL")
    if converted == '1':
        filters.append("wl.status = 'Converted to Contact'")
    if rejected == '1':
        filters.append("wl.status = 'Rejected'")
    if spam == '1':
        filters.append("wl.status = 'Spam'")
        
    if search:
        filters.append("(wl.full_name LIKE ? OR wl.business_email LIKE ? OR wl.phone LIKE ? OR wl.company LIKE ? OR wl.source_page LIKE ? OR wl.message LIKE ?)")
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param, search_param, search_param, search_param])
        
    if filters:
        where_clause += " AND " + " AND ".join(filters)
        
    query = f'''
        SELECT wl.*, u.name as owner_name 
        FROM website_leads wl
        LEFT JOIN crm_users u ON wl.assigned_owner_id = u.id
        WHERE {where_clause}
        ORDER BY wl.id DESC
    '''
    leads = db_query(query, params)
    
    # Filter dropdown lists
    statuses = ['New', 'Reviewed', 'Assigned', 'Converted to Contact', 'Rejected', 'Duplicate', 'Spam']
    source_forms = db_query("SELECT DISTINCT source_form FROM website_leads WHERE source_form != ''")
    geographies = db_query("SELECT DISTINCT geography FROM website_leads WHERE geography != ''")
    industries = db_query("SELECT DISTINCT industry FROM website_leads WHERE industry != ''")
    owners = db_query("SELECT id, name FROM crm_users WHERE is_active = 1 AND role != 'Telecaller'")
    
    return render_template(
        'crm/website_leads/list.html',
        leads=leads,
        statuses=statuses,
        source_forms=source_forms,
        geographies=geographies,
        industries=industries,
        owners=owners,
        active_page='crm_website_leads'
    )

@crm_bp.route('/crm/website-leads/<int:lead_id>', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager', 'Sales User', 'Read-Only User')
def crm_website_lead_detail(lead_id):
    lead = db_query_one('''
        SELECT wl.*, u.name as owner_name, creator.name as converted_by_name, c.full_name as crm_contact_name
        FROM website_leads wl
        LEFT JOIN crm_users u ON wl.assigned_owner_id = u.id
        LEFT JOIN crm_users creator ON wl.converted_by = creator.id
        LEFT JOIN contacts c ON wl.crm_contact_id = c.id
        WHERE wl.id = ?
    ''', (lead_id,))
    
    if not lead:
        flash("Staging website lead not found.", "error")
        return redirect(url_for('crm.crm_website_leads'))
        
    # Check duplicate suggestions
    from crm.models import detect_contact_duplicates
    duplicates = detect_contact_duplicates(
        email=lead['business_email'],
        phone=lead['phone'],
        company=lead['company'],
        first_name=lead['first_name'],
        last_name=lead['last_name']
    )
    
    # Fetch review logs
    logs = db_query('''
        SELECT rl.*, u.name as performed_by_name
        FROM website_lead_review_logs rl
        LEFT JOIN crm_users u ON rl.performed_by = u.id
        WHERE rl.website_lead_id = ?
        ORDER BY rl.id ASC
    ''', (lead_id,))
    
    owners = db_query("SELECT id, name FROM crm_users WHERE is_active = 1 AND role != 'Telecaller'")
    
    # Check if there are active assignment rules to show
    rules = db_query("SELECT id, rule_name FROM website_lead_assignment_rules WHERE is_active = 1")
    
    return render_template(
        'crm/website_leads/detail.html',
        lead=lead,
        duplicates=duplicates,
        logs=logs,
        owners=owners,
        rules=rules,
        active_page='crm_website_leads'
    )

# ============================================================
#  CONTACTS & ACCOUNTS ROUTES
# ============================================================

@crm_bp.route('/crm/contacts')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager', 'Sales User', 'Read-Only User')
def crm_contacts():
    where_clause, params = get_visibility_where_clause(table_prefix="c")
    
    geography = request.args.get('geography')
    source = request.args.get('source')
    owner_id = request.args.get('owner_id')
    search = request.args.get('search', '').strip()
    
    filters = []
    if geography:
        filters.append("c.geography = ?")
        params.append(geography)
    if source:
        filters.append("c.source = ?")
        params.append(source)
    if owner_id:
        filters.append("c.owner_id = ?")
        params.append(int(owner_id))
    if search:
        filters.append("(c.full_name LIKE ? OR c.email LIKE ? OR c.phone LIKE ? OR a.account_name LIKE ?)")
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param, search_param])
        
    if filters:
        where_clause += " AND " + " AND ".join(filters)
        
    query = f'''
        SELECT c.*, a.account_name as company_name, u.name as owner_name
        FROM contacts c
        LEFT JOIN accounts a ON c.account_id = a.id
        LEFT JOIN crm_users u ON c.owner_id = u.id
        WHERE {where_clause}
        ORDER BY c.id DESC
    '''
    contacts = db_query(query, params)
    
    geographies = db_query("SELECT DISTINCT geography FROM contacts WHERE geography != ''")
    sources = db_query("SELECT DISTINCT source FROM contacts WHERE source != ''")
    owners = db_query("SELECT id, name FROM crm_users WHERE is_active = 1 AND role != 'Telecaller'")
    
    return render_template(
        'crm/contacts/list.html',
        contacts=contacts,
        geographies=geographies,
        sources=sources,
        owners=owners,
        active_page='crm_contacts'
    )

@crm_bp.route('/crm/accounts')
@crm_login_required
@role_required('Platform Admin', 'Group Admin', 'Sales Head', 'Manager / Sales Manager', 'Sales User', 'Read-Only User')
def crm_accounts():
    where_clause, params = get_visibility_where_clause(table_prefix="a")
    
    industry = request.args.get('industry')
    geography = request.args.get('geography')
    owner_id = request.args.get('owner_id')
    search = request.args.get('search', '').strip()
    
    filters = []
    if industry:
        filters.append("a.industry = ?")
        params.append(industry)
    if geography:
        filters.append("a.geography = ?")
        params.append(geography)
    if owner_id:
        filters.append("a.owner_id = ?")
        params.append(int(owner_id))
    if search:
        filters.append("(a.account_name LIKE ? OR a.website LIKE ? OR a.domain LIKE ?)")
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param])
        
    if filters:
        where_clause += " AND " + " AND ".join(filters)
        
    query = f'''
        SELECT a.*, u.name as owner_name, (SELECT COUNT(*) FROM contacts c WHERE c.account_id = a.id) as contact_count
        FROM accounts a
        LEFT JOIN crm_users u ON a.owner_id = u.id
        WHERE {where_clause}
        ORDER BY a.id DESC
    '''
    accounts = db_query(query, params)
    
    industries = db_query("SELECT DISTINCT industry FROM accounts WHERE industry != ''")
    geographies = db_query("SELECT DISTINCT geography FROM accounts WHERE geography != ''")
    owners = db_query("SELECT id, name FROM crm_users WHERE is_active = 1 AND role != 'Telecaller'")
    
    return render_template(
        'crm/accounts/list.html',
        accounts=accounts,
        industries=industries,
        geographies=geographies,
        owners=owners,
        active_page='crm_accounts'
    )
