from flask import Flask, render_template, request, redirect, session, url_for, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai
from google.genai import types
import os
import re
import json
import random
from authlib.integrations.flask_client import OAuth
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or "supersecretkey_production_fallback_key_2026"

IS_PRODUCTION = bool(
    os.environ.get("DATABASE_URL")
    or os.environ.get("RENDER")
    or os.environ.get("RAILWAY_ENVIRONMENT")
    or os.environ.get("FLASK_ENV") == "production"
)

# Session cookie security — applied to all environments
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

if IS_PRODUCTION:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["PREFERRED_URL_SCHEME"] = "https"


# Real-time configurable credentials with environment variables & secure fallback
import secrets
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

if not ADMIN_EMAIL:
    # Safe random fallback email
    ADMIN_EMAIL = f"admin_{secrets.token_hex(4)}@example.com"

if not ADMIN_PASSWORD:
    # Generate a random 24-character token so a local attacker cannot guess it if not configured
    ADMIN_PASSWORD = secrets.token_urlsafe(18)
    print(f" * SECURE WARNING: ADMIN_PASSWORD environment variable was not set.")
    print(f" * A random temporary password has been generated for this session: {ADMIN_PASSWORD}")


# Database URL configuration and fallback
db_url = os.environ.get("DATABASE_URL")
if db_url:
    # Resolve PostgreSQL connection scheme issue common on production environments like Render/Heroku
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
else:
    db_user = os.environ.get("DB_USER", "root")
    db_pass = os.environ.get("DB_PASSWORD", "1817")
    db_host = os.environ.get("DB_HOST", "localhost")
    db_name = os.environ.get("DB_NAME", "ai_interview_platform")
    db_url = f'mysql+pymysql://{db_user}:{db_pass}@{db_host}/{db_name}'

# Verify MySQL connection or fallback to SQLite
if db_url.startswith("mysql"):
    try:
        import pymysql
        match = re.match(r'mysql\+pymysql://([^:]+):([^@]+)@([^/:]+)(?::(\d+))?/([^?]+)', db_url)
        if match:
            user, password, host, port, db_name = match.groups()
            port = int(port) if port else 3306
            # Connect to MySQL server to ensure it is alive and create database if missing
            conn = pymysql.connect(
                host=host,
                user=user,
                password=password,
                port=port,
                connect_timeout=3
            )
            with conn.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
            conn.close()
            print(f"Verified/Created MySQL database '{db_name}' successfully.")
        else:
            raise ValueError("Invalid MySQL URI format")
    except Exception as e:
        print(f"MySQL database connection failed ({e}). Falling back to SQLite.")
        # Support Render persistent disk for SQLite fallback
        render_persistent_dir = "/var/data"
        if os.environ.get("RENDER") and os.path.exists(render_persistent_dir):
            db_url = f"sqlite:///{os.path.join(render_persistent_dir, 'ai_interview_platform.db')}"
        else:
            db_url = "sqlite:///ai_interview_platform.db"

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Production database connection pooling (prevents dead connection stalls on Render PostgreSQL)
if not db_url.startswith("sqlite"):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 280,
        'pool_timeout': 20,
        'max_overflow': 5
    }

db = SQLAlchemy(app)

# Performance optimization: static asset browser caching
@app.after_request
def add_performance_headers(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'
    return response

# Support Render persistent disk for file uploads
render_persistent_dir = "/var/data"
if os.environ.get("RENDER") and os.path.exists(render_persistent_dir):
    app.config['UPLOAD_FOLDER'] = os.path.join(render_persistent_dir, 'uploads')
else:
    app.config['UPLOAD_FOLDER'] = 'uploads'

app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB limit
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
ALLOWED_RESUME_EXTENSIONS = {'pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_resume_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_RESUME_EXTENSIONS


gemini_api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None
MODEL_NAME = "gemini-flash-lite-latest"


def analyze_attachment(file_bytes, mime_type, context_hint=""):
    try:
        prompt = "Analyze this file in the context of a job interview. " + context_hint + " Be factual and concise, 2-4 sentences only."
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                prompt
            ]
        )
        return response.text.strip()
    except Exception as e:
        print(f"[ATTACHMENT ANALYSIS ERROR] {e}")
        return "Could not analyze the attached file."


GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
has_google_oauth = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

oauth = OAuth(app)
if has_google_oauth:
    google = oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )
else:
    google = None


def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def profile_is_complete(user):
    if not user.gender:
        return False
    if getattr(user, 'user_type', None) == 'professional':
        return bool(user.current_designation and user.years_of_experience)
    return bool(user.education and user.course and user.semester)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=True)
    gender = db.Column(db.String(10))
    education = db.Column(db.String(50))
    course = db.Column(db.String(100))
    semester = db.Column(db.String(20))
    auth_provider = db.Column(db.String(20), default='local')
    email_verified = db.Column(db.Boolean, default=False)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    registered_at = db.Column(db.DateTime, server_default=db.func.now())
    user_type = db.Column(db.String(20), default='student')
    github_url = db.Column(db.String(200))
    linkedin_url = db.Column(db.String(200))
    skills = db.Column(db.Text)
    years_of_experience = db.Column(db.String(20))
    current_designation = db.Column(db.String(100))
    resume_text = db.Column(db.Text)
    resume_filename = db.Column(db.String(255))
    extra_allowed_interviews = db.Column(db.Integer, default=0)


class InterviewResult(db.Model):
    __tablename__ = 'interview_results'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    score = db.Column(db.Numeric(4, 2))
    status = db.Column(db.String(50))
    strengths = db.Column(db.Text)
    improvements = db.Column(db.Text)
    summary = db.Column(db.Text)
    domain = db.Column(db.String(150))
    is_terminated = db.Column(db.Boolean, default=False)
    termination_reason = db.Column(db.Text)
    interview_datetime = db.Column(db.DateTime, server_default=db.func.now())



class InterviewProgress(db.Model):
    __tablename__ = 'interview_progress'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    chat_history = db.Column(db.Text, default='[]')
    q_count = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())


class AdminSettings(db.Model):
    __tablename__ = 'admin_settings'
    id = db.Column(db.Integer, primary_key=True)
    min_questions = db.Column(db.Integer, default=3)
    max_questions = db.Column(db.Integer, default=8)
    pass_score = db.Column(db.Integer, default=3)
    default_difficulty = db.Column(db.String(20), default='student')
    question_timer_seconds = db.Column(db.Integer, default=90)
    enable_attempt_limits = db.Column(db.Boolean, default=True)
    default_allowed_interviews = db.Column(db.Integer, default=2)


_cached_settings = None
_cached_settings_time = 0


from flask import has_app_context


class SettingsSnapshot:
    def __init__(self, s=None):
        self.min_questions = getattr(s, 'min_questions', 3) or 3
        self.max_questions = getattr(s, 'max_questions', 8) or 8
        self.pass_score = getattr(s, 'pass_score', 3) or 3
        self.default_difficulty = getattr(s, 'default_difficulty', 'student') or 'student'
        self.question_timer_seconds = getattr(s, 'question_timer_seconds', 90) or 90
        self.enable_attempt_limits = getattr(s, 'enable_attempt_limits', True)
        if self.enable_attempt_limits is None:
            self.enable_attempt_limits = True
        self.default_allowed_interviews = getattr(s, 'default_allowed_interviews', 2) or 2


def get_settings():
    global _cached_settings, _cached_settings_time
    import time
    now = time.time()
    if _cached_settings and (now - _cached_settings_time) < 60:
        return _cached_settings

    try:
        settings_row = AdminSettings.query.first()
        if not settings_row:
            settings_row = AdminSettings(
                min_questions=3,
                max_questions=8,
                pass_score=3,
                default_difficulty='student',
                question_timer_seconds=90,
                enable_attempt_limits=True,
                default_allowed_interviews=2
            )
            db.session.add(settings_row)
            db.session.commit()
        snapshot = SettingsSnapshot(settings_row)
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        snapshot = SettingsSnapshot()

    _cached_settings = snapshot
    _cached_settings_time = now
    return snapshot

def save_progress(user_id, chat_history, q_count):
    try:
        progress = InterviewProgress.query.filter_by(user_id=user_id).first()
        if not progress:
            progress = InterviewProgress(user_id=user_id)
            db.session.add(progress)
        progress.chat_history = json.dumps(chat_history)
        progress.q_count = q_count
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        try:
            progress = InterviewProgress.query.filter_by(user_id=user_id).first()
            if progress:
                progress.chat_history = json.dumps(chat_history)
                progress.q_count = q_count
                db.session.commit()
        except Exception:
            db.session.rollback()


def clear_progress(user_id):
    try:
        InterviewProgress.query.filter_by(user_id=user_id).delete()
        db.session.commit()
    except Exception:
        db.session.rollback()


# ── Security headers injected on every response ────────────────────────────
@app.after_request
def apply_security_headers(response):
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.route("/")
def home():
    if "user_id" in session:
        return redirect("/dashboard")
    if session.get("is_admin"):
        return redirect("/admin")
    return render_template("index.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email or "@" not in email:
            return render_template("signup.html", error="Please enter a valid email address.", has_google_oauth=has_google_oauth)

        if User.query.filter_by(email=email).first():
            return render_template("signup.html", error="An account with this email already exists. Please login.", has_google_oauth=has_google_oauth)

        otp = str(random.randint(100000, 999999))
        session["reg_otp"] = otp
        session["pending_signup_email"] = email

        if send_otp_email(email, otp):
            return redirect("/auth/register/verify-otp")
        else:
            return render_template("signup.html", error="Failed to send OTP email. Please try again.", has_google_oauth=has_google_oauth)

    return render_template("signup.html", has_google_oauth=has_google_oauth, error=None)


@app.route("/auth/register/verify-otp", methods=["GET", "POST"])
def verify_register_otp():
    email = session.get("pending_signup_email") or session.get("email_otp_verified")
    if not email or "reg_otp" not in session:
        if session.get("email_otp_verified"):
            return redirect("/signup/set-password")
        return redirect("/signup")

    if request.method == "GET":
        return render_template("verify_otp.html", error=None, email=email, next_step="set_password")

    entered = (request.form.get("otp") or "").strip()
    if entered == session.get("reg_otp"):
        session.pop("reg_otp", None)
        session["email_otp_verified"] = email
        return redirect("/signup/set-password")

    return render_template("verify_otp.html", error="Invalid OTP. Please try again.", email=email, next_step="set_password")


@app.route("/signup/set-password", methods=["GET", "POST"])
def signup_set_password():
    email = session.get("email_otp_verified") or session.get("pending_signup_email")
    if not email:
        return redirect("/signup")

    if request.method == "POST":
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm_password", "").strip()

        if not password or len(password) < 6:
            return render_template("set_password.html", error="Password must be at least 6 characters.", email=email)
        if password != confirm:
            return render_template("set_password.html", error="Passwords do not match.", email=email)

        session["verified_signup_email"] = email
        session["verified_signup_password"] = generate_password_hash(password)
        return redirect("/register")

    return render_template("set_password.html", error=None, email=email)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email or "@" not in email:
            return render_template("forgot_password.html", error="Please enter a valid email address.")

        user = User.query.filter_by(email=email).first()
        if not user:
            return render_template("forgot_password.html", error="No account found with this email address.")

        otp = str(random.randint(100000, 999999))
        session["fp_otp"] = otp
        session["fp_email"] = email

        if send_otp_email(email, otp):
            return redirect("/forgot-password/verify")
        else:
            return render_template("forgot_password.html", error="Failed to send OTP. Please try again.")

    return render_template("forgot_password.html", error=None)


@app.route("/forgot-password/verify", methods=["GET", "POST"])
def forgot_password_verify():
    if "fp_otp" not in session or "fp_email" not in session:
        return redirect("/forgot-password")

    email = session["fp_email"]
    if request.method == "GET":
        return render_template("verify_otp.html", error=None, email=email, next_step="reset_password")

    entered = (request.form.get("otp") or "").strip()
    if entered == session.get("fp_otp"):
        session.pop("fp_otp", None)
        session["fp_verified_email"] = email
        session.pop("fp_email", None)
        return redirect("/forgot-password/reset")

    return render_template("verify_otp.html", error="Invalid OTP. Please try again.", email=email, next_step="reset_password")


@app.route("/forgot-password/reset", methods=["GET", "POST"])
def forgot_password_reset():
    email = session.get("fp_verified_email")
    if not email:
        return redirect("/forgot-password")

    if request.method == "POST":
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm_password", "").strip()

        if not password or len(password) < 6:
            return render_template("set_password.html", error="Password must be at least 6 characters.", email=email, is_reset=True)
        if password != confirm:
            return render_template("set_password.html", error="Passwords do not match.", email=email, is_reset=True)

        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(password)
            db.session.commit()
        session.pop("fp_verified_email", None)
        return redirect("/login?msg=password_reset")

    return render_template("set_password.html", error=None, email=email, is_reset=True)

@app.route("/register", methods=["GET", "POST"])
def register():
    is_google = request.args.get("google") == "1"

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        gender = request.form.get("gender")
        education = request.form.get("education")
        course = request.form.get("course")
        semester = request.form.get("semester")
        user_type = request.form.get("user_type", "student")
        github_url = request.form.get("github_url", "").strip() or None
        linkedin_url = request.form.get("linkedin_url", "").strip() or None
        skills = request.form.get("skills", "").strip() or None
        years_of_experience = request.form.get("years_of_experience", "").strip() or None
        current_designation = request.form.get("current_designation", "").strip() or None

        email = session.get("pending_google_email") or session.get("verified_signup_email")
        password = session.get("verified_signup_password")

        def render_register_error(error_msg):
            return render_template("register.html", error=error_msg,
                                   is_google=is_google, prefill_name=full_name, prefill_email=email or "",
                                   prefill_gender=gender, prefill_education=education, prefill_course=course,
                                   prefill_semester=semester, prefill_user_type=user_type,
                                   prefill_github_url=github_url, prefill_linkedin_url=linkedin_url,
                                   prefill_skills=skills, prefill_years_of_experience=years_of_experience,
                                   prefill_current_designation=current_designation)

        if not full_name:
            return render_register_error("Please fill in your full name.")

        if not gender:
            return render_register_error("Please select your gender.")

        existing_name = User.query.filter(User.full_name.ilike(full_name)).first()
        if existing_name and ("user_id" not in session or session.get("user_id") != existing_name.id):
            return render_register_error("This name is already taken. Please use a different name.")

        if user_type == "student":
            if not education:
                return render_register_error("Please select your education level.")
            if not course:
                return render_register_error("Please enter your course/branch.")
            if not semester:
                return render_register_error("Please enter your semester/year.")
        elif user_type == "professional":
            if not current_designation:
                return render_register_error("Please enter your current designation.")
            if not years_of_experience:
                return render_register_error("Please enter your years of experience.")

        # Logged-in user updating their profile
        if "user_id" in session:
            user = db.session.get(User, session["user_id"])
            if user:
                user.full_name = full_name
                user.gender = gender
                user.education = education
                user.course = course
                user.semester = semester
                user.user_type = user_type
                user.github_url = github_url
                user.linkedin_url = linkedin_url
                user.skills = skills
                user.years_of_experience = years_of_experience
                user.current_designation = current_designation
                db.session.commit()
                session["user_name"] = user.full_name
                return redirect("/dashboard")

        # Google OAuth new user
        if session.get("pending_google_email"):
            g_email = session.pop("pending_google_email")
            google_id = session.pop("pending_google_id", None)
            session.pop("pending_google_name", None)
            new_user = User(
                full_name=full_name, email=g_email, password=None,
                gender=gender, education=education, course=course, semester=semester,
                auth_provider="google", google_id=google_id, email_verified=True,
                user_type=user_type, github_url=github_url, linkedin_url=linkedin_url,
                skills=skills, years_of_experience=years_of_experience,
                current_designation=current_designation
            )
            db.session.add(new_user)
            db.session.commit()
            session["user_id"] = new_user.id
            session["user_name"] = new_user.full_name
            session["user_email"] = new_user.email
            return redirect("/dashboard")

        # Local signup (email verified via OTP, password already set)
        if session.get("verified_signup_email"):
            new_user = User(
                full_name=full_name, email=email, password=password,
                gender=gender, education=education, course=course, semester=semester,
                auth_provider="local", email_verified=True,
                user_type=user_type, github_url=github_url, linkedin_url=linkedin_url,
                skills=skills, years_of_experience=years_of_experience,
                current_designation=current_designation
            )
            db.session.add(new_user)
            db.session.commit()
            session.pop("verified_signup_email", None)
            session.pop("verified_signup_password", None)
            session["user_id"] = new_user.id
            session["user_name"] = new_user.full_name
            session["user_email"] = new_user.email
            return redirect("/dashboard")

        return redirect("/login")

    # GET
    if "user_id" in session:
        user = db.session.get(User, session["user_id"])
        prefill_name = user.full_name if user else ""
        prefill_email = (user.email if user else "") or session.get("pending_google_email", "")
        if user and user.auth_provider == "google":
            is_google = True
    else:
        prefill_name = session.get("pending_google_name", "")
        prefill_email = session.get("pending_google_email") or session.get("verified_signup_email", "")
        if not prefill_email:
            return redirect("/login")

    return render_template("register.html", is_google=is_google,
                           prefill_name=prefill_name, prefill_email=prefill_email, error=None)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not is_valid_email(email):
            return render_template("login.html", error="Please enter a valid email address.", has_google_oauth=has_google_oauth)

        # Admin check
        if ADMIN_EMAIL and email == ADMIN_EMAIL.strip().lower() and password == ADMIN_PASSWORD.strip():
            session.clear()
            session["is_admin"] = True
            session["user_name"] = "Admin"
            return redirect("/admin")

        user = User.query.filter_by(email=email).first()

        if not user:
            return render_template("login.html", show_signup_prompt=True, prefill_email=email, has_google_oauth=has_google_oauth)

        if user and user.password and check_password_hash(user.password, password):
            session.clear()
            session["user_id"] = user.id
            session["user_name"] = user.full_name
            session["user_email"] = user.email
            session["is_admin"] = False
            if not profile_is_complete(user):
                return redirect("/register")
            return redirect("/dashboard")
        else:
            return render_template("login.html", error="Invalid password. Please try again.", has_google_oauth=has_google_oauth)

    error_msg = None
    err_code = request.args.get("error")
    if err_code == "file_too_large":
        error_msg = "Uploaded file is too large. The maximum size limit is 10MB."
    elif err_code == "google_not_configured":
        error_msg = "Google Sign-in is not configured on this server."
    return render_template("login.html", error=error_msg, has_google_oauth=has_google_oauth)


@app.route("/auth/google")
def auth_google():
    if not has_google_oauth:
        return redirect("/login?error=google_not_configured")
    redirect_uri = url_for("auth_google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route("/auth/google/callback")

def auth_google_callback():
    if not has_google_oauth:
        return redirect("/login")
    token = google.authorize_access_token()
    user_info = token.get("userinfo")

    if not user_info:
        return redirect("/login")

    google_id = user_info["sub"]
    email = user_info["email"]
    name = user_info.get("name", email.split("@")[0])

    user = User.query.filter_by(google_id=google_id).first()

    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            user.google_id = google_id
            user.auth_provider = "google"
            user.email_verified = True
            db.session.commit()

    if user:
        session.clear()
        session["user_id"] = user.id
        session["user_name"] = user.full_name
        session["user_email"] = user.email
        if not profile_is_complete(user):
            session["pending_google_email"] = user.email
            return redirect("/register?google=1")
        return redirect("/dashboard")
    else:
        session["pending_google_email"] = email
        session["pending_google_name"] = name
        session["pending_google_id"] = google_id
        return redirect("/register?google=1")


@app.errorhandler(413)
def request_entity_too_large(error):
    if "user_id" in session:
        return redirect("/dashboard?error=file_too_large")
    return redirect("/login?error=file_too_large")

@app.errorhandler(500)
def internal_server_error(error):
    try:
        db.session.rollback()
    except Exception:
        pass
    print(f"[Internal Server Error]: {error}")
    # For AJAX/submit route — return JSON so interview can continue
    if request.path == "/interview/submit" or request.headers.get("Content-Type", "").startswith("application/json"):
        return jsonify({"error": "server_error", "question": "Can you walk me through a challenging problem you solved recently?", "q_num": session.get("q_count", 0) + 1, "total": 10, "question_type": "text", "done": False}), 200
    # For all other routes — return a simple inline error page (NO redirects to avoid loops)
    back_url = "/dashboard" if "user_id" in session else "/login"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Error</title>
    <style>body{{font-family:sans-serif;background:#0a0f1e;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;flex-direction:column;gap:16px}}
    h2{{color:#00ffff}}a{{color:#00ffff;font-weight:bold}}</style></head>
    <body><h2>⚠️ Something went wrong</h2>
    <p>A temporary server error occurred. Your interview progress is saved.</p>
    <a href="{back_url}">← Return to Dashboard</a></body></html>""", 500


@app.route("/dashboard")
def dashboard():
    if session.get("is_admin"):
        return redirect("/admin")
    if "user_id" not in session:
        return redirect("/login")

    current_user = db.session.get(User, session["user_id"])
    if not current_user:
        session.clear()
        return redirect("/login")

    if not profile_is_complete(current_user):
        return redirect("/register")

    latest_res = InterviewResult.query.filter_by(user_id=session["user_id"]).order_by(InterviewResult.interview_datetime.desc()).first()
    if latest_res and latest_res.is_terminated:
        clear_progress(session["user_id"])
        has_progress = False
    else:
        progress = InterviewProgress.query.filter_by(user_id=session["user_id"]).first()
        has_progress = bool(progress and progress.q_count > 0)

    recent_results = InterviewResult.query.filter(
        InterviewResult.user_id == session["user_id"],
        ~InterviewResult.status.like('%Practice%')
    ).order_by(InterviewResult.interview_datetime.desc()).limit(5).all()
    has_result = len(recent_results) > 0

    error_msg = None
    err_code = request.args.get("error")
    if err_code == "file_too_large":
        error_msg = "Uploaded file is too large. The maximum size limit is 10MB."
    elif err_code == "api_key_missing":
        error_msg = "AI Placement evaluation is not configured. Please set the GEMINI_API_KEY environment variable."

    # Check attempt limit status (for UI button state)
    settings = get_settings()
    is_locked = False
    if settings.enable_attempt_limits:
        attempts_used = InterviewResult.query.filter(
            InterviewResult.user_id == session["user_id"],
            ~InterviewResult.status.like('%Practice%')
        ).count()
        extra_granted = current_user.extra_allowed_interviews or 0 if current_user else 0
        allowed_total = (settings.default_allowed_interviews or 2) + extra_granted
        if attempts_used >= allowed_total:
            is_locked = True

    return render_template("dashboard.html", name=session["user_name"], user=current_user,
                           has_progress=has_progress, has_result=has_result,
                           recent_results=recent_results, error=error_msg,
                           is_locked=is_locked)


@app.route("/dashboard/update-resume", methods=["POST"])
def dashboard_update_resume():
    if "user_id" not in session:
        return redirect("/login")
    
    user = db.session.get(User, session["user_id"])
    if not user:
        return redirect("/dashboard")
        
    resume_file = request.files.get("resume_file")
    
    if resume_file and resume_file.filename:
        filename = resume_file.filename
        if allowed_resume_file(filename):
            try:
                # Save original file to uploads directory
                ext = filename.rsplit('.', 1)[1].lower()
                saved_filename = f"user_{user.id}_resume.{ext}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], saved_filename)
                
                # Save file contents
                resume_file.seek(0)
                file_bytes = resume_file.read()
                with open(file_path, "wb") as f:
                    f.write(file_bytes)
                
                user.resume_filename = saved_filename

                # Call Gemini client to extract clean text from the uploaded PDF/Word/Image doc
                resume_file.seek(0)
                extracted_text = analyze_attachment(
                    file_bytes, resume_file.mimetype,
                    context_hint="Extract the text content and structure from this resume as cleanly as possible. Provide only the text transcription."
                )
                user.resume_text = extracted_text
                db.session.commit()
            except Exception as e:
                print(f"Error extracting text from uploaded resume: {e}")
                return redirect("/dashboard?error=resume_extraction_failed")
        else:
            return redirect("/dashboard?error=invalid_file_type")
            
    return redirect("/dashboard")


@app.route("/dashboard/remove-resume", methods=["GET", "POST"])
def dashboard_remove_resume():
    if "user_id" not in session:
        return redirect("/login")
    user = db.session.get(User, session["user_id"])
    if user:
        if user.resume_filename:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], user.resume_filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Error removing resume file: {e}")
            user.resume_filename = None
        user.resume_text = None
        db.session.commit()
    return redirect("/dashboard")


@app.route("/uploads/resumes/<filename>")
def view_original_resume(filename):
    if not session.get("is_admin") and "user_id" not in session:
        return redirect("/login")
    if not session.get("is_admin"):
        # Logged in user: find their user model
        user = db.session.get(User, session["user_id"])
        if not user or user.resume_filename != filename:
            # Unauthorized access to another user's file
            return "Unauthorized", 403
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route("/admin/user/<int:user_id>/resume")
def admin_view_user_resume(user_id):
    if not session.get("is_admin"):
        return redirect("/admin/login")
    user = db.session.get(User, user_id)
    if not user or not user.resume_filename:
        return redirect(f"/admin/user/{user_id}")
    return send_from_directory(app.config['UPLOAD_FOLDER'], user.resume_filename)


@app.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():
    if session.get("is_admin"):
        return redirect("/admin")
    if "user_id" not in session:
        return redirect("/login")

    user = db.session.get(User, session["user_id"])

    if request.method == "POST":
        user.full_name = request.form.get("full_name")
        user.gender = request.form.get("gender")
        user.education = request.form.get("education")
        user.course = request.form.get("course")
        user.semester = request.form.get("semester")
        user.user_type = request.form.get("user_type", "student")
        user.github_url = request.form.get("github_url", "").strip() or None
        user.linkedin_url = request.form.get("linkedin_url", "").strip() or None
        user.skills = request.form.get("skills", "").strip() or None
        user.years_of_experience = request.form.get("years_of_experience", "").strip() or None
        user.current_designation = request.form.get("current_designation", "").strip() or None
        db.session.commit()
        session["user_name"] = user.full_name
        return render_template("edit_profile.html", user=user, success="Profile updated successfully.")

    return render_template("edit_profile.html", user=user)


@app.route("/latest-result")
def latest_result():
    if session.get("is_admin"):
        return redirect("/admin")
    if "user_id" not in session:
        return redirect("/login")

    result = InterviewResult.query.filter_by(user_id=session["user_id"]).order_by(InterviewResult.interview_datetime.desc()).first()

    if not result:
        return redirect("/dashboard")

    return render_template(
        "interview_result.html",
        score=result.score,
        score_percent=min(int((float(result.score) / 10) * 100), 100) if result.score else 0,
        label="Excellent" if result.score and result.score >= 8 else "Good" if result.score and result.score >= 6 else "Fair" if result.score and result.score >= 4 else "Needs Work",
        label_color="#1cc88a" if result.score and result.score >= 8 else "#4e73df" if result.score and result.score >= 6 else "#f6c23e" if result.score and result.score >= 4 else "#e74a3b",
        summary=result.summary,
        verdict=result.status,
        verdict_message="🎉 Congratulations! You have met the recruitment selection criteria and successfully passed the assessment." if result.status in ("Selected", "PASS") or (result.status and "WELL DONE" in result.status) else "Thank you for taking the assessment. We regret that you did not meet the selection threshold for this placement round. Keep developing your skills.",
        candidate_name=session.get("user_name", "Candidate"),
        report_date=result.interview_datetime.strftime("%B %d, %Y"),
        domain=result.domain or "General"
    )



@app.route("/admin")
def admin():
    if "user_id" in session:
        return redirect("/dashboard")
    if not session.get("is_admin"):
        return redirect("/login")

    from datetime import date
    today = date.today()
    current_month = today.month
    current_year = today.year

    filter_type = request.args.get("filter", "all")

    all_results = db.session.query(InterviewResult, User).join(User, InterviewResult.user_id == User.id)\
        .filter(~InterviewResult.status.like('%Practice%'))\
        .order_by(InterviewResult.interview_datetime.desc()).all()

    today_count = sum(1 for r, u in all_results if r.interview_datetime.date() == today)
    month_count = sum(1 for r, u in all_results if r.interview_datetime.year == current_year and r.interview_datetime.month == current_month)
    total_count = len(all_results)
    selected_count = sum(1 for r, u in all_results if r.status == "Selected")
    rejected_count = sum(1 for r, u in all_results if r.status == "Rejected")

    if filter_type == "today":
        results = [(r, u) for r, u in all_results if r.interview_datetime.date() == today]
    elif filter_type == "month":
        results = [(r, u) for r, u in all_results if r.interview_datetime.year == current_year and r.interview_datetime.month == current_month]
    elif filter_type == "selected":
        results = [(r, u) for r, u in all_results if r.status == "Selected"]
    elif filter_type == "rejected":
        results = [(r, u) for r, u in all_results if r.status == "Rejected"]
    else:
        results = all_results

    settings = get_settings()

    # Optimized single GROUP BY query to avoid N+1 query buffering on Render
    attempt_counts_raw = db.session.query(
        InterviewResult.user_id, func.count(InterviewResult.id)
    ).filter(
        ~InterviewResult.status.like('%Practice%')
    ).group_by(InterviewResult.user_id).all()
    user_attempt_counts = {u_id: count for u_id, count in attempt_counts_raw}

    return render_template(
        "admin.html",
        results=results,
        today_count=today_count,
        month_count=month_count,
        total_count=total_count,
        selected_count=selected_count,
        rejected_count=rejected_count,
        filter_type=filter_type,
        settings=settings,
        user_attempt_counts=user_attempt_counts
    )

@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    if not session.get("is_admin"):
        return redirect("/login")

    settings = get_settings()

    if request.method == "POST":
        try:
            settings.min_questions = int(float(request.form.get("min_questions", 3)))
        except (ValueError, TypeError):
            pass
        try:
            settings.max_questions = int(float(request.form.get("max_questions", 8)))
        except (ValueError, TypeError):
            pass
        try:
            settings.pass_score = int(float(request.form.get("pass_score", 3)))
        except (ValueError, TypeError):
            pass
        settings.default_difficulty = request.form.get("default_difficulty", "student")
        if "question_timer_seconds" in request.form:
            try:
                settings.question_timer_seconds = int(float(request.form["question_timer_seconds"]))
            except (ValueError, TypeError):
                pass
        
        settings.enable_attempt_limits = bool(request.form.get("enable_attempt_limits"))
        if "default_allowed_interviews" in request.form:
            try:
                settings.default_allowed_interviews = int(float(request.form["default_allowed_interviews"]))
            except (ValueError, TypeError):
                pass

        db.session.commit()
        return redirect("/admin/settings?saved=1")

    return render_template("admin_settings.html", settings=settings, saved=request.args.get("saved"))


@app.route("/admin/delete/<int:result_id>")
def delete_result(result_id):
    if not session.get("is_admin"):
        return redirect("/login")

    record = db.session.get(InterviewResult, result_id)
    if record:
        db.session.delete(record)
        db.session.commit()

    return redirect("/admin")


@app.route("/admin/user/<int:user_id>/unlock-attempt", methods=["POST"])
def admin_unlock_attempt(user_id):
    if not session.get("is_admin"):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    user_obj = db.session.get(User, user_id)
    if not user_obj:
        return jsonify({"status": "error", "message": "User not found"}), 404

    current_extra = user_obj.extra_allowed_interviews or 0
    user_obj.extra_allowed_interviews = current_extra + 1
    db.session.commit()

    # Trigger automated notification email to candidate
    if user_obj.email:
        send_slot_unlocked_email(user_obj.email, user_obj.full_name)

    return jsonify({
        "status": "success",
        "message": f"Successfully granted 1 extra interview attempt for {user_obj.full_name or 'candidate'}.",
        "new_extra": user_obj.extra_allowed_interviews
    })


@app.route("/admin/delete-user/<int:user_id>")
def delete_user(user_id):
    if not session.get("is_admin"):
        return redirect("/login")

    InterviewResult.query.filter_by(user_id=user_id).delete()
    InterviewProgress.query.filter_by(user_id=user_id).delete()

    user = db.session.get(User, user_id)
    if user:
        db.session.delete(user)

    db.session.commit()

    next_url = request.args.get("next") or "/admin"
    return redirect(next_url)


@app.route("/admin/users")
def admin_users():
    if not session.get("is_admin"):
        return redirect("/login")

    q = request.args.get("q", "").strip()
    if q:
        users = User.query.filter(
            (User.full_name.ilike(f"%{q}%")) |
            (User.email.ilike(f"%{q}%")) |
            (User.course.ilike(f"%{q}%")) |
            (User.skills.ilike(f"%{q}%"))
        ).order_by(User.registered_at.desc()).all()
    else:
        users = User.query.order_by(User.registered_at.desc()).all()
    settings = get_settings()

    attempt_counts_raw = db.session.query(
        InterviewResult.user_id, func.count(InterviewResult.id)
    ).filter(
        ~InterviewResult.status.like('%Practice%')
    ).group_by(InterviewResult.user_id).all()
    user_attempt_counts = {u_id: count for u_id, count in attempt_counts_raw}

    return render_template("admin_users.html", users=users, q=q, settings=settings, user_attempt_counts=user_attempt_counts)



@app.route("/admin/user/<int:user_id>")
def admin_user_detail(user_id):
    if not session.get("is_admin"):
        return redirect("/login")

    user = db.session.get(User, user_id)
    if not user:
        return redirect("/admin")

    interviews = InterviewResult.query.filter(
        InterviewResult.user_id == user_id,
        ~InterviewResult.status.like('%Practice%')
    ).order_by(InterviewResult.interview_datetime.desc()).all()

    return render_template("admin_user_detail.html", user=user, interviews=interviews)


@app.route("/admin/interview/<int:result_id>")
def admin_interview_detail(result_id):
    if not session.get("is_admin"):
        return redirect("/login")

    result = db.session.get(InterviewResult, result_id)
    if not result:
        return redirect("/admin")

    candidate = db.session.get(User, result.user_id)

    try:
        score_percent = min(int((float(result.score) / 10) * 100), 100)
    except:
        score_percent = 0

    return render_template("admin_interview_detail.html", result=result, candidate=candidate, score_percent=score_percent)

@app.route("/practice-setup")
def practice_setup():
    if session.get("is_admin"):
        return redirect("/admin")
    if "user_id" not in session:
        return redirect("/login")
    return render_template("practice_setup.html")


@app.route("/practice-start", methods=["POST"])
def practice_start():
    if "user_id" not in session:
        return redirect("/login")
    
    mode = request.form.get("mode")
    viva_subject = request.form.get("viva_subject", "").strip()
    drill_subject = request.form.get("drill_subject", "").strip()
    
    session["interview_mode"] = mode
    if mode == "viva" and viva_subject:
        session["practice_topic"] = viva_subject
    elif mode == "drill" and drill_subject:
        session["practice_topic"] = drill_subject
    elif mode == "lang":
        lang_target = request.form.get("lang_target", "").strip()
        lang_focus = request.form.get("lang_focus", "conversation").strip()
        lang_level = request.form.get("lang_level", "intermediate").strip()
        
        session["lang_target"] = lang_target or "English"
        session["lang_focus"] = lang_focus
        session["lang_level"] = lang_level
        session["practice_topic"] = f"{session['lang_target']} ({lang_focus.capitalize()})"
    else:
        session["practice_topic"] = "General English Speaking"

    return redirect(url_for("interview", restart="1", practice="1"))


@app.route("/interview", methods=["GET", "POST"])
def interview():
    if session.get("is_admin"):
        return redirect("/admin")
    if "user_id" not in session:
        return redirect("/login")

    # Guard against missing Gemini API Key in production
    if not os.environ.get("GEMINI_API_KEY"):
        return redirect("/dashboard?error=api_key_missing")

    user_id = session["user_id"]

    settings = get_settings()
    MIN_QUESTIONS = settings.min_questions
    MAX_QUESTIONS = settings.max_questions
    timer_seconds = settings.question_timer_seconds or 90

    if request.args.get("restart") == "1":
        _existing_prog = InterviewProgress.query.filter_by(user_id=user_id).first()
        _ex_history = json.loads(_existing_prog.chat_history or '[]') if _existing_prog else []
        if not session.get("interview_mode") and request.args.get("practice") != "1" and _existing_prog and _existing_prog.q_count > 0:
            try:
                res_rec = InterviewResult(
                    user_id=user_id,
                    score=0.0,
                    status="Abandoned (Reset)",
                    summary="Candidate started a fresh interview session.",
                    domain=session.get("interview_domain", "General")
                )
                db.session.add(res_rec)
                db.session.commit()
            except Exception as ex:
                print(f"[RESTART LOG ERROR] {ex}")
                db.session.rollback()

        clear_progress(user_id)
        session.pop("chat_history", None)
        session.pop("q_count", None)
        session.pop("resume_summary", None)
        if request.args.get("practice") != "1":
            session.pop("interview_mode", None)
            session.pop("practice_topic", None)

    # Always load chat history from DB — avoids session cookie size limits in production
    try:
        _db_progress = InterviewProgress.query.filter_by(user_id=user_id).first()
        chat_history = json.loads(_db_progress.chat_history or '[]') if _db_progress else []
        if "q_count" not in session:
            session["q_count"] = _db_progress.q_count if _db_progress else 0
    except Exception as db_err:
        print(f"[DB LOAD ERROR] {db_err}")
        db.session.rollback()
        chat_history = session.get("chat_history", [])
    q_count = session.get("q_count", 0)

    if request.method == "POST":
        answer = request.form.get("answer", "").strip()
        code_answer = request.form.get("code_answer", "").strip()
        attachment = request.files.get("attachment")
        resume_file = request.files.get("resume")

        if q_count == 0 and not session.get("interview_mode") and resume_file and resume_file.filename and allowed_resume_file(resume_file.filename):
            try:
                filename = resume_file.filename
                ext = filename.rsplit('.', 1)[1].lower()
                user = db.session.get(User, user_id)
                saved_filename = f"user_{user.id}_resume.{ext}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], saved_filename)
                
                resume_file.seek(0)
                file_bytes = resume_file.read()
                with open(file_path, "wb") as f:
                    f.write(file_bytes)
                
                if user:
                    user.resume_filename = saved_filename
                    resume_file.seek(0)
                    resume_analysis = analyze_attachment(
                        file_bytes, resume_file.mimetype,
                        context_hint="Verify this is a candidate resume. If not, output NOT_A_RESUME. Otherwise summarize their role, key skills, and experience level in 2 concise sentences."
                    )
                    if "NOT_A_RESUME" not in resume_analysis:
                        user.resume_text = resume_analysis
                        session["resume_summary"] = resume_analysis
                    db.session.commit()
            except Exception as e:
                print(f"Error handling interview resume upload: {e}")
                db.session.rollback()

        if answer or code_answer:
            if q_count == 0:
                if session.get("interview_mode"):
                    session["interview_domain"] = session.get("practice_topic", "Practice")
                else:
                    session["interview_domain"] = answer.strip()
                # difficulty is set by admin globally — candidate has no choice
                session["interview_difficulty"] = settings.default_difficulty or "student"

            full_answer = answer
            if code_answer:
                if full_answer:
                    full_answer += "\n\n[Candidate Code Input]:\n" + code_answer
                else:
                    full_answer = "[Candidate Code Input]:\n" + code_answer

            if attachment and attachment.filename and allowed_file(attachment.filename):
                file_bytes = attachment.read()
                mime_type = attachment.mimetype
                analysis = analyze_attachment(
                    file_bytes, mime_type,
                    context_hint="This was attached by the candidate alongside their answer during a job interview."
                )
                full_answer += " [Attached file analysis: " + analysis + "]"

            try:
                chat_history.append({"role": "answer", "text": full_answer})
                q_count += 1
                session["q_count"] = q_count
                session.modified = True
                save_progress(user_id, chat_history, q_count)
            except Exception as save_err:
                print(f"[SAVE PROGRESS ERROR] {save_err}")
                db.session.rollback()

    # Practice mode has no question cap — user finishes via the Finish button
    is_practice = bool(session.get("interview_mode"))
    if not is_practice and q_count >= MAX_QUESTIONS:
        return redirect("/interview-result")

    if chat_history and chat_history[-1]["role"] == "question":
        last_question_entry = chat_history[-1]
        last_question = last_question_entry["text"]
        question_type = last_question_entry.get("type", "text")
        return render_template("interview.html", question=last_question, q_num=q_count + 1, total=MAX_QUESTIONS, question_type=question_type, is_practice=is_practice, timer_seconds=timer_seconds)

    # Build complete conversation text for Gemini prompt — full session context
    conversation_text = ""
    for entry in chat_history:
        conversation_text += f"{entry['role']}: {entry['text']}\n"
    question_text = ""
    prompt = ""
    try:
        if q_count == 0:
            practice_mode = session.get("interview_mode")
            practice_topic = session.get("practice_topic", "General")

            if practice_mode == "viva":
                prompt = (
                    f"You are an academic external examiner starting a Viva Voce exam on the subject: {practice_topic}. "
                    "Briefly introduce the exam and ask the candidate your very first conceptual question about this subject. "
                    "Output ONLY the question text followed by [TYPE: TEXT] at the end. No preamble, no intro."
                )
            elif practice_mode == "lang":
                target_lang = session.get("lang_target", "English")
                focus_cat = session.get("lang_focus", "conversation")
                level = session.get("lang_level", "intermediate")
                is_english_target = target_lang.strip().lower() == "english"
                translation_rule_q1 = (
                    ""
                    if is_english_target
                    else f"Format the question STRICTLY as follows: first write the question in {target_lang}, then on the very next line write the English translation in brackets like this: [English: <translation here>]. Do NOT skip the English translation. "
                )
                prompt = (
                    f"You are a language validator and native tutor. First, analyze the string: '{target_lang}'. "
                    "Is this a legitimate language name (e.g. English, French, Spanish, Hindi, Telugu, Sindhi, Japanese, Arabic, Russian, etc.)? "
                    "If it is NOT a legitimate or real language, respond with exactly: "
                    "'ERROR: Language not found. Please start a new session and specify a valid language. [TYPE: TEXT]' "
                    "If it IS a legitimate language, start a language speaking practice session. "
                    f"The target language is: {target_lang}. The candidate's level is: {level.capitalize()}. "
                    f"The focus category is: {focus_cat.capitalize()}. "
                    "Briefly introduce the session with a warm and slightly friendly tone, then ask the first practice question or prompt. "
                    f"{translation_rule_q1}"
                    "The user can answer in any language they prefer. "
                    "Output ONLY the formatted question followed by [TYPE: TEXT] at the end. No preamble, no extra commentary."
                )
            elif practice_mode == "drill":
                prompt = (
                    f"You are a friendly mentor starting a concept drill session on the topic: {practice_topic}. "
                    "State the topic and ask the candidate their first open conceptual question. "
                    "Output ONLY the question text followed by [TYPE: TEXT] at the end. No preamble, no intro."
                )
            else:
                if session.get("resume_summary"):
                    question_text = "Welcome! Based on your resume, which specific role or domain are you interviewing for? [TYPE: TEXT]"
                else:
                    question_text = "Which specific role or domain are you interviewing for? [TYPE: TEXT]"
        else:
            difficulty = session.get("interview_difficulty", "student")
            practice_mode = session.get("interview_mode")
            practice_topic = session.get("practice_topic", "General")

            if practice_mode == "viva":
                difficulty_instruction = (
                    f"The candidate is undergoing an Academic Viva Voce exam on: {practice_topic}. "
                    "Keep questions clear, technical, and strictly focused on academic course concepts. "
                    "Evaluate their understanding of theory, equations, algorithms, or definitions."
                )
            elif practice_mode == "lang":
                target_lang = session.get("lang_target", "English")
                focus_cat = session.get("lang_focus", "conversation")
                level = session.get("lang_level", "intermediate")
                is_english_target = target_lang.strip().lower() == "english"
                translation_rule = (
                    ""
                    if is_english_target
                    else f"IMPORTANT FORMAT RULE: Always write each question first in {target_lang}, then on the very next line write the English translation in brackets like this: [English: <translation here>]. Never skip the English translation. "
                )
                difficulty_instruction = (
                    f"This is a FluentFlow language practice session in {target_lang}. The candidate's level is {level.capitalize()}. "
                    f"Focus Category: {focus_cat.capitalize()}. "
                    "Maintain a warm, polite, and professional but encouraging tone. Keep any conversational remarks extremely short (under 2 sentences). "
                    "If the candidate's last response contained any clear grammatical, vocabulary, or structural mistakes, "
                    "provide a single, polite, direct correction sentence (e.g., 'Correction: Instead of ..., it is better to say ...'), then immediately ask the next question. "
                    f"{translation_rule}"
                    "The candidate can answer in any language they prefer — do not restrict or comment on the language of their answer."
                )
            elif practice_mode == "drill":
                difficulty_instruction = (
                    f"The candidate is doing a Concept Drill on: {practice_topic}. "
                    "Ask helpful conceptual questions that challenge their logic and reasoning on this topic."
                )
            else:
                if difficulty == "student":
                    difficulty_instruction = (
                        "The candidate is a Student/Beginner. Keep questions friendly and focus on fundamental concepts. "
                        "Ask practical, interview-style questions suitable for a junior role, rather than overly simplistic dictionary definitions (e.g. do not ask 'What is a computer?') and explore all categories of questions within the domain. "
                        "Do NOT ask highly complex technical questions. If they answer incorrectly or struggle, change the topic and ask different question within the same domain. "
                        "Do not end early unless you have asked at least 5 questions. "
                        "Keep conversational feedback minimal and professional."
                    )
                elif difficulty == "senior":
                    difficulty_instruction = (
                        "The candidate is a Senior/Expert. Ask challenging, deep architectural or practical scenarios. "
                        "Challenge their decisions, drill down into technical specifics, and maintain a high bar. Explore different categories of questions within the domain and output only question and not anything else. Do not offer any conversational filler or praise."
                    )
                else:
                    difficulty_instruction = (
                        "The candidate is Mid-Level. Ask standard industry questions with moderate scenarios and fundamentals. "
                        "Adjust difficulty adaptively based on their performance. Explore different categories of questions within the domain and output only the question. Keep feedback professional and minimal."
                    )

            completion_option = ""
            if q_count >= MIN_QUESTIONS:
                completion_option = f"If you have gathered enough evaluation data after {MIN_QUESTIONS} questions, you may conclude by outputting ONLY: [END_INTERVIEW]\n"

            prompt = (
                "You are an expert interviewer conducting a real-time assessment.\n\n"
                f"CANDIDATE TARGET LEVEL:\n{difficulty_instruction}\n\n"
                "CRITICAL DOMAIN RULE:\n"
                "Determine the candidate's core domain/role from their first answer. You MUST stay strictly 100% within this domain. Never switch to unrelated fields.\n\n"
                "RULES FOR OUTPUT:\n"
                "1. Output ONLY the raw next question. Keep it concise (under 2 sentences). ZERO preamble, conversational filler, praise, or acknowledgment.\n"
                "2. If they struggle or answer 'I don't know', DO NOT give them the answer. Change the topic/concept within the domain and output the next question immediately.\n"
                "3. Explore diverse categories of questions within the domain without repeating topics.\n"
                "4. HUMAN INTERVIEWER CLARIFICATION RULE: If the candidate indicates they do not understand a term or question, briefly clarify (in 1 short sentence), then state the question.\n"
                "5. BEHAVIORAL RULE: You may seamlessly integrate 1-2 behavioral or situational questions (e.g., 'Tell me about yourself', 'Why should we hire you?', or domain conflict scenarios).\n"
                "6. INPUT TAG RULE: You MUST append a tag at the very end of your output:\n"
                "   - `[TYPE: CODE]` if they need to write or fix code.\n"
                "   - `[TYPE: FILE]` if they need to upload a diagram or image.\n"
                "   - `[TYPE: TEXT]` for all standard conceptual questions.\n"
                f"{completion_option}\n"
                f"Conversation so far:\n{conversation_text}\n"
                "Output ONLY the raw question text with its tag below:"
            )

        if not question_text:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=80)
            )
            question_text = (response.text.strip() if response and hasattr(response, 'text') and response.text else "Could you share a key challenge you solved in your field recently? [TYPE: TEXT]")
    except Exception as e:
        print(f"[INTERVIEW ERROR] {e}")
        question_text = "Could you share a key challenge you solved in your field recently? [TYPE: TEXT]"

    if not is_practice and q_count >= MIN_QUESTIONS and ("INTERVIEW_COMPLETE" in question_text.upper() or "[END_INTERVIEW]" in question_text.upper()):
        return redirect("/interview-result")

    # Parse TYPE tag
    question_type = "text"
    match = re.search(r'\[TYPE:\s*([A-Z]+)\]', question_text)
    if match:
        tag_type = match.group(1).lower()
        if tag_type in ["code", "file", "text"]:
            question_type = tag_type
        # Strip the tag from the final display question text
        question_text = re.sub(r'\s*\[TYPE:\s*[A-Z]+\]', '', question_text).strip()

    chat_history.append({"role": "question", "text": question_text, "type": question_type})
    session.modified = True
    save_progress(user_id, chat_history, q_count)

    return render_template("interview.html", question=question_text, q_num=q_count + 1, total=MAX_QUESTIONS, question_type=question_type, is_practice=is_practice, timer_seconds=timer_seconds)

@app.route("/finish-interview", methods=["GET", "POST"])
def finish_interview():
    """Allows practice mode users to end their session early and go to results."""
    if "user_id" not in session:
        return redirect("/login")
    return redirect("/interview-result")


@app.route("/interview-result")
def interview_result():
    if session.get("is_admin"):
        return redirect("/admin")
    if "user_id" not in session:
        return redirect("/login")

    # If redirected from proctoring termination
    if request.args.get("terminated") == "1":
        latest_res = InterviewResult.query.filter_by(user_id=session["user_id"]).order_by(InterviewResult.interview_datetime.desc()).first()
        if latest_res and latest_res.is_terminated:
            return render_template(
                "interview_result.html",
                score=0,
                score_percent=0,
                label="Disqualified",
                label_color="#e74a3b",
                summary=latest_res.summary,
                verdict="Terminated (Breach)",
                verdict_message="This assessment session was automatically terminated by the automated security proctoring system due to a breach of the Candidate Code of Conduct.",
                is_practice=False,
                candidate_name=session.get("user_name", "Candidate"),
                report_date=datetime.now().strftime("%B %d, %Y"),
                domain=latest_res.domain or "General",
                is_terminated=True,
                termination_reason=latest_res.termination_reason or "Repeated window focus loss / tab switching detected during active assessment"
            )

    settings = get_settings()
    PASS_SCORE = settings.pass_score

    _result_progress = InterviewProgress.query.filter_by(user_id=session["user_id"]).first()
    _result_history = json.loads(_result_progress.chat_history or '[]') if _result_progress else []

    if not _result_history:
        latest_res = InterviewResult.query.filter_by(user_id=session["user_id"]).order_by(InterviewResult.interview_datetime.desc()).first()
        if latest_res:
            score_pct = int((latest_res.score / 10.0) * 100) if latest_res.score else 0
            return render_template(
                "interview_result.html",
                score=latest_res.score,
                score_percent=score_pct,
                label="Completed" if (latest_res.score or 0) >= PASS_SCORE else "Needs Improvement",
                label_color="#1cc88a" if (latest_res.score or 0) >= PASS_SCORE else "#f6c23e",
                summary=latest_res.summary,
                verdict=latest_res.status,
                verdict_message="Your official evaluation report is recorded.",
                is_practice=False,
                candidate_name=session.get("user_name", "Candidate"),
                report_date=latest_res.interview_datetime.strftime("%B %d, %Y") if latest_res.interview_datetime else datetime.now().strftime("%B %d, %Y"),
                domain=latest_res.domain or "General"
            )

    conversation_text = ""
    for entry in _result_history:
        conversation_text += entry["role"] + ": " + entry["text"] + "\n"

    try:
        practice_mode = session.get("interview_mode")
        practice_topic = session.get("practice_topic", "General")
        
        if practice_mode == "viva":
            grading_instruction = f"Academic Viva Voce exam on {practice_topic}. Grade strictly on theoretical accuracy and academic definitions."
        elif practice_mode == "lang":
            target_lang = session.get("lang_target", "English")
            grading_instruction = f"Language practice in {target_lang}. Grade on grammar, vocabulary, and conversational fluency."
        elif practice_mode == "drill":
            grading_instruction = f"Concept Drill on {practice_topic}. Grade on conceptual understanding and logical reasoning."
        else:
            difficulty = session.get("interview_difficulty", "student")
            if difficulty == "student":
                grading_instruction = "Candidate level: Student/Beginner. Grade encouragingly on fundamentals and potential."
            elif difficulty == "senior":
                grading_instruction = "Candidate level: Senior/Expert. Grade strictly on deep technical proficiency, design, and architecture."
            else:
                grading_instruction = "Candidate level: Mid-Level. Grade balanced on standard industry expectations."

        domain_val = session.get("interview_domain", "General")
        prompt = (
            f"Evaluate this {domain_val} interview assessment.\n"
            f"{grading_instruction}\n"
            "Format EXACTLY as follows:\n"
            "SCORE: [number 1-10]\n"
            "SUMMARY:\n"
            "[2 concise professional sentences evaluating candidate performance, technical strengths, and placement recommendation.]\n\n"
            f"Transcript:\n{conversation_text}"
        )

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=110)
        )
        evaluation = response.text.strip() if response and hasattr(response, 'text') and response.text else "SCORE: 7\nSUMMARY: The candidate actively completed their assessment questions within their core domain."

        score = "N/A"
        summary_lines = []
        in_summary = False

        for raw_line in evaluation.split("\n"):
            line = raw_line.strip()
            if not line:
                if in_summary:
                    summary_lines.append("")
                continue

            # Strip markdown formatting like **, *, # for checking
            clean_line = re.sub(r'[\*\#\_]', '', line).strip()
            upper_line = clean_line.upper()

            if upper_line.startswith("SCORE"):
                score = clean_line.split(":", 1)[-1].strip()
                in_summary = False
            elif upper_line.startswith("SUMMARY"):
                in_summary = True
            elif in_summary:
                summary_lines.append(line)

        # Robust regex extraction for score number (finds 8, 8.5, 8/10, etc.)
        score_num = 0.0
        score_match = re.search(r'SCORE\s*:\s*([0-9]+(?:\.[0-9]+)?)', evaluation, re.IGNORECASE)
        if score_match:
            try:
                score_num = float(score_match.group(1))
            except (ValueError, TypeError):
                score_num = 0.0
        else:
            # Fallback regex if SCORE is written without colon or with /10
            fallback_match = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*/\s*10', evaluation)
            if fallback_match:
                try:
                    score_num = float(fallback_match.group(1))
                except (ValueError, TypeError):
                    score_num = 0.0

        summary_text = "\n".join(summary_lines).strip()
        if not summary_text:
            # If summary splitting failed due to format, use the evaluation text
            summary_text = re.sub(r'SCORE\s*:\s*[^\n]+', '', evaluation, flags=re.IGNORECASE).strip()
            if not summary_text:
                summary_text = "Not enough data to generate a report."

        if score_num >= 8:
            label = "Excellent"
            label_color = "#1cc88a"
        elif score_num >= 6:
            label = "Good"
            label_color = "#4e73df"
        elif score_num >= 4:
            label = "Fair"
            label_color = "#f6c23e"
        else:
            label = "Needs Work"
            label_color = "#e74a3b"

        score_percent = min(int((score_num / 10) * 100), 100)

        is_practice = bool(session.get("interview_mode"))

        if is_practice:
            if score_num >= PASS_SCORE:
                verdict = "WELL DONE"
                verdict_message = "You are on the right track. Keep up the great work!"
            else:
                verdict = "ALMOST"
                verdict_message = "A little more practice needed. You are getting closer — keep going!"
            db_verdict = f"{verdict} (Practice)"
        else:
            verdict = "PASS" if score_num >= PASS_SCORE else "FAIL"
            if verdict == "PASS":
                verdict_message = "Congratulations! You have met the recruitment selection criteria and successfully passed the assessment."
            else:
                verdict_message = "Thank you for taking the assessment. We regret that you did not meet the selection threshold for this placement round. Keep developing your skills."
            db_verdict = verdict

        domain_val = session.get("interview_domain", "General")

        try:
            result_record = InterviewResult(
                user_id=session["user_id"],
                score=score_num,
                status=db_verdict,
                summary=summary_text,
                domain=domain_val
            )
            db.session.add(result_record)
            db.session.commit()
        except Exception as db_ex:
            print(f"[RESULT DB ERROR] {db_ex}")
            db.session.rollback()

    except Exception as e:
        print(f"[RESULT EVALUATION ERROR] {e}")
        db.session.rollback()
        score_num = 6.5
        score_percent = 65
        label = "Completed"
        label_color = "#1cc88a"
        summary_text = "The candidate actively completed their assessment questions within their core domain."
        verdict = "PASS"
        verdict_message = "Your assessment session was recorded successfully."
        domain_val = session.get("interview_domain", "General")
        is_practice = bool(session.get("interview_mode"))

    user_id = session["user_id"]
    session.pop("chat_history", None)
    session.pop("q_count", None)
    session.pop("resume_choice", None)
    session.pop("resume_summary", None)
    session.pop("interview_domain", None)
    session.pop("interview_difficulty", None)
    session.pop("interview_mode", None)
    session.pop("practice_topic", None)
    clear_progress(user_id)

    return render_template(
        "interview_result.html",
        score=score_num,
        score_percent=score_percent,
        label=label,
        label_color=label_color,
        summary=summary_text,
        verdict=verdict,
        verdict_message=verdict_message,
        is_practice=is_practice,
        candidate_name=session.get("user_name", "Candidate"),
        report_date=datetime.now().strftime("%B %d, %Y"),
        domain=domain_val
    )


@app.route("/my-history")
def my_history():
    if session.get("is_admin"):
        return redirect("/admin")
    if "user_id" not in session:
        return redirect("/login")

    attempts = InterviewResult.query.filter_by(user_id=session["user_id"]).order_by(InterviewResult.interview_datetime.desc()).all()

    chart_labels = [a.interview_datetime.strftime('%d %b') for a in reversed(attempts)]
    chart_scores = [float(a.score) if a.score is not None else 0 for a in reversed(attempts)]

    return render_template("my_history.html", attempts=attempts, chart_labels=chart_labels, chart_scores=chart_scores)


@app.route("/my-history/<int:result_id>")
def view_past_result(result_id):
    if session.get("is_admin"):
        return redirect("/admin")
    if "user_id" not in session:
        return redirect("/login")

    result = InterviewResult.query.filter_by(id=result_id, user_id=session["user_id"]).first()
    if not result:
        return redirect("/my-history")

    try:
        score_num = float(result.score)
    except:
        score_num = 0

    if score_num >= 8:
        label = "Excellent"
        label_color = "#1cc88a"
    elif score_num >= 6:
        label = "Good"
        label_color = "#4e73df"
    elif score_num >= 4:
        label = "Fair"
        label_color = "#f6c23e"
    else:
        label = "Needs Work"
        label_color = "#e74a3b"

    score_percent = min(int((score_num / 10) * 100), 100)
    verdict = result.status or "FAIL"
    is_terminated = bool(result.is_terminated)
    
    if is_terminated or "Terminated" in str(verdict):
        verdict = "Terminated (Breach)"
        verdict_message = "This assessment session was automatically terminated by the automated security proctoring system due to a breach of the Candidate Code of Conduct."
    else:
        is_pass = verdict in ("PASS", "Selected") or "WELL DONE" in verdict
        if is_pass:
            verdict_message = "🎉 Congratulations! You have met the recruitment selection criteria and successfully passed the assessment."
        else:
            verdict_message = "Thank you for taking the assessment. We regret that you did not meet the selection threshold for this placement round. Keep developing your skills."

    return render_template(
        "interview_result.html",
        score=score_num,
        score_percent=score_percent,
        label=label,
        label_color=label_color,
        summary=result.summary,
        verdict=verdict,
        verdict_message=verdict_message,
        candidate_name=session.get("user_name", "Candidate"),
        report_date=result.interview_datetime.strftime("%B %d, %Y"),
        domain=result.domain or "General",
        is_terminated=is_terminated,
        termination_reason=result.termination_reason or "Repeated window focus loss / tab switching detected during active assessment"
    )


@app.route("/quit-interview")
def quit_interview():
    """Quit a practice session — clears practice keys and returns to dashboard."""
    if "user_id" not in session:
        return redirect("/login")
    # Clear only practice-related session keys, keep user login
    session.pop("chat_history", None)
    session.pop("q_count", None)
    session.pop("interview_mode", None)
    session.pop("practice_topic", None)
    session.pop("lang_target", None)
    session.pop("lang_focus", None)
    session.pop("lang_level", None)
    session.pop("interview_domain", None)
    session.pop("interview_difficulty", None)
    session.pop("resume_summary", None)
    clear_progress(session["user_id"])
    return redirect("/dashboard")


@app.route("/reset-assessment", methods=["POST"])
def reset_assessment():
    """AJAX endpoint: clears all assessment progress so user can start fresh."""
    if "user_id" not in session:
        return jsonify({"status": "error", "reason": "not_logged_in"}), 401
    is_practice = bool(session.get("interview_mode"))
    q_count = session.get("q_count", 0)
    domain_val = session.get("interview_domain", "General")

    # If the user is abandoning/resetting an ACTIVE standard evaluation (q_count > 0), record an InterviewResult
    if not is_practice and q_count > 0:
        try:
            res_rec = InterviewResult(
                user_id=user_id,
                score=0.0,
                status="Abandoned (Reset)",
                summary="Candidate initiated a fresh session reset mid-assessment.",
                domain=domain_val
            )
            db.session.add(res_rec)
            db.session.commit()
        except Exception as e:
            print(f"[RESET ASSESSMENT LOG ERROR] {e}")
            db.session.rollback()

    # Clear all assessment-related session keys
    session.pop("chat_history", None)
    session.pop("q_count", None)
    session.pop("interview_mode", None)
    session.pop("practice_topic", None)
    session.pop("lang_target", None)
    session.pop("lang_focus", None)
    session.pop("lang_level", None)
    session.pop("interview_domain", None)
    session.pop("interview_difficulty", None)
    session.pop("resume_summary", None)
    session.pop("resume_choice", None)
    session.modified = True
    # Also delete persisted DB progress
    clear_progress(user_id)
    return jsonify({"status": "ok"})


@app.route("/terminate-proctoring", methods=["POST"])
def terminate_proctoring():
    """AJAX endpoint: Called when user breaches proctoring security 2 times."""
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "unauthorized"}), 401
    
    user_id = session["user_id"]
    domain_val = session.get("interview_domain", "General")
    
    reason = "Repeated window focus loss / tab switching detected during active assessment"
    summary_msg = (
        "OFFICIAL DISQUALIFICATION NOTICE:\n\n"
        "This assessment session was automatically terminated by the automated security proctoring system "
        "due to a breach of the Candidate Code of Conduct. Specifically, unauthorized application tab switching "
        "or window focus loss was detected on multiple occasions during an active examination session.\n\n"
        "In accordance with evaluation security standards, all progress has been recorded as terminated "
        "and flagged for administrator audit review."
    )
    
    try:
        result_record = InterviewResult(
            user_id=user_id,
            score=0.0,
            status="Terminated (Breach)",
            summary=summary_msg,
            domain=domain_val,
            is_terminated=True,
            termination_reason=reason
        )
        db.session.add(result_record)
        db.session.commit()
    except Exception as db_err:
        print(f"Error recording proctoring termination: {db_err}")
        db.session.rollback()

    # Clear active session progress keys
    session.pop("chat_history", None)
    session.pop("q_count", None)
    session.pop("resume_choice", None)
    session.pop("resume_summary", None)
    session.pop("interview_domain", None)
    session.pop("interview_difficulty", None)
    session.pop("interview_mode", None)
    session.pop("practice_topic", None)
    session.modified = True
    clear_progress(user_id)

    return jsonify({"status": "terminated", "redirect": "/interview-result?terminated=1"})


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")



# ─────────────────────────────────────────────────────────────────────────────
# INTERVIEW SUBMIT  –  AJAX endpoint (no full page reload between questions)
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/interview/submit", methods=["POST"])
def interview_submit():
    """AJAX endpoint: accepts an answer, calls Gemini, returns the next question as JSON."""
    if session.get("is_admin"):
        return jsonify({"redirect": "/admin"})
    if "user_id" not in session:
        return jsonify({"redirect": "/login"})
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"redirect": "/dashboard?error=api_key_missing"})

    user_id = session["user_id"]
    settings = get_settings()
    MIN_QUESTIONS = settings.min_questions
    MAX_QUESTIONS = settings.max_questions

    answer = (request.form.get("answer") or "").strip()
    code_answer = (request.form.get("code_answer") or "").strip()
    is_practice = bool(session.get("interview_mode"))  # any of: 'viva', 'drill', 'lang'

    if not answer and not code_answer:
        return jsonify({"error": "empty_answer"})

    full_answer = answer
    if code_answer:
        if full_answer:
            full_answer += "\n\n[Candidate Code]:\n" + code_answer
        else:
            full_answer = "[Candidate Code]:\n" + code_answer

    # Load chat history from DB — avoids session cookie size limits in production
    _submit_progress = InterviewProgress.query.filter_by(user_id=user_id).first()
    submit_history = json.loads(_submit_progress.chat_history or '[]') if _submit_progress else []
    submit_q_count = session.get("q_count", 0) + 1

    submit_history.append({"role": "answer", "text": full_answer})
    session["q_count"] = submit_q_count
    session.modified = True

    # Check if interview is complete
    if not is_practice and submit_q_count >= MAX_QUESTIONS:
        save_progress(user_id, submit_history, submit_q_count)
        return jsonify({"done": True, "redirect": "/interview-result"})

    # Generate next question
    domain = session.get("interview_domain", "Software Engineering")
    difficulty = session.get("interview_difficulty", "student")
    resume_summary = session.get("resume_summary", "")

    if difficulty == "student":
        diff_note = "Candidate level: Student/Beginner. Ask practical beginner-friendly questions. No advanced or architecture-level questions."
    elif difficulty == "senior":
        diff_note = "Candidate level: Senior/Expert. Ask deep technical, architectural, and scenario-based questions. Maintain a high bar."
    else:
        diff_note = "Candidate level: Mid-Level. Ask standard industry questions with moderate depth."

    prompt_parts = [
        f"You are a strict {domain} interviewer. Domain: {domain}. {diff_note}",
        f"Resume summary: {resume_summary}" if resume_summary else "",
        f"CRITICAL RULE: ALL questions MUST be strictly within the '{domain}' domain only. NEVER ask questions from unrelated fields.",
        "Output ONLY the raw next question. Explore diverse categories within the domain. Change topic if the previous answer was wrong. Keep it concise (1-2 sentences). ZERO preamble, filler, or acknowledgment.",
        "If they answer 'I don't know', DO NOT give them the answer. Just output the next question immediately.",
    ]
    if not is_practice:
        prompt_parts.append(
            "BEHAVIORAL/SITUATIONAL RULE: Ensure to ask 2 behavioral or situational questions "
            "(e.g., 'Tell me about yourself', 'Why should we hire you?', or domain scenario questions) randomly or near the end before concluding."
        )

    if not is_practice and submit_q_count >= MIN_QUESTIONS:
        prompt_parts.append("If the candidate has demonstrated sufficient knowledge and you are ready to finish the interview, output ONLY the exact phrase: [END_INTERVIEW]")

    prompt_parts.append(f"Question {submit_q_count + 1} (Max: {MAX_QUESTIONS}). You MUST append [TYPE: TEXT], [TYPE: CODE], or [TYPE: FILE] at the end.")

    system_prompt = " ".join(p for p in prompt_parts if p)

    chat_turns = []
    for msg in submit_history:
        role = "user" if msg["role"] == "answer" else "model"
        chat_turns.append({"role": role, "parts": [{"text": msg["text"]}]})

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=chat_turns,
            config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.3, max_output_tokens=120),
        )
        question_text = response.text.strip() if response.text else "Tell me about yourself."
        
        if not is_practice and "[END_INTERVIEW]" in question_text.upper() and submit_q_count >= MIN_QUESTIONS:
            save_progress(user_id, submit_history, submit_q_count)
            return jsonify({"done": True, "redirect": "/interview-result"})
            
    except Exception as e:
        print(f"[SUBMIT ERROR] {e}")
        question_text = "Can you walk me through a challenging technical problem you solved recently?"

    question_type = "text"
    match = re.search(r'\[TYPE:\s*([A-Z]+)\]', question_text)
    if match:
        tag = match.group(1).lower()
        if tag in ["code", "file", "text"]:
            question_type = tag
        question_text = re.sub(r'\s*\[TYPE:\s*[A-Z]+\]', '', question_text).strip()

    submit_history.append({"role": "question", "text": question_text, "type": question_type})
    save_progress(user_id, submit_history, submit_q_count)

    return jsonify({
        "question": question_text,
        "q_num": submit_q_count + 1,
        "total": MAX_QUESTIONS,
        "question_type": question_type,
        "done": False,
    })


# ─────────────────────────────────────────────────────────────────────────────
# OTP LOGIN  –  /auth/otp/send  and  /auth/otp/verify
# ─────────────────────────────────────────────────────────────────────────────
import smtplib
import threading
import urllib.request
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Shared HTML OTP email body builder
def _otp_html_body(otp):
    return f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 0; background: #080e1e; border-radius: 16px; border: 1px solid rgba(0, 255, 255, 0.25); overflow: hidden;">
      <div style="background: linear-gradient(135deg, rgba(0, 255, 255, 0.15), rgba(2, 132, 199, 0.1)); padding: 28px 32px 18px; text-align: center; border-bottom: 1px solid rgba(0, 255, 255, 0.15);">
        <div style="font-size: 28px; font-weight: 900; color: #ffffff; letter-spacing: 0.02em; margin-bottom: 4px;">AI Assessment <span style="color: #00ffff;">Studio</span></div>
        <div style="font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.15em;">Secure Authentication</div>
      </div>
      <div style="padding: 32px;">
        <div style="text-align: center; margin-bottom: 8px;">
          <span style="background: rgba(0, 255, 255, 0.12); color: #00ffff; border: 1px solid rgba(0, 255, 255, 0.3); border-radius: 100px; padding: 6px 18px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.12em;">
            One-Time Passcode
          </span>
        </div>
        <h2 style="color: #ffffff; font-size: 20px; font-weight: 800; margin: 16px 0 8px; text-align: center;">Your Verification Code</h2>
        <p style="color: #94a3b8; font-size: 14px; line-height: 1.6; margin-bottom: 24px; text-align: center;">
          Enter this code to securely access your <strong style="color: #e2e8f0;">AI Assessment Studio</strong> workspace.
        </p>
        <div style="background: rgba(0, 255, 255, 0.06); border: 1.5px solid rgba(0, 255, 255, 0.3); border-radius: 14px; text-align: center; padding: 28px 0; margin-bottom: 24px;">
          <span style="font-size: 42px; font-weight: 900; letter-spacing: 12px; color: #00ffff;">{otp}</span>
        </div>
        <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 16px; margin-bottom: 20px;">
          <div style="color: #94a3b8; font-size: 13px; line-height: 1.6;">
            &#8987; Valid for <strong style="color: #e2e8f0;">10 minutes</strong> &nbsp;|&nbsp; &#128274; Do not share this code with anyone
          </div>
        </div>
        <div style="text-align: center;">
          <a href="https://ai-interview-platform-3-vdic.onrender.com" style="color: #00ffff; font-size: 13px; font-weight: 600; text-decoration: none;">Visit AI Assessment Studio &rarr;</a>
        </div>
      </div>
      <div style="padding: 16px 32px; border-top: 1px solid rgba(255, 255, 255, 0.06); text-align: center;">
        <p style="color: #475569; font-size: 11px; margin: 0;">This is an automated message from AI Assessment Studio. Please do not reply.</p>
      </div>
    </div>
    """

def _send_via_resend(to_email, otp, api_key):
    """Send via Resend HTTP API (port 443 – works on Render free tier)."""
    from_addr = os.environ.get("MAIL_FROM", f"AI Assessment Studio <onboarding@{os.environ.get('RESEND_DOMAIN', 'resend.dev')}>")
    payload = json.dumps({
        "from": from_addr,
        "to": [to_email],
        "subject": "Your Verification Code — AI Assessment Studio",
        "html": _otp_html_body(otp),
        "text": f"Your AI Assessment Studio verification code is: {otp}\n\nValid for 10 minutes. Do not share it.\n\nVisit: https://ai-interview-platform-3-vdic.onrender.com"
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            print(f"[OTP] Resend response: {resp.status} {body[:120]}")
            return resp.status in (200, 201)
    except urllib.error.HTTPError as http_err:
        err_body = http_err.read().decode() if http_err.fp else ""
        print(f"[OTP] Resend HTTP error {http_err.code}: {err_body[:200]}")
        return False
    except urllib.error.URLError as url_err:
        print(f"[OTP] Resend URL error: {url_err.reason}")
        return False


def _send_via_sendgrid(to_email, otp, api_key):
    """Send via SendGrid HTTP API (port 443 – works on Render free tier)."""
    from_addr = os.environ.get("MAIL_FROM", "noreply@yourdomain.com")
    payload = json.dumps({
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_addr, "name": "AI Assessment Studio"},
        "subject": "Your Verification Code — AI Assessment Studio",
        "content": [
            {"type": "text/plain", "value": f"Your AI Assessment Studio verification code is: {otp}\n\nValid for 10 minutes.\n\nVisit: https://ai-interview-platform-3-vdic.onrender.com"},
            {"type": "text/html",  "value": _otp_html_body(otp)},
        ]
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[OTP] SendGrid response: {resp.status}")
            return resp.status == 202
    except urllib.error.HTTPError as http_err:
        err_body = http_err.read().decode() if http_err.fp else ""
        print(f"[OTP] SendGrid HTTP error {http_err.code}: {err_body[:200]}")
        return False
    except urllib.error.URLError as url_err:
        print(f"[OTP] SendGrid URL error: {url_err.reason}")
        return False


def _send_via_smtp(to_email, otp, mail_user, mail_pass):
    """SMTP fallback — may be blocked on Render free tier."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your Verification Code — AI Assessment Studio"
    msg["From"] = f"AI Assessment Studio <{mail_user}>"
    msg["To"] = to_email
    msg.attach(MIMEText(f"Your AI Assessment Studio verification code is: {otp}\n\nValid for 10 minutes.\n\nVisit: https://ai-interview-platform-3-vdic.onrender.com", "plain"))
    msg.attach(MIMEText(_otp_html_body(otp), "html"))

    import socket
    result = {"ok": False}

    def _smtp_thread():
        try:
            old_to = socket.getdefaulttimeout()
            socket.setdefaulttimeout(15)
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(mail_user, mail_pass)
                server.sendmail(mail_user, [to_email], msg.as_string())
            result["ok"] = True
            print(f"[OTP] SMTP sent to {to_email} successfully.")
        except Exception as exc:
            print(f"[OTP] SMTP error: {exc}")
        finally:
            socket.setdefaulttimeout(old_to if 'old_to' in dir() else None)

    t = threading.Thread(target=_smtp_thread, daemon=True)
    t.start()
    t.join(timeout=8)
    return result["ok"]


def send_slot_unlocked_email(to_email, candidate_name):
    """Send an automated HTML notification email when candidate slot is unlocked."""
    subject = "🎉 Your Assessment Slot Has Been Unlocked — AI Assessment Studio"
    candidate_display = (candidate_name or "Candidate").strip()
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 32px; background: #080e1e; color: #e2e8f0; border-radius: 16px; border: 1px solid rgba(0, 255, 255, 0.25);">
      <div style="text-align: center; margin-bottom: 24px;">
        <span style="background: rgba(0, 255, 255, 0.12); color: #00ffff; border: 1px solid rgba(0, 255, 255, 0.3); border-radius: 100px; padding: 6px 18px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em;">
          Assessment Status Update
        </span>
      </div>
      <h2 style="color: #ffffff; font-size: 22px; font-weight: 800; margin-bottom: 8px; text-align: center;">
        New Interview Slot Authorized!
      </h2>
      <p style="color: #94a3b8; font-size: 15px; line-height: 1.6; margin-bottom: 24px; text-align: center;">
        Great news, <strong>{candidate_display}</strong>! An additional standard evaluation slot has been unlocked for your account on AI Assessment Studio.
      </p>
      <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(0, 255, 255, 0.2); border-radius: 12px; padding: 20px; margin-bottom: 28px;">
        <div style="color: #00ffff; font-weight: 700; font-size: 14px; margin-bottom: 6px;">
          ✓ What's Next?
        </div>
        <div style="color: #cbd5e1; font-size: 13px; line-height: 1.6;">
          Log in to your workspace dashboard to launch your new assessment session. Ensure your camera, microphone, and quiet environment are ready.
        </div>
      </div>
      <div style="text-align: center; margin-bottom: 24px;">
        <a href="https://ai-interview-platform-3-vdic.onrender.com" style="background: linear-gradient(135deg, #00ffff, #0284c7); color: #020510; text-decoration: none; padding: 12px 32px; border-radius: 10px; font-weight: 800; font-size: 15px; display: inline-block;">
          Open AI Assessment Studio &rarr;
        </a>
      </div>
      <p style="color: #475569; font-size: 11px; text-align: center; margin: 0;">
        This is an automated notification from AI Assessment Studio. Please do not reply.
      </p>
    </div>
    """
    
    text_content = f"Hello {candidate_display},\n\nYour standard assessment slot has been unlocked! Log in to your workspace to begin your new evaluation session.\n\nOpen AI Assessment Studio: https://ai-interview-platform-3-vdic.onrender.com"

    def _dispatch():
        # 1. Gmail SMTP (Primary)
        mail_user = (os.environ.get("MAIL_USERNAME") or "").strip()
        mail_pass = (os.environ.get("MAIL_PASSWORD") or "").replace(" ", "").strip()
        if mail_user and mail_pass:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = f"AI Assessment Studio <{mail_user}>"
                msg["To"] = to_email
                msg["Auto-Submitted"] = "auto-generated"
                msg.attach(MIMEText(text_content, "plain"))
                msg.attach(MIMEText(html_content, "html"))
                with smtplib.SMTP("smtp.gmail.com", 587) as server:
                    server.ehlo()
                    server.starttls()
                    server.login(mail_user, mail_pass)
                    server.sendmail(mail_user, [to_email], msg.as_string())
                print(f"[UNLOCK EMAIL] SMTP sent to {to_email}")
                return
            except Exception as exc:
                print(f"[UNLOCK EMAIL] SMTP error: {exc}")

        # 2. Resend (fallback)
        resend_key = (os.environ.get("RESEND_API_KEY") or "").strip()
        if resend_key:
            try:
                from_addr = os.environ.get("MAIL_FROM", f"AI Assessment Studio <{mail_user if mail_user else 'onboarding@resend.dev'}>")
                payload = json.dumps({
                    "from": from_addr,
                    "to": [to_email],
                    "subject": subject,
                    "html": html_content,
                    "text": text_content
                }).encode("utf-8")
                req = urllib.request.Request(
                    "https://api.resend.com/emails",
                    data=payload,
                    headers={
                        "Authorization": f"Bearer {resend_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    print(f"[UNLOCK EMAIL] Resend status: {resp.status}")
                    return
            except Exception as e:
                print(f"[UNLOCK EMAIL] Resend error: {e}")

    t = threading.Thread(target=_dispatch, daemon=True)
    t.start()


def send_otp_email(to_email, otp):
    """
    Send OTP email. Tries providers in priority order:
      1. Gmail SMTP (MAIL_USERNAME + MAIL_PASSWORD — primary sender)
      2. Resend  (fallback — set RESEND_API_KEY)
      3. SendGrid (fallback — set SENDGRID_API_KEY)
    If none are configured, prints OTP to logs (dev/local fallback).
    """
    print(f"[OTP] ── Sending OTP to {to_email} ──")

    # ── 1. Gmail SMTP (primary) ───────────────────────────────────────────────
    mail_user = (os.environ.get("MAIL_USERNAME") or "").strip()
    mail_pass = (os.environ.get("MAIL_PASSWORD") or "").replace(" ", "").strip()
    if mail_user and mail_pass:
        print(f"[OTP] Trying Gmail SMTP ({mail_user})...")
        try:
            result = _send_via_smtp(to_email, otp, mail_user, mail_pass)
            if result:
                print(f"[OTP] ✓ Gmail SMTP: sent to {to_email}")
                return True
            else:
                print(f"[OTP] ✗ Gmail SMTP returned False, trying next provider...")
        except Exception as e:
            print(f"[OTP] ✗ Gmail SMTP exception: {e}")

    # ── 2. Resend (fallback) ──────────────────────────────────────────────────
    resend_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    if resend_key:
        print(f"[OTP] Trying Resend...")
        try:
            ok = _send_via_resend(to_email, otp, resend_key)
            if ok:
                print(f"[OTP] ✓ Resend: sent to {to_email}")
                return True
            else:
                print(f"[OTP] ✗ Resend returned False, trying next provider...")
        except Exception as e:
            print(f"[OTP] ✗ Resend exception: {e}")

    # ── 3. SendGrid (fallback) ────────────────────────────────────────────────
    sg_key = (os.environ.get("SENDGRID_API_KEY") or "").strip()
    if sg_key:
        print(f"[OTP] Trying SendGrid...")
        try:
            ok = _send_via_sendgrid(to_email, otp, sg_key)
            if ok:
                print(f"[OTP] ✓ SendGrid: sent to {to_email}")
                return True
            else:
                print(f"[OTP] ✗ SendGrid returned False")
        except Exception as e:
            print(f"[OTP] ✗ SendGrid exception: {e}")

    # ── Dev fallback: no provider configured ──────────────────────────────────
    print(f"[OTP] No email provider configured. OTP for {to_email}: {otp}")
    return True  # Allow flow to continue in dev/local mode


@app.route("/auth/otp/send", methods=["GET", "POST"])
def send_otp():
    if request.method == "GET":
        return render_template("send_otp.html", error=None)

    try:
        email = (request.form.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return render_template("send_otp.html", error="Please enter a valid email address.")

        # Check user exists or auto-create account for seamless OTP login
        user = User.query.filter_by(email=email).first()
        if not user:
            user_name = email.split("@")[0].capitalize()
            user = User(
                full_name=user_name,
                email=email,
                password=generate_password_hash(os.urandom(24).hex()),
                auth_provider="otp"
            )
            db.session.add(user)
            try:
                db.session.commit()
                print(f"[OTP] Auto-created user account for {email}")
            except Exception as e:
                db.session.rollback()
                print(f"[OTP] Error auto-creating user account: {e}")

        otp = str(random.randint(100000, 999999))
        session["otp_code"] = otp
        session["otp_email"] = email

        if send_otp_email(email, otp):
            return redirect("/auth/otp/verify")
        else:
            return render_template("send_otp.html", error="Failed to send OTP email. Please try again or use password login.")

    except Exception as e:
        print(f"[send_otp] Unexpected error: {e}")
        db.session.rollback()
        return render_template("send_otp.html", error="Something went wrong. Please try again.")



@app.route("/auth/otp/verify", methods=["GET", "POST"])
def verify_otp():
    if "otp_code" not in session:
        return redirect("/auth/otp/send")

    if request.method == "GET":
        return render_template("verify_otp.html", error=None, email=session.get("otp_email", ""))

    entered = (request.form.get("otp") or "").strip()
    if entered == session.get("otp_code"):
        email = session.pop("otp_email", None)
        session.pop("otp_code", None)
        user = User.query.filter_by(email=email).first()
        if user:
            session["user_id"] = user.id
            session["user_name"] = user.full_name
            session["user_email"] = user.email
            if not profile_is_complete(user):
                return redirect("/register")
            return redirect("/dashboard")
    return render_template("verify_otp.html", error="Invalid OTP. Please try again.", email=session.get("otp_email", ""))



# ─────────────────────────────────────────────────────────────────────────────
# COMPANY QUESTIONS  –  legacy routes redirect to tech-questions hub
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/company-questions")
def company_questions_home():
    if "user_id" not in session:
        return redirect("/login")
    return redirect("/tech-questions")


@app.route("/company-questions/<company_key>")
def company_questions_detail(company_key):
    if "user_id" not in session:
        return redirect("/login")
    return redirect(f"/tech-questions/{company_key}")


# ─────────────────────────────────────────────────────────────────────────────
# TECH QUESTIONS  –  Company Interview Prep Hub (curated external links only)
# ─────────────────────────────────────────────────────────────────────────────

COMPANY_HUB = [
    {
        "key": "google",
        "name": "Google",
        "color": "#4285F4",
        "description": "Data Structures, Algorithms, System Design, and Behavioral questions frequently asked at Google interviews.",
        "total_questions": 4,
        "resources": [
            {"site": "LeetCode",      "label": "Google Tagged Problems",       "desc": "Filter and solve coding problems tagged specifically for Google — sorted by frequency and difficulty.",          "url": "https://leetcode.com/company/google/",                           "icon": "bi-code-slash"},
            {"site": "GeeksForGeeks", "label": "Google Interview Questions",   "desc": "Topic-wise DSA prep, system design guides, and real interview experiences shared by Google candidates.",        "url": "https://www.geeksforgeeks.org/google-interview-preparation/",    "icon": "bi-mortarboard-fill"},
            {"site": "PrepInsta",     "label": "Google Placement Papers",      "desc": "Aptitude rounds, coding tests, and placement paper patterns based on past Google recruitment drives.",          "url": "https://prepinsta.com/google/",                                  "icon": "bi-file-earmark-text-fill"},
            {"site": "InterviewBit",  "label": "Google Interview Prep",        "desc": "Structured mock interviews, real Q&A from candidates, and company-specific preparation guides.",               "url": "https://www.interviewbit.com/google-interview-questions/",       "icon": "bi-chat-left-dots-fill"},
        ],
    },
    {
        "key": "microsoft",
        "name": "Microsoft",
        "color": "#00A4EF",
        "description": "OOP, OS, Networking, and problem-solving questions asked across SDE and SDET roles at Microsoft.",
        "total_questions": 4,
        "resources": [
            {"site": "LeetCode",      "label": "Microsoft Tagged Problems",     "desc": "Practice the most frequently asked coding problems tagged for Microsoft SDE and SDET roles.",                  "url": "https://leetcode.com/company/microsoft/",                        "icon": "bi-code-slash"},
            {"site": "GeeksForGeeks", "label": "Microsoft Interview Questions", "desc": "Round-wise preparation guide, interview experiences, and topic coverage for Microsoft placements.",            "url": "https://www.geeksforgeeks.org/microsoft-interview-preparation/", "icon": "bi-mortarboard-fill"},
            {"site": "PrepInsta",     "label": "Microsoft Placement Papers",    "desc": "Aptitude test patterns, coding round formats, and previous year placement papers from Microsoft.",             "url": "https://prepinsta.com/microsoft/",                               "icon": "bi-file-earmark-text-fill"},
            {"site": "InterviewBit",  "label": "Microsoft Interview Prep",      "desc": "Real interview experiences, mock tests, and structured question sets for Microsoft roles.",                    "url": "https://www.interviewbit.com/microsoft-interview-questions/",    "icon": "bi-chat-left-dots-fill"},
        ],
    },
    {
        "key": "amazon",
        "name": "Amazon",
        "color": "#FF9900",
        "description": "Leadership Principles, problem-solving, system design, and behavioral rounds for Amazon SDE roles.",
        "total_questions": 4,
        "resources": [
            {"site": "LeetCode",      "label": "Amazon Tagged Problems",        "desc": "Solve the most frequently asked Amazon SDE problems, filtered by topic and difficulty level.",                 "url": "https://leetcode.com/company/amazon/",                           "icon": "bi-code-slash"},
            {"site": "GeeksForGeeks", "label": "Amazon Interview Questions",    "desc": "Comprehensive preparation covering DSA, Leadership Principles, system design, and past experiences.",          "url": "https://www.geeksforgeeks.org/amazon-interview-preparation/",    "icon": "bi-mortarboard-fill"},
            {"site": "PrepInsta",     "label": "Amazon Placement Papers",       "desc": "Amazon online assessment patterns, aptitude questions, and coding test formats from recent drives.",           "url": "https://prepinsta.com/amazon/",                                  "icon": "bi-file-earmark-text-fill"},
            {"site": "InterviewBit",  "label": "Amazon Interview Prep",         "desc": "Behavioral question bank aligned to Amazon Leadership Principles plus technical DSA prep.",                    "url": "https://www.interviewbit.com/amazon-interview-questions/",       "icon": "bi-chat-left-dots-fill"},
        ],
    },
    {
        "key": "meta",
        "name": "Meta (Facebook)",
        "color": "#1877F2",
        "description": "Graphs, Dynamic Programming, system design at scale, and product sense questions asked at Meta.",
        "total_questions": 4,
        "resources": [
            {"site": "LeetCode",      "label": "Meta Tagged Problems",          "desc": "Top Meta/Facebook-tagged coding problems covering graphs, DP, and array manipulations.",                       "url": "https://leetcode.com/company/facebook/",                         "icon": "bi-code-slash"},
            {"site": "GeeksForGeeks", "label": "Meta Interview Questions",      "desc": "Interview experiences, system design at scale concepts, and topic-wise guides for Meta.",                      "url": "https://www.geeksforgeeks.org/facebook-interview-preparation/",  "icon": "bi-mortarboard-fill"},
            {"site": "PrepInsta",     "label": "Meta Placement Papers",         "desc": "Aptitude and coding round patterns from Meta campus and off-campus recruitment drives.",                       "url": "https://prepinsta.com/facebook/",                                "icon": "bi-file-earmark-text-fill"},
            {"site": "InterviewBit",  "label": "Meta Interview Prep",           "desc": "Real Meta interview Q&A, mock assessments, and tips from candidates who cracked the process.",                "url": "https://www.interviewbit.com/facebook-interview-questions/",     "icon": "bi-chat-left-dots-fill"},
        ],
    },
    {
        "key": "netflix",
        "name": "Netflix",
        "color": "#E50914",
        "description": "Distributed systems, microservices, system design, and culture-fit questions asked at Netflix.",
        "total_questions": 4,
        "resources": [
            {"site": "LeetCode",      "label": "Netflix Tagged Problems",       "desc": "Netflix-tagged coding problems focusing on system design and complex algorithmic challenges.",                  "url": "https://leetcode.com/company/netflix/",                          "icon": "bi-code-slash"},
            {"site": "GeeksForGeeks", "label": "Netflix Interview Questions",   "desc": "Distributed systems, microservices architecture concepts, and interview experience guides.",                   "url": "https://www.geeksforgeeks.org/netflix-interview-questions/",     "icon": "bi-mortarboard-fill"},
            {"site": "PrepInsta",     "label": "Netflix Placement Papers",      "desc": "Placement test formats, aptitude rounds, and coding assessment patterns from Netflix drives.",                 "url": "https://prepinsta.com/netflix/",                                 "icon": "bi-file-earmark-text-fill"},
            {"site": "InterviewBit",  "label": "Netflix Interview Prep",        "desc": "System design deep dives, culture-fit Q&A, and mock interview practice for Netflix roles.",                   "url": "https://www.interviewbit.com/netflix-interview-questions/",      "icon": "bi-chat-left-dots-fill"},
        ],
    },
    {
        "key": "tcs",
        "name": "TCS",
        "color": "#00579C",
        "description": "Aptitude, verbal, logical reasoning, and coding questions for TCS NQT and campus drives.",
        "total_questions": 4,
        "resources": [
            {"site": "PrepInsta",     "label": "TCS NQT Placement Papers",      "desc": "Full TCS NQT mock tests, aptitude papers, verbal ability, and coding round preparation.",                     "url": "https://prepinsta.com/tcs/",                                     "icon": "bi-file-earmark-text-fill"},
            {"site": "GeeksForGeeks", "label": "TCS Interview Questions",       "desc": "Topic-wise preparation guide, HR round questions, and technical interview experiences for TCS.",               "url": "https://www.geeksforgeeks.org/tcs-interview-experience/",        "icon": "bi-mortarboard-fill"},
            {"site": "IndiaBix",      "label": "TCS Aptitude Practice",         "desc": "Quantitative aptitude, logical reasoning, and verbal practice sets matched to TCS NQT patterns.",             "url": "https://www.indiabix.com/",                                      "icon": "bi-calculator-fill"},
            {"site": "InterviewBit",  "label": "TCS Interview Prep",            "desc": "TCS-specific mock tests, real interview Q&A, and structured coding practice for campus drives.",              "url": "https://www.interviewbit.com/tcs-interview-questions/",          "icon": "bi-chat-left-dots-fill"},
        ],
    },
    {
        "key": "infosys",
        "name": "Infosys",
        "color": "#007CC3",
        "description": "Aptitude, reasoning, verbal, and coding questions for Infosys InfyTQ and Springboard assessments.",
        "total_questions": 4,
        "resources": [
            {"site": "PrepInsta",     "label": "Infosys Placement Papers",      "desc": "Mock tests for Infosys online aptitude rounds, verbal sections, and coding challenges.",                      "url": "https://prepinsta.com/infosys/",                                 "icon": "bi-file-earmark-text-fill"},
            {"site": "GeeksForGeeks", "label": "Infosys Interview Questions",   "desc": "Interview experiences, HR round preparation, and topic-wise technical prep for Infosys roles.",               "url": "https://www.geeksforgeeks.org/infosys-interview-experience/",    "icon": "bi-mortarboard-fill"},
            {"site": "InfyTQ",        "label": "Infosys InfyTQ Platform",       "desc": "Official Infosys learning and certification platform — complete courses and mock assessments.",               "url": "https://www.infytq.com/",                                        "icon": "bi-award-fill"},
            {"site": "InterviewBit",  "label": "Infosys Interview Prep",        "desc": "Real interview Q&A from Infosys candidates, aptitude practice, and placement preparation tips.",              "url": "https://www.interviewbit.com/infosys-interview-questions/",      "icon": "bi-chat-left-dots-fill"},
        ],
    },
    {
        "key": "wipro",
        "name": "Wipro",
        "color": "#4CAF50",
        "description": "Aptitude, reasoning, verbal ability, and coding assessments for Wipro NLTH and campus placements.",
        "total_questions": 4,
        "resources": [
            {"site": "PrepInsta",     "label": "Wipro NLTH Placement Papers",   "desc": "Wipro NLTH mock tests, aptitude patterns, written communication, and coding round prep.",                    "url": "https://prepinsta.com/wipro/",                                   "icon": "bi-file-earmark-text-fill"},
            {"site": "GeeksForGeeks", "label": "Wipro Interview Questions",     "desc": "Interview experiences, technical Q&A, and preparation guides for Wipro placement rounds.",                    "url": "https://www.geeksforgeeks.org/wipro-interview-experience/",      "icon": "bi-mortarboard-fill"},
            {"site": "IndiaBix",      "label": "Wipro Aptitude Practice",       "desc": "Quantitative aptitude, logical reasoning, and verbal ability practice aligned to Wipro patterns.",           "url": "https://www.indiabix.com/",                                      "icon": "bi-calculator-fill"},
            {"site": "InterviewBit",  "label": "Wipro Interview Prep",          "desc": "Wipro-specific mock interviews, HR round tips, and structured technical preparation.",                        "url": "https://www.interviewbit.com/wipro-interview-questions/",        "icon": "bi-chat-left-dots-fill"},
        ],
    },
    {
        "key": "accenture",
        "name": "Accenture",
        "color": "#A100FF",
        "description": "Cognitive ability, verbal, logical, and communication-focused questions for Accenture campus drives.",
        "total_questions": 4,
        "resources": [
            {"site": "PrepInsta",     "label": "Accenture Placement Papers",    "desc": "Accenture mock tests covering cognitive ability, verbal reasoning, and communication rounds.",                 "url": "https://prepinsta.com/accenture/",                               "icon": "bi-file-earmark-text-fill"},
            {"site": "GeeksForGeeks", "label": "Accenture Interview Questions", "desc": "Interview experiences, HR round Q&A, and technical preparation guides for Accenture placements.",             "url": "https://www.geeksforgeeks.org/accenture-interview-experience/",  "icon": "bi-mortarboard-fill"},
            {"site": "IndiaBix",      "label": "Accenture Aptitude Practice",   "desc": "Quantitative aptitude and logical reasoning practice sets matched to Accenture test patterns.",              "url": "https://www.indiabix.com/",                                      "icon": "bi-calculator-fill"},
            {"site": "InterviewBit",  "label": "Accenture Interview Prep",      "desc": "Real Accenture interview Q&A, placement tips, and mock rounds from recent campus candidates.",               "url": "https://www.interviewbit.com/accenture-interview-questions/",    "icon": "bi-chat-left-dots-fill"},
        ],
    },
    {
        "key": "cognizant",
        "name": "Cognizant",
        "color": "#1565C0",
        "description": "Aptitude, coding, verbal, and HR round questions for Cognizant GenC, GenC Next, and campus drives.",
        "total_questions": 4,
        "resources": [
            {"site": "PrepInsta",     "label": "Cognizant Placement Papers",    "desc": "Cognizant GenC and GenC Next mock tests, aptitude papers, and coding challenge preparation.",                "url": "https://prepinsta.com/cognizant/",                               "icon": "bi-file-earmark-text-fill"},
            {"site": "GeeksForGeeks", "label": "Cognizant Interview Questions", "desc": "Interview experiences, topic-wise prep, and HR round guidance for Cognizant campus placements.",              "url": "https://www.geeksforgeeks.org/cognizant-interview-experience/",  "icon": "bi-mortarboard-fill"},
            {"site": "IndiaBix",      "label": "Cognizant Aptitude Practice",   "desc": "Quantitative aptitude, verbal, and logical reasoning practice for Cognizant assessment rounds.",             "url": "https://www.indiabix.com/",                                      "icon": "bi-calculator-fill"},
            {"site": "InterviewBit",  "label": "Cognizant Interview Prep",      "desc": "Real interview Q&A and mock rounds specifically tailored for Cognizant placement preparation.",               "url": "https://www.interviewbit.com/cognizant-interview-questions/",    "icon": "bi-chat-left-dots-fill"},
        ],
    },
    {
        "key": "capgemini",
        "name": "Capgemini",
        "color": "#0070AD",
        "description": "Aptitude, pseudocode, essay writing, and behavioral questions for Capgemini recruitment assessments.",
        "total_questions": 4,
        "resources": [
            {"site": "PrepInsta",     "label": "Capgemini Placement Papers",    "desc": "Capgemini mock tests covering aptitude, pseudocode, essay writing, and behavioral assessment rounds.",        "url": "https://prepinsta.com/capgemini/",                               "icon": "bi-file-earmark-text-fill"},
            {"site": "GeeksForGeeks", "label": "Capgemini Interview Questions", "desc": "Interview preparation guide, HR round Q&A, and technical experiences for Capgemini placements.",             "url": "https://www.geeksforgeeks.org/capgemini-interview-experience/",  "icon": "bi-mortarboard-fill"},
            {"site": "IndiaBix",      "label": "Capgemini Aptitude Practice",   "desc": "Aptitude, logical reasoning, and verbal practice sets matching Capgemini assessment patterns.",              "url": "https://www.indiabix.com/",                                      "icon": "bi-calculator-fill"},
            {"site": "InterviewBit",  "label": "Capgemini Interview Prep",      "desc": "Real Capgemini interview Q&A, placement tips, and structured mock preparation resources.",                   "url": "https://www.interviewbit.com/capgemini-interview-questions/",    "icon": "bi-chat-left-dots-fill"},
        ],
    },
]

# Quick lookup by key
COMPANY_HUB_MAP = {c["key"]: c for c in COMPANY_HUB}


@app.route("/tech-questions")
def tech_questions():
    if "user_id" not in session:
        return redirect("/login")
    companies = [
        {"key": c["key"], "name": c["name"], "color": c["color"],
         "description": c["description"], "total_questions": c["total_questions"]}
        for c in COMPANY_HUB
    ]
    return render_template("tech_questions.html", companies=companies)


@app.route("/tech-questions/<company_key>")
def tech_questions_detail(company_key):
    if "user_id" not in session:
        return redirect("/login")
    company = COMPANY_HUB_MAP.get(company_key.lower())
    if not company:
        return redirect("/tech-questions")
    return render_template("company_questions.html", company=company, company_key=company_key.lower())


# ─────────────────────────────────────────────────────────────────────────────
# Initialize tables dynamically on load for WSGI servers like Gunicorn
# ─────────────────────────────────────────────────────────────────────────────
with app.app_context():
    try:
        db.create_all()
        # Verify or add resume_text column dynamic schema update
        try:
            engine = db.engine
            with engine.connect() as conn:
                from sqlalchemy import inspect
                inspector = inspect(engine)
                if inspector.has_table('users'):
                    columns = [c['name'] for c in inspector.get_columns('users')]
                    if 'resume_text' not in columns:
                        conn.execute(db.text("ALTER TABLE users ADD COLUMN resume_text TEXT"))
                        conn.commit()
                        print("Added column 'resume_text' dynamically to users table.")
                    if 'resume_filename' not in columns:
                        conn.execute(db.text("ALTER TABLE users ADD COLUMN resume_filename VARCHAR(255)"))
                        conn.commit()
                        print("Added column 'resume_filename' dynamically to users table.")
                    if 'extra_allowed_interviews' not in columns:
                        conn.execute(db.text("ALTER TABLE users ADD COLUMN extra_allowed_interviews INT DEFAULT 0"))
                        conn.commit()
                        print("Added column 'extra_allowed_interviews' dynamically to users table.")
                if inspector.has_table('interview_results'):
                    res_columns = [c['name'] for c in inspector.get_columns('interview_results')]
                    if 'is_terminated' not in res_columns:
                        conn.execute(db.text("ALTER TABLE interview_results ADD COLUMN is_terminated BOOLEAN DEFAULT 0"))
                        conn.commit()
                        print("Added column 'is_terminated' dynamically to interview_results table.")
                    if 'termination_reason' not in res_columns:
                        conn.execute(db.text("ALTER TABLE interview_results ADD COLUMN termination_reason TEXT"))
                        conn.commit()
                        print("Added column 'termination_reason' dynamically to interview_results table.")
        except Exception as schema_err:
            print(f"Schema check notice: {schema_err}")
        print("Database tables verified/created successfully.")
    except Exception as e:
        print(f"Error creating/verifying database tables: {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)