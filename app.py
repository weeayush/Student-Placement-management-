# app.py
import os
from datetime import date, datetime
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Optional
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import text
from functools import wraps
from flask import abort
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import OperationalError, ProgrammingError


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'rgsoipl_placement_secret')

# POSTGRESQL CONFIGURATION
db_url = os.environ.get('DATABASE_URL', 'postgresql://postgres:password@localhost/rgsoipl_alumni')

# Render uses 'postgres://' which SQLAlchemy 3.x rejects; fix prefix automatically
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url


#  mysql set up ( enable it to check working on localhost set up )
# app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
#     'DATABASE_URL', 
#     'mysql+pymysql://root:Ayush%40123@localhost/rgsoipl_alumni'
# )

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='staff')  # 'admin', 'staff', 'viewer')
    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)
    
class Alumni(db.Model):
    __tablename__ = 'alumni'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    course = db.Column(db.String(50), nullable=False)
    batch = db.Column(db.String(20), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    organization = db.Column(db.String(150), nullable=False)
    position = db.Column(db.String(100), nullable=False)
    area_of_interest = db.Column(db.String(100), nullable=False)
    open_to_hiring = db.Column(db.String(10), nullable=False) 
    conversation_remarks = db.Column(db.Text, nullable=True) 

    recruiters_referred = db.relationship('Recruiter', backref='referred_by', lazy=True, cascade="all, delete-orphan")
    employment_history = db.relationship('EmploymentHistory', backref='alumni', lazy=True, cascade="all, delete-orphan", order_by='desc(EmploymentHistory.changed_on)')
    progress_logs = db.relationship('PlacementProgress', backref='alumni', lazy=True, cascade="all, delete-orphan", order_by='desc(PlacementProgress.action_date)')

class EmploymentHistory(db.Model):
    __tablename__ = 'employment_history'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    alumni_id = db.Column(db.Integer, db.ForeignKey('alumni.id'), nullable=False)
    organization = db.Column(db.String(150), nullable=False)
    position = db.Column(db.String(100), nullable=False)
    changed_on = db.Column(db.Date, nullable=False, default=date.today)

class RecruiterProgress(db.Model):
    __tablename__ = 'recruiter_progress'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    recruiter_id = db.Column(db.Integer, db.ForeignKey('recruiter.id'), nullable=False)
    action_date = db.Column(db.Date, nullable=False, default=date.today)
    action_text = db.Column(db.Text, nullable=False)

class Recruiter(db.Model):
    __tablename__ = 'recruiter'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # Changed nullable=True to allow direct recruiter entry without IntegrityError
    alumni_id = db.Column(db.Integer, db.ForeignKey('alumni.id'), nullable=True)
    company_name = db.Column(db.String(150), nullable=False)
    contact_name = db.Column(db.String(100), nullable=False)
    contact_email = db.Column(db.String(100), nullable=False)
    contact_phone = db.Column(db.String(20), nullable=False)
    hiring_remarks = db.Column(db.Text, nullable=True) 
    reference_date = db.Column(db.Date, nullable=False, default=date.today)
    
    progress_logs = db.relationship('RecruiterProgress', backref='recruiter', lazy=True, cascade="all, delete-orphan", order_by='desc(RecruiterProgress.action_date)')

class PlacementProgress(db.Model):
    __tablename__ = 'placement_progress'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    alumni_id = db.Column(db.Integer, db.ForeignKey('alumni.id'), nullable=False)
    action_date = db.Column(db.Date, nullable=False, default=date.today)
    action_text = db.Column(db.Text, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.role != 'admin':
            flash('You do not have permission to access that page.')
            if current_user.role == 'viewer':
                return redirect(url_for('recruiters_dashboard'))
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def full_access_required(f):
    """Blocks the read-only 'viewer' role from staff/admin pages."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.role == 'viewer':
            flash('Your account only has viewing access to the Recruiters Dashboard.')
            return redirect(url_for('recruiters_dashboard'))
        return f(*args, **kwargs)
    return decorated

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class AlumniForm(FlaskForm):
    name = StringField('Alumni Name', validators=[DataRequired()])
    course = SelectField('Course', choices=[('LLB (3 Years)', 'LLB (3 Years)'), ('LLM (2 Years)', 'LLM (2 Years)')], validators=[DataRequired()])
    batch = StringField('Batch (e.g., 2006-2009)', validators=[DataRequired()])
    phone = StringField('Phone Number', validators=[DataRequired()])
    email = StringField('Email ID', validators=[DataRequired()])
    organization = StringField('Organization/Company', validators=[DataRequired()])
    position = StringField('Position/Designation', validators=[DataRequired()])
    area_of_interest = StringField('Area of Interest/Practice', validators=[DataRequired()])
    open_to_hiring = SelectField('Open to Hiring / Connect to HR?', choices=[('Yes', 'Yes'), ('No', 'No')], validators=[DataRequired()])
    conversation_remarks = TextAreaField('Conversation / Outreach Remarks', validators=[Optional()])
    submit = SubmitField('Save Alumni Profile')

class RecruiterForm(FlaskForm):
    company_name = StringField('Recruiting Company Name', validators=[DataRequired()])
    contact_name = StringField('HR/Contact Person Name', validators=[DataRequired()])
    contact_email = StringField('Contact Email', validators=[DataRequired()])
    contact_phone = StringField('Contact Phone Number', validators=[DataRequired()])
    hiring_remarks = TextAreaField('Specific Hiring Remarks / Requirements', validators=[Optional()])
    submit = SubmitField('Save Recruiter Details')

class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password (leave blank to keep unchanged)', validators=[Optional()])
    role = SelectField('Access Level', choices=[
        ('staff', 'Full Access (Temporary Staff)'),
        ('viewer', 'Recruiter Dashboard Viewer (read-only)')
    ], validators=[DataRequired()])
    submit = SubmitField('Save User')

@app.route('/', methods=['GET'])
@login_required
@full_access_required
def dashboard():
    search_name = request.args.get('name', '').strip()
    filter_batch = request.args.get('batch', '').strip()
    filter_interest = request.args.get('interest_area', '').strip()
    filter_hiring = request.args.get('open_to_hiring', '').strip()

    query = Alumni.query.options(
        selectinload(Alumni.employment_history),
        selectinload(Alumni.progress_logs),
        selectinload(Alumni.recruiters_referred)
    )

    if search_name:
        query = query.filter(Alumni.name.ilike(f'%{search_name}%'))
    if filter_batch:
        query = query.filter(Alumni.batch == filter_batch)
    if filter_interest:
        query = query.filter(Alumni.area_of_interest == filter_interest)
    if filter_hiring:
        query = query.filter(Alumni.open_to_hiring == filter_hiring)

    alumni_records = query.order_by(Alumni.name).all()
    
    all_batches = [b[0] for b in db.session.query(Alumni.batch.distinct()).all() if b[0]]
    all_interests = [i[0] for i in db.session.query(Alumni.area_of_interest.distinct()).all() if i[0]]

    return render_template('dashboard.html', alumni=alumni_records, all_batches=all_batches, all_interests=all_interests)

@app.route('/recruiters', methods=['GET'])
@login_required
def recruiters_dashboard():
    filter_company = request.args.get('company_name', '').strip()

    query = Recruiter.query.options(
        joinedload(Recruiter.referred_by),
        selectinload(Recruiter.progress_logs)
    )

    if filter_company:
        query = query.filter(Recruiter.company_name == filter_company)

    recruiter_list = query.order_by(Recruiter.company_name).all()
    all_companies = [c[0] for c in db.session.query(Recruiter.company_name.distinct()).all() if c[0]]

    return render_template('recruiters.html', recruiters=recruiter_list, all_companies=all_companies)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            if user.role == 'viewer':
                return redirect(url_for('recruiters_dashboard'))
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add', methods=['GET', 'POST'])
@login_required
@full_access_required
def add_alumni():
    form = AlumniForm()
    if form.validate_on_submit():
        new_alumni = Alumni(
            name=form.name.data, course=form.course.data, batch=form.batch.data,
            phone=form.phone.data, email=form.email.data, organization=form.organization.data,
            position=form.position.data, area_of_interest=form.area_of_interest.data,
            open_to_hiring=form.open_to_hiring.data, conversation_remarks=form.conversation_remarks.data
        )
        db.session.add(new_alumni)
        db.session.commit()
        flash(f'{new_alumni.name} added successfully.')
        return redirect(url_for('dashboard'))
    return render_template('alumni_form.html', form=form, title="Register New Alumni")

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@full_access_required
def edit_alumni(id):
    alumni = Alumni.query.get_or_404(id)
    form = AlumniForm(obj=alumni)
    
    if form.validate_on_submit():
        if alumni.organization != form.organization.data or alumni.position != form.position.data:
            history_log = EmploymentHistory(
                alumni_id=alumni.id,
                organization=alumni.organization,
                position=alumni.position,
                changed_on=date.today()
            )
            db.session.add(history_log)

        form.populate_obj(alumni)
        db.session.commit()
        flash(f'Details for {alumni.name} updated successfully.')
        return redirect(url_for('dashboard'))
        
    return render_template('alumni_form.html', form=form, title=f"Edit Details: {alumni.name}")

@app.route('/add_recruiters/<int:alumni_id>', methods=['GET', 'POST'])
@login_required
@full_access_required
def add_recruiters(alumni_id):
    alumni = Alumni.query.get_or_404(alumni_id)
    form = RecruiterForm()

    if form.validate_on_submit():
        new_recruiter = Recruiter(
            alumni_id=alumni.id,
            company_name=form.company_name.data,
            contact_name=form.contact_name.data,
            contact_email=form.contact_email.data,
            contact_phone=form.contact_phone.data,
            hiring_remarks=form.hiring_remarks.data,
            reference_date=date.today()
        )
        db.session.add(new_recruiter)
        db.session.commit()
        flash(f'Recruiter {new_recruiter.company_name} added via {alumni.name}!')
        return redirect(url_for('recruiters_dashboard'))

    return render_template('hiring_form.html', form=form, alumni=alumni, title="Add Recruiter Reference")

@app.route('/add_progress/<int:alumni_id>', methods=['POST'])
@login_required
@full_access_required
def add_progress(alumni_id):
    alumni = Alumni.query.get_or_404(alumni_id)
    action_text = request.form.get('action_text')
    
    if action_text:
        new_progress = PlacementProgress(alumni_id=alumni.id, action_text=action_text)
        db.session.add(new_progress)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/add_recruiters_progress/<int:recruiter_id>', methods=['POST'])
@login_required
@full_access_required
def add_recruiters_progress(recruiter_id):
    recruiter = Recruiter.query.get_or_404(recruiter_id)
    action_text = request.form.get('action_text')
    
    if action_text:
        new_progress = RecruiterProgress(recruiter_id=recruiter.id, action_text=action_text)
        db.session.add(new_progress)
        db.session.commit()
    return redirect(url_for('recruiters_dashboard'))

@app.route('/reset_alumni_progress/<int:alumni_id>', methods=['POST'])
@login_required
@full_access_required
def reset_alumni_progress(alumni_id):
    PlacementProgress.query.filter_by(alumni_id=alumni_id).delete()
    db.session.commit()
    flash('Alumni progress reset successfully.')
    return redirect(url_for('dashboard'))

@app.route('/edit_recruiters/<int:id>', methods=['GET', 'POST'])
@login_required
@full_access_required
def edit_recruiters(id):
    recruiter = Recruiter.query.get_or_404(id)
    form = RecruiterForm(obj=recruiter)
    
    if form.validate_on_submit():
        form.populate_obj(recruiter)
        db.session.commit()
        flash(f'Recruiter details for {recruiter.company_name} updated successfully.')
        return redirect(url_for('recruiters_dashboard'))
        
    return render_template('hiring_form.html', form=form, alumni=recruiter.referred_by, title=f"Edit Recruiter: {recruiter.company_name}")

@app.route('/add_recruiter_direct', methods=['GET', 'POST'])
@login_required
@full_access_required
def add_recruiter_direct():
    form = RecruiterForm()
    if form.validate_on_submit():
        new_recruiter = Recruiter(
            alumni_id=None,
            company_name=form.company_name.data,
            contact_name=form.contact_name.data,
            contact_email=form.contact_email.data,
            contact_phone=form.contact_phone.data,
            hiring_remarks=form.hiring_remarks.data,
            reference_date=date.today()
        )
        db.session.add(new_recruiter)
        db.session.commit()
        flash(f'Recruiter {new_recruiter.company_name} added successfully!')
        return redirect(url_for('recruiters_dashboard'))
    return render_template('hiring_form.html', form=form, alumni=None, title="Add Company Directly")

@app.route('/reset_recruiters_progress/<int:recruiter_id>', methods=['POST'])
@login_required
@full_access_required
def reset_recruiters_progress(recruiter_id):
    RecruiterProgress.query.filter_by(recruiter_id=recruiter_id).delete()
    db.session.commit()
    flash('Recruiter progress reset successfully.')
    return redirect(url_for('recruiters_dashboard'))

@app.route('/reset_all_recruiters_progress', methods=['POST'])
@login_required
@full_access_required
def reset_all_recruiters_progress():
    # POSTGRESQL NATIVE CASCADING DELETE
    db.session.execute(text("TRUNCATE TABLE recruiter_progress RESTART IDENTITY CASCADE;"))
    db.session.commit()
    flash('Progress logs for all companies have been reset successfully.')
    return redirect(url_for('recruiters_dashboard'))

@app.route('/delete_recruiter/<int:id>', methods=['POST'])
@login_required
@full_access_required
def delete_recruiter(id):
    recruiter = Recruiter.query.get_or_404(id)
    company_name = recruiter.company_name
    db.session.delete(recruiter)
    db.session.commit()
    flash(f'Recruiter {company_name} deleted successfully.')
    return redirect(url_for('recruiters_dashboard'))

@app.route('/users')
@login_required
@admin_required
def manage_users():
    users = User.query.filter(User.role != 'admin').order_by(User.username).all()
    return render_template('users.html', users=users)

@app.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    form = UserForm()
    if form.validate_on_submit():
        if not form.password.data:
            flash('A password is required when creating a new user.')
            return render_template('user_form.html', form=form, title="Create Temporary User")
        new_user = User(username=form.username.data, role=form.role.data)
        new_user.set_password(form.password.data)
        db.session.add(new_user)
        db.session.commit()
        flash(f'User {new_user.username} created successfully.')
        return redirect(url_for('manage_users'))
    if request.method == 'POST':
        print("FORM VALIDATION ERRORS:", form.errors)
    return render_template('user_form.html', form=form, title="Create Temporary User")

@app.route('/users/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    if user.role == 'admin':
        abort(403)
    form = UserForm(obj=user)
    if request.method == 'GET':
        form.password.data = ''
    if form.validate_on_submit():
        user.username = form.username.data
        user.role = form.role.data
        if form.password.data:
            user.set_password(form.password.data)
        db.session.commit()
        flash(f'User {user.username} updated successfully.')
        return redirect(url_for('manage_users'))
    return render_template('user_form.html', form=form, title=f"Edit User: {user.username}")

@app.route('/users/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.role == 'admin':
        flash('Cannot delete the main admin account.')
        return redirect(url_for('manage_users'))
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'User {username} deleted successfully.')
    return redirect(url_for('manage_users'))

def init_db():
    with app.app_context():
        # Create all tables first
        db.create_all()
        try:
            # Check if admin exists
            if not User.query.filter_by(role='admin').first():
                admin_username = os.environ.get('ADMIN_USERNAME')
                admin_password = os.environ.get('ADMIN_PASSWORD')
                if admin_username and admin_password:
                    admin = User(username=admin_username, role='admin')
                    admin.set_password(admin_password)
                    db.session.add(admin)
                    db.session.commit()
                    print(f"Created main admin user: {admin_username}")
                else:
                    print("WARNING: no admin exists yet. Set ADMIN_USERNAME and ADMIN_PASSWORD env vars and restart.")
        except (ProgrammingError, OperationalError):
            # Prevents app crash if parallel Gunicorn workers query table before creation finishes
            db.session.rollback()
            print("Table setup skipped or already completed by another worker process.")

# Run database setup safely on startup
init_db()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')