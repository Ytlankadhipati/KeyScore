from flask import (
    Flask, request, render_template, flash, jsonify, current_app,
    redirect, url_for, session, send_from_directory, abort
)
from datetime import datetime
import sqlite3
import os
import re
from werkzeug.utils import secure_filename
from PIL import Image
from PyPDF2 import PdfReader
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask_mail import Mail, Message
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

# Load environment variables from .env
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Secret key from env (fallback only for local dev)
app.secret_key = os.getenv('SECRET_KEY', 'dev-fallback-secret-change-me')

# Upload configuration
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
ALLOWED_EXTENSIONS = {'jpg', 'png', 'gif', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Mail configuration from environment variables
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 465))
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'True').lower() in ('true', '1', 'yes')
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', app.config.get('MAIL_USERNAME'))

mail = Mail(app)

# Database helpers
DB_PATH = os.getenv('DB_PATH', 'users.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    try:
        with conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    description TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
    except Exception as e:
        print("An error occurred creating DB:", e)
    finally:
        conn.close()

# Utility functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/signup')
def signup():
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/loginpage')
def loginpage():
    return render_template('login.html')

@app.route('/uploadfile')
def upload():
    return render_template('upload.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part in the request.', 'error')
            return redirect(url_for('upload_file'))

        files = request.files.getlist('file')
        conn = get_db_connection()
        uploaded_files = []
        errors = []

        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                try:
                    file.save(file_path)
                    conn.execute(
                        'INSERT INTO files (user_id, file_name, file_path) VALUES (?, ?, ?)',
                        (session['user_id'], filename, file_path),
                    )
                    uploaded_files.append(filename)
                except Exception as e:
                    errors.append(f"Error with {filename}: {e}")
            else:
                # In case filename is empty or invalid
                fname = getattr(file, 'filename', 'unknown')
                errors.append(f"{fname} is not a valid file.")

        conn.commit()
        conn.close()

        if uploaded_files:
            flash(f'{len(uploaded_files)} file(s) uploaded successfully!', 'success')
        if errors:
            flash(f'{len(errors)} file(s) failed to upload: {", ".join(errors)}', 'error')

    return render_template('upload.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if request.method == 'POST':
        name = request.form.get('name', '')
        email = request.form.get('email', '')
        rating = request.form.get('rating', '')
        comments = request.form.get('comments', '')
        send_feedback_email(name, email, rating, comments)
        return redirect(url_for('thank_you'))
    return render_template('feedback.html')

def send_feedback_email(name, email, rating, comments):
    # Build email using smtplib (we're not exposing credentials, they come from env)
    msg = MIMEMultipart()
    sender = app.config.get('MAIL_USERNAME') or app.config.get('MAIL_DEFAULT_SENDER')
    msg['From'] = sender
    # Replace with the actual receiver for feedback in production
    msg['To'] = os.getenv('FEEDBACK_RECEIVER', 'your-email@example.com')
    msg['Subject'] = os.getenv('FEEDBACK_SUBJECT', 'Feedback from KeyScore')
    body = f"Name: {name}\nEmail: {email}\nRating: {rating}\nComments: {comments}\n"
    msg.attach(MIMEText(body, 'plain'))

    try:
        if app.config['MAIL_USE_SSL']:
            with smtplib.SMTP_SSL(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.sendmail(msg['From'], msg['To'], msg.as_string())
        else:
            with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                server.starttls()
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.sendmail(msg['From'], msg['To'], msg.as_string())
    except Exception as e:
        # Log the error and continue; in production use proper logger
        print(f"Error sending feedback email: {e}")

@app.route('/thank_you')
def thank_you():
    return render_template('thank_you.html')

@app.route('/Help')
def help():
    return render_template('help.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    conn = get_db_connection()
    files = conn.execute(
        'SELECT * FROM files WHERE user_id = ? ORDER BY id DESC LIMIT 4',
        (session['user_id'],)
    ).fetchall()
    conn.close()

    return render_template('dashboard.html', username=session.get('username'), files=files)

@app.route('/Project', methods=['GET'])
def Project():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    search_query = request.args.get('search', '').strip()
    sort_order = request.args.get('sort', 'none')

    conn = get_db_connection()

    if search_query:
        query = '''
            SELECT id, file_name, file_path, upload_time
            FROM files
            WHERE user_id = ? AND file_name LIKE ?
            ORDER BY upload_time DESC
        '''
        files = conn.execute(query, (session['user_id'], f"%{search_query}%")).fetchall()
    else:
        if sort_order == 'desc':
            order_clause = 'ORDER BY file_name DESC'
        elif sort_order == 'asc':
            order_clause = 'ORDER BY file_name ASC'
        else:
            order_clause = 'ORDER BY upload_time DESC'
        query = f'''
            SELECT id, file_name, file_path, upload_time
            FROM files
            WHERE user_id = ?
            {order_clause}
        '''
        files = conn.execute(query, (session['user_id'],)).fetchall()

    conn.close()

    return render_template(
        'Project.html',
        username=session.get('username'),
        files=files,
        sort_order=sort_order,
        search_query=search_query
    )

@app.route('/delete_file/<filename>')
def delete_file(filename):
    if 'user_id' not in session:
        return redirect(url_for('index'))

    conn = get_db_connection()
    conn.execute('DELETE FROM files WHERE file_name = ? AND user_id = ?', (filename, session['user_id']))
    conn.commit()
    conn.close()

    return redirect(url_for('Project'))

@app.route('/download_file/<filename>')
def download_file(filename):
    if 'user_id' not in session:
        return redirect(url_for('index'))

    upload_folder = current_app.config['UPLOAD_FOLDER']
    return send_from_directory(upload_folder, filename, as_attachment=True)

# Folders functionality
BASE_FOLDER_PATH = os.getenv('BASE_FOLDER_PATH', 'uploads/folders')
os.makedirs(BASE_FOLDER_PATH, exist_ok=True)

@app.route('/create_folder', methods=['POST'])
def create_folder():
    folder_name = request.form.get('folder_name')
    if folder_name:
        folder_path = os.path.join(BASE_FOLDER_PATH, folder_name)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            flash(f"Folder '{folder_name}' created successfully!", 'success')
        else:
            flash(f"Folder '{folder_name}' already exists!", 'error')
    folders = os.listdir(BASE_FOLDER_PATH)
    return render_template('partials/folders.html', folders=folders)

# Authentication routes
@app.route('/login', methods=['POST'])
def login():
    errors = {}
    email = request.form.get('email', '').lower()
    password = request.form.get('password', '')

    if not email:
        errors['email'] = "Please enter an email."
    if not password:
        errors['password'] = "Please enter a password."

    if errors:
        return render_template("login.html", errors=errors)

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()

    if user:
        stored_hash = user['password']
        if check_password_hash(stored_hash, password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        else:
            errors['password'] = "Incorrect password!"
            return render_template("login.html", errors=errors)
    else:
        errors['email'] = "Email not registered!"
        return render_template("login.html", errors=errors)

@app.route('/register', methods=['POST'])
def register():
    errors = {}
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').lower().strip()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm-password', '')
    email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    password_pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$"

    if not username:
        errors['username'] = "Please enter a username."
    if not email:
        errors['email'] = "Please enter an email."
    if not password:
        errors['password'] = "Please enter a password."

    if email and not re.match(email_pattern, email):
        errors['email'] = "Invalid email format!"
    if password and not re.match(password_pattern, password):
        errors['password'] = "Invalid password format! Password must contain at least 8 characters, with one uppercase letter, one lowercase letter, and one number."
    if password != confirm_password:
        errors['confirm-password'] = "Passwords do not match!"

    if errors:
        return render_template("signup.html", errors=errors)

    hashed = generate_password_hash(password)

    conn = get_db_connection()
    try:
        conn.execute(
            'INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
            (username, email, hashed)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        errors['email'] = "Email Already Registered!"
        return render_template("signup.html", errors=errors)
    except Exception as e:
        print("Error creating user:", e)
        errors['general'] = "An error occurred while creating the account."
        return render_template("signup.html", errors=errors)
    finally:
        conn.close()

    return redirect(url_for('index'))

# App start
if __name__ == '__main__':
    init_db()
    # Do not run debug=True in production. Use env var to control debug mode.
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5000))
    app.run(host=host, port=port, debug=debug_mode)
