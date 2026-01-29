<<<<<<< HEAD
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return "Home page working!"

@app.route('/signup')
def signup():
    return "Signup page working!"

@app.route('/login')
def login():
    return "Login page working!"

if __name__ == '__main__':
=======
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return "Home page working!"

@app.route('/signup')
def signup():
    return "Signup page working!"

@app.route('/login')
def login():
    return "Login page working!"

if __name__ == '__main__':
>>>>>>> eae67c6cd06c36c9dd29986198a9105c3c897a05
    app.run(debug=True)