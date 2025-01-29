from flask import Flask, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from celery import Celery
import os
import boto3
import requests
import speech_recognition as sr

# Flask app configuration
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:1234@localhost/call'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads/'

db = SQLAlchemy(app)

# Celery configuration
celery = Celery(app.name, broker='redis://localhost:6379/0')
celery.conf.update(app.config)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class CallRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(120), nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    hold_duration = db.Column(db.Integer, nullable=False)
    sentiment = db.Column(db.String(120), nullable=False)
    agent_score = db.Column(db.Float, nullable=False)

# Helper functions
def convert_audio_to_text(file_path):
    recognizer = sr.Recognizer()
    audio_file = sr.AudioFile(file_path)
    with audio_file as source:
        audio_data = recognizer.record(source)
    return recognizer.recognize_google(audio_data)

def analyze_sentiment(text):
    # Use Hugging Face API for sentiment analysis (or any LLM API)
    response = requests.post(
        "https://api-inference.huggingface.co/models/distilbert-base-uncased",
        headers={"Authorization": "Bearer YOUR_HUGGINGFACE_API_KEY"},
        json={"inputs": text}
    )
    return response.json()

def store_file_in_s3(file_path):
    s3 = boto3.client('s3')
    bucket_name = 'your-s3-bucket-name'
    file_name = os.path.basename(file_path)
    s3.upload_file(file_path, bucket_name, file_name)
    return f"s3://{bucket_name}/{file_name}"

# Celery task
@celery.task(bind=True)
def process_call_record(self, file_path):
    text = convert_audio_to_text(file_path)
    sentiment_data = analyze_sentiment(text)
    
    # Calculate call metrics (for now, assuming dummy data)
    duration = 120  # Dummy call duration
    hold_duration = 10  # Dummy hold duration
    agent_score = 0.85  # Dummy agent score
    
    # Store analysis in Postgres
    new_call = CallRecord(
        filename=file_path,
        duration=duration,
        hold_duration=hold_duration,
        sentiment=sentiment_data['label'],
        agent_score=agent_score
    )
    db.session.add(new_call)
    db.session.commit()

    return "Call processed successfully"

# Routes
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    new_user = User(username=data['username'], password=data['password'])
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message": "User registered successfully"}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(username=data['username'], password=data['password']).first()
    if user:
        return jsonify({"message": "Login successful"})
    return jsonify({"message": "Invalid credentials"}), 401

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"message": "No selected file"}), 400

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)

    # Store file in S3 and process in the background
    file_url = store_file_in_s3(file_path)
    process_call_record.apply_async(args=[file_path])
    
    return jsonify({"message": "File uploaded and processing started", "file_url": file_url})

@app.route('/results/<int:call_id>', methods=['GET'])
def get_results(call_id):
    call_record = CallRecord.query.get(call_id)
    if call_record:
        return jsonify({
            "filename": call_record.filename,
            "duration": call_record.duration,
            "hold_duration": call_record.hold_duration,
            "sentiment": call_record.sentiment,
            "agent_score": call_record.agent_score
        })
    return jsonify({"message": "Call record not found"}), 404

if __name__ == '__main__':
    app.run(debug=True)
