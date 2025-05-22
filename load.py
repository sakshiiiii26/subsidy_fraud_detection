from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import pickle
import pandas as pd
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "e8328a1d2f9c47208a3f7f2ea92b3cbecba67fa23d4c8c345fcaa31706b6d3d0"

# Load ML model
with open('model/fraud_model.pkl', 'rb') as f:
    model = pickle.load(f)

# Database connection
def get_db_connection():
    conn = sqlite3.connect('subsidy.db')
    conn.row_factory = sqlite3.Row
    return conn

# Initialize database
def init_db():
    conn = sqlite3.connect('subsidy.db')
    cursor = conn.cursor()

    # Drop tables if they exist (for development only)
    cursor.execute('DROP TABLE IF EXISTS applications')
    cursor.execute('DROP TABLE IF EXISTS users')

    # Create tables
    cursor.execute('''
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        is_admin BOOLEAN DEFAULT FALSE
    )
    ''')

    cursor.execute('''
    CREATE TABLE applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT NOT NULL,
        aadhaar TEXT NOT NULL,
        pan TEXT,
        phone TEXT NOT NULL,
        email TEXT,
        address TEXT NOT NULL,
        subsidy_type TEXT NOT NULL,
        income DECIMAL(10,2),
        family_members INTEGER,
        existing_benefits TEXT,
        application_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending',
        is_fraud BOOLEAN DEFAULT NULL,
        admin_notes TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # Add admin user
    from werkzeug.security import generate_password_hash
    hashed_password = generate_password_hash('admin123')
    cursor.execute('INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)', 
                  ('admin', hashed_password, True))

    conn.commit()
    conn.close()


# Routes
@app.route('/')
def home():
    return render_template('apply.html')

@app.route('/apply', methods=['POST'])
def apply():
    data = request.form
    
    # Basic validation
    required_fields = ['name', 'aadhaar', 'phone', 'address', 'subsidy_type']
    for field in required_fields:
        if not data.get(field):
            return "Missing required fields", 400
    
    conn = get_db_connection()
    try:
        # Check if Aadhaar already applied
        existing = conn.execute('SELECT id FROM applications WHERE aadhaar = ?', 
                               (data['aadhaar'],)).fetchone()
        if existing:
            return "Application with this Aadhaar already exists", 400
            
        # Insert application
        conn.execute('''
        INSERT INTO applications (
            name, aadhaar, pan, phone, email, address, 
            subsidy_type, income, family_members, existing_benefits
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['name'],
            data['aadhaar'],
            data.get('pan', ''),
            data['phone'],
            data.get('email', ''),
            data['address'],
            data['subsidy_type'],
            float(data.get('income', 0)),
            int(data.get('family_members', 1)),
            data.get('existing_benefits', '')
        ))
        conn.commit()
        application_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    finally:
        conn.close()
    
    return redirect(url_for('application_result', id=application_id))

@app.route('/result/<int:id>')
def application_result(id):
    conn = get_db_connection()
    application = conn.execute('SELECT * FROM applications WHERE id = ?', (id,)).fetchone()
    conn.close()
    return render_template('result.html', application=application)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['is_admin'] = user['is_admin']
            if user['is_admin']:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('home'))
        else:
            return "Invalid credentials", 401
    
    return render_template('login.html')

@app.route('/admin')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    pending = conn.execute('SELECT * FROM applications WHERE status = "pending"').fetchall()
    processed = conn.execute('SELECT * FROM applications WHERE status != "pending"').fetchall()
    conn.close()
    
    return render_template('admin.html', pending=pending, processed=processed)

@app.route('/predict/<int:id>')
def predict_fraud(id):
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    application = conn.execute('SELECT * FROM applications WHERE id = ?', (id,)).fetchone()
    
    if not application:
        return jsonify({'error': 'Application not found'}), 404
    
    # Prepare features for prediction
    features = {
        'income': application['income'],
        'family_members': application['family_members'],
        'existing_benefits': len(application['existing_benefits'].split(',')) if application['existing_benefits'] else 0,
        'subsidy_type': application['subsidy_type']  # Will need encoding
    }
    
    # Convert to DataFrame (in a real app, you'd properly encode categorical features)
    df = pd.DataFrame([features])
    
    # Predict
    prediction = model.predict(df)
    probability = model.predict_proba(df)[0][1]  # Probability of being fraud
    
    # Update database
    is_fraud = bool(prediction[0])
    conn.execute('UPDATE applications SET is_fraud = ?, status = "reviewed" WHERE id = ?', 
                (is_fraud, id))
    conn.commit()
    conn.close()
    
    return jsonify({
        'is_fraud': is_fraud,
        'probability': float(probability),
        'message': 'Fraud detected' if is_fraud else 'Likely legitimate'
    })

@app.route('/update_status/<int:id>', methods=['POST'])
def update_status(id):
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    status = data.get('status')
    notes = data.get('notes', '')
    
    conn = get_db_connection()
    conn.execute('UPDATE applications SET status = ?, admin_notes = ? WHERE id = ?', 
                (status, notes, id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)