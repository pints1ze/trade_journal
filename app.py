from flask import Flask, render_template, g, request, redirect, url_for, flash, jsonify
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
import json
from datetime import datetime, date

app = Flask(__name__)
app.config['DATABASE'] = os.path.join(app.root_path, 'trade_journal.db')
app.secret_key = os.environ.get('SECRET_KEY', 'dev')

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL)"
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    db.commit()


import click


@app.cli.command("init-db")
def init_db_command():
    """Initialize the database."""
    init_db()
    click.echo("Initialized the database.")


class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = str(id)
        self.username = username
        self.password_hash = password_hash

    @staticmethod
    def get(user_id):
        db = get_db()
        row = db.execute("SELECT id, username, password FROM users WHERE id = ?", (user_id,)).fetchone()
        if row:
            return User(row['id'], row['username'], row['password'])
        return None

    @staticmethod
    def get_by_username(username):
        db = get_db()
        row = db.execute("SELECT id, username, password FROM users WHERE username = ?", (username,)).fetchone()
        if row:
            return User(row['id'], row['username'], row['password'])
        return None

    @staticmethod
    def create(username, password):
        db = get_db()
        password_hash = generate_password_hash(password)
        try:
            cur = db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password_hash))
            db.commit()
            return User(cur.lastrowid, username, password_hash)
        except sqlite3.IntegrityError:
            return None


@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash('Username and password are required.')
            return redirect(url_for('register'))
        user = User.create(username, password)
        if user is None:
            flash('Username already taken.')
            return redirect(url_for('register'))
        flash('Registration successful. Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.get_by_username(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Logged in successfully.')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        flash('Invalid username or password.')
        return redirect(url_for('login'))
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.')
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    rows = db.execute("SELECT id, date, type, amount, description FROM transactions WHERE user_id = ? ORDER BY date",
                      (current_user.id,)).fetchall()

    # normalize rows to a list of dicts
    entries = []
    for r in rows:
        entries.append({
            'id': r['id'],
            'date': r['date'],
            'type': r['type'],
            'amount': r['amount'],
            'description': r['description']
        })

    # build daily aggregated P&L
    daily = {}
    for e in entries:
        d = e['date']
        daily.setdefault(d, 0)
        daily[d] += e['amount']

    # produce ordered lists
    dates = sorted(daily.keys())
    pnl_daily = [{'date': d, 'amount': daily[d]} for d in dates]

    # cumulative balance series
    cumulative = []
    running = 0.0
    for item in pnl_daily:
        running += item['amount']
        cumulative.append({'date': item['date'], 'balance': running})

    # win/loss stats (trades only)
    trade_amounts = [e['amount'] for e in entries if e['type'] == 'trade']
    wins = [v for v in trade_amounts if v > 0]
    losses = [v for v in trade_amounts if v < 0]
    total_trades = len(trade_amounts)
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
    avg_win = (sum(wins) / len(wins)) if wins else 0
    avg_loss = (sum(losses) / len(losses)) if losses else 0

    # running account total (starting at 0) and last balance
    account_total = running

    return render_template('dashboard.html', user=current_user,
                           entries=entries,
                           pnl_daily=pnl_daily,
                           pnl_daily_json=json.dumps(pnl_daily),
                           cumulative=cumulative,
                           cumulative_json=json.dumps(cumulative),
                           win_rate=round(win_rate, 2),
                           avg_win=round(avg_win, 2),
                           avg_loss=round(avg_loss, 2),
                           account_total=round(account_total, 2))


@app.route('/add-entry', methods=['POST'])
@login_required
def add_entry():
    db = get_db()
    entry_date = request.form.get('date') or date.today().isoformat()
    entry_type = request.form.get('type')
    amount_raw = request.form.get('amount') or '0'
    try:
        amount = float(amount_raw)
    except ValueError:
        flash('Invalid amount')
        return redirect(url_for('dashboard'))
    description = request.form.get('description')

    db.execute("INSERT INTO transactions (user_id, date, type, amount, description) VALUES (?, ?, ?, ?, ?)",
               (current_user.id, entry_date, entry_type, amount, description))
    db.commit()
    flash('Entry added.')
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True)
