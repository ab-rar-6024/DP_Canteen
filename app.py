from flask import Flask, render_template, request, redirect, session, url_for
from db import get_db_connection
import random
import string
from datetime import date
from flask import send_file
import pandas as pd
import io


app = Flask(__name__)
app.secret_key = "supersecretkey"

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    # clear any previous session
    session.clear()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        db = get_db_connection()
        cur = db.cursor(dictionary=True)

        cur.execute("""
            SELECT username, role
            FROM users
            WHERE username=%s
              AND password=%s
              AND status=1
        """, (username, password))

        user = cur.fetchone()

        if user:
            session['user'] = user['username']
            session['role'] = user['role']

            # ROLE BASED REDIRECT
            if user['role'] == "canteen":
                return redirect("/canteen/home")
            else:  # department (default)
                return redirect("/department/dashboard")

        return render_template(
            "login.html",
            error="Invalid username or password"
        )

    return render_template("login.html")



# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ================== DEPARTMENT ==================
@app.route("/department/dashboard")
def dept_dashboard():
    if session.get("role") != "department":
        return redirect("/")
    return render_template("department/dashboard.html")

# ---------- NEW / DELETE USER ----------

@app.route("/department/users", methods=["GET", "POST"])
def department_users():
    if session.get("role") != "department":
        return redirect("/")

    db = get_db_connection()
    cur = db.cursor(dictionary=True)

    generated_pin = None
    message = None
    error = None

    if request.method == "POST":
        action = request.form.get("action")

        # ---------- ADD USER ----------
        if action == "add":
            import random
            generated_pin = str(random.randint(1000, 9999))

            try:
                cur.execute("""
                    INSERT INTO employees
                    (emp_code, emp_name, dob, doj, department, designation,
                     reporting_to, access_status, shift_name, company,
                     rfid_pin, active)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)
                """, (
                    request.form['emp_code'].strip(),
                    request.form['emp_name'],
                    request.form['dob'],
                    request.form['doj'],
                    request.form['department'],
                    request.form['designation'],
                    request.form['reporting_to'],
                    request.form['access'],
                    request.form['shift'],
                    request.form['company'],
                    generated_pin
                ))
                db.commit()
                message = "User created successfully"

            except Exception as e:
                db.rollback()
                error = "Employee Code already exists"

        # ---------- DELETE USER (HARD DELETE) ----------
        elif action == "delete":
            emp_code = request.form['emp_code'].strip()

            cur.execute(
                "SELECT emp_code FROM employees WHERE emp_code=%s",
                (emp_code,)
            )
            emp = cur.fetchone()

            if emp:
                cur.execute(
                    "DELETE FROM employees WHERE emp_code=%s",
                    (emp_code,)
                )
                db.commit()
                message = f"Employee {emp_code} deleted successfully"
            else:
                error = "Employee code not found"

    return render_template(
        "department/users.html",
        generated_pin=generated_pin,
        message=message,
        error=error
    )

# ---------- WASTAGE COUNT ----------

@app.route("/department/wastage", methods=["GET", "POST"])
def department_wastage():
    if session.get("role") != "department":
        return redirect("/")

    message = None
    db = get_db_connection()
    cur = db.cursor()

    if request.method == "POST":
        cur.execute("""
            INSERT INTO wastage
            (waste_date, breakfast, lunch, snacks, dinner, supper)
            VALUES (CURDATE(), %s, %s, %s, %s, %s)
        """, (
            request.form['breakfast'] or 0,
            request.form['lunch'] or 0,
            request.form['snacks'] or 0,
            request.form['dinner'] or 0,
            request.form['supper'] or 0
        ))
        db.commit()
        message = "Wastage saved successfully"

    return render_template("department/wastage.html", message=message)

# ---------- CANTEEN TIMING ----------

@app.route("/department/timing", methods=["GET", "POST"])
def department_timing():
    if session.get("role") != "department":
        return redirect("/")

    message = None
    db = get_db_connection()
    cur = db.cursor()

    if request.method == "POST":
        cur.execute("""
            INSERT INTO canteen_timing
            (emp_code, meal_type, start_time, end_time)
            VALUES (%s, %s, %s, %s)
        """, (
            request.form['emp_code'],
            request.form['meal'],
            request.form['start_time'],
            request.form['end_time']
        ))
        db.commit()
        message = "Canteen timing saved successfully"

    return render_template("department/timing.html", message=message)

# ---------- REPORTS ----------

@app.route("/department/reports", methods=["GET", "POST"])
def department_reports():
    if session.get("role") != "department":
        return redirect("/")

    db = get_db_connection()
    cur = db.cursor(dictionary=True)

    results = []

    if request.method == "POST":
        from_date = request.form['from_date']
        to_date = request.form['to_date']
        department = request.form['department']
        company = request.form['company']
        action = request.form['action']

        query = """
            SELECT o.emp_code, o.emp_name, o.item, o.meal_type,
                   e.department, e.company, o.order_time
            FROM orders o
            JOIN employees e ON o.emp_code = e.emp_code
            WHERE DATE(o.order_time) BETWEEN %s AND %s
        """
        params = [from_date, to_date]

        if department:
            query += " AND e.department = %s"
            params.append(department)

        if company:
            query += " AND e.company = %s"
            params.append(company)

        cur.execute(query, tuple(params))
        results = cur.fetchall()

        # ---------- EXPORT TO EXCEL ----------
        if action == "export":
            df = pd.DataFrame(results)
            output = io.BytesIO()
            df.to_excel(output, index=False)
            output.seek(0)

            return send_file(
                output,
                download_name="canteen_report.xlsx",
                as_attachment=True
            )

    return render_template("department/reports.html", results=results)

# ---------- FOOD BOOKING ----------

@app.route("/department/customs", methods=["GET", "POST"])
def department_custom():
    if session.get("role") != "department":
        return redirect("/")

    message = None
    otp = None

    if request.method == "POST":
        booking_type = request.form['type']
        otp = str(random.randint(1000, 9999))

        department = request.form['department']
        name = request.form['name']
        persons = request.form['persons']
        company = request.form['company']

        # INTERN DATES
        from_date = request.form.get('from_date')
        to_date = request.form.get('to_date')

        # PERSON TO MEET ONLY FOR GUEST
        person_to_meet = (
            request.form['person_to_meet']
            if booking_type == "Guest"
            else None
        )

        db = get_db_connection()
        cur = db.cursor()

        cur.execute("""
            INSERT INTO guest_bookings
            (booking_type, department, name, person_to_meet,
             no_of_persons, company, otp, from_date, to_date)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            booking_type,
            department,
            name,
            person_to_meet,
            persons,
            company,
            otp,
            from_date,
            to_date
        ))
        db.commit()

        message = f"Booking successful. OTP: {otp}"

    return render_template("department/customs.html", message=message)

# ---------- USER MASTER ----------

@app.route("/department/user-master", methods=["GET", "POST"])
def user_master():
    if session.get("role") != "department":
        return redirect("/")

    generated_password = None

    if request.method == "POST":
        username = request.form['username']
        role = request.form['role']

        # auto password
        generated_password = ''.join(
            random.choices(string.ascii_letters + string.digits, k=8)
        )

        db = get_db_connection()
        cur = db.cursor()

        cur.execute("""
            INSERT INTO users (username, password, role, status)
            VALUES (%s,%s,%s,1)
        """, (username, generated_password, role))

        db.commit()

    return render_template(
        "department/user_master.html",
        password=generated_password
    )

@app.route("/department/get-users/<department>")
def get_users_by_department(department):
    if session.get("role") != "department":
        return {"error": "Unauthorized"}, 403

    db = get_db_connection()
    cur = db.cursor(dictionary=True)

    cur.execute("""
        SELECT id, username, password
        FROM users
        WHERE department=%s
          AND status=1
        ORDER BY username
    """, (department,))

    users = cur.fetchall()
    return users


@app.route("/department/update-password", methods=["POST"])
def update_password():
    if session.get("role") != "department":
        return {"error": "Unauthorized"}, 403

    user_id = request.form.get("user_id")
    new_password = request.form.get("new_password")

    if not user_id or not new_password:
        return {"error": "Missing data"}, 400

    db = get_db_connection()
    cur = db.cursor()

    cur.execute("""
        UPDATE users
        SET password=%s
        WHERE id=%s
    """, (new_password, user_id))

    db.commit()
    return {"success": True}


# ---------- RESET PASSWORD ----------

@app.route("/department/reset-password")
def reset_password():
    if session.get("role") != "department":
        return redirect("/")

    return render_template("department/reset_password.html")



# ================== CANTEEN ==================
# ---------------- CANTEEN HOME (PIN PAGE) ----------------
@app.route("/canteen/home", methods=["GET", "POST"])
def canteen_home():
    if session.get("role") != "canteen":
        return redirect("/")

    db = get_db_connection()
    cur = db.cursor(dictionary=True)

    # -------- CURRENT MENU --------
    cur.execute("SELECT * FROM menu_items WHERE active=1")
    menu = cur.fetchall()

    # -------- WASTAGE (TODAY → FALLBACK YESTERDAY) --------
    cur.execute("""
        SELECT breakfast, lunch, snacks, dinner, supper
        FROM wastage
        WHERE waste_date = CURDATE()
        LIMIT 1
    """)
    wastage = cur.fetchone()

    if not wastage:
        cur.execute("""
            SELECT breakfast, lunch, snacks, dinner, supper
            FROM wastage
            WHERE waste_date = CURDATE() - INTERVAL 1 DAY
            LIMIT 1
        """)
        wastage = cur.fetchone()

    # If still no wastage data
    if not wastage:
        wastage = {
            "breakfast": 0,
            "lunch": 0,
            "snacks": 0,
            "dinner": 0,
            "supper": 0
        }

    wastage["total"] = (
        wastage["breakfast"] +
        wastage["lunch"] +
        wastage["snacks"] +
        wastage["dinner"] +
        wastage["supper"]
    )

    # -------- LAST 7 ORDERS --------
    cur.execute("""
        SELECT emp_name, item
        FROM orders
        ORDER BY order_time DESC
        LIMIT 7
    """)
    orders = cur.fetchall()

    # -------- PIN / OTP LOGIN --------
    if request.method == "POST":
        pin = request.form['pin']

        # ---- EMPLOYEE PIN CHECK ----
        cur.execute("""
            SELECT emp_code, emp_name, photo
            FROM employees
            WHERE rfid_pin=%s
              AND active=1
              AND access_status='Yes'
        """, (pin,))
        emp = cur.fetchone()

        if emp:
            session['emp_code'] = emp['emp_code']
            session['emp_name'] = emp['emp_name']
            session['emp_photo'] = emp['photo']
            return redirect("/canteen/order")

        # ---- GUEST / CUSTOM OTP CHECK ----
        cur.execute("""
            SELECT id, name
            FROM guest_bookings
            WHERE otp=%s
              AND used=0
        """, (pin,))
        guest = cur.fetchone()

        if guest:
            # mark OTP as used
            cur.execute(
                "UPDATE guest_bookings SET used=1 WHERE id=%s",
                (guest['id'],)
            )
            db.commit()

            session['emp_code'] = "GUEST"
            session['emp_name'] = guest['name']
            session['emp_photo'] = "default.jpg"
            return redirect("/canteen/order")

        # ---- INVALID PIN / OTP ----
        return render_template(
            "canteen/home.html",
            error="Invalid PIN",
            menu=menu,
            wastage=wastage,
            orders=orders
        )

    # -------- INITIAL PAGE LOAD --------
    return render_template(
        "canteen/home.html",
        menu=menu,
        wastage=wastage,
        orders=orders
    )


# ---------------- ORDER PAGE (AFTER PIN) ----------------
@app.route("/canteen/order", methods=["GET", "POST"])
def canteen_order():
    if "emp_code" not in session:
        return redirect("/canteen/home")

    db = get_db_connection()
    cur = db.cursor(dictionary=True)

    # ---- FETCH EMPLOYEE MEAL TIMINGS ----
    cur.execute("""
        SELECT meal_type, start_time, end_time
        FROM canteen_timing
        WHERE emp_code = %s
        ORDER BY FIELD(meal_type,
            'Breakfast','Lunch','Snacks','Dinner','Supper')
    """, (session['emp_code'],))
    timings_raw = cur.fetchall()

    # ---- CONVERT timedelta → HH:MM ----
    timings = []
    for t in timings_raw:
        def fmt(td):
            total_seconds = int(td.total_seconds())
            h = total_seconds // 3600
            m = (total_seconds % 3600) // 60
            return f"{h:02d}:{m:02d}"

        timings.append({
            "meal_type": t["meal_type"],
            "start_time": fmt(t["start_time"]),
            "end_time": fmt(t["end_time"])
        })

    # ---- SAVE ORDER ----
    if request.method == "POST":
        cur.execute("""
            INSERT INTO orders (emp_code, emp_name, item, meal_type)
            VALUES (%s,%s,%s,%s)
        """, (
            session['emp_code'],
            session['emp_name'],
            request.form['item'],
            request.form['meal']
        ))
        db.commit()

        # auto logout
        session.pop("emp_code", None)
        session.pop("emp_name", None)
        session.pop("emp_photo", None)

        return render_template("canteen/success.html")

    return render_template(
        "canteen/order.html",
        emp_name=session['emp_name'],
        emp_photo=session['emp_photo'],
        timings=timings
    )



@app.route("/api/last-orders")
def last_orders():
    db = get_db_connection()
    cur = db.cursor(dictionary=True)

    cur.execute("""
        SELECT emp_name, item
        FROM orders
        ORDER BY order_time DESC
        LIMIT 7
    """)
    orders = cur.fetchall()

    return {"orders": orders}


if __name__ == "__main__":
    app.run(debug=True)
