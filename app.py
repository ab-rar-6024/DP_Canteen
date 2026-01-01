from flask import Flask, render_template, request, redirect, session, url_for, send_file
from db import get_db_connection
import random
import string
import pandas as pd
import io
import psycopg2.extras

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    session.clear()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        db = get_db_connection()
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT username, role
            FROM users
            WHERE username=%s
              AND password=%s
              AND status = TRUE
        """, (username, password))

        user = cur.fetchone()

        if user:
            session["user"] = user["username"]
            session["role"] = user["role"]

            if user["role"] == "canteen":
                return redirect("/canteen/home")
            return redirect("/department/dashboard")

        return render_template("login.html", error="Invalid username or password")

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


# ---------- USERS ----------
@app.route("/department/users", methods=["GET", "POST"])
def department_users():
    if session.get("role") != "department":
        return redirect("/")

    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    generated_pin = message = error = None

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add":
            generated_pin = str(random.randint(1000, 9999))
            try:
                cur.execute("""
                    INSERT INTO employees
                    (emp_code, emp_name, dob, doj, department, designation,
                     reporting_to, access_status, shift_name, company,
                     rfid_pin, active)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
                """, (
                    request.form["emp_code"].strip(),
                    request.form["emp_name"],
                    request.form["dob"],
                    request.form["doj"],
                    request.form["department"],
                    request.form["designation"],
                    request.form["reporting_to"],
                    request.form["access"],
                    request.form["shift"],
                    request.form["company"],
                    generated_pin
                ))
                db.commit()
                message = "User created successfully"
            except Exception:
                db.rollback()
                error = "Employee Code already exists"

        elif action == "delete":
            emp_code = request.form["emp_code"].strip()
            cur.execute("DELETE FROM employees WHERE emp_code=%s", (emp_code,))
            db.commit()
            message = f"Employee {emp_code} deleted"

    return render_template("department/users.html",
                           generated_pin=generated_pin,
                           message=message,
                           error=error)


# ---------- WASTAGE ----------
@app.route("/department/wastage", methods=["GET", "POST"])
def department_wastage():
    if session.get("role") != "department":
        return redirect("/")

    db = get_db_connection()
    cur = db.cursor()
    message = None

    if request.method == "POST":
        cur.execute("""
            INSERT INTO wastage
            (waste_date, breakfast, lunch, snacks, dinner, supper)
            VALUES (CURRENT_DATE, %s,%s,%s,%s,%s)
        """, (
            request.form["breakfast"] or 0,
            request.form["lunch"] or 0,
            request.form["snacks"] or 0,
            request.form["dinner"] or 0,
            request.form["supper"] or 0
        ))
        db.commit()
        message = "Wastage saved"

    return render_template("department/wastage.html", message=message)


# ---------- REPORTS ----------
@app.route("/department/reports", methods=["GET", "POST"])
def department_reports():
    if session.get("role") != "department":
        return redirect("/")

    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    results = []

    if request.method == "POST":
        from_date = request.form["from_date"]
        to_date = request.form["to_date"]
        department = request.form["department"]
        company = request.form["company"]
        action = request.form["action"]

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

        if action == "export":
            df = pd.DataFrame(results)
            output = io.BytesIO()
            df.to_excel(output, index=False)
            output.seek(0)
            return send_file(output,
                             download_name="canteen_report.xlsx",
                             as_attachment=True)

    return render_template("department/reports.html", results=results)


# ---------- FOOD BOOKING ----------
@app.route("/department/customs", methods=["GET", "POST"])
def department_custom():
    if session.get("role") != "department":
        return redirect("/")

    message = otp = None

    if request.method == "POST":
        booking_type = request.form["type"]
        otp = str(random.randint(1000, 9999))

        db = get_db_connection()
        cur = db.cursor()

        cur.execute("""
            INSERT INTO guest_bookings
            (booking_type, department, name, person_to_meet,
             no_of_persons, company, otp, from_date, to_date)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            booking_type,
            request.form["department"],
            request.form["name"],
            request.form.get("person_to_meet"),
            request.form["persons"],
            request.form["company"],
            otp,
            request.form.get("from_date"),
            request.form.get("to_date")
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
        generated_password = ''.join(
            random.choices(string.ascii_letters + string.digits, k=8)
        )

        db = get_db_connection()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO users (username, password, role, status)
            VALUES (%s,%s,%s,TRUE)
        """, (
            request.form["username"],
            generated_password,
            request.form["role"]
        ))
        db.commit()

    return render_template("department/user_master.html",
                           password=generated_password)


@app.route("/department/get-users")
def get_users():
    if session.get("role") != "department":
        return {"error": "Unauthorized"}, 403

    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, username, password FROM users WHERE status = TRUE")
    return cur.fetchall()


@app.route("/department/update-password", methods=["POST"])
def update_password():
    if session.get("role") != "department":
        return {"error": "Unauthorized"}, 403

    db = get_db_connection()
    cur = db.cursor()
    cur.execute("UPDATE users SET password=%s WHERE id=%s",
                (request.form["new_password"], request.form["user_id"]))
    db.commit()
    return {"success": True}


# ---------- RESET PASSWORD ----------
@app.route("/department/reset-password")
def reset_password():
    if session.get("role") != "department":
        return redirect("/")
    return render_template("department/reset_password.html")


# ================== CANTEEN ==================
@app.route("/canteen/home", methods=["GET", "POST"])
def canteen_home():
    if session.get("role") != "canteen":
        return redirect("/")

    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM menu_items WHERE active = TRUE")
    menu = cur.fetchall()

    cur.execute("""
        SELECT breakfast, lunch, snacks, dinner, supper
        FROM wastage
        WHERE waste_date = CURRENT_DATE
        LIMIT 1
    """)
    wastage = cur.fetchone()

    if not wastage:
        cur.execute("""
            SELECT breakfast, lunch, snacks, dinner, supper
            FROM wastage
            WHERE waste_date = CURRENT_DATE - INTERVAL '1 day'
            LIMIT 1
        """)
        wastage = cur.fetchone()

    if not wastage:
        wastage = dict(breakfast=0, lunch=0, snacks=0, dinner=0, supper=0)

    wastage["total"] = sum(wastage.values())

    cur.execute("""
        SELECT emp_name, item
        FROM orders
        ORDER BY order_time DESC
        LIMIT 7
    """)
    orders = cur.fetchall()

    if request.method == "POST":
        pin = request.form['pin']

        cur.execute("""
            SELECT emp_code, emp_name, photo
            FROM employees
            WHERE rfid_pin=%s
              AND active = TRUE
              AND access_status='Yes'
        """, (pin,))
        emp = cur.fetchone()

        if emp:
            session.update(emp)
            return redirect("/canteen/order")

        cur.execute("""
            SELECT id, name
            FROM guest_bookings
            WHERE otp=%s
              AND used = FALSE
        """, (pin,))
        guest = cur.fetchone()

        if guest:
            cur.execute("UPDATE guest_bookings SET used=TRUE WHERE id=%s",
                        (guest['id'],))
            db.commit()

            session['emp_code'] = "GUEST"
            session['emp_name'] = guest['name']
            return redirect("/canteen/order")

        return render_template(
            "canteen/home.html",
            error="Invalid PIN",
            menu=menu,
            wastage=wastage,
            orders=orders
        )

    return render_template(
        "canteen/home.html",
        menu=menu,
        wastage=wastage,
        orders=orders
    )


# ---------------- ORDER PAGE ----------------
@app.route("/canteen/order", methods=["GET", "POST"])
def canteen_order():
    if "emp_code" not in session:
        return redirect("/canteen/home")

    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT meal_type, start_time, end_time
        FROM canteen_timing
        WHERE emp_code=%s
        ORDER BY
          CASE meal_type
            WHEN 'Breakfast' THEN 1
            WHEN 'Lunch' THEN 2
            WHEN 'Snacks' THEN 3
            WHEN 'Dinner' THEN 4
            ELSE 5
          END
    """, (session['emp_code'],))
    timings = cur.fetchall()

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
        session.clear()
        return render_template("canteen/success.html")

    return render_template(
        "canteen/order.html",
        emp_name=session['emp_name'],
        timings=timings
    )


@app.route("/api/last-orders")
def last_orders():
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

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
