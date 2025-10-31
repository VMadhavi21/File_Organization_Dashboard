from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import os, shutil, sqlite3, subprocess
from datetime import datetime

app = Flask(__name__)
app.secret_key = "SmartOrganizerSecret"

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DB_PATH = "file_records.db"

# Render deployment flags
IS_RENDER = os.environ.get("RENDER") is not None
AUTO_PUSH = os.environ.get("AUTO_PUSH") == "1"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS organized_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT,
                    filetype TEXT,
                    new_path TEXT,
                    date TEXT
                )''')
    conn.commit()
    conn.close()


def git_auto_push():
    if not AUTO_PUSH:
        return
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Auto backup update"], check=False)
        subprocess.run(["git", "push"], check=False)
    except Exception as e:
        print("Git push skipped:", e)


def organize_files(target_path=None):
    try:
        base_folder = target_path if (target_path and os.path.exists(target_path)) else UPLOAD_FOLDER
        categories = {
            "images": [".jpg", ".jpeg", ".png", ".gif"],
            "documents": [".pdf", ".docx", ".txt", ".pptx", ".csv"],
            "videos": [".mp4", ".mkv", ".mov"],
            "audio": [".mp3", ".wav"],
            "archives": [".zip", ".rar"],
        }

        moved_count = 0
        summary = {k: 0 for k in list(categories.keys()) + ["others"]}
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        for filename in os.listdir(base_folder):
            filepath = os.path.join(base_folder, filename)
            if not os.path.isfile(filepath):
                continue

            ext = os.path.splitext(filename)[1].lower()
            category = next((k for k, exts in categories.items() if ext in exts), "others")

            category_path = os.path.join(base_folder, category)
            os.makedirs(category_path, exist_ok=True)
            new_path = os.path.join(category_path, filename)
            shutil.move(filepath, new_path)
            moved_count += 1
            summary[category] += 1

            c.execute("INSERT INTO organized_files (filename, filetype, new_path, date) VALUES (?, ?, ?, ?)",
                      (filename, category, new_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        conn.commit()
        conn.close()
        git_auto_push()

        return {"status": "ok", "message": f"✅ Organized {moved_count} files successfully!", "summary": summary}
    except Exception as e:
        return {"status": "error", "message": str(e), "summary": {}}


@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM organized_files ORDER BY date DESC LIMIT 10")
    recent_logs = c.fetchall()
    c.execute("SELECT filetype, COUNT(*) FROM organized_files GROUP BY filetype")
    counts = dict(c.fetchall())
    conn.close()
    total_files = sum(counts.values())
    return render_template("dashboard.html", total_files=total_files, counts=counts, recent_logs=recent_logs)


@app.route("/organize", methods=["POST"])
def organize_route():
    data = request.get_json(silent=True)
    dest_path = None
    if request.form.get("path"):
        dest_path = request.form.get("path")
    elif data and data.get("path"):
        dest_path = data.get("path")

    result = organize_files(dest_path)
    return jsonify(result)


@app.route("/records")
def records():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM organized_files ORDER BY date DESC")
    rows = c.fetchall()
    conn.close()
    return render_template("records.html", files=rows)


@app.route("/api/summary")
def api_summary():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT filetype, COUNT(*) FROM organized_files GROUP BY filetype")
    rows = c.fetchall()
    conn.close()
    data = {r[0]: r[1] for r in rows}
    for k in ["images", "documents", "videos", "audio", "archives", "others"]:
        data.setdefault(k, 0)
    return jsonify(data)


@app.route("/api/chartdata")
def api_chartdata():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT date, COUNT(*) FROM organized_files GROUP BY date ORDER BY date ASC")
    rows = c.fetchall()
    conn.close()
    labels = [r[0].split(" ")[0] for r in rows]
    counts = [r[1] for r in rows]
    return jsonify({"labels": labels, "counts": counts})


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
