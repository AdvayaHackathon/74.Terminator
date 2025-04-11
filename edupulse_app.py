from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import os
import traceback
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler()])
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for flash messages
bcrypt = Bcrypt(app)

# Configure upload folder before any routes are defined
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
    logger.info(f"Created upload folder: {app.config['UPLOAD_FOLDER']}")

# MongoDB Connection - Using local MongoDB for reliable development
try:
    # Using local MongoDB connection which is more reliable for development
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=5000)
    # Test the connection
    client.admin.command('ping')
    logger.info("Connected successfully to MongoDB")
except (ConnectionFailure, ServerSelectionTimeoutError) as e:
    logger.error(f"MongoDB Connection Error: {e}")
    raise

# Initialize database collections
db = client['edupulse_db']
contact_collection = db['contact_messages']
users_collection = db["users"]
attendance_collection = db["attendance"]
activities_collection = db["activities"]
daily_attendance_collection = db["daily_attendance"]
teacher_monthly_stats = db["teacher_monthly_stats"]
subject_activity_stats = db["subject_activity_stats"]

# Function to verify database connection
def verify_db_connection():
    try:
        # Try to ping the database
        client.admin.command('ping')
        return True
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return False

# Make sure we have at least one test user
def create_test_user():
    try:
        # Check if test user exists
        if not users_collection.find_one({"email": "teacher@example.com"}):
            # Create a test user
            test_user = {
                "name": "Test Teacher",
                "email": "teacher@example.com",
                "password": generate_password_hash("password123")
            }
            users_collection.insert_one(test_user)
            logger.info("Created test user: teacher@example.com with password: password123")
    except Exception as e:
        logger.error(f"Error creating test user: {e}")

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

@app.route("/social_science")
def social_science():
    if "email" not in session:
        return redirect(url_for("login"))
    return render_template("social_science.html")

@app.route("/science")
def science():
    if "email" not in session:
        return redirect(url_for("login"))
    return render_template("science.html")

@app.route("/english")
def english():
    if "email" not in session:
        return redirect(url_for("login"))
    return render_template("english.html")

@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    if "email" not in session:
        logger.warning("Unauthorized attendance marking attempt")
        return jsonify({"status": "fail", "message": "Please login first"})
    
    # Verify database connection before proceeding
    if not verify_db_connection():
        logger.error("Database connection error during attendance marking")
        return jsonify({
            "status": "fail",
            "message": "Database connection error. Please try again."
        })
    
    try:
        logger.info(f"Received attendance marking request from: {session['email']}")
        
        # Log form data for debugging
        logger.info(f"Form data: {request.form}")
        logger.info(f"Files: {request.files}")
        
        # Get form data
        subject = request.form.get("subject")
        activity_type = request.form.get("activity_type")
        
        # Validate required fields
        if not subject:
            logger.warning("Missing subject in attendance request")
            return jsonify({"status": "fail", "message": "Subject is required"})
            
        if not activity_type:
            logger.warning("Missing activity_type in attendance request")
            return jsonify({"status": "fail", "message": "Activity type is required"})
        
        # Get current date info
        current_date = datetime.now()
        today = current_date.strftime("%Y-%m-%d")
        
        # Get teacher details
        teacher = users_collection.find_one({"email": session["email"]})
        if not teacher:
            logger.error(f"Teacher not found: {session['email']}")
            return jsonify({"status": "fail", "message": "Teacher not found"})

        # Handle file upload
        if 'activity_photos' not in request.files:
            logger.warning("No activity photos in request")
            return jsonify({"status": "fail", "message": "Activity photos are required for attendance"})
        
        files = request.files.getlist('activity_photos')
        if not files or files[0].filename == '':
            logger.warning("Empty file selection")
            return jsonify({"status": "fail", "message": "Please select at least one photo"})
        
        # Create date-based directory for photos
        date_folder = os.path.join(app.config['UPLOAD_FOLDER'], today)
        if not os.path.exists(date_folder):
            os.makedirs(date_folder)
            logger.info(f"Created date folder: {date_folder}")
        
        # Save files with timestamps
        file_paths = []
        for file in files:
            if file and file.filename:
                timestamp = datetime.now().strftime("%H%M%S")
                filename = secure_filename(f"{session['email']}_{timestamp}_{file.filename}")
                file_path = os.path.join(date_folder, filename)
                try:
                    file.save(file_path)
                    logger.info(f"Saved file: {file_path}")
                    file_paths.append(file_path)
                except Exception as e:
                    logger.error(f"Error saving file {filename}: {e}")
                    return jsonify({
                        "status": "fail",
                        "message": f"Error saving file: {str(e)}"
                    })

        # First mark the daily attendance
        daily_attendance = {
            "teacher_id": str(teacher.get("_id", "")),
            "teacher_email": session["email"],
            "teacher_name": teacher.get("name", "Unknown"),
            "date": current_date,
            "date_str": today,
            "time_in": current_date.strftime("%H:%M:%S"),
            "status": "present",
            "attendance_method": "activity_completion",
            "created_at": current_date
        }

        # Insert or update daily attendance with error handling
        try:
            attendance_result = daily_attendance_collection.update_one(
                {
                    "teacher_email": session["email"],
                    "date_str": today
                },
                {"$setOnInsert": daily_attendance},
                upsert=True
            )
            
            logger.info(f"Attendance result: {attendance_result.acknowledged}")
            
            if not attendance_result.acknowledged:
                raise Exception("Failed to record attendance")
                
        except Exception as e:
            logger.error(f"Error recording attendance: {e}")
            return jsonify({
                "status": "fail",
                "message": "Failed to record attendance in database"
            })
        
        # Record activity completion with photos
        activity_record = {
            "teacher_id": str(teacher.get("_id", "")),
            "teacher_email": session["email"],
            "teacher_name": teacher.get("name", "Unknown"),
            "subject": subject,
            "activity_type": activity_type,
            "completion_date": current_date,
            "date_str": today,
            "completion_time": current_date.strftime("%H:%M:%S"),
            "photo_paths": file_paths,
            "photo_count": len(file_paths),
            "status": "completed",
            "verified": True,
            "created_at": current_date
        }
        
        # Insert activity record with error handling
        try:
            activity_result = activities_collection.insert_one(activity_record)
            logger.info(f"Activity result: {activity_result.acknowledged}")
            
            if not activity_result.acknowledged:
                raise Exception("Failed to record activity")
        except Exception as e:
            logger.error(f"Error recording activity: {e}")
            return jsonify({
                "status": "fail",
                "message": "Failed to record activity in database"
            })
        
        # Update statistics with error handling
        try:
            # Update monthly attendance statistics
            monthly_stats_result = teacher_monthly_stats.update_one(
                {
                    "teacher_email": session["email"],
                    "year": current_date.year,
                    "month": current_date.month
                },
                {
                    "$inc": {
                        "days_present": 1,
                        "activities_completed": 1,
                        "photos_submitted": len(file_paths)
                    },
                    "$set": {
                        "last_activity_date": current_date,
                        "last_updated": current_date
                    },
                    "$setOnInsert": {
                        "teacher_name": teacher.get("name", "Unknown"),
                        "created_at": current_date
                    }
                },
                upsert=True
            )
            logger.info(f"Monthly stats update result: {monthly_stats_result.acknowledged}")

            # Update subject-wise activity tracking
            subject_stats_result = subject_activity_stats.update_one(
                {
                    "teacher_email": session["email"],
                    "subject": subject,
                    "year": current_date.year,
                    "month": current_date.month
                },
                {
                    "$inc": {
                        "total_activities": 1,
                        f"activity_counts.{activity_type}": 1
                    },
                    "$set": {
                        "last_activity_date": current_date,
                        "last_activity_type": activity_type
                    },
                    "$setOnInsert": {
                        "teacher_name": teacher.get("name", "Unknown"),
                        "created_at": current_date
                    }
                },
                upsert=True
            )
            logger.info(f"Subject stats update result: {subject_stats_result.acknowledged}")

        except Exception as e:
            logger.error(f"Error updating statistics: {e}")
            # Continue as the main records are saved
        
        logger.info("Attendance and activity recorded successfully")
        return jsonify({
            "status": "success",
            "message": "Attendance marked and activity recorded successfully",
            "data": {
                "attendance_date": today,
                "attendance_time": current_date.strftime("%H:%M:%S"),
                "subject": subject,
                "activity_type": activity_type,
                "photos_uploaded": len(file_paths),
                "attendance_verified": True
            }
        })
        
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error marking attendance: {str(e)}")
        logger.error(error_trace)
        return jsonify({
            "status": "fail",
            "message": f"Failed to mark attendance: {str(e)}"
        })

@app.route("/get_attendance_status")
def get_attendance_status():
    if "email" not in session:
        return jsonify({"status": "fail", "message": "Please login first"})
    
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Check daily attendance
        attendance = daily_attendance_collection.find_one({
            "teacher_email": session["email"],
            "date_str": today
        })
        
        # Get today's activities
        activities = list(activities_collection.find({
            "teacher_email": session["email"],
            "date_str": today
        }))
        
        return jsonify({
            "status": "success",
            "data": {
                "is_present": bool(attendance),
                "attendance_time": attendance.get("time_in") if attendance else None,
                "activities_completed": len(activities),
                "last_activity": activities[-1] if activities else None
            }
        })
        
    except Exception as e:
        print(f"Error getting attendance status: {str(e)}")
        return jsonify({
            "status": "fail",
            "message": "Failed to get attendance status"
        })

@app.route("/get_activity_status")
def get_activity_status():
    if "email" not in session:
        return jsonify({"status": "fail", "message": "Please login first"})
    
    subject = request.args.get("subject")
    date = datetime.now().date()
    
    # Check if activity is completed for today
    activity = activities_collection.find_one({
        "teacher_email": session["email"],
        "subject": subject,
        "completion_date": {
            "$gte": datetime.combine(date, datetime.min.time()),
            "$lte": datetime.combine(date, datetime.max.time())
        }
    })
    
    return jsonify({
        "status": "success",
        "completed": bool(activity)
    })

@app.route("/debug/check_attendance")
def debug_check_attendance():
    if "email" not in session:
        return jsonify({"status": "fail", "message": "Please login first"})
    
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Get all records for debugging
        daily_attendance = daily_attendance_collection.find_one({
            "teacher_email": session["email"],
            "date_str": today
        })
        
        activities = list(activities_collection.find({
            "teacher_email": session["email"],
            "date_str": today
        }))
        
        monthly_stats = teacher_monthly_stats.find_one({
            "teacher_email": session["email"],
            "year": datetime.now().year,
            "month": datetime.now().month
        })
        
        return jsonify({
            "status": "success",
            "data": {
                "daily_attendance": {
                    "exists": bool(daily_attendance),
                    "record": str(daily_attendance) if daily_attendance else None
                },
                "activities": {
                    "count": len(activities),
                    "records": [str(act) for act in activities]
                },
                "monthly_stats": str(monthly_stats) if monthly_stats else None
            }
        })
        
    except Exception as e:
        return jsonify({
            "status": "fail",
            "message": f"Error checking attendance: {str(e)}"
        })

if __name__ == '__main__':
    # Create test user for easy login
    create_test_user()
    
    # Run the app
    logger.info("Starting Flask application...")
    app.run(debug=True)
