from flask import Flask, render_template, redirect, url_for
from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, IntegerField, BooleanField,
                     RadioField, SelectField, DateField, SubmitField)
from wtforms.validators import InputRequired, Length

app = Flask(__name__)


@app.route('/', methods=('GET', 'POST'))
def index():  # put application's code here
    x = ['2022-04-22-19-1', '2022-04-22-20-2', '2022-04-22-21-3']
    days = SelectField('Date', choices=[(y, y) for y in x])
    submit = SubmitField('Register')
    return render_template('index.html', tester=days)


@app.route('/<date>')
def results(date):
    print(date)
    return render_template(str(date + '/index.html'))


@app.route('/<date>/<jobposting>')
def jobpost(date, jobposting):
    print(date + '/' + jobposting)
    return render_template(date + '/' + jobposting + '/content.html')

if __name__ == '__main__':
    app.run()
