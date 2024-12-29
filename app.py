from flask import Flask, request, render_template, flash, jsonify, current_app, redirect, url_for, session
from datetime import datetime
import sqlite3
import os
import re
from werkzeug.utils import secure_filename
from flask import send_from_directory
from PIL import Image
from PyPDF2 import PdfReader
from flask import abort
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask_mail import Mail, Message

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'jpg', 'png', 'gif', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        conn = get_db_connection()
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
        print("An error occurred:", e)
    finally:
        conn.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
                errors.append(f"{file.filename} is not a valid file.")

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

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = 'rishuawasthi1020@gmail.com'
app.config['MAIL_PASSWORD'] = 'vrsz ttrt fukt rvia'
app.config['MAIL_DEFAULT_SENDER'] = 'rishuawasthi1020@gmail.com'

mail = Mail(app)

@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        rating = request.form['rating']
        comments = request.form['comments']
        send_feedback_email(name, email, rating, comments)
        return redirect(url_for('thank_you'))
    return render_template('feedback.html')

def send_feedback_email(name, email, rating, comments):
    msg = MIMEMultipart()
    msg['From'] = app.config['MAIL_USERNAME']
    msg['To'] = 'your-email@example.com'
    msg['Subject'] = 'KISI NE YAAD KIYA'
    body = f"""
    Name: {name}
    Email: {email}
    Rating: {rating}
    Comments: {comments}
    """
    msg.attach(MIMEText(body, 'plain'))
    try:
        with smtplib.SMTP_SSL(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
            server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            server.sendmail(msg['From'], msg['To'], msg.as_string())
    except Exception as e:
        print(f"Error: {str(e)}")

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
    files = conn.execute('SELECT * FROM files WHERE user_id = ?  ORDER by id DESC limit 4', (session['user_id'],)).fetchall()
    conn.close()

    return render_template('dashboard.html', username=session['username'], files=files)

@app.route('/Project')
def Project():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    sort_order = request.args.get('sort', 'none')

    conn = get_db_connection()
    
    if sort_order == 'desc':
        query = '''
        SELECT id, file_name, file_path, upload_time 
        FROM files 
        WHERE user_id = ? 
        ORDER BY file_name DESC
        LIMIT 25
        '''
    elif sort_order == 'none':
        query = '''
        SELECT id, file_name, file_path, upload_time 
        FROM files 
        WHERE user_id = ? 
        ORDER BY upload_time DESC
        LIMIT 25
        '''
    else:
        query = '''
        SELECT id, file_name, file_path, upload_time 
        FROM files 
        WHERE user_id = ? 
        ORDER BY file_name ASC
        LIMIT 25
        '''
    
    files = conn.execute(query, (session['user_id'],)).fetchall()
    conn.close()

    return render_template(
        'Project.html',
        username=session['username'],
        files=files,
        sort_order=sort_order
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

BASE_FOLDER_PATH = 'uploads/folders'
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

@app.route('/login', methods=['POST'])
def login():
    errors = {}
    email = request.form['email'].lower()
    password = request.form['password']

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
        if user['password'] == password:
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
    username = request.form['username']
    email = request.form['email'].lower()
    password = request.form['password']
    confirm_password = request.form['confirm-password']
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
    
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)', (username, email, password))
        conn.commit()
    except sqlite3.IntegrityError:
        errors['email'] = "Email Already Registered!"
        return render_template("signup.html", errors=errors)
    finally:
        conn.close()

    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
