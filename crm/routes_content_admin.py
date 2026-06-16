import json
import os
import hashlib
from flask import render_template, request, redirect, url_for, flash, jsonify, g
from datetime import datetime
from werkzeug.utils import secure_filename
from crm import crm_bp
from crm.auth import crm_login_required, role_required
from crm.models import db_query, db_query_one, db_execute

# Configure upload directories
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xlsx', 'xls', 'ppt', 'pptx', 'jpg', 'jpeg', 'png', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_hash(filepath):
    """Generate SHA256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# ============================================================================
# WHITEPAPERS MANAGEMENT
# ============================================================================

@crm_bp.route('/admin/resources/whitepapers', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin')
def admin_whitepapers():
    """Manage whitepapers - upload, edit, delete"""
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'upload':
            title = request.form.get('title', '').strip()
            slug = request.form.get('slug', '').strip().lower().replace(' ', '-')
            description = request.form.get('description', '').strip()
            category = request.form.get('category', '').strip()
            industry = request.form.get('industry', '').strip()
            author = request.form.get('author', '').strip()
            status = request.form.get('status', 'Published')
            featured = 1 if request.form.get('featured') == 'on' else 0
            
            if 'file' not in request.files:
                flash("No file selected.", "error")
                return redirect(url_for('crm.admin_whitepapers'))
            
            file = request.files['file']
            if file.filename == '' or not allowed_file(file.filename):
                flash("Invalid file type. Allowed: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, images", "error")
                return redirect(url_for('crm.admin_whitepapers'))
            
            if not slug:
                flash("Slug is required.", "error")
                return redirect(url_for('crm.admin_whitepapers'))
            
            # Check if slug already exists
            existing = db_query_one("SELECT id FROM whitepapers WHERE slug = ?", (slug,))
            if existing:
                flash("Whitepaper slug already exists.", "error")
                return redirect(url_for('crm.admin_whitepapers'))
            
            # Save file
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            filename = secure_filename(f"wp_{slug}_{datetime.now().timestamp()}.{file.filename.rsplit('.', 1)[1].lower()}")
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(file_path)
            
            file_size = os.path.getsize(file_path)
            file_hash = get_file_hash(file_path)
            file_url = f"/uploads/{filename}"
            
            # Insert into database
            db_execute('''
                INSERT INTO whitepapers (title, slug, description, category, industry, author, file_path, file_size, file_hash, status, featured, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, slug, description, category, industry, author, file_url, file_size, file_hash, status, featured, g.crm_user['email'], now_str, now_str))
            
            flash(f"Whitepaper '{title}' uploaded successfully.", "success")
            return redirect(url_for('crm.admin_whitepapers'))
        
        elif action == 'edit':
            wp_id = request.form.get('whitepaper_id')
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            category = request.form.get('category', '').strip()
            industry = request.form.get('industry', '').strip()
            author = request.form.get('author', '').strip()
            status = request.form.get('status', 'Published')
            featured = 1 if request.form.get('featured') == 'on' else 0
            
            db_execute('''
                UPDATE whitepapers 
                SET title=?, description=?, category=?, industry=?, author=?, status=?, featured=?, updated_by=?, updated_at=?
                WHERE id=?
            ''', (title, description, category, industry, author, status, featured, g.crm_user['email'], now_str, wp_id))
            
            flash("Whitepaper updated successfully.", "success")
            return redirect(url_for('crm.admin_whitepapers'))
        
        elif action == 'delete':
            wp_id = request.form.get('whitepaper_id')
            wp = db_query_one("SELECT file_path FROM whitepapers WHERE id = ?", (wp_id,))
            if wp:
                # Delete file
                if wp['file_path'] and wp['file_path'].startswith('/uploads/'):
                    file_to_delete = os.path.join(UPLOAD_FOLDER, wp['file_path'].replace('/uploads/', ''))
                    if os.path.exists(file_to_delete):
                        os.remove(file_to_delete)
                
                db_execute("DELETE FROM whitepapers WHERE id = ?", (wp_id,))
                flash("Whitepaper deleted successfully.", "success")
            
            return redirect(url_for('crm.admin_whitepapers'))
    
    whitepapers = db_query("SELECT * FROM whitepapers ORDER BY created_at DESC")
    return render_template('admin/whitepapers.html', whitepapers=whitepapers, active_page='admin_whitepapers')


# ============================================================================
# CASE STUDIES MANAGEMENT
# ============================================================================

@crm_bp.route('/admin/resources/case-studies', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin')
def admin_case_studies():
    """Manage case studies - upload, edit, delete"""
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'upload':
            title = request.form.get('title', '').strip()
            slug = request.form.get('slug', '').strip().lower().replace(' ', '-')
            client_name = request.form.get('client_name', '').strip()
            industry = request.form.get('industry', '').strip()
            solution_area = request.form.get('solution_area', '').strip()
            business_challenge = request.form.get('business_challenge', '').strip()
            solution_summary = request.form.get('solution_summary', '').strip()
            business_outcomes = request.form.get('business_outcomes', '').strip()
            status = request.form.get('status', 'Published')
            featured = 1 if request.form.get('featured') == 'on' else 0
            
            if 'pdf_file' not in request.files:
                flash("No PDF file selected.", "error")
                return redirect(url_for('crm.admin_case_studies'))
            
            pdf_file = request.files['pdf_file']
            if pdf_file.filename == '' or not pdf_file.filename.lower().endswith('.pdf'):
                flash("Invalid file. Please upload a PDF.", "error")
                return redirect(url_for('crm.admin_case_studies'))
            
            if not slug:
                flash("Slug is required.", "error")
                return redirect(url_for('crm.admin_case_studies'))
            
            # Check if slug already exists
            existing = db_query_one("SELECT id FROM case_studies WHERE slug = ?", (slug,))
            if existing:
                flash("Case study slug already exists.", "error")
                return redirect(url_for('crm.admin_case_studies'))
            
            # Save PDF
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            pdf_filename = secure_filename(f"cs_{slug}_{datetime.now().timestamp()}.pdf")
            pdf_path = os.path.join(UPLOAD_FOLDER, pdf_filename)
            pdf_file.save(pdf_path)
            
            pdf_size = os.path.getsize(pdf_path)
            pdf_hash = get_file_hash(pdf_path)
            pdf_url = f"/uploads/{pdf_filename}"
            
            # Insert into database
            db_execute('''
                INSERT INTO case_studies (title, slug, client_name, industry, solution_area, business_challenge, 
                    solution_summary, business_outcomes, pdf_file_path, pdf_file_hash, status, featured, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, slug, client_name, industry, solution_area, business_challenge, solution_summary, 
                  business_outcomes, pdf_url, pdf_hash, status, featured, now_str, now_str))
            
            flash(f"Case study '{title}' uploaded successfully.", "success")
            return redirect(url_for('crm.admin_case_studies'))
        
        elif action == 'edit':
            cs_id = request.form.get('case_study_id')
            title = request.form.get('title', '').strip()
            client_name = request.form.get('client_name', '').strip()
            industry = request.form.get('industry', '').strip()
            solution_area = request.form.get('solution_area', '').strip()
            business_challenge = request.form.get('business_challenge', '').strip()
            solution_summary = request.form.get('solution_summary', '').strip()
            business_outcomes = request.form.get('business_outcomes', '').strip()
            status = request.form.get('status', 'Published')
            featured = 1 if request.form.get('featured') == 'on' else 0
            
            db_execute('''
                UPDATE case_studies 
                SET title=?, client_name=?, industry=?, solution_area=?, business_challenge=?, 
                    solution_summary=?, business_outcomes=?, status=?, featured=?, updated_at=?
                WHERE id=?
            ''', (title, client_name, industry, solution_area, business_challenge, solution_summary, 
                  business_outcomes, status, featured, now_str, cs_id))
            
            flash("Case study updated successfully.", "success")
            return redirect(url_for('crm.admin_case_studies'))
        
        elif action == 'delete':
            cs_id = request.form.get('case_study_id')
            cs = db_query_one("SELECT pdf_file_path FROM case_studies WHERE id = ?", (cs_id,))
            if cs:
                # Delete PDF file
                if cs['pdf_file_path'] and cs['pdf_file_path'].startswith('/uploads/'):
                    file_to_delete = os.path.join(UPLOAD_FOLDER, cs['pdf_file_path'].replace('/uploads/', ''))
                    if os.path.exists(file_to_delete):
                        os.remove(file_to_delete)
                
                db_execute("DELETE FROM case_studies WHERE id = ?", (cs_id,))
                flash("Case study deleted successfully.", "success")
            
            return redirect(url_for('crm.admin_case_studies'))
    
    case_studies = db_query("SELECT * FROM case_studies ORDER BY created_at DESC")
    return render_template('admin/case_studies.html', case_studies=case_studies, active_page='admin_case_studies')


# ============================================================================
# BLOGS MANAGEMENT
# ============================================================================

@crm_bp.route('/admin/resources/blogs', methods=['GET', 'POST'])
@crm_login_required
@role_required('Platform Admin')
def admin_blogs():
    """Manage blog posts - create, edit, delete"""
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create' or action == 'edit':
            title = request.form.get('title', '').strip()
            slug = request.form.get('slug', '').strip().lower().replace(' ', '-')
            author = request.form.get('author', '').strip()
            excerpt = request.form.get('excerpt', '').strip()
            content = request.form.get('content', '').strip()
            category = request.form.get('category', '').strip()
            tags = request.form.get('tags', '').strip()
            status = request.form.get('status', 'Published')
            featured = 1 if request.form.get('featured') == 'on' else 0
            
            if not title or not slug or not content:
                flash("Title, slug, and content are required.", "error")
                return redirect(url_for('crm.admin_blogs'))
            
            # Handle featured image upload
            featured_image_path = None
            if 'featured_image' in request.files:
                featured_image = request.files['featured_image']
                if featured_image and featured_image.filename and allowed_file(featured_image.filename):
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    img_filename = secure_filename(f"blog_{slug}_{datetime.now().timestamp()}.{featured_image.filename.rsplit('.', 1)[1].lower()}")
                    img_path = os.path.join(UPLOAD_FOLDER, img_filename)
                    featured_image.save(img_path)
                    featured_image_path = f"/uploads/{img_filename}"
            
            if action == 'create':
                # Check if slug already exists
                existing = db_query_one("SELECT id FROM blogs WHERE slug = ?", (slug,))
                if existing:
                    flash("Blog slug already exists.", "error")
                    return redirect(url_for('crm.admin_blogs'))
                
                db_execute('''
                    INSERT INTO blogs (title, slug, author, excerpt, content, category, tags, featured_image_path, 
                        status, featured, created_by, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (title, slug, author, excerpt, content, category, tags, featured_image_path, 
                      status, featured, g.crm_user['email'], now_str, now_str))
                
                flash(f"Blog post '{title}' created successfully.", "success")
            
            elif action == 'edit':
                blog_id = request.form.get('blog_id')
                
                # If a new featured image is provided, use it; otherwise keep the old one
                if featured_image_path:
                    db_execute('''
                        UPDATE blogs 
                        SET title=?, slug=?, author=?, excerpt=?, content=?, category=?, tags=?, featured_image_path=?, 
                            status=?, featured=?, updated_by=?, updated_at=?
                        WHERE id=?
                    ''', (title, slug, author, excerpt, content, category, tags, featured_image_path, 
                          status, featured, g.crm_user['email'], now_str, blog_id))
                else:
                    db_execute('''
                        UPDATE blogs 
                        SET title=?, slug=?, author=?, excerpt=?, content=?, category=?, tags=?, 
                            status=?, featured=?, updated_by=?, updated_at=?
                        WHERE id=?
                    ''', (title, slug, author, excerpt, content, category, tags, status, featured, g.crm_user['email'], now_str, blog_id))
                
                flash("Blog post updated successfully.", "success")
            
            return redirect(url_for('crm.admin_blogs'))
        
        elif action == 'delete':
            blog_id = request.form.get('blog_id')
            blog = db_query_one("SELECT featured_image_path FROM blogs WHERE id = ?", (blog_id,))
            if blog:
                # Delete featured image if exists
                if blog['featured_image_path'] and blog['featured_image_path'].startswith('/uploads/'):
                    file_to_delete = os.path.join(UPLOAD_FOLDER, blog['featured_image_path'].replace('/uploads/', ''))
                    if os.path.exists(file_to_delete):
                        os.remove(file_to_delete)
                
                db_execute("DELETE FROM blogs WHERE id = ?", (blog_id,))
                flash("Blog post deleted successfully.", "success")
            
            return redirect(url_for('crm.admin_blogs'))
    
    blogs = db_query("SELECT * FROM blogs ORDER BY created_at DESC")
    return render_template('admin/blogs.html', blogs=blogs, active_page='admin_blogs')
