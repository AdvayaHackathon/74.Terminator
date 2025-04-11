from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
import os


app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for flash messages
bcrypt = Bcrypt(app)

# ✅ MongoDB Atlas Connection
client = MongoClient("mongodb://localhost:27017")
db = client['edupulse_db']  # Database name
contact_collection = db['contact_messages']  # Collection name
users_collection = db["users"]  # ✅ Define this here

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/about')
def about():
    return render_template("about.html")

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get("name")
        email = request.form.get("email")
        message = request.form.get("message")

        contact_data = {
            "name": name,
            "email": email,
            "message": message
        }

        contact_collection.insert_one(contact_data)
        flash("Thanks for contacting us! We'll get back to you soon.")
        return redirect(url_for('contact'))

    return render_template("contact.html")



@app.route('/signup', methods=['POST'])
def signup():
    name = request.form['name']
    email = request.form['email']
    password = generate_password_hash(request.form['password'])

    if users_collection.find_one({"email": email}):
        return jsonify({"status": "fail", "message": "Email already registered."})

    users_collection.insert_one({"name": name, "email": email, "password": password})
    return jsonify({"status": "success", "message": "Signup successful!"})


@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"]
    password = request.form["password"]

    user = users_collection.find_one({"email": email})

    if user and check_password_hash(user["password"], password):
        session["email"] = user["email"]
        return jsonify({"status": "success", "message": "Login successful!"})
    
    return jsonify({"status": "fail", "message": "Invalid email or password."})


@app.route("/teacher_dashboard")
def teacher_dashboard():
    if "email" not in session:
        return redirect(url_for("login"))
    return render_template("teacher_dashboard.html")


if __name__ == '__main__':
    app.run(debug=True)
