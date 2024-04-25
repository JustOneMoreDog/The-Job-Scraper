import json
import logging
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta
from threading import Thread
from ansi2html import Ansi2HTMLConverter

import psutil
import yaml
from apscheduler.executors.pool import ProcessPoolExecutor, ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template, request
from psutil import AccessDenied, NoSuchProcess, ZombieProcess
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

DEMO_STATE = False
DEBUG_MODE = True
WORKING_DIR = os.path.dirname(os.path.realpath(__file__))
JOB_SCRAPER_RUNNING = False
app = Flask(__name__)


class LogWatcher(FileSystemEventHandler):
    """Watches our log directories for new log files/screenshots and then creates a symlink to the latest ones."""
    def __init__(self, symlink_path):
        self.symlink_path = symlink_path
    
    def on_created(self, event: FileSystemEvent):
        if event.is_directory:
            return
        new_log_entry = os.path.abspath(event.src_path)
        if os.path.basename(new_log_entry) == self.symlink_path:
            return
        # Remove existing symlink if it exists
        if os.path.islink(self.symlink_path):
            os.unlink(self.symlink_path)
        # Create new symlink with absolute paths
        logging.info(f"Creating symlink for {new_log_entry}")
        os.symlink(src=new_log_entry, dst=self.symlink_path, target_is_directory=False)

### HELPER FUNCTIONS ###
        
def run_job_scraper(retry: bool = True) -> None:
    global JOB_SCRAPER_RUNNING
    JOB_SCRAPER_RUNNING = True
    timeout = 28800  # 8 hours
    scraper_had_issues = False
    virtual_env_path = os.path.abspath(os.path.join(WORKING_DIR, 'virtualenv/bin/python'))
    job_scraper_path = os.path.abspath(os.path.join(WORKING_DIR, 'job_scraper.py'))
    job_scraper = subprocess.Popen([virtual_env_path, job_scraper_path])
    start_time = time.time()
    while time.time() - start_time < timeout and job_scraper.poll() is None:
        time.sleep(300)
    if job_scraper.poll() is None:
        logging.info("Job scraper has been running for over 4 hours. Killing the process.")
        scraper_had_issues = True
    elapsed_time = time.gmtime(int(time.time()) - int(start_time))
    formatted_runtime = time.strftime("%H:%M:%S", elapsed_time)
    logging.info(f"Job scraper ran for {formatted_runtime}")
    kill_the_parents_and_children(job_scraper.pid)
    kill_chrome_processes()
    logging.info("Killed the parent and child processes")
    JOB_SCRAPER_RUNNING = False
    if retry and scraper_had_issues:
        logging.info("Sleeping for one hour and then retrying the job scraper one more time")
        time.sleep(3600)
        run_job_scraper(retry=False)
    return

def kill_the_parents_and_children(parent_pid):
    try:
        parent = psutil.Process(parent_pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except (NoSuchProcess, AccessDenied, ZombieProcess):
                pass
        parent.kill()
    except (NoSuchProcess, AccessDenied, ZombieProcess):
        pass

def kill_chrome_processes():
    for proc in psutil.process_iter():
        try:
            if "chrome" in proc.name() or "undetected" in proc.name():
                kill_the_parents_and_children(proc.pid)
        except (NoSuchProcess, AccessDenied, ZombieProcess):
            pass

def close_observers(obs):
    for observer, observer_thread in obs:
        observer.stop()
        observer_thread.join()
        
def setup_log_watcher(log_directory: str, symlink_path: str):
    event_handler = LogWatcher(symlink_path)
    observer = Observer()
    observer.schedule(event_handler, log_directory, recursive=False)
    observer_thread = threading.Thread(target=observer.start)
    observer_thread.start()
    return observer, observer_thread

def setup_watchdogs() -> list:
    observers = []
    for dir in os.listdir("logs"):
        log_directory = os.path.abspath(os.path.join(WORKING_DIR, "logs", dir))
        if not os.path.isdir(log_directory) or dir == "latest" or dir == "debug_data":
            continue
        extension = ".log"
        if dir == "screenshots":
            extension = ".png"
        symlink_path = os.path.abspath(os.path.join(WORKING_DIR, "logs", "latest", dir + extension))
        observer, observer_thread = setup_log_watcher(log_directory, symlink_path)
        observers.append((observer, observer_thread))    
    return observers

def setup_logging():
    """Sets up the logging for the project."""

    class WatchdogFilter(logging.Filter):
        """Filter to prevent the Watchdog library from spamming the logs."""
        def filter(self, record):
            if "InotifyEvent" in record.getMessage():
                return 0
            return 1
    
    while True:
        logs_directory = os.path.abspath(os.path.join(WORKING_DIR, "logs", "flask"))
        log_filename = datetime.now().strftime("%m_%d_%Y_%H_%M_%S") + ".log"
        log_filepath = os.path.join(logs_directory, log_filename)
        if not os.path.exists(log_filepath):
            logging.basicConfig(filename=log_filepath, level=logging.INFO, filemode="w")
            break
        time.sleep(1)
        continue
    logging.info("Logging has been setup for flask")

def get_scraper_status():
    running_time = None
    if JOB_SCRAPER_RUNNING:
        log_dir = os.path.abspath(os.path.join(WORKING_DIR, 'logs/scraper'))
        latest_log = max(os.listdir(log_dir), key=os.path.getctime)  
        log_timestamp = datetime.strptime(latest_log.split('.')[0], '%m_%d_%Y_%H_%M_%S')
        running_time = datetime.now() - log_timestamp

    next_run_time = datetime.today().replace(hour=5, minute=0, second=0, microsecond=0)
    if next_run_time < datetime.now():
         next_run_time += timedelta(days=1)
    hours_until_next_run = (next_run_time - datetime.now()).seconds // 3600
    return JOB_SCRAPER_RUNNING, running_time, hours_until_next_run

def get_job_scrape_dates() -> list:
    # Find dates from job scrape files
    job_scrape_dir = 'scrapes'
    all_scrape_dates = []
    for filename in os.listdir(job_scrape_dir):
        if not filename.endswith('.json'):
            continue
        file_date_str = filename.split('.')[0]
        try:
            file_date = datetime.strptime(file_date_str, '%m_%d_%Y_%H_%M')
            all_scrape_dates.append(file_date.strftime('%m-%d-%Y-%H-%M'))
        except ValueError:
            pass
    scrape_dates = list(set(all_scrape_dates))
    scrape_dates.sort(reverse=True)
    scrape_dates.append("Past Day")
    scrape_dates.append("Past Week")
    scrape_dates.append("Past Month")
    scrape_dates.append("All Jobs")
    return scrape_dates

def get_job_scrape_filename(date_str: str) -> str:
    job_scrape_dir = 'scrapes'
    json_filename = None
    for scrape in os.listdir(job_scrape_dir):
        if date_str in scrape:
            json_filename = scrape
    return json_filename

def load_customizations() -> dict:
    customization_data = {}
    with open('customizations.yaml', 'r') as f:
        customization_data = yaml.safe_load(f)
    return customization_data

### FLASK ROUTES ###

@app.route('/', methods=['GET'])
def index():
    is_running, running_time, hours_until_next_run = get_scraper_status()
    posting_dates = get_job_scrape_dates()
    latest_date = posting_dates[0]
    return render_template(
        'index.html',
        demo_state=DEMO_STATE,
        is_running=is_running,
        running_time=running_time,
        hours_until_next_run=hours_until_next_run,
        posting_dates=posting_dates,
        latest_date=latest_date
    )

@app.route('/get_job_data', methods=['POST']) 
def get_job_data():
    if not request.method == 'POST':
        return jsonify({'error': 'Invalid request method'})
    selected_date = request.form['date']
    job_scrape_dir = 'scrapes'
    file_date_str = selected_date.replace('-', '_').replace(' ', '_').lower()
    json_filename = get_job_scrape_filename(file_date_str)
    if not json_filename:
        return jsonify({'error': 'Data for the selected date not found.'})
    json_filepath = os.path.join(job_scrape_dir, json_filename)
    with open(json_filepath, 'r') as f:
        data = json.load(f)
        return jsonify(data)
    
@app.route('/customizations')
def customizations():
    customization_data = load_customizations()
    return render_template('customizations.html', data=customization_data, demo_state=DEMO_STATE)

@app.route('/save_customizations', methods=['POST'])
def save_customizations():
    if request.method != 'POST':
        return jsonify({'error': 'Invalid request method'})
    new_customizations_data = request.get_json()
    customization_data = load_customizations()
    customizations_filename = 'customizations_' + str(int(time.time())) + '.yaml'
    customizations_backup_path = os.path.abspath(os.path.join('customizations_backups', customizations_filename))
    with open(customizations_backup_path, 'x') as f:
        yaml.dump(customization_data, f)
    with open('customizations.yaml', 'w') as f:
        yaml.dump(new_customizations_data, f)
    return jsonify({'status': 'success'})

@app.route('/logs/latest/<path:filename>', methods=['GET'])
def get_latest_log(filename):
    # TO-DO: Add support for screenshot.png
    if request.method != 'GET':
        return jsonify({'error': 'Invalid request method'})
    if not filename:
        return jsonify({'error': 'Log name required'})
    log_dir = os.path.join(WORKING_DIR, "logs/latest")
    match filename:
        case 'flask.log':
            latest_log_path = os.path.join(log_dir, 'flask.log')
        case 'scraper.log':
            latest_log_path = os.path.join(log_dir, 'scraper.log')
        case _:
            return jsonify({'error': 'Unsupported log file'})
    with open(latest_log_path, 'r') as f:
        data = f.read()
    ansi_converter = Ansi2HTMLConverter(font_size="x-large")
    html_data = ansi_converter.convert(data)
    return html_data

@app.route('/applications')
def applications():
    return render_template('applications.html')

@app.route('/statistics')
def statistics():
    return render_template('statistics.html')

### MAIN ###

observers = []
try:
    observers = setup_watchdogs()
    time.sleep(1)
    setup_logging()
    logging.info("Starting the background scheduler")
    executors = {
        'default': ThreadPoolExecutor(16),
        'processpool': ProcessPoolExecutor(4)
    }
    schedule = BackgroundScheduler(timezone='America/New_York', executors=executors)
    schedule.start()
    logging.info("Started")
    today = datetime.today()
    first_run = today + timedelta(days=1)
    first_runtime = first_run.strftime("%y-%m-%d 01:00:00")
    first_runtime_obj = datetime.strptime(first_runtime, "%y-%m-%d %H:%M:%S")
    schedule.add_job(
        run_job_scraper,
        'interval',
        hours=24,
        start_date=first_runtime_obj,
        end_date='2050-01-01 02:00:00',
        id='job_scraper'
    )
    logging.info("Job added")
except Exception as e:
    close_observers(observers)
    raise e

if __name__ == '__main__':
    try:
        config = {}
        with open('server_config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        app.run(host=config['flask_ip_address'], port=config['flask_port'], debug=config['flask_debug_mode'])
    except Exception as e:
        logging.exception(e)
    finally:
        close_observers(observers)
