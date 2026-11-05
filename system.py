from flask import Flask,url_for,session,redirect,render_template
from config import configserver,historia
from db import db

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///configserver.db'
app.config['SQLALCHEMY_BINDS'] = {
    'historia_db': 'sqlite:///hinstorias.db'
    }
db.init_app(app)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)