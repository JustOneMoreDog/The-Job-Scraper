
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from flask import Flask, render_template, redirect, url_for, request, g
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, FormField, SelectField, FieldList, SubmitField, validators
from wtforms.validators import InputRequired, Length
import subprocess
import time
from collections import namedtuple
from forms import SearchTermsForm, MinJobsForm, LocationsForm, ExperienceLevelsForm, ExcludedLocationsForm, \
    ExcludedCompanies, WordWeightForm
import yaml

app = Flask(__name__)
app.config['SECRET_KEY'] = 'makesuretochangethisbeforehittingcommit'

executors = {
    'default': ThreadPoolExecutor(16),
    'processpool': ProcessPoolExecutor(4)
}
schedule = BackgroundScheduler(timezone='America/New_York', executors=executors)


def run_job_scraper():
    x = subprocess.run(['C:/Users/sandwich/PycharmProjects/LinkedIn-Job-Scraper/venv/Scripts/python.exe',
                    'C:/Users/sandwich/PycharmProjects/LinkedIn-Job-Scraper/files/job_scraper.py'
                    ])



def process_customizations(get=None, post=None, form=None):
    pass


@app.route('/', methods=('GET', 'POST'))
def index():  # put application's code here
    #print("Now we are going to update the config search terms like we would from a post request")
    #scraper.config['searches'] = ['1', '2', '3']
    #print(yaml.dump(scraper.config))
    #scraper.set_customizations(scraper.config)
    #print("It has been updated?")
    x = ['2022-04-22-19-1', '2022-04-22-20-2', '2022-04-22-21-3']
    days = SelectField('Date', choices=[(y, y) for y in x])
    submit = SubmitField('Register')
    return render_template('index.html', tester=days)


@app.route('/<date>')
def results(date):
    return render_template(str(date + '/index.html'))


@app.route('/<date>/<jobposting>')
def jobpost(date, jobposting):
    print(date + '/' + jobposting)
    return render_template(date + '/' + jobposting + '/content.html')


@app.route('/customizations', methods=['GET'])
def customizations():
    with open("C:/Users/sandwich/PycharmProjects/LinkedIn-Job-Scraper/files/customizations.yaml", "r") as f:
        customizations = yaml.load(f, Loader=yaml.FullLoader)
    search_form_data = getFormData('search_term_label', 'searches', customizations)
    min_jobs_form_data = getFormData('min_jobs_label', 'minimum_jobs_per_search', customizations)
    location_form_data = getFormData('location_label', 'locations', customizations)
    experience_form_data = getFormData('experience_level_label', 'experience_levels', customizations)
    excluded_location_form_data = getFormData('exclude_location_label', 'excluded_locations', customizations)
    excluded_org_form_data = getFormData('excluded_org_label', 'excluded_companies', customizations)
    keyword_form_data = getFormData('keyword_label', 'word_weights', customizations)
    return render_template(
        'customizations.html',
        searchTerms=SearchTermsForm(data=search_form_data),
        minEntries=MinJobsForm(data=min_jobs_form_data),
        locations=LocationsForm(data=location_form_data),
        experiences=ExperienceLevelsForm(data=experience_form_data),
        excluded_locations=ExcludedLocationsForm(data=excluded_location_form_data),
        excluded_companies=ExcludedCompanies(data=excluded_org_form_data),
        keyword_weights=WordWeightForm(data=keyword_form_data)
    )


def getFormData(html_label, yaml_label, customizations):
    search_term = namedtuple('Terms', [html_label])
    data = {'rows': []}
    if html_label == "min_jobs_label":
        data['rows'].append(search_term(str(customizations[yaml_label])))
        return data
    if html_label == "experience_level_label":
        # This will require a little hands on to ensure order
        data['rows'].append(search_term(str(customizations[yaml_label]['Internship'])))
        data['rows'].append(search_term(str(customizations[yaml_label]['Entry level'])))
        data['rows'].append(search_term(str(customizations[yaml_label]['Associate'])))
        data['rows'].append(search_term(str(customizations[yaml_label]['Mid-Senior level'])))
        data['rows'].append(search_term(str(customizations[yaml_label]['Director'])))
        return data
    if html_label == "keyword_label":
        # Need to manually translate the data here
        # Also I have no idea why this works and I am not questioning it
        keyword_term = namedtuple('Terms', ["keyword_label"])
        weight_term = namedtuple('Terms', ["weight_label"])
        for k, v in customizations[yaml_label].items():
            data['rows'].append(keyword_term(k))
            data['rows'].append(weight_term(str(v)))
        for i in range(4):
            data['rows'].append(keyword_term(''))
            data['rows'].append(weight_term(''))
        return data
    for x in customizations[yaml_label]:
        data['rows'].append(search_term(x))
    # Adding some blank entries
    for i in range(3):
        data['rows'].append(search_term(''))
    return data


@app.route('/customizations_set', methods=['POST'])
def customizations1():
    print("in customizations 1")
    r = request
    return redirect(url_for('customizations'))


if __name__ == '__main__':
    #schedule.start()
    #schedule.add_job(run_job_scraper, 'interval', seconds=60)
    # print("Scrapper class been called and we can see that the search term values are %s" %
    #       ','.join(scraper.config['searches'])
    #       )
    # print("Now we are going to start the background scheduler")
    # scraper.init_scheduling()
    # print("Now we are going to sleep for 5 seconds to give it a chance to run its first loop")
    # time.sleep(5)
    app.debug = True
    app.run(host="0.0.0.0")


# https://blog.jcharistech.com/2019/12/12/how-to-render-markdown-in-flask/

# Known bugs
# when you click on the content button, it takes you to a url that ends in /content.html and we need to remove that part
# need a documentation page

'''
Next steps 
trim up all the fat 
build out the rest of the form 
ps aux grep job scraper if not null it is running 
to minimize errors, lets get a global variable going that contains the customization data
    this variable is init-ed when program first runs
    modified when the user does a post on customizations form 
    written to disk during that post
# checking to make sure the file is not open to avoid file locks
while true:
    try to open the file; break (or put code in here) except some error continue 
# 
when saving a new customizations to disk, a function is run
    moves current customizations.yaml file to a customizations_history folder 
    name of file is unix time code
when user loads customizations form
    dropdown list is populated with contents of customizations_history folder
    unix time code stamp translated to standard date / time strings
    hitting restore does a post to customizations_restore which takes the strings and restores the file accordingly and then redirects back
'''