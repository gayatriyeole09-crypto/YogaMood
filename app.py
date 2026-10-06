from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import smtplib
import os
import secrets
import time

from email.message import EmailMessage
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "yogamood_secret_key_2026"
DATABASE = "database.db"

EMAIL_ADDRESS = os.getenv("YOGAMOOD_EMAIL")
EMAIL_APP_PASSWORD = os.getenv("YOGAMOOD_APP_PASSWORD")
CODE_EXPIRY = 10 * 60


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_database():
    conn = sqlite3.connect(DATABASE)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mood_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mood TEXT NOT NULL,
            selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            yoga_name TEXT NOT NULL,
            saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, yoga_name),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS yoga_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            yoga_name TEXT NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]

    if "verified" not in columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN verified INTEGER NOT NULL DEFAULT 1"
        )

    if "verification_code" not in columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN verification_code TEXT"
        )

    if "verification_expiry" not in columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN verification_expiry REAL"
        )

    if "reset_code" not in columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN reset_code TEXT"
        )

    if "reset_expiry" not in columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN reset_expiry REAL"
        )

    conn.commit()
    conn.close()


create_database()


def generate_code():
    return str(secrets.randbelow(900000) + 100000)


def send_email(receiver_email, subject, message_text):
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        print("Email settings are missing.")
        return False

    try:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = EMAIL_ADDRESS
        message["To"] = receiver_email
        message.set_content(message_text)

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            server.send_message(message)

        return True

    except Exception as e:
        print("Email error:", e)
        return False


@app.route("/")
def home():
    return render_template(
        "index.html",
        logged_in="user_id" in session,
        user_name=session.get("user_name")
    )


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            return render_template(
                "signup.html",
                error="Please fill all required fields."
            )

        if password != confirm_password:
            return render_template(
                "signup.html",
                error="Passwords do not match."
            )

        if len(password) < 6:
            return render_template(
                "signup.html",
                error="Password must contain at least 6 characters."
            )

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        )
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return render_template(
                "signup.html",
                error="This email is already registered. Please login."
            )

        hashed_password = generate_password_hash(password)
        verification_code = generate_code()
        verification_expiry = time.time() + CODE_EXPIRY

        cursor.execute("""
            INSERT INTO users
            (name, email, password, verified, verification_code, verification_expiry)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            name,
            email,
            hashed_password,
            0,
            verification_code,
            verification_expiry
        ))

        conn.commit()
        conn.close()

        email_sent = send_email(
            email,
            "YogaMood Email Verification Code",
            f"""Hello {name},

Welcome to YogaMood 🌿

Your 6-digit verification code is:

{verification_code}

This code is valid for 10 minutes.

Please do not share this code with anyone.

Regards,
YogaMood Team
"""
        )

        if not email_sent:
            return render_template(
                "signup.html",
                error="Account created, but verification email could not be sent. Check Gmail settings."
            )

        session["pending_email"] = email
        return redirect(url_for("verify_email"))

    return render_template("signup.html")


@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    email = session.get("pending_email")

    if not email:
        return redirect(url_for("signup"))

    if request.method == "POST":

        code = request.form.get("verification_code", "").strip()

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, verification_code, verification_expiry, verified
            FROM users
            WHERE email = ?
        """, (email,))

        user = cursor.fetchone()

        if not user:
            conn.close()
            return render_template(
                "verify-email.html",
                email=email,
                error="User account not found."
            )

        user_id, saved_code, expiry, verified = user

        if verified == 1:
            conn.close()
            session.pop("pending_email", None)
            return redirect(url_for("login"))

        if not saved_code or not expiry:
            conn.close()
            return render_template(
                "verify-email.html",
                email=email,
                error="Verification code not found."
            )

        if time.time() > expiry:
            conn.close()
            return render_template(
                "verify-email.html",
                email=email,
                error="Verification code has expired."
            )

        if code != saved_code:
            conn.close()
            return render_template(
                "verify-email.html",
                email=email,
                error="Invalid verification code."
            )

        cursor.execute("""
            UPDATE users
            SET verified = 1,
                verification_code = NULL,
                verification_expiry = NULL
            WHERE id = ?
        """, (user_id,))

        conn.commit()
        conn.close()

        session.pop("pending_email", None)
        return redirect(url_for("login"))

    return render_template("verify-email.html", email=email)


@app.route("/resend-code", methods=["POST"])
def resend_code():
    email = session.get("pending_email")

    if not email:
        return redirect(url_for("signup"))

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, verified FROM users WHERE email = ?",
        (email,)
    )

    user = cursor.fetchone()

    if not user:
        conn.close()
        return redirect(url_for("signup"))

    user_id, user_name, verified = user

    if verified == 1:
        conn.close()
        return redirect(url_for("login"))

    new_code = generate_code()
    new_expiry = time.time() + CODE_EXPIRY

    cursor.execute("""
        UPDATE users
        SET verification_code = ?, verification_expiry = ?
        WHERE id = ?
    """, (new_code, new_expiry, user_id))

    conn.commit()
    conn.close()

    email_sent = send_email(
        email,
        "YogaMood New Verification Code",
        f"""Hello {user_name},

Your new YogaMood verification code is:

{new_code}

This code is valid for 10 minutes.

Regards,
YogaMood Team
"""
    )

    if email_sent:
        return render_template(
            "verify-email.html",
            email=email,
            message="A new verification code has been sent."
        )

    return render_template(
        "verify-email.html",
        email=email,
        error="Could not send verification email."
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, email, password, verified
            FROM users
            WHERE email = ?
        """, (email,))

        user = cursor.fetchone()
        conn.close()

        if not user:
            return render_template(
                "login.html",
                error="Invalid email or password."
            )

        if not check_password_hash(user[3], password):
            return render_template(
                "login.html",
                error="Invalid email or password."
            )

        if user[4] == 0:
            session["pending_email"] = email
            return redirect(url_for("verify_email"))

        session["user_id"] = user[0]
        session["user_name"] = user[1]
        session["user_email"] = user[2]

        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, name FROM users WHERE email = ?",
            (email,)
        )

        user = cursor.fetchone()

        if not user:
            conn.close()
            return render_template(
                "forgot-password.html",
                error="No account found with this email."
            )

        user_id, user_name = user
        reset_code = generate_code()
        reset_expiry = time.time() + CODE_EXPIRY

        cursor.execute("""
            UPDATE users
            SET reset_code = ?, reset_expiry = ?
            WHERE id = ?
        """, (reset_code, reset_expiry, user_id))

        conn.commit()
        conn.close()

        email_sent = send_email(
            email,
            "YogaMood Password Reset Code",
            f"""Hello {user_name},

Your YogaMood password reset code is:

{reset_code}

This code is valid for 10 minutes.

If you did not request a password reset,
you can ignore this email.

Regards,
YogaMood Team
"""
        )

        if not email_sent:
            return render_template(
                "forgot-password.html",
                error="Reset email could not be sent. Check Gmail settings."
            )

        session["reset_email"] = email
        return redirect(url_for("reset_password"))

    return render_template("forgot-password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    email = session.get("reset_email")

    if not email:
        return redirect(url_for("forgot_password"))

    if request.method == "POST":

        reset_code = request.form.get("reset_code", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if new_password != confirm_password:
            return render_template(
                "reset-password.html",
                email=email,
                error="Passwords do not match."
            )

        if len(new_password) < 6:
            return render_template(
                "reset-password.html",
                email=email,
                error="Password must contain at least 6 characters."
            )

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, reset_code, reset_expiry
            FROM users
            WHERE email = ?
        """, (email,))

        user = cursor.fetchone()

        if not user:
            conn.close()
            session.pop("reset_email", None)
            return redirect(url_for("forgot_password"))

        user_id, saved_code, expiry = user

        if not saved_code or not expiry:
            conn.close()
            return render_template(
                "reset-password.html",
                email=email,
                error="Reset code not found."
            )

        if time.time() > expiry:
            conn.close()
            return render_template(
                "reset-password.html",
                email=email,
                error="Reset code has expired."
            )

        if reset_code != saved_code:
            conn.close()
            return render_template(
                "reset-password.html",
                email=email,
                error="Invalid reset code."
            )

        hashed_password = generate_password_hash(new_password)

        cursor.execute("""
            UPDATE users
            SET password = ?, reset_code = NULL, reset_expiry = NULL
            WHERE id = ?
        """, (hashed_password, user_id))

        conn.commit()
        conn.close()

        session.pop("reset_email", None)

        return redirect(url_for("login"))

    return render_template("reset-password.html", email=email)


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db_connection()

    # =====================================================
    # MOOD HISTORY
    # =====================================================

    moods = conn.execute("""
        SELECT mood, selected_at
        FROM mood_history
        WHERE user_id = ?
        ORDER BY selected_at DESC
    """, (user_id,)).fetchall()


    # =====================================================
    # FEEDBACK
    # =====================================================

    feedbacks = conn.execute("""
        SELECT rating, comment, submitted_at
        FROM feedback
        WHERE user_id = ?
        ORDER BY submitted_at DESC
    """, (user_id,)).fetchall()


    rating_result = conn.execute("""
        SELECT AVG(rating)
        FROM feedback
        WHERE user_id = ?
    """, (user_id,)).fetchone()


    average_rating = (
        round(rating_result[0], 1)
        if rating_result[0] is not None
        else 0
    )


    feedback_count = conn.execute("""
        SELECT COUNT(*)
        FROM feedback
        WHERE user_id = ?
    """, (user_id,)).fetchone()[0]


    # =====================================================
    # FAVORITES
    # =====================================================

    favorites = conn.execute("""
        SELECT id, yoga_name, saved_at
        FROM favorites
        WHERE user_id = ?
        ORDER BY saved_at DESC
    """, (user_id,)).fetchall()


    # =====================================================
    # YOGA PROGRESS
    # =====================================================

    progress = conn.execute("""
        SELECT id, yoga_name, completed_at
        FROM yoga_progress
        WHERE user_id = ?
        ORDER BY completed_at DESC
    """, (user_id,)).fetchall()


    progress_count = conn.execute("""
        SELECT COUNT(*)
        FROM yoga_progress
        WHERE user_id = ?
    """, (user_id,)).fetchone()[0]


    # =====================================================
    # YOGA STREAK
    # =====================================================

    completed_dates = conn.execute("""
        SELECT DISTINCT DATE(completed_at) AS completed_date
        FROM yoga_progress
        WHERE user_id = ?
        ORDER BY completed_date DESC
    """, (user_id,)).fetchall()


    # Convert database dates into Python date objects
    from datetime import datetime, date, timedelta

    date_list = []

    for row in completed_dates:

        try:
            completed_date = datetime.strptime(
                row["completed_date"],
                "%Y-%m-%d"
            ).date()

            date_list.append(completed_date)

        except (ValueError, TypeError):
            pass


    # =====================================================
    # CALCULATE CURRENT STREAK
    # =====================================================

    current_streak = 0

    if date_list:

        today = date.today()

        # Streak is active only if user completed yoga
        # today or yesterday.
        if date_list[0] == today:

            current_day = today

        elif date_list[0] == today - timedelta(days=1):

            current_day = today - timedelta(days=1)

        else:

            current_day = None


        if current_day:

            for completed_date in date_list:

                if completed_date == current_day:

                    current_streak += 1

                    current_day = current_day - timedelta(days=1)

                elif completed_date < current_day:

                    break


    # =====================================================
    # ACHIEVEMENTS
    # =====================================================

    achievements = []


    # First Session
    if progress_count >= 1:

        achievements.append({
            "icon": "🌱",
            "title": "First Session",
            "description": "Completed your first yoga session",
            "unlocked": True
        })


    # 5 Sessions
    if progress_count >= 5:

        achievements.append({
            "icon": "🧘",
            "title": "5 Sessions",
            "description": "Completed 5 yoga sessions",
            "unlocked": True
        })


    # 7 Sessions
    if progress_count >= 7:

        achievements.append({
            "icon": "🔥",
            "title": "7 Sessions",
            "description": "Completed 7 yoga sessions",
            "unlocked": True
        })


    # 10 Sessions
    if progress_count >= 10:

        achievements.append({
            "icon": "💚",
            "title": "10 Sessions",
            "description": "Completed 10 yoga sessions",
            "unlocked": True
        })


    # 20 Sessions
    if progress_count >= 20:

        achievements.append({
            "icon": "🏆",
            "title": "20 Sessions",
            "description": "Completed 20 yoga sessions",
            "unlocked": True
        })


    # 30 Sessions
    if progress_count >= 30:

        achievements.append({
            "icon": "👑",
            "title": "30 Sessions",
            "description": "Completed 30 yoga sessions",
            "unlocked": True
        })


    # =====================================================
    # NEXT ACHIEVEMENT
    # =====================================================

    if progress_count < 1:

        next_achievement = {
            "title": "First Session",
            "remaining": 1 - progress_count,
            "icon": "🌱"
        }

    elif progress_count < 5:

        next_achievement = {
            "title": "5 Sessions",
            "remaining": 5 - progress_count,
            "icon": "🧘"
        }

    elif progress_count < 7:

        next_achievement = {
            "title": "7 Sessions",
            "remaining": 7 - progress_count,
            "icon": "🔥"
        }

    elif progress_count < 10:

        next_achievement = {
            "title": "10 Sessions",
            "remaining": 10 - progress_count,
            "icon": "💚"
        }

    elif progress_count < 20:

        next_achievement = {
            "title": "20 Sessions",
            "remaining": 20 - progress_count,
            "icon": "🏆"
        }

    elif progress_count < 30:

        next_achievement = {
            "title": "30 Sessions",
            "remaining": 30 - progress_count,
            "icon": "👑"
        }

    else:

        next_achievement = {
            "title": "All Achievements",
            "remaining": 0,
            "icon": "🏆"
        }


    # =====================================================
    # CURRENT MOOD
    # =====================================================

    current_mood = (
        moods[0]["mood"]
        if moods
        else "Not Selected"
    )


    conn.close()


    # =====================================================
    # SEND DATA TO DASHBOARD
    # =====================================================

    return render_template(

        "dashboard.html",

        name=session["user_name"],

        email=session["user_email"],

        moods=moods,

        current_mood=current_mood,

        feedbacks=feedbacks,

        average_rating=average_rating,

        feedback_count=feedback_count,

        favorites=favorites,

        progress=progress,

        progress_count=progress_count,

        # New features
        current_streak=current_streak,

        achievements=achievements,

        next_achievement=next_achievement
    )


@app.route("/mood")
def mood():
    return render_template("mood.html")


@app.route("/save-mood", methods=["POST"])
def save_mood():
    mood_value = request.form.get("mood", "").strip()

    if mood_value and "user_id" in session:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO mood_history(user_id, mood)
            VALUES (?, ?)
        """, (session["user_id"], mood_value))

        conn.commit()
        conn.close()

    return redirect(url_for("yoga", mood=mood_value))


@app.route("/yoga")
def yoga():
    selected_mood = request.args.get("mood", "Stressed")
    return render_template(
        "yoga.html",
        selected_mood=selected_mood
    )


@app.route("/yoga-details")
def yoga_details():
    yoga_name = request.args.get(
        "yoga",
        "Child's Pose"
    )

    is_favorite = False
    is_completed = False

    if "user_id" in session:

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id
            FROM favorites
            WHERE user_id = ?
            AND yoga_name = ?
        """, (session["user_id"], yoga_name))

        if cursor.fetchone():
            is_favorite = True

        cursor.execute("""
            SELECT id
            FROM yoga_progress
            WHERE user_id = ?
            AND yoga_name = ?
            LIMIT 1
        """, (session["user_id"], yoga_name))

        if cursor.fetchone():
            is_completed = True

        conn.close()

    return render_template(
        "yoga-details.html",
        yoga_name=yoga_name,
        is_favorite=is_favorite,
        is_completed=is_completed
    )


@app.route("/save-favorite", methods=["POST"])
def save_favorite():
    if "user_id" not in session:
        return redirect(url_for("login"))

    yoga_name = request.form.get(
        "yoga_name",
        ""
    ).strip()

    if yoga_name:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO favorites(user_id, yoga_name)
            VALUES (?, ?)
        """, (session["user_id"], yoga_name))

        conn.commit()
        conn.close()

    return redirect(
        url_for("yoga_details", yoga=yoga_name)
    )


@app.route("/remove-favorite", methods=["POST"])
def remove_favorite():
    if "user_id" not in session:
        return redirect(url_for("login"))

    yoga_name = request.form.get(
        "yoga_name",
        ""
    ).strip()

    if yoga_name:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM favorites
            WHERE user_id = ?
            AND yoga_name = ?
        """, (session["user_id"], yoga_name))

        conn.commit()
        conn.close()

    return redirect(
        url_for("yoga_details", yoga=yoga_name)
    )


@app.route("/complete-yoga", methods=["POST"])
def complete_yoga():
    if "user_id" not in session:
        return redirect(url_for("login"))

    yoga_name = request.form.get(
        "yoga_name",
        ""
    ).strip()

    if yoga_name:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO yoga_progress(user_id, yoga_name)
            VALUES (?, ?)
        """, (session["user_id"], yoga_name))

        conn.commit()
        conn.close()

    return redirect(
        url_for("yoga_details", yoga=yoga_name)
    )


@app.route("/daily-plan")
def daily_plan():
    if "user_id" not in session:
        return redirect(url_for("login"))

    mood_value = request.args.get(
        "mood",
        "Stressed"
    )

    daily_plans = {
        "Stressed": [
            "Child's Pose",
            "Cat-Cow Pose",
            "Legs Up The Wall"
        ],
        "Tired": [
            "Mountain Pose",
            "Cobra Pose",
            "Sun Salutation"
        ],
        "Anxious": [
            "Child's Pose",
            "Easy Pose",
            "Cat-Cow Pose"
        ],
        "Low Mood": [
            "Mountain Pose",
            "Tree Pose",
            "Warrior II"
        ],
        "Poor Sleep": [
            "Child's Pose",
            "Legs Up The Wall",
            "Easy Pose"
        ],
        "Low Flexibility": [
            "Cat-Cow Pose",
            "Butterfly Pose",
            "Seated Forward Fold"
        ],
        "Concentration": [
            "Tree Pose",
            "Easy Pose",
            "Mountain Pose"
        ],
        "Fitness": [
            "Warrior II",
            "Chair Pose",
            "Sun Salutation"
        ]
    }

    plan = daily_plans.get(
        mood_value,
        daily_plans["Stressed"]
    )

    return render_template(
        "daily-plan.html",
        mood=mood_value,
        plan=plan
    )


@app.route("/videos")
def videos():
    return render_template("videos.html")


@app.route("/breathing")
def breathing():
    return render_template("breathing.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        rating = request.form.get(
            "rating",
            ""
        ).strip()

        comment = request.form.get(
            "comment",
            ""
        ).strip()

        if not rating:
            return render_template(
                "feedback.html",
                error="Please select a rating."
            )

        try:
            rating_value = int(rating)
        except ValueError:
            return render_template(
                "feedback.html",
                error="Invalid rating."
            )

        if rating_value < 1 or rating_value > 5:
            return render_template(
                "feedback.html",
                error="Rating must be between 1 and 5."
            )

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO feedback(user_id, rating, comment)
            VALUES (?, ?, ?)
        """, (
            session["user_id"],
            rating_value,
            comment
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("feedback.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.errorhandler(404)
def page_not_found(error):
    return """
    <div style="font-family:Arial;text-align:center;padding:80px 20px;">
        <h1>404</h1>
        <h2>Page Not Found</h2>
        <p>The requested page could not be found.</p>
        <a href="/">Go to YogaMood Home</a>
    </div>
    """, 404


if __name__ == "__main__":
    app.run(debug=True)
