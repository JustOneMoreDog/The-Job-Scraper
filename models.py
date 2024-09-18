from datetime import date
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class JobPostingDatabase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    applied = db.Column(db.Boolean)
    posted_time = db.Column(db.String)
    title = db.Column(db.String)
    company = db.Column(db.String)
    industry = db.Column(db.String)
    location = db.Column(db.String)
    rating = db.Column(db.Integer)
    keywords = db.Column(db.String)
    search = db.Column(db.String)
    url = db.Column(db.String, unique=True)
    content = db.Column(db.Text)
