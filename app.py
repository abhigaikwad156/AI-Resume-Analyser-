from flask import Flask, render_template, request, redirect, url_for, session, g
from werkzeug.utils import secure_filename
import sqlite3
import pdfplumber
import docx2txt
import os
import datetime

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    TfidfVectorizer = None
    cosine_similarity = None

app = Flask(__name__)
app.secret_key = "replace-this-with-a-secure-key"
UPLOAD_FOLDER = "uploads"
DATABASE = "jobs.db"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employer_name TEXT NOT NULL,
            job_title TEXT NOT NULL,
            job_desc TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            candidate_name TEXT NOT NULL,
            resume_filename TEXT NOT NULL,
            score REAL NOT NULL,
            missing_skills TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        """
    )
    db.commit()


with app.app_context():
    init_db()


# 🔹 Extract text from PDF
def extract_pdf(file_path):
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text


# 🔹 Extract text from DOCX
def extract_docx(file_path):
    return docx2txt.process(file_path)


# 🔹 Extract skills (simple keyword matching)
def extract_skills(text):
    skills_list = [
        "python", "java", "c++", "machine learning", "data science",
        "sql", "html", "css", "javascript", "react", "node"
    ]
    found_skills = []
    text = (text or "").lower()
    for skill in skills_list:
        if skill in text:
            found_skills.append(skill)
    return found_skills


# 🔹 Compute similarity

def get_similarity(resume_text, job_desc):
    if TfidfVectorizer is None or cosine_similarity is None:
        return 0.0
    vectorizer = TfidfVectorizer()
    vectors = vectorizer.fit_transform([resume_text or "", job_desc or ""])
    similarity = cosine_similarity(vectors[0], vectors[1])
    return round(float(similarity[0][0]) * 100, 2)


def login_required(role):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if session.get("role") != role:
                return redirect(url_for("home"))
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/employer/login", methods=["GET", "POST"])
def employer_login():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            session["role"] = "employer"
            session["user"] = name
            return redirect(url_for("employer_dashboard"))
    return render_template("employer_login.html")


@app.route("/candidate/login", methods=["GET", "POST"])
def candidate_login():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            session["role"] = "candidate"
            session["user"] = name
            return redirect(url_for("candidate_dashboard"))
    return render_template("candidate_login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/employer/dashboard")
@login_required("employer")
def employer_dashboard():
    db = get_db()
    employer = session["user"]
    jobs = db.execute(
        "SELECT * FROM jobs WHERE employer_name = ? ORDER BY created_at DESC",
        (employer,)
    ).fetchall()
    applications = db.execute(
        "SELECT a.*, j.job_title FROM applications a "
        "JOIN jobs j ON a.job_id = j.id WHERE j.employer_name = ? "
        "ORDER BY a.created_at DESC",
        (employer,)
    ).fetchall()
    return render_template("employer_dashboard.html", employer=employer, jobs=jobs, applications=applications)


@app.route("/employer/job/create", methods=["POST"])
@login_required("employer")
def create_job():
    employer = session["user"]
    job_title = request.form.get("job_title", "").strip()
    job_desc = request.form.get("job_desc", "").strip()
    if job_title and job_desc:
        db = get_db()
        db.execute(
            "INSERT INTO jobs (employer_name, job_title, job_desc, created_at) VALUES (?, ?, ?, ?)",
            (employer, job_title, job_desc, datetime.datetime.utcnow().isoformat())
        )
        db.commit()
    return redirect(url_for("employer_dashboard"))


@app.route("/candidate/dashboard")
@login_required("candidate")
def candidate_dashboard():
    db = get_db()
    jobs = db.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    applications = db.execute(
        "SELECT a.*, j.job_title FROM applications a "
        "JOIN jobs j ON a.job_id = j.id WHERE a.candidate_name = ? "
        "ORDER BY a.created_at DESC",
        (session["user"],)
    ).fetchall()
    message = request.args.get("message")
    return render_template("candidate_dashboard.html", candidate=session["user"], jobs=jobs, applications=applications, message=message)


@app.route("/candidate/apply", methods=["POST"])
@login_required("candidate")
def candidate_apply():
    job_id = request.form.get("job_id")
    file = request.files.get("resume")
    candidate = session["user"]
    if not job_id or not file:
        return redirect(url_for("candidate_dashboard", message="Please select a job and upload a resume."))

    filename = secure_filename(file.filename)
    if not filename:
        return redirect(url_for("candidate_dashboard", message="Invalid resume file."))

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    if filename.lower().endswith(".pdf"):
        resume_text = extract_pdf(filepath)
    elif filename.lower().endswith(".docx"):
        try:
            resume_text = extract_docx(filepath)
        except Exception:
            resume_text = ""
    else:
        return redirect(url_for("candidate_dashboard", message="Only PDF and DOCX resumes are supported."))

    db = get_db()
    job = db.execute("SELECT job_desc FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        return redirect(url_for("candidate_dashboard", message="Selected job not found."))

    score = get_similarity(resume_text, job["job_desc"])
    missing_skills = list(set(extract_skills(job["job_desc"])) - set(extract_skills(resume_text)))
    missing_text = ", ".join(missing_skills)

    db.execute(
        "INSERT INTO applications (job_id, candidate_name, resume_filename, score, missing_skills, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (job_id, candidate, filename, score, missing_text, datetime.datetime.utcnow().isoformat())
    )
    db.commit()

    return redirect(url_for("candidate_dashboard", message="Resume submitted successfully."))


if __name__ == "__main__":
    app.run(debug=True, port=5500)
