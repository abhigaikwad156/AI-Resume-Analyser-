from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from bson.objectid import ObjectId
import pdfplumber
import docx2txt
import os
import datetime
import hashlib
import re

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


def validate_username(username):
    """Validate username format: 3-20 chars, only letters, numbers, underscores"""
    if not username or len(username) < 3 or len(username) > 20:
        return False, "Username must be between 3 and 20 characters."
    
    # Only allow letters (a-z, A-Z), numbers (0-9), and underscores (_)
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return False, "Username can only contain letters, numbers, and underscores."
    
    return True, "Valid"


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
        "sql", "html", "css", "javascript", "react", "node", "aws", "docker",
        "git", "api", "rest", "agile", "scrum", "leadership", "communication",
        "project management", "database", "mongodb", "postgresql", "kubernetes"
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


# 🔹 Generate AI-based recommendations for resume improvement
def generate_ai_recommendations(resume_text, job_desc, job_title):
    """
    Generate actionable AI recommendations to help candidates improve their resumes
    """
    recommendations = []

    resume_text = resume_text or ""
    job_desc = job_desc or ""
    resume_lower = resume_text.lower()
    job_lower = job_desc.lower()

    # deterministically vary phrasing per resume+job so recommendations are unique
    seed = (resume_text[:500] + job_desc[:500])
    def pick_variant(key, options):
        h = hashlib.md5((seed + key).encode()).hexdigest()
        idx = int(h, 16) % len(options)
        return options[idx]

    # 1) Extract explicit skills
    resume_skills = set(extract_skills(resume_text))
    job_skills = set(extract_skills(job_desc))
    missing_skills = list(job_skills - resume_skills)

    # 2) Extract top job keywords using TF-IDF when available
    top_keywords = []
    try:
        if TfidfVectorizer is not None and job_desc.strip():
            vec = TfidfVectorizer(stop_words='english', ngram_range=(1, 2))
            tfidf = vec.fit_transform([job_desc])
            feature_array = vec.get_feature_names_out()
            tfidf_scores = tfidf.toarray()[0]
            pairs = list(zip(feature_array, tfidf_scores))
            pairs.sort(key=lambda x: x[1], reverse=True)
            top_keywords = [p[0] for p in pairs[:8]]
    except Exception:
        top_keywords = []

    # Fallback: frequent long words from job description
    if not top_keywords:
        tokens = [w for w in job_lower.split() if len(w) > 4]
        freq = {}
        for t in tokens:
            freq[t] = freq.get(t, 0) + 1
        top_keywords = sorted(freq.keys(), key=lambda k: freq[k], reverse=True)[:8]

    # Filter keywords that appear in the resume
    unmatched_keywords = [k for k in top_keywords if k and k not in resume_lower]

    # Personalized recommendation: missing technical skills
    if missing_skills:
        sample = ", ".join(missing_skills[:4])
        first_skill = missing_skills[0]
        verb = pick_variant("skill_verb", ["Implemented", "Built", "Developed", "Integrated"])
        # longer, detailed personalized recommendation
        recommendations.append({
            "type": "skill",
            "title": "Add role-specific technical skills",
            "description": (
                f"The job posting specifically mentions these skills: {sample}. Your resume doesn't show direct experience with {first_skill}. "
                f"To improve your match score, add 1–2 detailed bullets demonstrating hands-on experience with this skill. "
                f"For example, write: '{verb} {first_skill} to achieve a measurable outcome (e.g. reduced processing time by 30% or improved system reliability).' "
                f"If you lack direct professional experience, describe relevant projects, coursework, or self-study that demonstrates your familiarity and capability with {first_skill}."
            ),
            "priority": "high"
        })

    # Personalized keyword alignment with example bullet suggestions
    if unmatched_keywords:
        sample_kw = unmatched_keywords[:4]
        kw_list = ", ".join(sample_kw)
        verb = pick_variant("align_verb", ["Worked on", "Led efforts in", "Contributed to", "Implemented"])
        # longer, detailed personalized recommendation
        recommendations.append({
            "type": "alignment",
            "title": f"Mirror job wording for {job_title}",
            "description": (
                f"The job posting repeatedly emphasizes these keywords: {kw_list}. Your resume doesn't use this terminology, which lowers your ATS (Applicant Tracking System) match score. "
                f"Rewrite or add resume bullets using these exact keywords to describe your relevant experience. For example: '{verb} {sample_kw[0]} to improve system reliability and user satisfaction.' "
                f"Use action verbs combined with these keywords and always include a measurable outcome or benefit. This simple change can significantly improve your visibility to both automated systems and human recruiters."
            ),
            "priority": "high"
        })

    # Suggest quoting specific job sentences as inspiration (personalized)
    job_sentences = [s.strip() for s in job_desc.split('.') if s.strip()]
    insp_sentences = []
    for sent in job_sentences:
        lc = sent.lower()
        # choose sentences containing top keywords that are missing from resume
        if any(kw in lc for kw in unmatched_keywords[:3]):
            insp_sentences.append(sent)
    if insp_sentences:
        chosen = insp_sentences[0]
        verb = pick_variant("insp_verb", ["Led", "Implemented", "Designed", "Improved"])
        recommendations.append({
            "type": "example",
            "title": "Phrasing inspiration",
            "description": (
                f"Here's a key phrase from the job posting: '{chosen}'. Study this sentence to understand what the employer values. "
                f"Now rewrite your own resume bullet to mirror this phrasing while staying true to your actual experience. "
                f"For example, if the posting says this, you might write: '{verb} a solution that directly addresses their requirement and delivered measurable results (e.g., cost savings, faster processing, improved quality).' "
                f"This approach ensures your resume speaks the employer's language and emphasizes the outcomes they care about."
            ),
            "priority": "medium"
        })

    # Experience phrasing: check for action verbs and suggest concrete verbs
    experience_verbs = ["developed", "implemented", "designed", "led", "optimized", "deployed", "managed", "built"]
    has_action = any(v in resume_lower for v in experience_verbs)
    if not has_action:
        sample_kw = unmatched_keywords[0] if unmatched_keywords else job_title
        verb = pick_variant("action_verb", ["Developed", "Implemented", "Optimized", "Designed", "Led"])
        recommendations.append({
            "type": "keyword",
            "title": "Use strong action verbs",
            "description": (
                f"Your resume uses weak language that doesn't convey strong accomplishments. Start every bullet point with a powerful action verb such as: "
                f"{verb}, Architected, Engineered, Accelerated, Scaled, Automated. For example: '{verb} {sample_kw} to achieve a 25% improvement in performance.' "
                f"Then always include the outcome—what changed, improved, or was achieved as a result. This structure makes your accomplishments stand out to hiring managers."
            ),
            "priority": "high"
        })

    # Metrics recommendation: look for numeric evidence
    if not any(ch.isdigit() for ch in resume_text):
        example = pick_variant("metric_example", [
            "Reduced page load time by 40% by refactoring caching.",
            "Improved CI/CD deploy success to 99% by automating tests.",
            "Cut processing cost by 25% by optimizing data pipelines."
        ])
        recommendations.append({
            "type": "metrics",
            "title": "Add quantifiable impact",
            "description": (
                "Resumes without numbers are less compelling and harder to remember. Every bullet should ideally quantify the impact: a percentage improvement, dollar amount saved, time reduced, or number of users affected. "
                f"For example: {example} Even estimates are better than no numbers. If you improved something, think about the scale (10% faster, 50% cheaper, 5x more users served). "
                "These metrics prove your value and make you stand out among candidates."
            ),
            "priority": "high"
        })

    # Certifications (personalized): if job requests certs, call out names if present
    cert_keywords = ["certification", "certified", "aws", "azure", "gcp", "pmp", "cissp", "ccna"]
    certs_in_job = [w for w in cert_keywords if w in job_lower]
    has_cert = any(w in resume_lower for w in cert_keywords)
    if certs_in_job and not has_cert:
        recommendations.append({
            "type": "certification",
            "title": "Add relevant certifications",
            "description": (
                f"The job posting specifically mentions certifications such as {', '.join(certs_in_job)}, which suggests they're important for this role. "
                f"If you hold any of these certifications, add them prominently to your resume in a dedicated Certifications section near the top. "
                f"If you don't yet have these certifications but are actively pursuing them, mention it (e.g., 'AWS Solutions Architect – Associate (expected Q3 2024)'). "
                f"If neither applies, consider adding related coursework, training, or self-study that demonstrates foundational knowledge in this area."
            ),
            "priority": "medium"
        })

    # Soft skills: personalized suggestion if job emphasizes them
    soft_skills = ["communication", "teamwork", "problem-solving", "analytical", "collaborat"]
    job_soft = [s for s in soft_skills if s in job_lower]
    resume_soft = [s for s in soft_skills if s in resume_lower]
    if job_soft and len(resume_soft) < len(job_soft):
        skill_examples = pick_variant("soft_example", [
            "Led a cross-functional team to deliver a product on schedule.",
            "Coordinated with stakeholders to reduce delivery risk and improve quality.",
            "Facilitated technical discussions to align engineering and business goals."
        ])
        recommendations.append({
            "type": "soft_skills",
            "title": "Show soft skills with examples",
            "description": (
                f"The job posting emphasizes soft skills: {', '.join(job_soft)}. Your resume currently lacks evidence of these attributes. Add specific examples from your experience that demonstrate each of these skills. "
                f"For instance: {skill_examples} Use concrete situations (the problem, your role, the outcome) to show how you've successfully applied these soft skills. "
                f"Hiring managers increasingly value collaboration, communication, and adaptability, so showcasing these strengths will strengthen your candidacy."
            ),
            "priority": "medium"
        })

    # Length/structure personalized advice
    resume_length = len(resume_text.split())
    if resume_length < 250:
        recommendations.append({
            "type": "content",
            "title": "Expand relevant experience",
            "description": "Your resume is quite brief, which may not give hiring managers enough information to assess your qualifications fully. Add 2–3 detailed achievement-focused bullets per recent role that highlight concrete results and accomplishments related to this position. Focus on your most relevant roles and explain what you built, improved, or led. Include metrics wherever possible (e.g., 'Reduced response time by 30%' rather than just 'Improved response time'). A well-filled one-page resume is much more persuasive than a sparse one.",
            "priority": "medium"
        })
    elif resume_length > 1200:
        recommendations.append({
            "type": "content",
            "title": "Focus and condense",
            "description": "Trim older or irrelevant details and prioritize achievements that match this job's top keywords.",
            "priority": "low"
        })

    # If we still have no recommendations, return a friendly generic hint
    if not recommendations:
        recommendations.append({
            "type": "general",
            "title": "Strong alignment with some room for polish",
            "description": "Your resume aligns well with this job posting. To further strengthen your candidacy, mirror a few key phrases from the job posting into your resume to improve ATS matching. Add one or two quantifiable metrics to demonstrate impact. Ensure each role has 3–5 achievement-focused bullets that highlight outcomes, not just responsibilities. Finally, review the job description one more time and look for any technical terms or keywords you might have missed—if they appear in your experience, add them to increase visibility.",
            "priority": "low"
        })

    # Return a single, longer, detailed recommendation chosen deterministically
    h = hashlib.md5(seed.encode()).hexdigest()
    idx = int(h, 16) % len(recommendations)
    chosen = recommendations[idx]
    final_text = chosen.get('description', 'We recommend improving your resume for this role.')
    return [{
        'description': final_text,
        'priority': chosen.get('priority', 'medium')
    }]


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
        else:
            # Validate username format
            is_valid, validation_message = validate_username(username)
            if not is_valid:
                message = validation_message
            elif db.employers.find_one({"username": username}):
                message = "Username already taken. Please choose another one."
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
        else:
            # Validate username format
            is_valid, validation_message = validate_username(username)
            if not is_valid:
                message = validation_message
            elif db.candidates.find_one({"username": username}):
                message = "Username already taken. Please choose another one."
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


@app.route("/api/check-username", methods=["POST"])
def check_username():
    """AJAX endpoint to check if username is available (real-time validation)"""
    data = request.get_json()
    username = data.get("username", "").strip().lower()
    user_type = data.get("type", "candidate")  # "candidate" or "employer"
    
    # Validate format
    is_valid, validation_message = validate_username(username)
    if not is_valid:
        return jsonify({
            "available": False,
            "message": validation_message,
            "valid_format": False
        })
    
    # Check if username exists (case-insensitive)
    collection = db.candidates if user_type == "candidate" else db.employers
    exists = collection.find_one({"username": username}) is not None
    
    if exists:
        return jsonify({
            "available": False,
            "message": "Username already taken. Please choose another one.",
            "valid_format": True
        })
    else:
        return jsonify({
            "available": True,
            "message": "Username available!",
            "valid_format": True
        })


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/download-resume/<filename>")
@login_required("employer")
def download_resume(filename):
    """Serve resume files for download (only for logged-in employers)"""
    try:
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(filename))
        # Verify file exists and is in the uploads folder
        if os.path.exists(filepath) and os.path.dirname(os.path.abspath(filepath)) == os.path.abspath(app.config["UPLOAD_FOLDER"]):
            return send_file(filepath, as_attachment=True)
        else:
            return redirect(url_for("employer_dashboard", message="Resume file not found."))
    except Exception as e:
        return redirect(url_for("employer_dashboard", message="Error downloading resume."))


@app.route("/employer/dashboard")
@login_required("employer")
def employer_dashboard():
    employer = session["user"]
    jobs = normalize_docs(db.jobs.find({"employer_name": employer}).sort("created_at", -1))
    applications = normalize_docs(db.applications.find({"employer_name": employer}).sort("created_at", -1))
    message = request.args.get("message", "")
    return render_template("employer_dashboard.html", employer=employer, jobs=jobs, applications=applications, message=message)


@app.route("/employer/job/create", methods=["POST"])
@login_required("employer")
def create_job():
    employer = session["user"]
    
    # Handle both single job (old format) and multiple jobs (new batch format)
    job_titles = request.form.getlist("job_titles")
    job_descs = request.form.getlist("job_descs")
    
    # If empty arrays, try old single job format for backward compatibility
    if not job_titles:
        job_title = request.form.get("job_title", "").strip()
        job_desc = request.form.get("job_desc", "").strip()
        if job_title and job_desc:
            job_titles = [job_title]
            job_descs = [job_desc]
    
    # Create jobs
    created_count = 0
    for title, desc in zip(job_titles, job_descs):
        title = title.strip()
        desc = desc.strip()
        if title and desc:
            db.jobs.insert_one({
                "employer_name": employer,
                "job_title": title,
                "job_desc": desc,
                "created_at": datetime.datetime.utcnow().isoformat()
            })
            created_count += 1
    
    if created_count == 1:
        message = "Job posted successfully!"
    elif created_count > 1:
        message = f"{created_count} jobs posted successfully!"
    else:
        message = "No jobs were created. Please fill in all fields."
    
    return redirect(url_for("employer_dashboard", message=message))


@app.route("/candidate/dashboard")
@login_required("candidate")
def candidate_dashboard():
    jobs = normalize_docs(db.jobs.find().sort("created_at", -1))
    applications = normalize_docs(db.applications.find({"candidate_name": session["user"]}).sort("created_at", -1))
    
    # Ensure all applications have recommendations
    for application in applications:
        if 'recommendations' not in application or not application.get('recommendations'):
            try:
                # Try to load resume and generate recommendations
                job_obj = db.jobs.find_one({"_id": ObjectId(application.get('job_id'))})
                if job_obj and application.get('resume_filename'):
                    filepath = os.path.join(app.config["UPLOAD_FOLDER"], application.get('resume_filename'))
                    if os.path.exists(filepath):
                        if application.get('resume_filename').lower().endswith(".pdf"):
                            resume_text = extract_pdf(filepath)
                        elif application.get('resume_filename').lower().endswith(".docx"):
                            try:
                                resume_text = extract_docx(filepath)
                            except Exception:
                                resume_text = ""
                        else:
                            resume_text = ""
                        
                        if resume_text:
                            recommendations = generate_ai_recommendations(
                                resume_text, 
                                job_obj.get("job_desc", ""), 
                                job_obj.get("job_title", "")
                            )
                            application['recommendations'] = recommendations
                            # Optionally update the database
                            try:
                                db.applications.update_one(
                                    {"_id": ObjectId(application['id'])},
                                    {"$set": {"recommendations": recommendations}}
                                )
                            except Exception:
                                pass
            except Exception as e:
                # If recommendation generation fails, provide default recommendations
                application['recommendations'] = [{
                    "type": "general",
                    "title": "Resume Analysis Available",
                    "description": "Your resume has been received. AI recommendations will be generated soon.",
                    "priority": "low"
                }]
    
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
    
    # Generate AI-based recommendations instead of missing skills
    recommendations = generate_ai_recommendations(resume_text, job_obj["job_desc"], job_obj["job_title"])

    db.applications.insert_one({
        "job_id": job_obj["_id"],
        "job_title": job_obj["job_title"],
        "employer_name": job_obj["employer_name"],
        "candidate_name": candidate,
        "resume_filename": filename,
        "score": score,
        "recommendations": recommendations,
        "created_at": datetime.datetime.utcnow().isoformat()
    })

    return redirect(url_for("candidate_dashboard", message="Resume submitted successfully."))


if __name__ == "__main__":
    app.run(debug=True, port=5500)
