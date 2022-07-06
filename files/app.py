from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from collections import namedtuple
from datetime import datetime
from forms import SearchTermsForm, MinJobsForm, LocationsForm, ExperienceLevelsForm, ExcludedLocationsForm, \
    ExcludedCompanies, WordWeightForm, SubmitButton, ExcludedTitles, RestoreButton, RunTimeForm
from flask import Flask, render_template, redirect, url_for, request
from flask_caching import Cache
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, FormField, SelectField, FieldList, \
    SubmitField, validators
from wtforms.validators import InputRequired, Length
import subprocess
import time
import os
import yaml

app_config = {
    "SECRET_KEY": "makesuretochangethisbeforehittingcommit",
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 0,
    "CACHE_DIR": "C:/Users/sandwich/PycharmProjects/LinkedIn-Job-Scraper/files/cache/"
}
app = Flask(__name__)
app.config.from_mapping(app_config)
cache = Cache(app)
customizations_path = "C:/Users/sandwich/PycharmProjects/LinkedIn-Job-Scraper/files/customizations.yaml"
customizations_backup_path = "C:/Users/sandwich/PycharmProjects/LinkedIn-Job-Scraper/files/customizations_backups/"


def save_customizations(path):
    with open(path, "w") as f:
        yaml.dump(cache.get("customizations"), f)


def load_customizations(path):
    with open(path, "r") as f:
        cache.set("customizations", yaml.load(f, Loader=yaml.FullLoader))


load_customizations(customizations_path)

cache.clear()
curr_ts = 0
restore_points = []
for file in os.listdir('files/customizations_backups'):
    if file.endswith('.yaml'):
        ts = int(file.split("-")[1].split(".")[0])
        restore_points.append((file, datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')))
        if ts > curr_ts:
            curr_ts = ts
restore_points.reverse()
job_data_list = []
for x in os.listdir('files/templates'):
    if os.path.isdir(os.path.join('files/templates', x)):
        job_data_list.append(x)
job_data_list.reverse()
cache.set("current_job_data_selection", job_data_list[0])
cache.set("job_data_list", job_data_list)

executors = {
    'default': ThreadPoolExecutor(16),
    'processpool': ProcessPoolExecutor(4)
}
schedule = BackgroundScheduler(timezone='America/New_York', executors=executors)


def run_job_scraper():
    x = subprocess.run(['C:/Users/sandwich/PycharmProjects/LinkedIn-Job-Scraper/venv/Scripts/python.exe',
                        'C:/Users/sandwich/PycharmProjects/LinkedIn-Job-Scraper/files/job_scraper.py'
                        ])


@app.route('/', methods=['GET'])
def index():
    print("index %s" % cache.get("current_job_data_selection"))
    print("list %s" % ','.join(list(cache.get("job_data_list"))))

    class JobDataDropdown(FlaskForm):
        dropdown = SelectField()

    job_list = list(cache.get("job_data_list"))
    curr = cache.get("current_job_data_selection")
    new_job_list = False
    print("curr %s" % curr)
    print("job_list %s" % job_list[0])
    if curr != job_list[0]:
        job_list.remove(curr)
        new_job_list = sorted(set(job_list))
        new_job_list.reverse()
        new_job_list.insert(0, curr)
        print("inserted")
        print(new_job_list)
        cache.set("job_data_list", new_job_list)

    job_dropdown = JobDataDropdown()
    job_dropdown.dropdown.choices = new_job_list if new_job_list else job_list
    table_choice = job_dropdown.dropdown.choices[0] + "/index.html"
    '''
    so we can basically just render the actual job
    '''
    return render_template(
        'index.html',
        job_scrapes=job_dropdown,
        job_table_choice=table_choice
    )


@app.route('/display_jobs_set', methods=['POST'])
def displays_jobs_set():
    print(request.form['dropdown'])
    cache.set("current_job_data_selection", request.form['dropdown'])
    print("here %s" % cache.get("current_job_data_selection"))
    return redirect(url_for('index'))


@app.route('/customizations', methods=['GET'])
def customizations_get():
    customizations = cache.get("customizations")
    search_form_data = getFormData('search_term_label', 'searches', customizations)
    min_jobs_form_data = getFormData('min_jobs_label', 'minimum_jobs_per_search', customizations)
    location_form_data = getFormData('location_label', 'locations', customizations)
    experience_form_data = getFormData('experience_level_label', 'experience_levels', customizations)
    excluded_location_form_data = getFormData('exclude_location_label', 'excluded_locations', customizations)
    excluded_org_form_data = getFormData('excluded_org_label', 'excluded_companies', customizations)
    excluded_title_data = getFormData('excluded_titles_label', 'excluded_title_keywords', customizations)
    keyword_form_data = getFormData('keyword_label', 'word_weights', customizations)

    # run_time_data = getFormData('run_time_label', 'run_time', customizations)

    class RestoreOptionsDropdown(FlaskForm):
        dropdown = SelectField('restores', choices=cache.get("restore_points"))

    return render_template(
        'customizations.html',
        searchTerms=SearchTermsForm(data=search_form_data),
        minEntries=MinJobsForm(data=min_jobs_form_data),
        locations=LocationsForm(data=location_form_data),
        experiences=ExperienceLevelsForm(data=experience_form_data),
        excluded_locations=ExcludedLocationsForm(data=excluded_location_form_data),
        excluded_companies=ExcludedCompanies(data=excluded_org_form_data),
        excluded_titles=ExcludedTitles(data=excluded_title_data),
        keyword_weights=WordWeightForm(data=keyword_form_data),
        confirm_button=SubmitButton(),
        last_updated=cache.get("last_updated"),
        restore_points=RestoreOptionsDropdown(),
        restore_button=RestoreButton(),
        # run_time=RunTimeForm(data=run_time_data)
    )


@app.route('/<date>')
def results(date):
    return render_template(str(date + '/index.html'))


@app.route('/<date>/<jobposting>')
def jobpost(date, jobposting):
    print(date + '/' + jobposting)
    return render_template(date + '/' + jobposting + '/content.html')


def getFormData(html_label, yaml_label, customizations):
    search_term = namedtuple('Terms', [html_label])
    data = {'rows': []}
    if html_label == "min_jobs_label":
        data['rows'].append(search_term(str(customizations[yaml_label])))
        return data
    # if html_label == "run_time_label":
    #     data['rows'].append(search_term(str(customizations[yaml_label])))
    #     return data
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
        for i in range(8):
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
def customizations_set():
    process_customizations(request)
    return redirect(url_for('customizations_get'))


@app.route('/customizations_restore', methods=['POST'])
def customizations_restore():
    name = "customizations-" + str(int(time.time())) + ".yaml"
    ts = datetime.utcfromtimestamp(int(time.time())).strftime('%Y-%m-%d %H:%M:%S')
    backup_file = os.path.join(customizations_backup_path, request.form['dropdown'])
    load_customizations(backup_file)
    save_customizations(customizations_path)
    rp = list(cache.get("restore_points"))
    rp.insert(0, (name, ts))
    cache.set("restore_points", rp)
    cache.set("last_updated", ts)
    return redirect(url_for('customizations_get'))


def process_customizations(r):
    curr = dict(cache.get("customizations"))
    data = {
        'searches': [],
        'minimum_jobs_per_search': 0,
        'locations': [],
        'experience_levels': {},
        'excluded_locations': [],
        'excluded_companies': [],
        'excluded_title_keywords': [],
        'word_weights': {}
    }
    curr_kw = ''
    for k, v in r.form.items():
        if not v or not k:
            continue
        elif 'search_term' in k:
            data['searches'].append(v)
        elif 'min_jobs' in k:
            data['minimum_jobs_per_search'] = int(v)
        elif '-location' in k:
            data['locations'].append(v)
        elif 'experience_level' in k:
            if v.lower() == 'true':
                x = True
            else:
                x = False
            if '0' in k:
                data['experience_levels']['Internship'] = x
            elif '1' in k:
                data['experience_levels']['Entry level'] = x
            elif '2' in k:
                data['experience_levels']['Associate'] = x
            elif '3' in k:
                data['experience_levels']['Mid-Senior level'] = x
            else:
                data['experience_levels']['Director'] = x
        elif 'exclude_location' in k:
            data['excluded_locations'].append(v)
        elif 'excluded_org' in k:
            data['excluded_companies'].append(v)
        elif 'excluded_titles' in k:
            data['excluded_title_keywords'].append(v)
        # TO-DO figure out why 5:00 turns into 300 ?????
        # elif 'run_time' in k:
        #     data['run_time'] = "\"" + str(v) + "\""
        elif 'keyword' in k or 'weight' in k:
            if int(str(k).split("-")[1]) % 2 == 0:
                curr_kw = v
                continue
            data['word_weights'][curr_kw] = int(v)
    # Checking if the data has been changed at all
    changed = False
    for k, v in data.items():
        if k not in curr:
            exit(-1)
        if data[k] != curr[k]:
            print("failed to match these two")
            print(data[k])
            print(curr[k])
            changed = True
    if changed:
        name = "customizations-" + str(int(time.time())) + ".yaml"
        ts = datetime.utcfromtimestamp(int(time.time())).strftime('%Y-%m-%d %H:%M:%S')
        rp = list(cache.get("restore_points"))
        rp.insert(0, (name, ts))
        cache.set("restore_points", rp)
        save_customizations(os.path.join(customizations_backup_path, name))
        save_customizations(customizations_path)
        cache.set("customizations", data)
        cache.set("last_updated", ts)


if __name__ == '__main__':
    # schedule.start()
    # schedule.add_job(run_job_scraper, 'interval', seconds=60)
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
