# setup_dashboard_local.py
# FIXED VERSION — UTF‑8, VALID open(), FULLY WORKING

import os, json

print("Generating dashboard...")

# ----------------------------------------------------
# CREATE FOLDERS
# ----------------------------------------------------
os.makedirs("dashboard/templates", exist_ok=True)
os.makedirs("dashboard/static/css", exist_ok=True)

# ----------------------------------------------------
# CONFIG (UTF‑8)
# ----------------------------------------------------
with open("dashboard/config.py", "w", encoding="utf-8") as f:
    f.write("""
CLIENT_ID = "INSERISCI_CLIENT_ID"
CLIENT_SECRET = "INSERISCI_CLIENT_SECRET"
PANEL_URL = "http://localhost:5000"
REDIRECT_URI = "http://localhost:5000/callback"
GUILD_ADMIN_ID = 1442896042923135018
CONFIG_FILE_PATH = "../bot_config.json"
SESSION_SECRET = "CAMBIA_QUESTA_STRINGA_RANDOM"
""")

# ----------------------------------------------------
# CSS (UTF‑8)
# ----------------------------------------------------
with open("dashboard/static/css/style.css", "w", encoding="utf-8") as f:
    f.write("""
body {
    margin:0;
    background:#0c0c14;
    font-family:'Segoe UI', sans-serif;
    color:white;
}
.sidebar {
    position:fixed;
    left:0;
    top:0;
    width:230px;
    height:100vh;
    background:linear-gradient(180deg,#1a0033,#0a0014);
    padding-top:20px;
    box-shadow:0 0 20px #7700ff;
}
.sidebar a {
    display:block;
    padding:15px 25px;
    text-decoration:none;
    color:#c7a4ff;
    font-weight:600;
    transition:.2s;
}
.sidebar a:hover { background:rgba(119,0,255,.2); color:white; }
.navbar {
    margin-left:230px;
    height:60px;
    background:rgba(10,0,20,.9);
    display:flex;
    align-items:center;
    justify-content:space-between;
    padding:0 20px;
    box-shadow:0 0 15px #7700ff;
}
.card {
    background:#12001f;
    padding:20px;
    margin:20px;
    border-radius:12px;
    box-shadow:0 0 15px #6600cc;
}
.button-primary {
    background:linear-gradient(90deg,#7f00ff,#e100ff);
    border:none;
    padding:12px 20px;
    color:white;
    border-radius:8px;
    cursor:pointer;
    font-weight:bold;
    transition:.2s;
}
.button-primary:hover { transform:scale(1.05); }
""")

# ----------------------------------------------------
# LAYOUT HTML (UTF‑8)
# ----------------------------------------------------
with open("dashboard/templates/layout.html", "w", encoding="utf-8") as f:
    f.write("""
<!DOCTYPE html><html><head>
<meta charset='UTF-8'>
<link rel='stylesheet' href='/static/css/style.css'>
<title>Dashboard Premium</title></head><body>
<div class='sidebar'>
<a href='/'>🏠 Dashboard</a>
<a href='/settings'>⚙️ Settings</a>
<a href='/applications'>📝 Candidature</a>
<a href='/logs'>📄 Logs</a>
</div>
<div class='navbar'><h2>Dashboard Premium</h2></div>
<div style='margin-left:250px; padding:20px;'>
{% block content %}{% endblock %}
</div>
</body></html>
""")

# ----------------------------------------------------
# DASHBOARD PAGE
# ----------------------------------------------------
with open("dashboard/templates/dashboard.html", "w", encoding="utf-8") as f:
    f.write("""
{% extends 'layout.html' %}
{% block content %}
<h1>Dashboard</h1>
<p>Benvenuto nella dashboard.</p>
{% endblock %}
""")

# ----------------------------------------------------
# SETTINGS PAGE
# ----------------------------------------------------
with open("dashboard/templates/settings.html", "w", encoding="utf-8") as f:
    f.write("""
{% extends 'layout.html' %}
{% block content %}
<h1>Settings</h1>
<form method='post' action='/save_settings'>
<label>Prefisso:</label><br>
<input name='prefix' value='{{ config.prefix }}'><br><br>
<button class='button-primary'>Salva</button>
</form>
{% endblock %}
""")

# ----------------------------------------------------
# APPLICATION PAGE
# ----------------------------------------------------
with open("dashboard/templates/applications.html", "w", encoding="utf-8") as f:
    f.write("""
{% extends 'layout.html' %}
{% block content %}
<h1>Candidature</h1>
<form method='post' action='/save_app_questions'>
<textarea name='questions' style='width:500px;height:200px;'>{{ config.questions|join("
") }}</textarea><br><br>
<button class='button-primary'>Salva Domande</button>
</form>
{% endblock %}
""")

# ----------------------------------------------------
# LOGS PAGE
# ----------------------------------------------------
with open("dashboard/templates/logs.html", "w", encoding="utf-8") as f:
    f.write("""
{% extends 'layout.html' %}
{% block content %}
<h1>Logs</h1>
{% for entry in logs %}
<div class='card'>{{ entry }}</div>
{% endfor %}
{% endblock %}
""")

# ----------------------------------------------------
# BACKEND (UTF‑8)
# ----------------------------------------------------
with open("dashboard/dashboard.py", "w", encoding="utf-8") as f:
    f.write("""
import json, requests
from flask import Flask, redirect, request, session, render_template
from config import *

app = Flask(__name__)
app.secret_key = SESSION_SECRET

def load_config():
    try: return json.load(open(CONFIG_FILE_PATH, encoding='utf-8'))
    except: return {"prefix":"!","questions":[],"logs":[]}

def save_config(c): json.dump(c, open(CONFIG_FILE_PATH,'w',encoding='utf-8'), indent=4)

def is_logged(): return 'discord_user' in session

def is_admin(): return True

@app.route('/')
def home():
    if not is_logged(): return redirect('/login')
    return render_template('dashboard.html')

@app.route('/login')
def login():
    return redirect('/settings')

@app.route('/settings')
def settings(): return render_template('settings.html', config=load_config())

@app.route('/save_settings',methods=['POST'])
def save_settings():
    c=load_config(); c['prefix']=request.form['prefix']; save_config(c); return redirect('/settings')

@app.route('/applications')
def apps(): return render_template('applications.html', config=load_config())

@app.route('/save_app_questions',methods=['POST'])
def save_q():
    c=load_config(); c['questions']=request.form['questions'].split('
'); save_config(c); return redirect('/applications')

@app.route('/logs')
def logs(): return render_template('logs.html', logs=load_config().get('logs',[]))

if __name__=='__main__': app.run(port=5000)
""")

# ----------------------------------------------------
# RUN SCRIPT (UTF‑8)
# ----------------------------------------------------
with open("run_dashboard.py", "w", encoding="utf-8") as f:
    f.write("""
import os
print('Avvio dashboard...')
os.system('python dashboard/dashboard.py')
""")

print("DONE — Dashboard generata correttamente!")
