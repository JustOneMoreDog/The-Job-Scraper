import logging
import logging.handlers
import os
import psutil
import re
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
from forms import SearchTermsForm, MinJobsForm, LocationsForm, ExcludedIndustries, ExcludedLocationsForm, \
    ExcludedCompanies, WordWeightForm, SubmitButton, ExcludedTitles
from wtforms import SelectField
import platform
import os


app_config = {
    "SECRET_KEY": "wearenotreallykeepingsecretssowhatever",
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 0,
    "CACHE_DIR": "/app/cache/"
}
app = Flask(__name__)
app.config.from_mapping(app_config)
cache = Cache(app)
working_directory = "C:\\Users\\Name\\Documents\\GitHub\\The-Job-Scraper\\files" if platform.system() == 'Windows' else "/app"
customizations_path = os.path.join(working_directory, "customizations.yaml")
customizations_backup_path = os.path.join(working_directory, "customizations_backups")


def init_logging() -> None:
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


def save_customizations(path) -> None:
    with open(path, "w") as f:
        yaml.dump(cache.get("customizations"), f)


def load_customizations(path) -> None:
    with open(path, "r") as f:
        cache.set("customizations", yaml.load(f, Loader=yaml.FullLoader))


def get_job_scrapes() -> list:
    job_data_list = []
    templates_directory = os.path.join(working_directory, 'templates')
    for x in os.listdir(templates_directory):
        if os.path.isdir(os.path.join('/app/templates', x)) and x != 'Welcome Page':
            job_data_list.append(x)
    job_data_list.sort(reverse=True)
    job_data_list.append('Welcome Page')
    return job_data_list


def clear_input_validation_checks() -> None:
    customization_errors = dict()
    for k in dict(cache.get("customizations")).keys():
        customization_errors[k] = False
    cache.set("customizations_errors", customization_errors)


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
# Setting the input validation cache values
cache.set("customizations_errors", False)
clear_input_validation_checks()

executors = {
    'default': ThreadPoolExecutor(16),
    'processpool': ProcessPoolExecutor(4)
}
schedule = BackgroundScheduler(timezone='America/New_York', executors=executors)


def check_scraper() -> dict:
    is_running = [proc.cmdline() for proc in psutil.process_iter()
                  if '/usr/bin/python3' in proc.cmdline() and '/app/job_scraper.py' in proc.cmdline()
                  ]
    if datetime.today().hour > 5:
        hours_until = 24 - datetime.today().hour + 5
    elif datetime.today().hour < 5:
        hours_until = (-1 * datetime.today().hour) + 5
    else:
        hours_until = 0
    if is_running:
        logging.info("Job Scraper is currently running")
        x = os.listdir("/app/flask_logs/")
        x.sort()
        runtime = str(timedelta(seconds=(int(time.time()) - int(x[-1].split(".")[0]))))
        return {
            'status': "Running",
            'runtime': runtime,
            'hours': hours_until
        }
    else:
        return {
            'status': "Stopped",
            'runtime': "0:00:00",
            'hours': hours_until
        }


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
        curr_scrape_list.remove('Welcome Page') if 'Welcome Page' in curr_scrape_list else None
        new_job_list = sorted(set(curr_scrape_list))
        new_job_list.reverse()
        new_job_list.insert(0, curr_scrape_selection)
        new_job_list.append('Welcome Page')
        cache.set("job_data_list", new_job_list)

    job_dropdown = JobDataDropdown()
    job_dropdown.dropdown.choices = new_job_list if new_job_list else curr_scrape_list
    table_choice = job_dropdown.dropdown.choices[0] + "/index.html"
    scraper_status = check_scraper()
    return render_template(
        'index.html',
        job_scrapes=job_dropdown,
        job_table_choice=table_choice,
        scraper_status=scraper_status
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
    excluded_industries_data = getFormData('excluded_industries_label', 'excluded_industries', customizations)
    keyword_form_data = getFormData('keyword_label', 'word_weights', customizations)

    # Now we check if there are any input validation errors
    error_check = bool(cache.get("customizations_errors"))
    customizations_errors = dict(cache.get("customizations_errors"))
    if error_check:
        # Since we have everything already pulled out we can reset the errors and pass the dict to jinja
        clear_input_validation_checks()

    class RestoreOptionsDropdown(FlaskForm):
        dropdown = SelectField('restores', choices=cache.get("restore_points"))

    scraper_status = check_scraper()
    return render_template(
        'customizations.html',
        searchTerms=SearchTermsForm(data=search_form_data),
        minEntries=MinJobsForm(data=min_jobs_form_data),
        locations=LocationsForm(data=location_form_data),
        experiences=experience_form_data,
        excluded_locations=ExcludedLocationsForm(data=excluded_location_form_data),
        excluded_companies=ExcludedCompanies(data=excluded_org_form_data),
        excluded_titles=ExcludedTitles(data=excluded_title_data),
        keyword_weights=WordWeightForm(data=keyword_form_data),
        confirm_button=SubmitButton(),
        last_updated=cache.get("last_updated"),
        restore_points=RestoreOptionsDropdown(),
        excluded_industries=ExcludedIndustries(data=excluded_industries_data),
        scraper_status=scraper_status,
        customizations_errors=customizations_errors
    )


@app.route('/<date>/<job_posting>')
def job_posting_content(date, job_posting):
    logging.info("User is looking at the content for %s" % (date + '/' + job_posting))
    return render_template(date + '/' + job_posting + '/content.html')


def getFormData(html_label, yaml_label, customizations):
    search_term = namedtuple('Terms', [html_label])
    data = {'rows': []}
    if html_label == "min_jobs_label":
        data['rows'].append(search_term(str(customizations[yaml_label])))
        return data
    if html_label == "experience_level_label":
        data = {}
        for k, v in customizations[yaml_label].items():
            if v:
                data[k] = "<input type='checkbox' value=\"" + k + "\" name='explvl' checked>"
            else:
                data[k] = "<input type='checkbox' value=\"" + k + "\" name='explvl'>"
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
        'excluded_industries': [],
        'word_weights': {}
    }
    curr_kw = ''
    for k, v in r.form.items():
        if not v or not k:
            continue
        elif 'search_term' in k:
            data['searches'].append(str(v).strip())
        elif 'min_jobs' in k:
            data['minimum_jobs_per_search'] = str(v)
        elif '-location' in k:
            data['locations'].append(str(v).strip())
        elif 'exclude_location' in k:
            data['excluded_locations'].append(str(v).strip())
        elif 'excluded_org' in k:
            data['excluded_companies'].append(str(v).strip())
        elif 'excluded_industries' in k:
            data['excluded_industries'].append(str(v).strip())
        elif 'excluded_titles' in k:
            data['excluded_title_keywords'].append(str(v).strip())
        elif 'keyword' in k or 'weight' in k:
            if int(str(k).split("-")[1]) % 2 == 0:
                curr_kw = str(v).strip()
                continue
            data['word_weights'][curr_kw] = str(v).strip()
    for exp in ['Internship', 'Entry level', 'Associate', 'Mid-Senior level', 'Director']:
        data['experience_levels'][exp] = True if exp in r.form.getlist('explvl') else False
    # Now we verify if the data is valid
    invalid_data = False
    pattern = re.compile(r'^[\sa-zA-Z0-9-,]+$')
    customizations_errors = dict(cache.get("customizations_errors"))
    for k, v in data.items():
        message = ""
        needs_error_element = False
        if not v:
            invalid_data = True
            needs_error_element = True
            message = "You must specify at least one value"
        elif type(v) == list:
            for entry in v:
                if not re.search(pattern, entry):
                    invalid_data = True
                    needs_error_element = True
                    message = "Entries must only contain letters, numbers, dashes, and commas"
                    break
        elif k == 'word_weights':
            for l, w in v.items():
                if not re.search(pattern, l):
                    invalid_data = True
                    needs_error_element = True
                    message = "Entries must only contain letters, numbers, dashes, and commas"
                    break
                if (w[0] == "-" and w[1:].isnumeric()) or (w[0] != "-" and w.isnumeric()):
                    # Once we have confirmed that it is either a positive or negative number we make it an int
                    data[k][l] = int(w)
                else:
                    invalid_data = True
                    needs_error_element = True
                    message = "Weights must be either a positive or negative number"
                    break
        elif k == 'minimum_jobs_per_search':
            if v.isnumeric() and int(v) > 0:
                data[k] = int(v)
            else:
                invalid_data = True
                needs_error_element = True
                message = "This must be a positive number greater than 0"
        elif k == 'experience_levels':
            # If none of the checkboxes are checked then all the values will be false
            if all(not x for x in v.values()):
                invalid_data = True
                needs_error_element = True
                message = "At least one experience level must be checked"
        if needs_error_element:
            logging.error("%s has incorrect values" % k)
            html_error_element = "<p style=\"color:red;\"><b>" + message + "</b></p><br>"
            customizations_errors[k] = html_error_element
            continue
    # end validation check for loop
    # TO-DO:
    # Instead of clearing everything the user did because they did not do one field correctly
    # lets just make it appear as if it saved when it did not
    # put a message at the top saying something like, "changes have not been saved. See below for errors"
    if invalid_data:
        cache.set("customizations_errors", invalid_data)
        cache.set("customizations_errors", customizations_errors)
        return
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
    subprocess.run(['/usr/bin/python3', '/app/job_scraper_new.py'])


if not schedule.running:
    logging.info("Starting the background scheduler")
    schedule.start()
    logging.info("Started")
    today = datetime.today()
    first_run = today + timedelta(days=1)
    first_runtime = first_run.strftime("%y-%m-%d 05:00:00")
    first_runtime_obj = datetime.strptime(first_runtime, "%y-%m-%d %H:%M:%S")
    schedule.add_job(
        run_job_scraper,
        'interval',
        hours=24,
        start_date=first_runtime_obj,
        end_date='2050-01-01 06:00:00'
    )
    logging.info("Job added")


if __name__ == '__main__':
    app.run(host="127.0.0.1", port=8080)
