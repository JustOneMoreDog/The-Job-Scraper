import logging
import logging.handlers
import os
import psutil
import subprocess
import time
import yaml

from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from collections import namedtuple
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, request
from flask_caching import Cache
from flask_wtf import FlaskForm
from forms import SearchTermsForm, MinJobsForm, LocationsForm, ExperienceLevelsForm, ExcludedLocationsForm, \
    ExcludedCompanies, WordWeightForm, SubmitButton, ExcludedTitles, RestoreButton
from wtforms import SelectField


app_config = {
    "SECRET_KEY": "makesuretochangethisbeforehittingcommit",
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 0,
    "CACHE_DIR": "/app/cache/"
}
app = Flask(__name__)
app.config.from_mapping(app_config)
cache = Cache(app)
customizations_path = "/app/customizations.yaml"
customizations_backup_path = "/app/customizations_backups/"


def init_logging():
    # Setting up our log files
    if not os.path.exists("flask_logs"):
        os.mkdir("flask_logs")
    log_filepath = "flask_logs/" + str(int(time.time())) + ".log"
    log_file_handler = logging.handlers.WatchedFileHandler(os.environ.get(
        "LOGFILE", os.path.join(os.getcwd(), log_filepath)
    ))
    formatter = logging.Formatter(logging.BASIC_FORMAT)
    log_file_handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(os.environ.get("LOGLEVEL", "INFO"))
    root.addHandler(log_file_handler)
    logging.info("Logging has been setup for flask")


def save_customizations(path):
    with open(path, "w") as f:
        yaml.dump(cache.get("customizations"), f)


def load_customizations(path):
    with open(path, "r") as f:
        cache.set("customizations", yaml.load(f, Loader=yaml.FullLoader))


def get_job_scrapes():
    job_data_list = list()
    for x in os.listdir('/app/templates'):
        if os.path.isdir(os.path.join('/app/templates', x)) and x != 'Welcome Page':
            job_data_list.append(x)
    job_data_list.sort(reverse=True)
    job_data_list.append('Welcome Page')
    return job_data_list


init_logging()
logging.info("Starting first time run initialization")
cache.clear()
logging.info("Cache cleared")
load_customizations(customizations_path)
logging.info("Customizations loaded")
curr_ts = 0
restore_points = []
for file in os.listdir(customizations_backup_path):
    if file.endswith('.yaml'):
        ts = int(file.split("-")[1].split(".")[0])
        restore_points.append((file, datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')))
        if ts > curr_ts:
            curr_ts = ts
restore_points.reverse()
cache.set("restore_points", restore_points)
logging.info("Restore points set")
job_data_list = get_job_scrapes()
cache.set("current_job_data_selection", job_data_list[0])
cache.set("job_data_list", job_data_list)
logging.info("Previous scrapes loaded")

executors = {
    'default': ThreadPoolExecutor(16),
    'processpool': ProcessPoolExecutor(4)
}
schedule = BackgroundScheduler(timezone='America/New_York', executors=executors)


def check_scraper():
    is_running = [proc.cmdline() for proc in psutil.process_iter()
                  if '/usr/bin/python3' in proc.cmdline() and '/app/job_scraper.py' in proc.cmdline()
                  ]
    if is_running:
        logging.info("Job Scraper is currently running")
        x = os.listdir("/app/flask_logs/")
        x.sort()
        runtime = str(timedelta(seconds=(int(time.time()) - int(x[-1].split(".")[0]))))
        return "Running", runtime
    else:
        return "Stopped", '0:00:00'


@app.route('/', methods=['GET'])
def index():
    class JobDataDropdown(FlaskForm):
        dropdown = SelectField()

    curr_scrape_selection = str(cache.get("current_job_data_selection"))
    curr_scrape_list = list(cache.get("job_data_list"))
    new_scrape_list = get_job_scrapes()
    logging.info("Current Selection: %s" % curr_scrape_selection)
    logging.info("Current List: %s" % ','.join(curr_scrape_list))
    logging.info("New List: %s" % ','.join(new_scrape_list))
    for scrape in new_scrape_list:
        if scrape not in curr_scrape_list:
            logging.info("New scrapes detected")
            cache.set("job_data_list", new_scrape_list)
            curr_scrape_list = new_scrape_list
            break

    new_job_list = False
    if curr_scrape_selection != curr_scrape_list[0]:
        curr_scrape_list.remove(curr_scrape_selection)
        curr_scrape_list.remove('Welcome Page')
        new_job_list = sorted(set(curr_scrape_list))
        new_job_list.reverse()
        new_job_list.insert(0, curr_scrape_selection)
        new_job_list.append('Welcome Page')
        logging.info("Inserted new selection choice and welcome page option")
        logging.info("Formatted new list: %s" % ','.join(new_job_list))
        cache.set("job_data_list", new_job_list)

    job_dropdown = JobDataDropdown()
    job_dropdown.dropdown.choices = new_job_list if new_job_list else curr_scrape_list
    table_choice = job_dropdown.dropdown.choices[0] + "/index.html"
    scraper_status, scraper_runtime = check_scraper()
    return render_template(
        'index.html',
        job_scrapes=job_dropdown,
        job_table_choice=table_choice,
        scraper_status=scraper_status,
        scraper_runtime=scraper_runtime
    )


@app.route('/display_jobs_set', methods=['POST'])
def displays_jobs_set():
    logging.info(request.form['dropdown'])
    cache.set("current_job_data_selection", request.form['dropdown'])
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

    class RestoreOptionsDropdown(FlaskForm):
        dropdown = SelectField('restores', choices=cache.get("restore_points"))

    scraper_status, scraper_runtime = check_scraper()
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
        scraper_status=scraper_status,
        scraper_runtime=scraper_runtime
    )


@app.route('/<date>')
def results(date):
    return render_template(str(date + '/index.html'))


@app.route('/<date>/<jobposting>')
def jobpost(date, jobposting):
    logging.info(date + '/' + jobposting)
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
            logging.info("failed to match these two")
            logging.info(data[k])
            logging.info(curr[k])
            changed = True
    if changed:
        logging.info("Customizations changed, saving to file")
        name = "customizations-" + str(int(time.time())) + ".yaml"
        ts = datetime.utcfromtimestamp(int(time.time())).strftime('%Y-%m-%d %H:%M:%S')
        rp = list(cache.get("restore_points"))
        rp.insert(0, (name, ts))
        cache.set("restore_points", rp)
        logging.info("Saving backup")
        save_customizations(os.path.join(customizations_backup_path, name))
        cache.set("customizations", data)
        logging.info("Saving new")
        save_customizations(customizations_path)
        cache.set("last_updated", ts)


def run_job_scraper():
    os.environ["SCRAPERRUNNING"] = "True"
    subprocess.run(['/usr/bin/python3',
                    '/app/job_scraper.py'
                    ])


if not schedule.running:
    logging.info("Starting the background scheduler")
    schedule.start()
    logging.info("Started")
    # today = datetime.today()
    # first_run = today + timedelta(days=1)
    # first_runtime = first_run.strftime("%y-%m-%d 05:00:00")
    # first_runtime_obj = datetime.strptime(first_runtime, "%y-%m-%d %H:%M:%S")
    # schedule.add_job(run_job_scraper,
    #                  'interval', hours=24, start_date=first_runtime_obj, end_date='2050-01-01 06:00:00'
    #                  )
    schedule.add_job(run_job_scraper, 'interval', hours=3)
    logging.info("Job added")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080)

# https://blog.jcharistech.com/2019/12/12/how-to-render-markdown-in-flask/
