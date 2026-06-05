# AI Resume Analyzer - Job Portal

A modern Flask-based job portal application with AI-powered resume analysis, real-time job matching, and intelligent recommendations.

## Features

### 🎯 For Candidates
- **User Registration & Authentication**: Create account with unique username
- **Job Search**: Real-time search and filtering through available jobs
- **Resume Upload**: Upload resumes in PDF, DOCX, or TXT format
- **Resume Parsing**: Automatic text extraction from resumes
- **Job Matching**: AI-powered match scoring based on resume-job alignment
- **Personalized Recommendations**: NLP-based suggestions to improve resume (unique per job)
- **Application History**: View all applications with match scores
- **Secure Authentication**: Password hashing with werkzeug.security

### 💼 For Employers
- **Company Registration**: Create employer account with authentication
- **Batch Job Posting**: Post 1-5 jobs simultaneously instead of one at a time
- **Application Management**: View all received applications
- **Resume Downloads**: Securely download candidate resumes
- **Smart Filtering**: Filter applications by match score (High/Medium/Low or custom range)
- **Performance Dashboard**: Track posted jobs and applications received

### 🤖 AI & NLP Features
- **TF-IDF Vectorization**: Extract important keywords from job descriptions
- **Cosine Similarity**: Calculate resume-job match percentage (0-100%)
- **Personalized Recommendations**: Unique suggestions for each resume-job pair using deterministic hashing
- **Keyword Analysis**: Identify missing skills and required technologies

## Tech Stack

- **Backend**: Flask (Python web framework)
- **Database**: MongoDB with PyMongo
- **Frontend**: Bootstrap 5.3.0, Vanilla JavaScript
- **Security**: werkzeug (password hashing), secure file handling
- **Text Processing**: TF-IDF (scikit-learn), pdfplumber, docx2txt
- **Styling**: Bootstrap, custom CSS, dark mode support

## Installation

### Prerequisites
- Python 3.8+
- MongoDB (local or MongoDB Atlas)
- Git

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/YOUR_USERNAME/ai-resume-analyzer.git
cd ai-resume-analyzer
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**
Create a `.env` file in the root directory:
```
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/job_portal
MONGO_DBNAME=job_portal
SECRET_KEY=your-secret-key-here
```

5. **Run the application**
```bash
python app.py
```

Visit `http://localhost:5500` in your browser.

## Project Structure

```
ai-resume-analyzer/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── templates/             # HTML templates
│   ├── index.html
│   ├── candidate_login.html
│   ├── candidate_register.html
│   ├── candidate_dashboard.html
│   ├── employer_login.html
│   ├── employer_register.html
│   └── employer_dashboard.html
├── static/                # Static files (CSS, JS, images)
│   ├── dark-mode.css
│   └── dark-mode.js
├── uploads/               # Resume storage (git ignored)
└── .gitignore            # Git ignore rules
```

## API Routes

### Authentication
- `GET /` - Home page
- `POST /candidate/register` - Candidate registration
- `POST /candidate/login` - Candidate login
- `POST /employer/register` - Employer registration
- `POST /employer/login` - Employer login
- `GET /logout` - Logout

### Candidate Routes
- `GET /candidate/dashboard` - View available jobs and applications
- `POST /candidate/apply` - Submit resume and apply to job
- `GET /api/check-username` - Real-time username validation (AJAX)

### Employer Routes
- `GET /employer/dashboard` - View posted jobs and applications
- `POST /employer/job/create` - Post new jobs (1-5 at a time)
- `GET /download-resume/<filename>` - Download candidate resume

## Key Features Explained

### Username Validation
- 3-20 characters only
- Letters (a-z, A-Z), numbers (0-9), underscores (_)
- Case-insensitive uniqueness checks
- Real-time validation with AJAX
- Format feedback: ✅ available or ❌ taken/invalid

### Batch Job Posting
- Add up to 5 jobs at once
- Dynamic form with add/remove buttons
- Single form submission for efficiency
- Real-time job numbering

### Smart Resume Filtering
- Filter by score range: High (80-100%), Medium (60-79%), Low (0-59%)
- Custom min/max score range filters
- Live application count updates
- Download resumes securely

### AI Recommendations
- Personalized for each resume-job combination
- Uses deterministic hashing for consistency
- Identifies skill gaps
- Provides actionable improvement suggestions
- Unique variants for each job using MD5-based selection

## Database Schema

### Collections

**candidates**
```json
{
  "_id": ObjectId,
  "username": "string",
  "password_hash": "string",
  "created_at": "ISO datetime"
}
```

**employers**
```json
{
  "_id": ObjectId,
  "username": "string",
  "password_hash": "string",
  "created_at": "ISO datetime"
}
```

**jobs**
```json
{
  "_id": ObjectId,
  "employer_name": "string",
  "job_title": "string",
  "job_desc": "string",
  "created_at": "ISO datetime"
}
```

**applications**
```json
{
  "_id": ObjectId,
  "job_id": ObjectId,
  "job_title": "string",
  "employer_name": "string",
  "candidate_name": "string",
  "resume_filename": "string",
  "score": "float (0-100)",
  "recommendations": ["string"],
  "created_at": "ISO datetime"
}
```

## Deployment

### Option 1: Render.com (Recommended)
1. Create account at [render.com](https://render.com)
2. Connect GitHub repository
3. Set environment variables
4. Deploy with one click

### Option 2: Railway.app
1. Create account at [railway.app](https://railway.app)
2. Connect GitHub
3. Set environment variables
4. Auto-deployes

### Option 3: PythonAnywhere
1. Create account at [pythonanywhere.com](https://pythonanywhere.com)
2. Upload code and configure
3. Set MongoDB connection
4. Enable web app

## Environment Variables

```
MONGO_URI          # MongoDB Atlas connection string
MONGO_DBNAME       # Database name (default: job_portal)
SECRET_KEY         # Flask secret key for sessions
PORT               # Server port (default: 5500)
```

## Security Features

- ✅ Password hashing with werkzeug.security
- ✅ Secure session management
- ✅ File upload validation
- ✅ Secure file serving with path verification
- ✅ SQL injection prevention (PyMongo)
- ✅ CSRF protection via session
- ✅ Unique database indexes for usernames

## Performance Optimizations

- TF-IDF caching for job descriptions
- Deterministic recommendation generation (no repeated computation)
- Database indexes on frequently queried fields
- Client-side filtering for responsive UX
- Debounced real-time validation (500ms)

## Common Issues & Solutions

### Issue: "Cannot connect to MongoDB"
**Solution**: Check MongoDB Atlas connection string and whitelist IP address (0.0.0.0/0 for testing)

### Issue: "Resume upload fails"
**Solution**: Ensure uploads folder exists and is writable. Check supported formats (PDF, DOCX, TXT)

### Issue: "Username validation not working"
**Solution**: Ensure `/api/check-username` endpoint is accessible. Check AJAX headers in browser console.

## Contributing

Contributions are welcome! Please fork the repository and create a pull request with your changes.

## License

This project is open source and available under the MIT License.

## Support

For issues, questions, or suggestions, please open an issue on GitHub.

## Author

Created as an AI-powered job portal with resume analysis and matching capabilities.

---

**Last Updated**: June 2026
