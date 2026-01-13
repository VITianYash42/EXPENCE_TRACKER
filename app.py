from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import json

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  

def get_db_connection():
    conn = sqlite3.connect('expenses.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            period TEXT NOT NULL DEFAULT 'monthly',
            start_date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        
        try:
            hashed_password = generate_password_hash(password)
            conn.execute(
                'INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                (username, email, hashed_password)
            )
            conn.commit()
            flash('Account created successfully! Please login.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists!')
        finally:
            conn.close()
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Logged in successfully!')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials!')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # Get total expenses
    total_expenses = conn.execute(
        'SELECT SUM(amount) FROM expenses WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()[0] or 0
    
    # Get monthly expenses
    current_month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
    monthly_expenses = conn.execute(
        'SELECT SUM(amount) FROM expenses WHERE user_id = ? AND date >= ?',
        (session['user_id'], current_month_start)
    ).fetchone()[0] or 0
    
    # Get recent expenses
    recent_expenses = conn.execute('''
        SELECT * FROM expenses 
        WHERE user_id = ? 
        ORDER BY date DESC 
        LIMIT 5
    ''', (session['user_id'],)).fetchall()
    
    # Get budget information
    budgets = conn.execute('''
        SELECT * FROM budgets 
        WHERE user_id = ?
    ''', (session['user_id'],)).fetchall()
    
    # Calculate budget summary
    total_budget = 0
    total_budget_spent = 0
    budget_alerts = []
    
    current_month = datetime.now().strftime('%Y-%m')
    for budget in budgets:
        budget_amount = float(budget['amount'])
        total_budget += budget_amount
        
        # Calculate actual spending based on period
        if budget['period'] == 'monthly':
            start_date = datetime.now().replace(day=1).strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')
        elif budget['period'] == 'weekly':
            start_date = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')
        else:  
            start_date = datetime.now().replace(month=1, day=1).strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        actual_spending = conn.execute('''
            SELECT COALESCE(SUM(amount), 0) FROM expenses 
            WHERE user_id = ? AND category = ? AND date >= ? AND date <= ?
        ''', (session['user_id'], budget['category'], start_date, end_date)).fetchone()[0] or 0
        
        actual_spending = float(actual_spending)
        total_budget_spent += actual_spending
        
        percentage_used = (actual_spending / budget_amount * 100) if budget_amount > 0 else 0
        
        # Add alerts for budgets over 80% or exceeded
        if percentage_used >= 100:
            budget_alerts.append({
                'category': budget['category'],
                'status': 'exceeded',
                'percentage': percentage_used,
                'remaining': budget_amount - actual_spending
            })
        elif percentage_used >= 80:
            budget_alerts.append({
                'category': budget['category'],
                'status': 'warning',
                'percentage': percentage_used,
                'remaining': budget_amount - actual_spending
            })
    
    conn.close()
    
    return render_template('dashboard.html', 
                         total_expenses=total_expenses,
                         monthly_expenses=monthly_expenses,
                         recent_expenses=recent_expenses,
                         total_budget=total_budget,
                         total_budget_spent=total_budget_spent,
                         budget_alerts=budget_alerts)

@app.route('/expenses')
def expenses():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    expenses_list = conn.execute('''
        SELECT * FROM expenses 
        WHERE user_id = ? 
        ORDER BY date DESC
    ''', (session['user_id'],)).fetchall()
    conn.close()
    
    return render_template('expenses.html', expenses=expenses_list)

@app.route('/add_expense', methods=['GET', 'POST'])
def add_expense():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        amount = float(request.form['amount'])
        category = request.form['category']
        description = request.form['description']
        date = request.form['date'] or datetime.now().strftime('%Y-%m-%d')
        
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?, ?, ?, ?, ?)',
            (session['user_id'], amount, category, description, date)
        )
        conn.commit()
        conn.close()
        
        flash('Expense added successfully!')
        return redirect(url_for('expenses'))
    
    return render_template('add_expense.html')

@app.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        amount = float(request.form['amount'])
        category = request.form['category']
        description = request.form['description']
        date = request.form['date']
        
        conn.execute(
            'UPDATE expenses SET amount = ?, category = ?, description = ?, date = ? WHERE id = ? AND user_id = ?',
            (amount, category, description, date, expense_id, session['user_id'])
        )
        conn.commit()
        conn.close()
        
        flash('Expense updated successfully!')
        return redirect(url_for('expenses'))
    
    expense = conn.execute(
        'SELECT * FROM expenses WHERE id = ? AND user_id = ?',
        (expense_id, session['user_id'])
    ).fetchone()
    conn.close()
    
    if not expense:
        flash('Expense not found!')
        return redirect(url_for('expenses'))
    
    return render_template('edit_expense.html', expense=expense)

@app.route('/delete_expense/<int:expense_id>')
def delete_expense(expense_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    conn.execute(
        'DELETE FROM expenses WHERE id = ? AND user_id = ?',
        (expense_id, session['user_id'])
    )
    conn.commit()
    conn.close()
    
    flash('Expense deleted successfully!')
    return redirect(url_for('expenses'))

@app.route('/analytics')
def analytics():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # Get daily spending for last 7 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=6)
    
    daily_data = []
    labels = []
    
    for i in range(7):
        current_date = (start_date + timedelta(days=i)).strftime('%Y-%m-%d')
        labels.append((start_date + timedelta(days=i)).strftime('%b %d'))
        
        total = conn.execute('''
            SELECT SUM(amount) FROM expenses 
            WHERE user_id = ? AND date = ?
        ''', (session['user_id'], current_date)).fetchone()[0] or 0
        
        daily_data.append(float(total))
    
    # Get category-wise spending
    categories_data = conn.execute('''
        SELECT category, SUM(amount) as total 
        FROM expenses 
        WHERE user_id = ? 
        GROUP BY category
    ''', (session['user_id'],)).fetchall()
    
    category_labels = [row['category'] for row in categories_data]
    category_totals = [float(row['total']) for row in categories_data]
    
    conn.close()
    
    return render_template('analytics.html',
                         labels=json.dumps(labels),
                         daily_data=json.dumps(daily_data),
                         category_labels=json.dumps(category_labels),
                         category_totals=json.dumps(category_totals))

@app.route('/budgets')
def budgets():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # Get all budgets for the user
    budgets_list = conn.execute('''
        SELECT * FROM budgets 
        WHERE user_id = ? 
        ORDER BY category
    ''', (session['user_id'],)).fetchall()
    
    # Calculate actual spending for each budget
    budgets_with_spending = []
    current_month = datetime.now().strftime('%Y-%m')
    
    for budget in budgets_list:
        budget_dict = dict(budget)
        
        # Calculate actual spending based on period
        if budget['period'] == 'monthly':
            start_date = datetime.now().replace(day=1).strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')
        elif budget['period'] == 'weekly':
            start_date = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')
        else:  
            start_date = datetime.now().replace(month=1, day=1).strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        actual_spending = conn.execute('''
            SELECT COALESCE(SUM(amount), 0) FROM expenses 
            WHERE user_id = ? AND category = ? AND date >= ? AND date <= ?
        ''', (session['user_id'], budget['category'], start_date, end_date)).fetchone()[0] or 0
        
        budget_dict['actual_spending'] = float(actual_spending)
        budget_dict['remaining'] = float(budget['amount']) - float(actual_spending)
        budget_dict['percentage_used'] = (float(actual_spending) / float(budget['amount']) * 100) if budget['amount'] > 0 else 0
        budgets_with_spending.append(budget_dict)
    
    conn.close()
    
    return render_template('budgets.html', budgets=budgets_with_spending)

@app.route('/add_budget', methods=['GET', 'POST'])
def add_budget():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        category = request.form['category']
        amount = float(request.form['amount'])
        period = request.form['period']
        start_date = request.form['start_date'] or datetime.now().strftime('%Y-%m-%d')
        
        conn = get_db_connection()
        
        # Check if budget already exists for this category and period
        existing = conn.execute('''
            SELECT * FROM budgets 
            WHERE user_id = ? AND category = ? AND period = ?
        ''', (session['user_id'], category, period)).fetchone()
        
        if existing:
            flash('Budget already exists for this category and period!')
            conn.close()
            return render_template('add_budget.html')
        
        conn.execute(
            'INSERT INTO budgets (user_id, category, amount, period, start_date) VALUES (?, ?, ?, ?, ?)',
            (session['user_id'], category, amount, period, start_date)
        )
        conn.commit()
        conn.close()
        
        flash('Budget added successfully!')
        return redirect(url_for('budgets'))
    
    return render_template('add_budget.html')

@app.route('/edit_budget/<int:budget_id>', methods=['GET', 'POST'])
def edit_budget(budget_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        amount = float(request.form['amount'])
        period = request.form['period']
        start_date = request.form['start_date']
        
        conn.execute(
            'UPDATE budgets SET amount = ?, period = ?, start_date = ? WHERE id = ? AND user_id = ?',
            (amount, period, start_date, budget_id, session['user_id'])
        )
        conn.commit()
        conn.close()
        
        flash('Budget updated successfully!')
        return redirect(url_for('budgets'))
    
    budget = conn.execute(
        'SELECT * FROM budgets WHERE id = ? AND user_id = ?',
        (budget_id, session['user_id'])
    ).fetchone()
    conn.close()
    
    if not budget:
        flash('Budget not found!')
        return redirect(url_for('budgets'))
    
    return render_template('edit_budget.html', budget=budget)

@app.route('/delete_budget/<int:budget_id>')
def delete_budget(budget_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    conn.execute(
        'DELETE FROM budgets WHERE id = ? AND user_id = ?',
        (budget_id, session['user_id'])
    )
    conn.commit()
    conn.close()
    
    flash('Budget deleted successfully!')
    return redirect(url_for('budgets'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)