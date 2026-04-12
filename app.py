from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from bson.objectid import ObjectId
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
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MONGO_URI"] = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
app.config["MONGO_DBNAME"] = os.environ.get("MONGO_DBNAME", "job_portal")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

mongo_client = MongoClient(app.config["MONGO_URI"])
db = mongo_client[app.config["MONGO_DBNAME"]]


def init_db():
    db.jobs.create_index([("employer_name", 1)])
    db.jobs.create_index([("created_at", -1)])
    db.applications.create_index([("candidate_name", 1)])
    db.applications.create_index([("employer_name", 1)])
    db.applications.create_index([("created_at", -1)])
    db.employers.create_index([("username", 1)], unique=True)
    db.employers.create_index([("created_at", -1)])
    db.candidates.create_index([("username", 1)], unique=True)
    db.candidates.create_index([("created_at", -1)])


def normalize_docs(cursor):
    docs = []
    for doc in cursor:
        doc["id"] = str(doc["_id"])
        docs.append(doc)
    return docs


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


@app.route("/employer/auth")
def employer_auth():
    return render_template("employer_auth.html")


@app.route("/candidate/auth")
def candidate_auth():
    return render_template("candidate_auth.html")


@app.route("/employer/login", methods=["GET", "POST"])
def employer_login():
    message = request.args.get("message")
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        if username and password:
            user = db.employers.find_one({"username": username})
            if user and check_password_hash(user.get("password_hash", ""), password):
                session["role"] = "employer"
                session["user"] = username
                session["user_id"] = str(user["_id"])
                return redirect(url_for("employer_dashboard"))
        message = "Invalid username or password."
    return render_template("employer_login.html", message=message)


@app.route("/employer/register", methods=["GET", "POST"])
def employer_register():
    message = request.args.get("message")
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not username or not password:
            message = "Username and password are required."
        elif password != confirm_password:
            message = "Passwords do not match."
        elif db.employers.find_one({"username": username}):
            message = "That username is already taken."
        else:
            result = db.employers.insert_one({
                "username": username,
                "password_hash": generate_password_hash(password),
                "created_at": datetime.datetime.utcnow().isoformat()
            })
            session["role"] = "employer"
            session["user"] = username
            session["user_id"] = str(result.inserted_id)
            return redirect(url_for("employer_dashboard"))
    return render_template("employer_register.html", message=message)


@app.route("/candidate/login", methods=["GET", "POST"])
def candidate_login():
    message = request.args.get("message")
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        if username and password:
            user = db.candidates.find_one({"username": username})
            if user and check_password_hash(user.get("password_hash", ""), password):
                session["role"] = "candidate"
                session["user"] = username
                session["user_id"] = str(user["_id"])
                return redirect(url_for("candidate_dashboard"))
        message = "Invalid username or password."
    return render_template("candidate_login.html", message=message)


@app.route("/candidate/register", methods=["GET", "POST"])
def candidate_register():
    message = request.args.get("message")
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not username or not password:
            message = "Username and password are required."
        elif password != confirm_password:
            message = "Passwords do not match."
        elif db.candidates.find_one({"username": username}):
            message = "That username is already taken."
        else:
            result = db.candidates.insert_one({
                "username": username,
                "password_hash": generate_password_hash(password),
                "created_at": datetime.datetime.utcnow().isoformat()
            })
            session["role"] = "candidate"
            session["user"] = username
            session["user_id"] = str(result.inserted_id)
            return redirect(url_for("candidate_dashboard"))
    return render_template("candidate_register.html", message=message)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/employer/dashboard")
@login_required("employer")
def employer_dashboard():
    employer = session["user"]
    jobs = normalize_docs(db.jobs.find({"employer_name": employer}).sort("created_at", -1))
    applications = normalize_docs(db.applications.find({"employer_name": employer}).sort("created_at", -1))
    return render_template("employer_dashboard.html", employer=employer, jobs=jobs, applications=applications)


@app.route("/employer/job/create", methods=["POST"])
@login_required("employer")
def create_job():
    employer = session["user"]
    job_title = request.form.get("job_title", "").strip()
    job_desc = request.form.get("job_desc", "").strip()
    if job_title and job_desc:
        db.jobs.insert_one({
            "employer_name": employer,
            "job_title": job_title,
            "job_desc": job_desc,
            "created_at": datetime.datetime.utcnow().isoformat()
        })
    return redirect(url_for("employer_dashboard"))


@app.route("/candidate/dashboard")
@login_required("candidate")
def candidate_dashboard():
    jobs = normalize_docs(db.jobs.find().sort("created_at", -1))
    applications = normalize_docs(db.applications.find({"candidate_name": session["user"]}).sort("created_at", -1))
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

    try:
        job_obj = db.jobs.find_one({"_id": ObjectId(job_id)})
    except Exception:
        job_obj = None

    if not job_obj:
        return redirect(url_for("candidate_dashboard", message="Selected job not found."))

    score = get_similarity(resume_text, job_obj["job_desc"])
    missing_skills = list(set(extract_skills(job_obj["job_desc"])) - set(extract_skills(resume_text)))
    missing_text = ", ".join(missing_skills)

    db.applications.insert_one({
        "job_id": job_obj["_id"],
        "job_title": job_obj["job_title"],
        "employer_name": job_obj["employer_name"],
        "candidate_name": candidate,
        "resume_filename": filename,
        "score": score,
        "missing_skills": missing_text,
        "created_at": datetime.datetime.utcnow().isoformat()
    })

    return redirect(url_for("candidate_dashboard", message="Resume submitted successfully."))


if __name__ == "__main__":
    app.run(debug=True, port=5500)
