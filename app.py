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

if __name__ == '__main__':
    app.run(debug=True)
