import os
import json
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify, session
from werkzeug.utils import secure_filename
from flask import send_file

app = Flask(__name__)
app.secret_key = 'super_secret_instructor_key_change_me'

UPLOAD_FOLDER = 'uploads'
CONFIG_FILE = 'classes_config.json'
DATA_FILE = 'annotations.json'
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

DEFAULT_CLASSES = {
    "Class 01": {
        "password": "Apple1",
        "pdfs": []
    },
    "Class 03": {
        "password": "Banana2",
        "pdfs": []
    }
}

INSTRUCTOR_PASSWORD = "adminpassword"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_classes_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return DEFAULT_CLASSES
    return DEFAULT_CLASSES

def save_classes_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def load_annotations_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_annotations_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

@app.route('/admin/download-annotations')
def download_annotations():
    if not session.get('is_admin'):
        return "Unauthorized", 403
    
    # Ensure annotations.json exists before sending
    if not os.path.exists(DATA_FILE):
        save_annotations_data({})
        
    return send_file(DATA_FILE, as_attachment=True, download_name='annotations_backup.json')

@app.route('/')
def index():
    classes = load_classes_config()
    return render_template('index.html', classes=classes)

@app.route('/verify-class', methods=['POST'])
def verify_class():
    data = request.json
    class_name = data.get("className")
    password = data.get("password")
    classes = load_classes_config()
    
    if class_name in classes and classes[class_name]["password"] == password:
        session[f'authed_{class_name}'] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Incorrect password."}), 401

@app.route('/class/<class_name>')
def class_dashboard(class_name):
    classes = load_classes_config()
    if class_name not in classes:
        return redirect(url_for('index'))
    
    if not session.get(f'authed_{class_name}') and not session.get('is_admin'):
        return redirect(url_for('index'))
        
    return render_template('class_dashboard.html', class_name=class_name, pdfs=classes[class_name]["pdfs"])

@app.route('/verify-admin', methods=['POST'])
def verify_admin():
    data = request.json
    if data.get("password") == INSTRUCTOR_PASSWORD:
        session['is_admin'] = True
        return jsonify({"success": True})
    return jsonify({"success": False}), 401

@app.route('/check-admin', methods=['GET'])
def check_admin():
    return jsonify({"isAdmin": session.get('is_admin', False)})

@app.route('/logout-admin', methods=['POST'])
def logout_admin():
    session.pop('is_admin', None)
    return jsonify({"success": True})

@app.route('/upload', methods=['POST'])
def upload_file():
    if not session.get('is_admin'):
        return "Unauthorized", 403
    
    class_name = request.form.get("class_name")
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    
    if file and allowed_file(file.filename) and class_name:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        classes = load_classes_config()
        if class_name in classes:
            if filename not in classes[class_name]["pdfs"]:
                classes[class_name]["pdfs"].append(filename)
                save_classes_config(classes)
                
        return redirect(url_for('class_dashboard', class_name=class_name))
    return 'Invalid upload. Make sure you selected a class and uploaded a valid PDF file.', 400

@app.route('/uploads/<filename>')
def view_pdf(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/annotate/<filename>')
def annotation_page(filename):
    return render_template('viewer.html', filename=filename)

@app.route('/api/annotations/<filename>', methods=['GET'])
def get_annotations(filename):
    data = load_annotations_data()
    return jsonify(data.get(filename, []))

@app.route('/api/annotations/<filename>', methods=['POST'])
def add_annotation(filename):
    req_data = request.json
    data = load_annotations_data()
    
    if filename not in data:
        data[filename] = []
        
    author = req_data.get("author", "").strip()
    if not author:
        author = "Anonymous"

    new_comment = {
        "id": str(len(data[filename]) + 1) + "_" + os.urandom(2).hex(),
        "author": author,
        "text": req_data.get("text", ""),
        "pageNum": req_data.get("pageNum", 1),
        "x": req_data.get("x", 0),
        "y": req_data.get("y", 0),
        "replies": []
    }
    
    data[filename].append(new_comment)
    save_annotations_data(data)
    return jsonify({"success": True, "comment": new_comment})

@app.route('/api/annotations/<filename>/reply', methods=['POST'])
def add_reply(filename):
    req_data = request.json
    comment_id = req_data.get("comment_id")
    data = load_annotations_data()
    
    if filename in data:
        for c in data[filename]:
            if c["id"] == comment_id:
                author = req_data.get("author", "").strip()
                if not author:
                    author = "Anonymous"
                reply = {
                    "author": author,
                    "text": req_data.get("text", "")
                }
                c["replies"].append(reply)
                save_annotations_data(data)
                return jsonify({"success": True})
                
    return jsonify({"success": False}), 404

@app.route('/api/annotations/<filename>/<comment_id>', methods=['DELETE'])
def delete_annotation(filename, comment_id):
    if not session.get('is_admin'):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    data = load_annotations_data()
    if filename in data:
        data[filename] = [c for c in data[filename] if c["id"] != comment_id]
        save_annotations_data(data)
        return jsonify({"success": True})
    return jsonify({"success": False}), 404

if __name__ == '__main__':
    app.run(debug=True)
