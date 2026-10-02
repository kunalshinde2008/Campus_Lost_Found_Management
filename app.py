import os
from datetime import date
from functools import wraps

import mysql.connector
from dotenv import load_dotenv
from flask import (Flask, abort, flash, redirect, render_template,
                   request, session, url_for)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-key")


# ---------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------
def get_db():
    """Open a connection to your existing MySQL database."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", 3306)),
    )


def query(sql, params=(), one=False):
    """Run a SELECT and return rows as dictionaries."""
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, params=()):
    """Run an INSERT/UPDATE/DELETE and return the new row id."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    new_id = cur.lastrowid
    cur.close()
    conn.close()
    return new_id


def get_or_create_user(name, email, phone):
    """Find a user by email, or add a new one to the Users table."""
    user = query("SELECT user_id FROM users WHERE email = %s", (email,), one=True)
    if user:
        return user["user_id"]
    return execute(
        "INSERT INTO users (name, email, phone, user_type) VALUES (%s, %s, %s, %s)",
        (name, email, phone, "Student"),
    )


@app.errorhandler(mysql.connector.Error)
def db_error(err):
    return (f"<h2>Database error</h2><p>{err}</p>"
            "<p><a href='/'>Back to home</a></p>"), 500


# ---------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search")
def search():
    fields = ("item_type", "colour", "brand", "model", "personalization")
    f = {k: request.args.get(k, "").strip() for k in fields}
    results = None

    if request.args.get("searched"):
        sql = """
            SELECT item_id, item_name, item_type, colour, brand, model,
                   personalization, location_lost_found, date_lost_found, status,
                   CalculateMatchScore(%s, %s, %s, colour, brand, model) AS match_score
            FROM items
            WHERE report_type = 'FOUND' AND COALESCE(status, '') <> 'Returned'
        """
        params = [f["colour"], f["brand"], f["model"]]
        if f["item_type"]:
            sql += " AND item_type LIKE %s"
            params.append("%" + f["item_type"] + "%")
        if f["personalization"]:
            sql += " AND personalization LIKE %s"
            params.append("%" + f["personalization"] + "%")
        sql += " ORDER BY match_score DESC, date_lost_found DESC"
        results = query(sql, params)

    return render_template("search.html", f=f, results=results)


@app.route("/report/<kind>", methods=["GET", "POST"])
def report(kind):
    if kind not in ("lost", "found"):
        abort(404)
    categories = query("SELECT category_id, category_name FROM categories ORDER BY category_name")

    if request.method == "POST":
        f = request.form
        user_id = get_or_create_user(f["name"].strip(), f["email"].strip(), f["phone"].strip())
        item_id = execute(
            """INSERT INTO items
               (item_name, item_type, report_type, colour, brand, model,
                personalization, location_lost_found, date_lost_found,
                status, category_id, reporter_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (f["item_name"].strip(), f["item_type"].strip(), kind.upper(),
             f["colour"].strip(), f["brand"].strip(), f["model"].strip(),
             f["personalization"].strip(), f["location"].strip(), f["date"],
             "Open", f["category_id"], user_id),
        )
        flash(f"Your {kind} item was reported successfully.", "success")
        return redirect(url_for("item_detail", item_id=item_id))

    return render_template("report.html", kind=kind, categories=categories,
                           today=date.today().isoformat())


@app.route("/item/<int:item_id>")
def item_detail(item_id):
    item = query(
        """SELECT i.*, c.category_name
           FROM items i LEFT JOIN categories c ON i.category_id = c.category_id
           WHERE i.item_id = %s""", (item_id,), one=True)
    if not item:
        abort(404)
    return render_template("item.html", item=item)


@app.route("/item/<int:item_id>/claim", methods=["POST"])
def claim_item(item_id):
    f = request.form
    user_id = get_or_create_user(f["name"].strip(), f["email"].strip(), f["phone"].strip())
    execute(
        """INSERT INTO claims (item_id, claimer_id, proof_description, claim_status, claim_date)
           VALUES (%s, %s, %s, %s, CURDATE())""",
        (item_id, user_id, f["proof"].strip(), "Pending"),
    )
    flash("Claim submitted. An admin will review it.", "success")
    return redirect(url_for("item_detail", item_id=item_id))


# ---------------------------------------------------------------
# Admin
# ---------------------------------------------------------------
def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapper


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if (request.form["username"] == os.getenv("ADMIN_USERNAME")
                and request.form["password"] == os.getenv("ADMIN_PASSWORD")):
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Wrong username or password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    lost = query("SELECT COUNT(*) AS n FROM items WHERE report_type = 'LOST'", one=True)["n"]
    found = query("SELECT COUNT(*) AS n FROM items WHERE report_type = 'FOUND'", one=True)["n"]
    pending = query("SELECT COUNT(*) AS n FROM claims WHERE claim_status = 'Pending'", one=True)["n"]
    items = query(
        """SELECT i.*, c.category_name, u.name AS reporter_name
           FROM items i
           LEFT JOIN categories c ON i.category_id = c.category_id
           LEFT JOIN users u ON i.reporter_id = u.user_id
           ORDER BY i.item_id DESC""")
    claims = query(
        """SELECT cl.*, i.item_name, u.name AS claimer_name, u.email AS claimer_email
           FROM claims cl
           JOIN items i ON cl.item_id = i.item_id
           JOIN users u ON cl.claimer_id = u.user_id
           ORDER BY cl.claim_id DESC""")
    return render_template("admin.html", lost=lost, found=found,
                           pending=pending, items=items, claims=claims)


@app.route("/admin/claim/<int:claim_id>/<action>", methods=["POST"])
@admin_required
def update_claim(claim_id, action):
    if action not in ("approve", "reject"):
        abort(404)
    claim = query("SELECT item_id FROM claims WHERE claim_id = %s", (claim_id,), one=True)
    if not claim:
        abort(404)
    if action == "approve":
        execute("UPDATE claims SET claim_status = 'Approved' WHERE claim_id = %s", (claim_id,))
        execute("UPDATE items SET status = 'Returned' WHERE item_id = %s", (claim["item_id"],))
        flash("Claim approved. Item marked as Returned.", "success")
    else:
        execute("UPDATE claims SET claim_status = 'Rejected' WHERE claim_id = %s", (claim_id,))
        flash("Claim rejected.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/item/<int:item_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_item(item_id):
    item = query("SELECT * FROM items WHERE item_id = %s", (item_id,), one=True)
    if not item:
        abort(404)
    if request.method == "POST":
        f = request.form
        execute(
            """UPDATE items SET item_name=%s, item_type=%s, colour=%s, brand=%s,
               model=%s, personalization=%s, location_lost_found=%s, status=%s
               WHERE item_id=%s""",
            (f["item_name"], f["item_type"], f["colour"], f["brand"], f["model"],
             f["personalization"], f["location"], f["status"], item_id),
        )
        flash("Item updated.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("edit_item.html", item=item)


@app.route("/admin/item/<int:item_id>/delete", methods=["POST"])
@admin_required
def delete_item(item_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM claims WHERE item_id = %s", (item_id,))
    cur.execute("DELETE FROM items WHERE item_id = %s", (item_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Item deleted.", "success")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    app.run(debug=True)