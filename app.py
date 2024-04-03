import json
import logging
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta
from threading import Thread

import psutil
from psutil import NoSuchProcess, AccessDenied, ZombieProcess
import yaml
from apscheduler.executors.pool import ProcessPoolExecutor, ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template, request
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

DEMO_STATE = True
DEBUG_MODE = True
WORKING_DIR = os.path.dirname(os.path.realpath(__file__))
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
        
def run_job_scraper():
    virtual_env_path = os.path.abspath(os.path.join(WORKING_DIR, 'virtualenv/bin/python'))
    job_scraper_path = os.path.abspath(os.path.join(WORKING_DIR, 'job_scraper.py'))
    subprocess.run([virtual_env_path, job_scraper_path])

def close_observers(obs):
    for observer, observer_thread in obs:
        observer.stop()
        observer_thread.join()
        
def setup_log_watcher(log_directory: str, symlink_path: str) -> tuple[BaseObserver, Thread]:
    event_handler = LogWatcher(symlink_path)
    observer = Observer()
    observer.schedule(event_handler, log_directory, recursive=False)
    observer_thread = threading.Thread(target=observer.start)
    observer_thread.start()
    return observer, observer_thread

def setup_watchdogs() -> list[tuple[BaseObserver, Thread]]:
    observers = []
    for dir in os.listdir("logs"):
        log_directory = os.path.abspath(os.path.join(WORKING_DIR, "logs", dir))
        if not os.path.isdir(log_directory) or dir == "latest":
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
    
    logs_directory = os.path.abspath(os.path.join(WORKING_DIR, "logs", "flask"))
    log_filename = datetime.now().strftime("%m_%d_%Y_%H_%M") + ".log"
    log_filepath = os.path.join(logs_directory, log_filename)
    logging.basicConfig(filename=log_filepath, level=logging.INFO, filemode="w")
    logging.info("Logging has been setup for flask")

def get_scraper_status():
    is_running = False
    for proc in psutil.process_iter():
        try:
            is_python = '/usr/bin/python3' in proc.cmdline()
            is_job_scraper = 'job_scraper.py' in proc.cmdline()
            if is_python and is_job_scraper:
                is_running = True
                break
        except (NoSuchProcess, AccessDenied, ZombieProcess):
            pass

    running_time = None
    if is_running:
        log_dir = 'scraper_logs'
        latest_log = max(os.listdir(log_dir), key=os.path.getctime)  
        log_timestamp = datetime.strptime(latest_log.split('.')[0], '%m_%d_%Y_%H_%M_%S')
        running_time = datetime.now() - log_timestamp

    next_run_time = datetime.today().replace(hour=5, minute=0, second=0, microsecond=0)
    if next_run_time < datetime.now():
         next_run_time += timedelta(days=1)
    hours_until_next_run = (next_run_time - datetime.now()).seconds // 3600
    return is_running, running_time, hours_until_next_run

def get_job_scrape_dates() -> list:
    # Find dates from job scrape files
    job_scrape_dir = 'scrapes'
    all_scrape_dates = []
    for filename in os.listdir(job_scrape_dir):
        if not filename.endswith('.json'):
            continue
        file_date_str = filename.split('.')[0]  # Get the timestamp part
        try:
            file_date = datetime.strptime(file_date_str, '%m_%d_%Y_%H_%M')
            all_scrape_dates.append(file_date.strftime('%m-%d-%Y-%H-%M'))
        except ValueError:
            pass
    scrape_dates = list(set(all_scrape_dates))
    scrape_dates.sort(reverse=True)
    return scrape_dates

def get_job_scrape_filename(date_str: str) -> str:
    job_scrape_dir = 'scrapes'
    json_filename = None
    for scrape in os.listdir(job_scrape_dir):
        if date_str in scrape:
            json_filename = scrape
    return json_filename

def get_latest_job_scrape_data(latest_date: str) -> list:
    if latest_date:
        json_filename = get_job_scrape_filename(latest_date)
        with open(os.path.join('scrapes', json_filename), 'r') as f:
            latest_data = json.load(f)
    else:
        latest_data = []
    return latest_data

def load_customizations():
    customization_data = {}
    with open('customizations.yaml', 'r') as f:
        customization_data = yaml.safe_load(f)
    return customization_data

### FLASK ROUTES ###

@app.route('/', methods=['GET'])
def index():
    is_running, running_time, hours_until_next_run = get_scraper_status()
    posting_dates = get_job_scrape_dates()
    latest_date = posting_dates[0].replace('-', '_') if posting_dates else None
    latest_data = get_latest_job_scrape_data(latest_date)
    return render_template(
        'index.html',
        demo_state=DEMO_STATE,
        is_running=is_running,
        running_time=running_time,
        hours_until_next_run=hours_until_next_run,
        posting_dates=posting_dates,
        latest_date=latest_date,
        latest_data=latest_data
    )

@app.route('/get_job_data', methods=['POST']) 
def get_job_data():
    if not request.method == 'POST':
        return jsonify({'error': 'Invalid request method'})
    selected_date = request.form['date']
    job_scrape_dir = 'scrapes'
    file_date_str = selected_date.replace('-', '_')
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
    return render_template('customizations.html', data=customization_data)

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
    first_runtime = first_run.strftime("%y-%m-%d 03:00:00")
    first_runtime_obj = datetime.strptime(first_runtime, "%y-%m-%d %H:%M:%S")
    schedule.add_job(
        run_job_scraper,
        'interval',
        hours=24,
        start_date=first_runtime_obj,
        end_date='2050-01-01 06:00:00'
    )
    logging.info("Job added")
except Exception as e:
    close_observers(observers)
    raise e

if __name__ == '__main__':
    try:
        app.run(host="127.0.0.1", port=9090)
    except Exception as e:
        logging.exception(e)
    finally:
        close_observers(observers)
