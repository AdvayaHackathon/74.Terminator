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
import calendar

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
principals_collection = db["principals"]
attendance_collection = db["attendance"]
activities_collection = db["activities"]
daily_attendance_collection = db["daily_attendance"]
teacher_monthly_stats = db["teacher_monthly_stats"]
subject_activity_stats = db["subject_activity_stats"]
curriculum_collection = db["curriculum"]
course_progress_collection = db["course_progress"]

# Activity types with associated icons and colors
ACTIVITY_TYPES = {
    "quiz": {"icon": "fas fa-question-circle", "color": "blue-500"},
    "video": {"icon": "fas fa-video", "color": "red-500"},
    "pdf": {"icon": "fas fa-file-pdf", "color": "orange-500"},
    "interactive": {"icon": "fas fa-hands", "color": "green-500"},
    "discussion": {"icon": "fas fa-comments", "color": "purple-500"}
}

# Function to verify database connection
def verify_db_connection():
    try:
        # Try to ping the database
        client.admin.command('ping')
        return True
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return False

# Make sure we have at least one test user and principal
def create_test_users():
    try:
        # Check if test user exists
        if not users_collection.find_one({"email": "teacher@example.com"}):
            # Create a test user
            test_user = {
                "name": "Test Teacher",
                "email": "teacher@example.com",
                "password": generate_password_hash("password123"),
                "school": "Test School",
                "teacher_id": "TEST001",
                "subject": "science",
                "class": "class9",
                "role": "teacher",
                "created_at": datetime.now()
            }
            users_collection.insert_one(test_user)
            logger.info("Created test user: teacher@example.com with password: password123")
            
        # Check if test principal exists
        if not principals_collection.find_one({"email": "principal@example.com"}):
            # Create a test principal
            test_principal = {
                "name": "Test Principal",
                "email": "principal@example.com",
                "password": generate_password_hash("admin123"),
                "school": "Test School",
                "role": "principal",
                "created_at": datetime.now()
            }
            principals_collection.insert_one(test_principal)
            logger.info("Created test principal: principal@example.com with password: admin123")
    except Exception as e:
        logger.error(f"Error creating test users: {e}")

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
    school = request.form['school']
    teacher_id = request.form['teacher_id']
    subject = request.form['subject']
    class_level = request.form['class']

    if users_collection.find_one({"email": email}):
        return jsonify({"status": "fail", "message": "Email already registered."})
    
    if users_collection.find_one({"teacher_id": teacher_id}):
        return jsonify({"status": "fail", "message": "Teacher ID already registered."})

    users_collection.insert_one({
        "name": name, 
        "email": email, 
        "password": password,
        "school": school,
        "teacher_id": teacher_id,
        "subject": subject,
        "class": class_level,
        "created_at": datetime.now()
    })
    
    return jsonify({"status": "success", "message": "Signup successful!"})

@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"]
    password = request.form["password"]

    # First check if this is a teacher
    user = users_collection.find_one({"email": email})

    if user and check_password_hash(user["password"], password):
        session["email"] = user["email"]
        session["name"] = user["name"]
        session["teacher_id"] = user.get("teacher_id", "")
        session["school"] = user.get("school", "")
        session["subject"] = user.get("subject", "")
        session["class"] = user.get("class", "")
        session["role"] = "teacher"
        return jsonify({"status": "success", "message": "Login successful!", "redirect": "/teacher_dashboard"})
    
    # If not a teacher, check if it's a principal
    principal = principals_collection.find_one({"email": email})
    
    if principal and check_password_hash(principal["password"], password):
        session["email"] = principal["email"]
        session["name"] = principal["name"]
        session["school"] = principal.get("school", "")
        session["role"] = "principal"
        return jsonify({"status": "success", "message": "Login successful!", "redirect": "/principal_dashboard"})
    
    return jsonify({"status": "fail", "message": "Invalid email or password."})

@app.route("/teacher_dashboard")
@app.route("/teacher_dashboard/<class_level>")
def teacher_dashboard(class_level=None):
    if "email" not in session:
        return redirect(url_for("login"))
    
    try:
        # Get the teacher's class and subject from session or request
        if class_level and class_level in ["class8", "class9", "class10"]:
            current_class = class_level
        else:
            current_class = session.get("class", "class9")  # Default to class9 if not set
        
        subject = session.get("subject", "science")  # Default to science if not set
        
        logger.info(f"Loading dashboard for {session['email']}, class: {current_class}, subject: {subject}")
        
        # Get or initialize teacher's progress
        progress = get_or_initialize_progress(session["email"], current_class, subject)
        
        # Get curriculum for this class and subject
        curriculum = curriculum_collection.find_one({
            "class": current_class,
            "subject": subject
        })
        
        # Get today's random activity
        daily_activity = get_daily_activity(session["email"], current_class, subject)
        logger.info(f"Daily activity data: {daily_activity}")
        
        # Generate weekly schedule
        weekly_schedule = generate_weekly_schedule(session["email"], current_class, subject)
        logger.info(f"Weekly schedule generated with {len(weekly_schedule)} days")
        
        # Calculate attendance percentage for current month
        attendance_data = calculate_teacher_attendance(session["email"])
        logger.info(f"Attendance data: {attendance_data}")
        
        return render_template(
            "teacher_dashboard.html", 
            progress=progress,
            curriculum=curriculum,
            daily_activity=daily_activity,
            weekly_schedule=weekly_schedule,
            current_class=current_class,
            activity_types=ACTIVITY_TYPES,
            attendance=attendance_data
        )
    except Exception as e:
        logger.error(f"Error loading dashboard: {e}")
        flash(f"An error occurred while loading your dashboard. Please try again later.", "error")
        # Return a basic dashboard with error information
        return render_template(
            "teacher_dashboard.html",
            progress=None,
            curriculum=None,
            daily_activity=None,
            weekly_schedule=None,
            current_class=class_level or session.get("class", "class9"),
            activity_types=ACTIVITY_TYPES,
            error_message="We encountered an error loading your dashboard. Please try again later."
        )

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
            "teacher_id": teacher.get("teacher_id", ""),
            "teacher_email": session["email"],
            "teacher_name": teacher.get("name", "Unknown"),
            "school": teacher.get("school", "Unknown"),
            "subject": teacher.get("subject", ""),
            "class": teacher.get("class", ""),
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
            "teacher_id": teacher.get("teacher_id", ""),
            "teacher_email": session["email"],
            "teacher_name": teacher.get("name", "Unknown"),
            "school": teacher.get("school", "Unknown"),
            "subject": subject,
            "class": teacher.get("class", ""),
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
                        "teacher_id": teacher.get("teacher_id", ""),
                        "school": teacher.get("school", "Unknown"),
                        "subject": teacher.get("subject", ""),
                        "class": teacher.get("class", ""),
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
                    "class": teacher.get("class", ""),
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
                        "teacher_id": teacher.get("teacher_id", ""),
                        "school": teacher.get("school", "Unknown"),
                        "class": teacher.get("class", ""),
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

# Initialize curriculum for different classes and subjects if not present
def initialize_curriculum():
    try:
        # Check if curriculum already exists
        if curriculum_collection.count_documents({}) == 0:
            logger.info("Initializing curriculum data...")
            
            # Sample curriculum structure for different classes and subjects
            classes = ["class8", "class9", "class10"]
            subjects = ["science", "social_science", "english", "mathematics"]
            
            for class_level in classes:
                for subject in subjects:
                    # Create curriculum data with modules for each class-subject combination
                    modules = [
                        {
                            "module_id": 1,
                            "title": f"Introduction to {subject.replace('_', ' ').title()}",
                            "activities": [
                                {"activity_id": 1, "type": "video", "title": "Course Overview", "duration": 15},
                                {"activity_id": 2, "type": "pdf", "title": "Reading Materials", "duration": 30},
                                {"activity_id": 3, "type": "quiz", "title": "Basic Concepts Quiz", "duration": 20},
                                {"activity_id": 4, "type": "interactive", "title": "Engage with Concepts", "duration": 25}
                            ]
                        },
                        {
                            "module_id": 2,
                            "title": "Core Concepts",
                            "activities": [
                                {"activity_id": 5, "type": "video", "title": "Key Principles", "duration": 20},
                                {"activity_id": 6, "type": "interactive", "title": "Hands-on Exercise", "duration": 35},
                                {"activity_id": 7, "type": "discussion", "title": "Group Discussion", "duration": 40},
                                {"activity_id": 8, "type": "quiz", "title": "Progress Check", "duration": 15}
                            ]
                        },
                        {
                            "module_id": 3,
                            "title": "Advanced Topics",
                            "activities": [
                                {"activity_id": 9, "type": "pdf", "title": "Research Materials", "duration": 45},
                                {"activity_id": 10, "type": "video", "title": "Expert Insights", "duration": 25},
                                {"activity_id": 11, "type": "interactive", "title": "Problem Solving", "duration": 40},
                                {"activity_id": 12, "type": "quiz", "title": "Mastery Test", "duration": 30}
                            ]
                        },
                        {
                            "module_id": 4,
                            "title": "Practical Applications",
                            "activities": [
                                {"activity_id": 13, "type": "interactive", "title": "Real-world Applications", "duration": 50},
                                {"activity_id": 14, "type": "video", "title": "Case Studies", "duration": 30},
                                {"activity_id": 15, "type": "pdf", "title": "Additional Resources", "duration": 35},
                                {"activity_id": 16, "type": "discussion", "title": "Reflection Session", "duration": 25}
                            ]
                        },
                        {
                            "module_id": 5,
                            "title": "Final Assessment",
                            "activities": [
                                {"activity_id": 17, "type": "video", "title": "Review Session", "duration": 20},
                                {"activity_id": 18, "type": "pdf", "title": "Study Guide", "duration": 30},
                                {"activity_id": 19, "type": "interactive", "title": "Preparation Exercise", "duration": 35},
                                {"activity_id": 20, "type": "quiz", "title": "Final Examination", "duration": 60}
                            ]
                        }
                    ]
                    
                    # Calculate total activities and duration
                    total_activities = sum(len(module["activities"]) for module in modules)
                    total_duration = sum(activity["duration"] for module in modules for activity in module["activities"])
                    
                    curriculum_data = {
                        "class": class_level,
                        "subject": subject,
                        "title": f"{class_level.replace('class', 'Class ')} {subject.replace('_', ' ').title()}",
                        "modules": modules,
                        "total_activities": total_activities,
                        "total_duration": total_duration,
                        "created_at": datetime.now()
                    }
                    
                    curriculum_collection.insert_one(curriculum_data)
            
            logger.info(f"Curriculum initialized for {len(classes)} classes and {len(subjects)} subjects")
        else:
            # Ensure all class-subject combinations have curriculum data
            classes = ["class8", "class9", "class10"]
            subjects = ["science", "social_science", "english", "mathematics"]
            
            for class_level in classes:
                for subject in subjects:
                    # Check if this class-subject combination exists
                    existing = curriculum_collection.find_one({
                        "class": class_level,
                        "subject": subject
                    })
                    
                    if not existing:
                        logger.info(f"Adding missing curriculum for {class_level} {subject}")
                        
                        # Create curriculum data with modules for this class-subject combination
                        modules = [
                            {
                                "module_id": 1,
                                "title": f"Introduction to {subject.replace('_', ' ').title()}",
                                "activities": [
                                    {"activity_id": 1, "type": "video", "title": "Course Overview", "duration": 15},
                                    {"activity_id": 2, "type": "pdf", "title": "Reading Materials", "duration": 30},
                                    {"activity_id": 3, "type": "quiz", "title": "Basic Concepts Quiz", "duration": 20},
                                    {"activity_id": 4, "type": "interactive", "title": "Engage with Concepts", "duration": 25}
                                ]
                            },
                            {
                                "module_id": 2,
                                "title": "Core Concepts",
                                "activities": [
                                    {"activity_id": 5, "type": "video", "title": "Key Principles", "duration": 20},
                                    {"activity_id": 6, "type": "interactive", "title": "Hands-on Exercise", "duration": 35},
                                    {"activity_id": 7, "type": "discussion", "title": "Group Discussion", "duration": 40},
                                    {"activity_id": 8, "type": "quiz", "title": "Progress Check", "duration": 15}
                                ]
                            }
                        ]
                        
                        # Calculate total activities and duration
                        total_activities = sum(len(module["activities"]) for module in modules)
                        total_duration = sum(activity["duration"] for module in modules for activity in module["activities"])
                        
                        curriculum_data = {
                            "class": class_level,
                            "subject": subject,
                            "title": f"{class_level.replace('class', 'Class ')} {subject.replace('_', ' ').title()}",
                            "modules": modules,
                            "total_activities": total_activities,
                            "total_duration": total_duration,
                            "created_at": datetime.now()
                        }
                        
                        curriculum_collection.insert_one(curriculum_data)
    except Exception as e:
        logger.error(f"Error initializing curriculum: {e}")

# Initialize curriculum after app startup
initialize_curriculum()

# Get or initialize teacher's course progress 
def get_or_initialize_progress(teacher_email, class_level, subject):
    try:
        # Check if progress exists
        progress = course_progress_collection.find_one({
            "teacher_email": teacher_email,
            "class": class_level,
            "subject": subject
        })
        
        if not progress:
            # Get curriculum for this class and subject
            curriculum = curriculum_collection.find_one({
                "class": class_level,
                "subject": subject
            })
            
            if not curriculum:
                logger.error(f"No curriculum found for {class_level} {subject}")
                # Return a default progress object instead of None
                return {
                    "teacher_email": teacher_email,
                    "class": class_level,
                    "subject": subject,
                    "modules_progress": [],
                    "completed_activities": 0,
                    "total_activities": 0,
                    "progress_percentage": 0,
                    "last_activity_date": None,
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                }
            
            # Initialize progress data with all activities marked as not completed
            modules_progress = []
            for module in curriculum["modules"]:
                module_activities = []
                for activity in module["activities"]:
                    module_activities.append({
                        "activity_id": activity["activity_id"],
                        "type": activity["type"],
                        "title": activity["title"],
                        "completed": False,
                        "completion_date": None
                    })
                
                modules_progress.append({
                    "module_id": module["module_id"],
                    "title": module["title"],
                    "activities": module_activities,
                    "completed_activities": 0,
                    "total_activities": len(module_activities)
                })
            
            # Calculate total stats
            total_activities = curriculum["total_activities"]
            
            # Create progress record
            try:
                teacher = users_collection.find_one({"email": teacher_email})
                teacher_name = teacher["name"] if teacher else "Unknown Teacher"
            except Exception as e:
                logger.error(f"Error getting teacher details: {e}")
                teacher_name = "Unknown Teacher"
            
            progress_data = {
                "teacher_email": teacher_email,
                "teacher_name": teacher_name,
                "class": class_level,
                "subject": subject,
                "modules_progress": modules_progress,
                "completed_activities": 0,
                "total_activities": total_activities,
                "progress_percentage": 0,
                "last_activity_date": None,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            
            try:
                course_progress_collection.insert_one(progress_data)
                progress = progress_data
            except Exception as e:
                logger.error(f"Error inserting new progress: {e}")
                # Still return the data even if we couldn't save it
                progress = progress_data
        
        return progress
    
    except Exception as e:
        logger.error(f"Error getting or initializing progress: {e}")
        # Return a default progress object instead of None
        return {
            "teacher_email": teacher_email,
            "class": class_level,
            "subject": subject,
            "modules_progress": [],
            "completed_activities": 0,
            "total_activities": 0,
            "progress_percentage": 0,
            "last_activity_date": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }

# Generate a random next activity that hasn't been completed yet
def generate_next_activity(modules_progress):
    try:
        # Collect all incomplete activities
        incomplete_activities = []
        
        for module in modules_progress:
            for activity in module["activities"]:
                if not activity["completed"]:
                    incomplete_activities.append({
                        "module_id": module["module_id"],
                        "module_title": module["title"],
                        "activity_id": activity["activity_id"],
                        "activity_title": activity["title"],
                        "activity_type": activity["type"]
                    })
        
        if not incomplete_activities:
            return None
        
        # Randomly select one of the incomplete activities
        import random
        next_activity = random.choice(incomplete_activities)
        
        return next_activity
    
    except Exception as e:
        logger.error(f"Error generating next activity: {e}")
        return None

# Mark an activity as completed and update progress
def mark_activity_completed(teacher_email, class_level, subject, activity_id):
    try:
        # Get the teacher's progress
        progress = course_progress_collection.find_one({
            "teacher_email": teacher_email,
            "class": class_level,
            "subject": subject
        })
        
        if not progress:
            logger.error(f"No progress found for {teacher_email} in {class_level} {subject}")
            return False
        
        # Find and update the activity
        activity_found = False
        modules_progress = progress["modules_progress"]
        
        for module in modules_progress:
            for activity in module["activities"]:
                if activity["activity_id"] == activity_id and not activity["completed"]:
                    activity["completed"] = True
                    activity["completion_date"] = datetime.now()
                    module["completed_activities"] += 1
                    activity_found = True
                    break
            
            if activity_found:
                break
        
        if not activity_found:
            logger.warning(f"Activity {activity_id} not found or already completed")
            return False
        
        # Update total completed activities and percentage
        completed_activities = sum(module["completed_activities"] for module in modules_progress)
        progress_percentage = int((completed_activities / progress["total_activities"]) * 100)
        
        # Update the progress record
        course_progress_collection.update_one(
            {
                "teacher_email": teacher_email,
                "class": class_level,
                "subject": subject
            },
            {
                "$set": {
                    "modules_progress": modules_progress,
                    "completed_activities": completed_activities,
                    "progress_percentage": progress_percentage,
                    "last_activity_date": datetime.now(),
                    "updated_at": datetime.now()
                }
            }
        )
        
        return True
    
    except Exception as e:
        logger.error(f"Error marking activity as completed: {e}")
        return False

# Generate a daily random activity based on date for consistency
def get_daily_activity(teacher_email, class_level, subject):
    try:
        today = datetime.now().date()
        today_str = today.strftime("%Y-%m-%d")
        yesterday = today - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y-%m-%d")
        
        # Check if we already have an assigned activity for today (completed or not)
        today_activity = activities_collection.find_one({
            "teacher_email": teacher_email,
            "class": class_level,
            "subject": subject,
            "date_str": today_str
        })
        
        # If there's an activity for today that's completed, return it
        if today_activity and today_activity.get("status") == "completed":
            logger.info(f"Found completed activity for today: {today_activity}")
            return {
                "completed": True, 
                "activity": {
                    "activity_id": today_activity.get("activity_id", 0),
                    "activity_title": today_activity.get("activity_title", "Unknown Activity"),
                    "activity_type": today_activity.get("activity_type", "quiz"),
                    "module_title": today_activity.get("module_title", "Completed Activity"),
                }, 
                "message": "Today's activity already completed"
            }
        # If there's an assigned but not completed activity, return it
        elif today_activity and today_activity.get("status") == "assigned":
            logger.info(f"Found assigned activity for today: {today_activity}")
            return {
                "completed": False, 
                "activity": {
                    "activity_id": today_activity.get("activity_id", 0),
                    "activity_title": today_activity.get("activity_title", "Unknown Activity"),
                    "activity_type": today_activity.get("activity_type", "quiz"),
                    "module_title": today_activity.get("module_title", "Assigned Activity"),
                }, 
                "message": "Today's activity ready"
            }
        
        # Get teacher's progress
        progress = course_progress_collection.find_one({
            "teacher_email": teacher_email,
            "class": class_level,
            "subject": subject
        })
        
        if not progress:
            # Need to initialize progress first
            progress = get_or_initialize_progress(teacher_email, class_level, subject)
            if not progress or not progress.get("modules_progress"):
                logger.error(f"Failed to get or initialize progress for {teacher_email}, {class_level}, {subject}")
                return {"completed": False, "activity": None, "message": "No curriculum found"}
        
        # Get all incomplete activities grouped by type
        activities_by_type = {
            "quiz": [],
            "video": [],
            "interactive": [],
            "pdf": [],
            "discussion": []
        }
        
        # Track total activities found
        total_activities_found = 0
        
        for module in progress.get("modules_progress", []):
            for activity in module.get("activities", []):
                total_activities_found += 1
                if not activity.get("completed", True):
                    activity_type = activity.get("type", "quiz")
                    if activity_type in activities_by_type:
                        activities_by_type[activity_type].append({
                            "module_id": module.get("module_id", 0),
                            "module_title": module.get("title", "Unknown Module"),
                            "activity_id": activity.get("activity_id", 0),
                            "activity_title": activity.get("title", "Unknown Activity"),
                            "activity_type": activity_type
                        })
        
        # Get all incomplete activities
        incomplete_activities = []
        for activities in activities_by_type.values():
            incomplete_activities.extend(activities)
        
        logger.info(f"Found {len(incomplete_activities)} incomplete activities out of {total_activities_found} total")
        
        if not incomplete_activities:
            if total_activities_found > 0:
                return {"completed": False, "activity": None, "message": "All activities completed"}
            else:
                return {"completed": False, "activity": None, "message": "No activities found for this class and subject"}
        
        # Check what activity type was assigned yesterday
        yesterday_activity = activities_collection.find_one({
            "teacher_email": teacher_email,
            "class": class_level,
            "subject": subject,
            "date_str": yesterday_str
        })
        
        yesterday_activity_type = yesterday_activity.get("activity_type", None) if yesterday_activity else None
        
        # Get available activity types that have activities and aren't the same as yesterday
        available_types = []
        for activity_type, activities in activities_by_type.items():
            if activities and activity_type != yesterday_activity_type:
                available_types.append(activity_type)
        
        # If no other types are available, use any type with activities
        if not available_types:
            available_types = [t for t, activities in activities_by_type.items() if activities]
        
        # Get previously assigned activities from the past 7 days to avoid repetition
        recent_date = today - timedelta(days=7)
        recent_activities = list(activities_collection.find({
            "teacher_email": teacher_email,
            "class": class_level,
            "subject": subject,
            "completion_date": {"$gte": datetime.combine(recent_date, datetime.min.time())}
        }))
        
        # Extract activity IDs that were recently completed
        recent_activity_ids = [act.get("activity_id") for act in recent_activities if act.get("activity_id")]
        
        # Use the date as a seed for random selection to ensure the same activity is shown all day
        import random
        # Create a seed from the date and teacher email to keep it consistent for the whole day
        seed = f"{today_str}_{teacher_email}"
        random.seed(seed)
        
        # Randomly select an activity type for today, preferring one different from yesterday
        if available_types:
            selected_type = random.choice(available_types)
            
            # Filter out recently completed activities for variety
            fresh_activities = [
                act for act in activities_by_type[selected_type] 
                if act["activity_id"] not in recent_activity_ids
            ]
            
            # If no fresh activities are available, use all activities of this type
            if not fresh_activities:
                fresh_activities = activities_by_type[selected_type]
            
            # Select one random activity for today
            daily_activity = random.choice(fresh_activities)
        else:
            # Fallback to any incomplete activity
            # Filter out recently completed activities for variety
            fresh_activities = [act for act in incomplete_activities if act["activity_id"] not in recent_activity_ids]
            
            # If no fresh activities are available, use all incomplete activities
            if not fresh_activities:
                fresh_activities = incomplete_activities
            
            # Select one random activity for today
            daily_activity = random.choice(fresh_activities)
        
        # Store today's assigned activity in a separate collection for reference
        try:
            today_assignment = {
                "teacher_email": teacher_email,
                "class": class_level,
                "subject": subject,
                "activity_id": daily_activity["activity_id"],
                "activity_type": daily_activity["activity_type"],
                "activity_title": daily_activity["activity_title"],
                "module_title": daily_activity["module_title"],
                "assigned_date": today,
                "date_str": today_str,
                "status": "assigned",
                "completed": False,
                "created_at": datetime.now()
            }
            assign_result = activities_collection.update_one(
                {
                    "teacher_email": teacher_email,
                    "class": class_level, 
                    "subject": subject,
                    "date_str": today_str,
                    "status": "assigned"
                },
                {"$setOnInsert": today_assignment},
                upsert=True
            )
            logger.info(f"Activity assignment result: matched={assign_result.matched_count}, modified={assign_result.modified_count}, upserted={assign_result.upserted_id is not None}")
        except Exception as e:
            logger.warning(f"Failed to store today's activity assignment: {e}")
        
        return {"completed": False, "activity": daily_activity, "message": "Today's activity ready"}
    
    except Exception as e:
        logger.error(f"Error getting daily activity: {e}")
        return {"completed": False, "activity": None, "message": f"Error: {str(e)}"}

@app.route("/complete_activity", methods=["POST"])
def complete_activity():
    if "email" not in session:
        return jsonify({"status": "fail", "message": "Please login first"})
    
    try:
        activity_id = int(request.form.get("activity_id"))
        class_level = request.form.get("class_level") or session.get("class", "class9")
        subject = session.get("subject", "science")
        
        # First mark the activity as completed
        success = mark_activity_completed(session["email"], class_level, subject, activity_id)
        
        if success:
            # Also mark attendance for today
            today = datetime.now()
            today_str = today.strftime("%Y-%m-%d")
            
            # Get teacher details
            teacher = users_collection.find_one({"email": session["email"]})
            
            # Mark daily attendance
            daily_attendance = {
                "teacher_id": teacher.get("teacher_id", ""),
                "teacher_email": session["email"],
                "teacher_name": teacher.get("name", "Unknown"),
                "school": teacher.get("school", "Unknown"),
                "subject": teacher.get("subject", ""),
                "class": class_level,
                "date": today,
                "date_str": today_str,
                "time_in": today.strftime("%H:%M:%S"),
                "status": "present",
                "attendance_method": "activity_completion",
                "created_at": today
            }
            
            # Update attendance record
            daily_attendance_collection.update_one(
                {
                    "teacher_email": session["email"],
                    "date_str": today_str
                },
                {"$setOnInsert": daily_attendance},
                upsert=True
            )
            
            # Record in activities collection too
            activity_record = {
                "teacher_id": teacher.get("teacher_id", ""),
                "teacher_email": session["email"],
                "teacher_name": teacher.get("name", "Unknown"),
                "school": teacher.get("school", "Unknown"),
                "subject": subject,
                "class": class_level,
                "activity_id": activity_id,
                "activity_type": request.form.get("activity_type"),
                "activity_title": request.form.get("activity_title"),
                "completion_date": today,
                "date_str": today_str,
                "completion_time": today.strftime("%H:%M:%S"),
                "status": "completed",
                "created_at": today
            }
            
            activities_collection.insert_one(activity_record)
            
            # Get updated progress
            progress = course_progress_collection.find_one({
                "teacher_email": session["email"],
                "class": class_level,
                "subject": subject
            })
            
            return jsonify({
                "status": "success",
                "message": "Activity completed and attendance marked successfully",
                "progress_percentage": progress["progress_percentage"],
                "completed_activities": progress["completed_activities"],
                "total_activities": progress["total_activities"]
            })
        else:
            return jsonify({"status": "fail", "message": "Failed to complete activity"})
        
    except Exception as e:
        logger.error(f"Error completing activity: {e}")
        return jsonify({"status": "fail", "message": f"Error: {str(e)}"})

# Generate a weekly schedule with random activities for each day
def generate_weekly_schedule(teacher_email, class_level, subject):
    try:
        # Get teacher's progress
        progress = course_progress_collection.find_one({
            "teacher_email": teacher_email,
            "class": class_level,
            "subject": subject
        })
        
        if not progress:
            # Need to initialize progress first
            progress = get_or_initialize_progress(teacher_email, class_level, subject)
            if not progress or not progress.get("modules_progress"):
                logger.error(f"No progress found for {teacher_email} in {class_level} {subject}")
                return []
        
        # Get all incomplete activities grouped by type
        activities_by_type = {
            "quiz": [],
            "video": [],
            "interactive": [],
            "pdf": [],
            "discussion": []
        }
        
        for module in progress.get("modules_progress", []):
            for activity in module.get("activities", []):
                if not activity.get("completed", True):
                    activity_type = activity.get("type", "quiz")
                    if activity_type in activities_by_type:
                        activities_by_type[activity_type].append({
                            "module_id": module.get("module_id", 0),
                            "module_title": module.get("title", "Unknown Module"),
                            "activity_id": activity.get("activity_id", 0),
                            "activity_title": activity.get("title", "Unknown Activity"),
                            "activity_type": activity_type
                        })
        
        # Check if we have activities available
        all_incomplete_activities = []
        for activities in activities_by_type.values():
            all_incomplete_activities.extend(activities)
            
        if not all_incomplete_activities:
            logger.info(f"No incomplete activities found for {teacher_email} in {class_level} {subject}")
            return []
        
        # Get current week start and end dates
        import random
        from datetime import datetime, timedelta
        
        today = datetime.now().date()
        start_of_week = today - timedelta(days=today.weekday())  # Monday
        end_of_week = start_of_week + timedelta(days=6)  # Sunday
        
        # Get all assigned activities for the current week to maintain consistency
        this_week_activities = list(activities_collection.find({
            "teacher_email": teacher_email,
            "class": class_level,
            "subject": subject,
            "$or": [
                {"status": "assigned"},
                {"status": "completed"}
            ],
            "date_str": {
                "$gte": start_of_week.strftime("%Y-%m-%d"),
                "$lte": end_of_week.strftime("%Y-%m-%d")
            }
        }).sort("date_str", 1))  # Sort by date
        
        # Create a map of date -> activity_id for already assigned/completed activities
        existing_activities_map = {}
        for act in this_week_activities:
            existing_activities_map[act.get("date_str")] = {
                "activity_id": act.get("activity_id"),
                "activity_title": act.get("activity_title"),
                "activity_type": act.get("activity_type"),
                "module_title": act.get("module_title", "Unknown Module"),
                "completed": act.get("status") == "completed"
            }
        
        # Use the week number and teacher email as the seed for consistent random generation
        week_number = start_of_week.isocalendar()[1]  # Week number of the year
        year = start_of_week.year
        seed = f"{year}_{week_number}_{teacher_email}"
        random.seed(seed)
        
        # Create a schedule for Monday to Friday
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        weekly_schedule = []
        
        # Track assigned activity IDs and types to prevent duplicates
        assigned_activity_ids = [act.get("activity_id") for act in this_week_activities if act.get("activity_id")]
        assigned_activity_types = []
        
        # Get existing activity types for this week to maintain consistency
        for day_str, activity in existing_activities_map.items():
            if activity.get("activity_type") and activity.get("activity_type") not in assigned_activity_types:
                assigned_activity_types.append(activity.get("activity_type"))
        
        # Define a priority list of activity types to ensure variety
        activity_types_priority = ["quiz", "video", "interactive", "pdf", "discussion"]
        
        # Shuffle the priority list using the seed for consistency
        activity_types_copy = activity_types_priority.copy()
        random.shuffle(activity_types_copy)
        
        # Randomly select activities for each day, ensuring different types
        try:
            # For days that already have activities assigned, use those
            # For days that don't have activities assigned, select new ones
            for i, day in enumerate(weekdays):
                day_date = start_of_week + timedelta(days=i)
                day_str = day_date.strftime("%Y-%m-%d")
                is_past = day_date < today
                is_today = day_date == today
                
                # Check if this day already has an activity assigned
                if day_str in existing_activities_map:
                    activity = existing_activities_map[day_str]
                    completed = activity.get("completed", False)
                    
                    # If this was already assigned or completed, use that activity
                    weekly_schedule.append({
                        "day": day,
                        "date": day_date,
                        "date_str": day_str,
                        "activity": {
                            "activity_id": activity.get("activity_id"),
                            "activity_title": activity.get("activity_title"),
                            "activity_type": activity.get("activity_type"),
                            "module_title": activity.get("module_title")
                        },
                        "is_past": is_past,
                        "is_today": is_today,
                        "completed": completed
                    })
                    
                    # Make sure we don't reuse this activity for other days
                    if activity.get("activity_id") not in assigned_activity_ids:
                        assigned_activity_ids.append(activity.get("activity_id"))
                else:
                    # Need to assign a new activity for this day
                    # Try to find an activity type that hasn't been used yet this week
                    available_types = [t for t in activity_types_copy if t not in assigned_activity_types]
                    
                    if not available_types:
                        # If all types have been used, allow repeating but prioritize types with the most activities
                        available_types = sorted(
                            activities_by_type.keys(), 
                            key=lambda t: len(activities_by_type[t]), 
                            reverse=True
                        )
                    
                    # Take the first available type with activities
                    selected_type = None
                    for activity_type in available_types:
                        if activities_by_type[activity_type]:
                            selected_type = activity_type
                            break
                    
                    # If no activities of the preferred types, pick any type with activities
                    if not selected_type:
                        for activity_type, activities in activities_by_type.items():
                            if activities:
                                selected_type = activity_type
                                break
                    
                    # If still no activities found, use any incomplete activity
                    if not selected_type or not activities_by_type[selected_type]:
                        # Choose random activity from all incomplete
                        random_activity = random.choice(all_incomplete_activities)
                        selected_type = random_activity["activity_type"]
                    
                    # Get available activities of this type that haven't been assigned yet
                    available_activities = [
                        a for a in activities_by_type[selected_type] 
                        if a["activity_id"] not in assigned_activity_ids
                    ]
                    
                    # If no available activities of this type, use any activities of this type
                    if not available_activities:
                        available_activities = activities_by_type[selected_type]
                    
                    # Select a random activity for this day
                    activity = random.choice(available_activities)
                    
                    # Add to assigned tracking
                    assigned_activity_ids.append(activity["activity_id"])
                    assigned_activity_types.append(selected_type)
                    
                    # For future days, check if there's any record of completion
                    completed = False
                    if is_past or is_today:
                        completed_activity = activities_collection.find_one({
                            "teacher_email": teacher_email,
                            "date_str": day_str,
                            "status": "completed"
                        })
                        completed = bool(completed_activity)
                    
                    # Store this assignment in the activities collection for future reference
                    if not is_past:  # Don't create assignments for past dates
                        try:
                            day_assignment = {
                                "teacher_email": teacher_email,
                                "class": class_level,
                                "subject": subject,
                                "activity_id": activity["activity_id"],
                                "activity_type": activity["activity_type"],
                                "activity_title": activity["activity_title"],
                                "module_title": activity["module_title"],
                                "assigned_date": day_date,
                                "date_str": day_str,
                                "status": "assigned",
                                "completed": completed,
                                "created_at": datetime.now()
                            }
                            activities_collection.update_one(
                                {
                                    "teacher_email": teacher_email,
                                    "date_str": day_str,
                                    "status": "assigned"
                                },
                                {"$setOnInsert": day_assignment},
                                upsert=True
                            )
                        except Exception as e:
                            logger.warning(f"Failed to store activity assignment for {day_str}: {e}")
                    
                    weekly_schedule.append({
                        "day": day,
                        "date": day_date,
                        "date_str": day_str,
                        "activity": activity,
                        "is_past": is_past,
                        "is_today": is_today,
                        "completed": completed
                    })
            
        except Exception as e:
            logger.error(f"Error generating weekly days: {e}")
            return []
        
        return weekly_schedule
    
    except Exception as e:
        logger.error(f"Error generating weekly schedule: {e}")
        return []

# Calculate attendance percentage for a teacher for the current month
def calculate_teacher_attendance(teacher_email):
    try:
        # Get current month and year
        current_date = datetime.now()
        current_month = current_date.month
        current_year = current_date.year
        
        # Get the first and last day of the current month
        last_day = calendar.monthrange(current_year, current_month)[1]
        first_day_of_month = datetime(current_year, current_month, 1)
        last_day_of_month = datetime(current_year, current_month, last_day)
        
        # First, check if we have monthly stats already calculated
        monthly_stats = teacher_monthly_stats.find_one({
            "teacher_email": teacher_email,
            "year": current_year,
            "month": current_month
        })
        
        if monthly_stats and "days_present" in monthly_stats:
            # Get total working days so far this month (exclude weekends)
            today = current_date.day
            working_days = 0
            for day in range(1, today + 1):
                day_date = datetime(current_year, current_month, day)
                # Skip weekends (5 is Saturday, 6 is Sunday)
                if day_date.weekday() not in [5, 6]:
                    working_days += 1
            
            # Calculate attendance percentage
            days_present = monthly_stats.get("days_present", 0)
            if working_days > 0:
                attendance_percentage = min(round((days_present / working_days) * 100), 100)
            else:
                attendance_percentage = 0
                
            return {
                "percentage": attendance_percentage,
                "days_present": days_present,
                "working_days": working_days,
                "month": current_date.strftime("%B")
            }
        
        # If no monthly stats, calculate from daily attendance records
        attendance_records = list(daily_attendance_collection.find({
            "teacher_email": teacher_email,
            "date": {
                "$gte": first_day_of_month,
                "$lte": last_day_of_month
            },
            "status": "present"
        }))
        
        # Count distinct days with attendance
        days_present = len(set(record.get("date_str") for record in attendance_records))
        
        # Get total working days so far this month (exclude weekends)
        today = current_date.day
        working_days = 0
        for day in range(1, today + 1):
            day_date = datetime(current_year, current_month, day)
            # Skip weekends (5 is Saturday, 6 is Sunday)
            if day_date.weekday() not in [5, 6]:
                working_days += 1
        
        # Calculate attendance percentage
        if working_days > 0:
            attendance_percentage = min(round((days_present / working_days) * 100), 100)
        else:
            attendance_percentage = 0
        
        return {
            "percentage": attendance_percentage,
            "days_present": days_present,
            "working_days": working_days,
            "month": current_date.strftime("%B")
        }
    
    except Exception as e:
        logger.error(f"Error calculating attendance: {e}")
        return {
            "percentage": 0,
            "days_present": 0,
            "working_days": 0,
            "month": current_date.strftime("%B")
        }

# Get teacher stats for principal dashboard
def get_teacher_stats():
    try:
        # Get current date info
        current_date = datetime.now()
        today_str = current_date.strftime("%Y-%m-%d")
        
        # Count total teachers
        total_count = users_collection.count_documents({"role": "teacher"})
        
        # Count teachers present today
        present_today = daily_attendance_collection.count_documents({
            "date_str": today_str,
            "status": "present"
        })
        
        # Calculate average attendance percentage across all teachers
        # First, get all teachers
        teachers = list(users_collection.find({"role": "teacher"}))
        
        if teachers:
            # Calculate attendance for each teacher
            attendance_sum = 0
            for teacher in teachers:
                attendance_data = calculate_teacher_attendance(teacher["email"])
                attendance_sum += attendance_data["percentage"]
            
            avg_attendance = round(attendance_sum / len(teachers))
        else:
            avg_attendance = 0
        
        # Count total activities completed this month
        month_start = datetime(current_date.year, current_date.month, 1)
        total_activities = activities_collection.count_documents({
            "status": "completed",
            "completion_date": {"$gte": month_start}
        })
        
        return {
            "total_count": total_count,
            "present_today": present_today,
            "avg_attendance": avg_attendance,
            "total_activities": total_activities
        }
    
    except Exception as e:
        logger.error(f"Error getting teacher stats: {e}")
        return {
            "total_count": 0,
            "present_today": 0,
            "avg_attendance": 0,
            "total_activities": 0
        }

# Get chart data for principal dashboard
def get_chart_data():
    try:
        # Get the last 7 days for weekly attendance chart
        current_date = datetime.now().date()
        dates = []
        attendance_counts = []
        
        for i in range(6, -1, -1):
            date = current_date - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            dates.append(date.strftime("%a"))
            
            # Count attendance for this day
            count = daily_attendance_collection.count_documents({
                "date_str": date_str,
                "status": "present"
            })
            attendance_counts.append(count)
        
        # Get activity type distribution
        activity_counts = {
            "quiz": activities_collection.count_documents({"activity_type": "quiz", "status": "completed"}),
            "video": activities_collection.count_documents({"activity_type": "video", "status": "completed"}),
            "interactive": activities_collection.count_documents({"activity_type": "interactive", "status": "completed"}),
            "pdf": activities_collection.count_documents({"activity_type": "pdf", "status": "completed"}),
            "discussion": activities_collection.count_documents({"activity_type": "discussion", "status": "completed"})
        }
        
        activity_types = [
            activity_counts["quiz"],
            activity_counts["video"],
            activity_counts["interactive"],
            activity_counts["pdf"],
            activity_counts["discussion"]
        ]
        
        return {
            "weekly_dates": dates,
            "attendance_counts": attendance_counts,
            "activity_types": activity_types
        }
    
    except Exception as e:
        logger.error(f"Error getting chart data: {e}")
        return {
            "weekly_dates": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            "attendance_counts": [0, 0, 0, 0, 0, 0, 0],
            "activity_types": [0, 0, 0, 0, 0]
        }

# Get teacher list with performance metrics for principal dashboard
def get_teacher_performance():
    try:
        teachers = list(users_collection.find({"role": "teacher"}))
        teacher_performance = []
        
        for teacher in teachers:
            # Get attendance percentage
            attendance_data = calculate_teacher_attendance(teacher["email"])
            
            # Get progress percentage (use most recent class-subject combination if multiple)
            progress = course_progress_collection.find_one(
                {"teacher_email": teacher["email"]},
                sort=[("updated_at", -1)]
            )
            
            # Get last active timestamp
            last_activity = activities_collection.find_one(
                {"teacher_email": teacher["email"]},
                sort=[("created_at", -1)]
            )
            
            teacher_info = {
                "name": teacher["name"],
                "email": teacher["email"],
                "subject": teacher.get("subject", ""),
                "class": teacher.get("class", ""),
                "attendance_percentage": attendance_data["percentage"],
                "progress_percentage": progress["progress_percentage"] if progress else 0,
                "last_active": last_activity["created_at"] if last_activity else None
            }
            
            teacher_performance.append(teacher_info)
        
        return teacher_performance
    
    except Exception as e:
        logger.error(f"Error getting teacher performance: {e}")
        return []

@app.route("/principal_dashboard")
def principal_dashboard():
    if "email" not in session or session.get("role") != "principal":
        return redirect(url_for("login"))
    
    try:
        # Get teacher statistics
        teacher_stats = get_teacher_stats()
        
        # Get chart data
        chart_data = get_chart_data()
        
        # Get teacher performance metrics
        teachers = get_teacher_performance()
        
        return render_template(
            "principal_dashboard.html",
            teacher_stats=teacher_stats,
            chart_data=chart_data,
            teachers=teachers
        )
    
    except Exception as e:
        logger.error(f"Error loading principal dashboard: {e}")
        return render_template(
            "principal_dashboard.html",
            error_message="We encountered an error loading your dashboard. Please try again later.",
            teacher_stats={"total_count": 0, "present_today": 0, "avg_attendance": 0, "total_activities": 0},
            chart_data={"weekly_dates": [], "attendance_counts": [], "activity_types": []},
            teachers=[]
        )

@app.route("/logout")
def logout():
    # Clear all session data
    session.clear()
    return redirect(url_for("index"))

@app.route("/add_teacher", methods=["POST"])
def add_teacher():
    # Check if user is logged in and is a principal
    if "email" not in session or session.get("role") != "principal":
        logger.warning("Unauthorized attempt to add teacher")
        return jsonify({"status": "fail", "message": "Unauthorized access"})
    
    try:
        # Get form data
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        school = request.form.get("school")
        teacher_id = request.form.get("teacher_id")
        subject = request.form.get("subject")
        class_level = request.form.get("class")
        
        # Validate required fields
        if not all([name, email, password, school, teacher_id, subject, class_level]):
            return jsonify({"status": "fail", "message": "All fields are required"})
        
        # Check if email already exists
        if users_collection.find_one({"email": email}):
            return jsonify({"status": "fail", "message": "Email already registered"})
        
        # Check if teacher ID already exists
        if users_collection.find_one({"teacher_id": teacher_id}):
            return jsonify({"status": "fail", "message": "Teacher ID already registered"})
        
        # Hash the password
        hashed_password = generate_password_hash(password)
        
        # Create teacher document
        teacher_data = {
            "name": name,
            "email": email,
            "password": hashed_password,
            "school": school,
            "teacher_id": teacher_id,
            "subject": subject,
            "class": class_level,
            "role": "teacher",
            "created_at": datetime.now(),
            "created_by": session.get("email")
        }
        
        # Insert into database
        result = users_collection.insert_one(teacher_data)
        
        if result.inserted_id:
            logger.info(f"New teacher added: {email} by principal: {session.get('email')}")
            
            # Initialize progress for the new teacher
            get_or_initialize_progress(email, class_level, subject)
            
            return jsonify({
                "status": "success", 
                "message": f"Teacher {name} added successfully"
            })
        else:
            logger.error("Failed to insert new teacher")
            return jsonify({"status": "fail", "message": "Failed to add teacher"})
            
    except Exception as e:
        logger.error(f"Error adding teacher: {str(e)}")
        return jsonify({"status": "fail", "message": f"An error occurred: {str(e)}"})

if __name__ == '__main__':
    # Create test user for easy login
    create_test_users()
    
    # Initialize curriculum data for all classes and subjects
    initialize_curriculum()
    
    # Run the application
    logger.info("Starting Flask application...")
    app.run(debug=True)
