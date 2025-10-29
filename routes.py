import os
from flask import session, render_template, request, redirect, url_for, flash, send_file
from werkzeug.utils import secure_filename
from app import app, db
from flask_login import current_user, login_required
from models import Dataset
from auth import auth_bp
import pandas as pd
# REMOVED: from ydata_profiling import ProfileReport
from datetime import datetime

app.register_blueprint(auth_bp, url_prefix="/auth")

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('auth.login'))

@app.route('/dashboard')
@login_required
def dashboard():
    datasets = Dataset.query.filter_by(user_id=current_user.id).order_by(Dataset.uploaded_at.desc()).all()
    return render_template('dashboard.html', user=current_user, datasets=datasets)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{current_user.id}_{timestamp}_{filename}"
            
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            
            dataset = Dataset(
                user_id=current_user.id,
                filename=unique_filename,
                original_filename=filename,
                file_size=os.path.getsize(filepath)
            )
            db.session.add(dataset)
            db.session.commit()
            
            flash('File uploaded successfully!', 'success')
            return redirect(url_for('profile_dataset', dataset_id=dataset.id))
        else:
            flash('Invalid file type. Please upload CSV or Excel files.', 'error')
            return redirect(request.url)
    
    return render_template('upload.html', user=current_user)

@app.route('/profile/<int:dataset_id>')
@login_required
def profile_dataset(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)
    
    if dataset.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    if not dataset.profile_generated:
        try:
            # LAZY IMPORT - moved inside the function
            from ydata_profiling import ProfileReport
            
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], dataset.filename)
            
            file_ext = dataset.original_filename.lower().rsplit('.', 1)[-1]
            if file_ext == 'csv':
                df = pd.read_csv(filepath)
            elif file_ext in ['xlsx', 'xls']:
                df = pd.read_excel(filepath, engine='openpyxl' if file_ext == 'xlsx' else 'xlrd')
            else:
                raise ValueError(f'Unsupported file format: {file_ext}')
            
            profile = ProfileReport(df, title=f"Profile Report - {dataset.original_filename}", explorative=True)
            
            profile_filename = f"profile_{dataset.id}.html"
            profile_path = os.path.join(app.config['UPLOAD_FOLDER'], profile_filename)
            profile.to_file(profile_path)
            
            dataset.profile_generated = True
            dataset.profile_path = profile_filename
            db.session.commit()
            
            flash('Profile report generated successfully!', 'success')
        except Exception as e:
            flash(f'Error generating profile: {str(e)}', 'error')
            return redirect(url_for('dashboard'))
    
    return render_template('profile.html', dataset=dataset, user=current_user)

@app.route('/view_profile/<int:dataset_id>')
@login_required
def view_profile(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)
    
    if dataset.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    if not dataset.profile_generated:
        return redirect(url_for('profile_dataset', dataset_id=dataset_id))
    
    return render_template('view_report.html', dataset=dataset, user=current_user)

@app.route('/profile_report/<int:dataset_id>')
@login_required
def profile_report(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)
    
    if dataset.user_id != current_user.id:
        return "Access denied", 403
    
    if not dataset.profile_generated:
        return "Profile not generated", 404
    
    profile_path = os.path.join(app.config['UPLOAD_FOLDER'], dataset.profile_path)
    return send_file(profile_path)

@app.route('/delete/<int:dataset_id>', methods=['POST'])
@login_required
def delete_dataset(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)
    
    if dataset.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], dataset.filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        
        if dataset.profile_path:
            profile_path = os.path.join(app.config['UPLOAD_FOLDER'], dataset.profile_path)
            if os.path.exists(profile_path):
                os.remove(profile_path)
        
        db.session.delete(dataset)
        db.session.commit()
        flash('Dataset deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting dataset: {str(e)}', 'error')
    
    return redirect(url_for('dashboard'))
