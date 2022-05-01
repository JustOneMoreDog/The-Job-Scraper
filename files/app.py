from flask import Flask, render_template, redirect, url_for, request
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, FormField, SelectField, FieldList, SubmitField
from wtforms.validators import InputRequired, Length
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
import time
import os
import job_scraper
from collections import namedtuple

app = Flask(__name__)
app.config['SECRET_KEY'] = 'makesuretochangethisbeforehittingcommit'
executors = {
    'default': ThreadPoolExecutor(16),
    'processpool': ProcessPoolExecutor(4)
}
sched = BackgroundScheduler(timezone='America/New_York', executors=executors)

#sched.add_job(run_job_scraper, 'interval', minutes=120)
def run_job_scraper():
    os.chdir("/app")
    job_scraper.main()


def process_customizations(get=None, post=None, form=None):



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


class SearchTermRow(FlaskForm):
    search_term_label = StringField()
    delete_btn = SubmitField(label='Delete')


class SearchTermForm(FlaskForm):
    rows = FieldList(FormField(SearchTermRow), min_entries=0)
    add_row = SubmitField(label='Add Row')
    confirm = SubmitField(label='Confirm')


@app.route('/customizations', methods=['GET'])
def customizations():
    search_term = namedtuple('Terms', ['search_term_label'])
    s1 = search_term('1')
    s2 = search_term('2')
    s3 = search_term('3')
    s4 = search_term('4')
    output = "<h1>"
    #form = SearchTermForm()
    data = {'rows': [s1, s2, s3, s4]}
    # if form.add_row.data:
    #     s5 = search_term('5')
    #     data = {'rows': [s1, s2, s3, s4, s5]}
    #     #form = SearchTermForm(data=data)
    # if form.confirm.data:
    #     for field in form.rows:
    #         output += field.search_term_label.data + ' <br />'
    #     output += '</h1>'
    #     return output
    form = SearchTermForm(data=data)
    return render_template('customizations.html', form=form)


@app.route('/customizations1', methods=['POST'])
def customizations1():
    print("in customizations 1")
    r = request
    return redirect(url_for('customizations'))


if __name__ == '__main__':
    #sched.start()
    app.debug = True
    app.run(host="0.0.0.0")


# https://blog.jcharistech.com/2019/12/12/how-to-render-markdown-in-flask/

# Known bugs
# when you click on the content button, it takes you to a url that ends in /content.html and we need to remove that part
# need a documentation page
