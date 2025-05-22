from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import pandas as pd
import pickle
import os
from datetime import datetime

app = Flask(__name__, template_folder='templates')
CORS(app)

model = None
try:
    with open('fraud_model.pkl', 'rb') as f:
        model = pickle.load(f)
    print("✅ Model loaded successfully")
except Exception as e:
    print(f"❌ Error loading model: {e}")
    from sklearn.ensemble import RandomForestClassifier
    model = RandomForestClassifier()
    print("⚠️ Using dummy model for testing")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
def predict():
    if request.method != 'POST':
        return jsonify({'error': 'Method not allowed'}), 405
        
    if model is None:
        return jsonify({'error': 'Model not loaded'}), 500
        
    try:
        data = request.get_json()
        print(f"📦 Received data at {datetime.now()}: {data}")
        
        required_fields = [
            'applicant_income', 'claimed_subsidy_amount', 'land_owned_acres',
            'number_of_dependents', 'previous_claims', 'region', 'is_employed'
        ]
        
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({'error': f'Missing fields: {", ".join(missing_fields)}'}), 400

        input_data = pd.DataFrame({
            'applicant_income': [float(data['applicant_income'])],
            'claimed_subsidy_amount': [float(data['claimed_subsidy_amount'])],
            'land_owned_acres': [float(data['land_owned_acres'])],
            'number_of_dependents': [int(data['number_of_dependents'])],
            'previous_claims': [int(data['previous_claims'])],
            'is_employed': [1 if data['is_employed'] else 0],
            'region_North': [1 if data['region'] == 'North' else 0],
            'region_South': [1 if data['region'] == 'South' else 0],
            'region_West': [1 if data['region'] == 'West' else 0]
        })
        
        prediction = model.predict(input_data)
        probability = model.predict_proba(input_data)[0][1] if hasattr(model, 'predict_proba') else 0.75
        
        return jsonify({
            'prediction': 'Fraudulent' if prediction[0] == 1 else 'Legitimate',
            'probability': round(probability * 100, 2),
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    
    except Exception as e:
        return jsonify({'error': str(e), 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}), 400

if __name__ == '__main__':
   
    print(f"🚀 Starting server at {datetime.now()}")
    print(f"📂 Current directory: {os.getcwd()}")
    print(f"🖥️ Template path: {os.path.abspath('templates')}")
    
    if not os.path.exists('templates'):
        os.makedirs('templates')
        print("📁 Created templates directory")
    
    app.run(debug=True, port=5000, host='0.0.0.0')