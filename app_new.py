from flask import Flask, render_template, request, jsonify
import os
import json
import psutil
import datetime

DEMO_STATE = True
app = Flask(__name__, template_folder='new_templates')

### HELPER FUNCTIONS ###

def get_scraper_status():
    is_running = False
    for proc in psutil.process_iter():
        is_python = '/usr/bin/python3' in proc.cmdline()
        is_job_scraper = 'job_scraper.py' in proc.cmdline()
        if is_python and is_job_scraper:
            is_running = True
            break

    running_time = None
    if is_running:
        log_dir = 'scraper_logs'
        latest_log = max(os.listdir(log_dir), key=os.path.getctime)  
        log_timestamp = datetime.datetime.strptime(latest_log.split('.')[0], '%m_%d_%Y_%H_%M_%S')
        running_time = datetime.datetime.now() - log_timestamp

    next_run_time = datetime.datetime.today().replace(hour=5, minute=0, second=0, microsecond=0)
    if next_run_time < datetime.datetime.now():
         next_run_time += datetime.timedelta(days=1)
    hours_until_next_run = (next_run_time - datetime.datetime.now()).seconds // 3600
    print(f"is_running: {is_running}, running_time: {running_time}, hours_until_next_run: {hours_until_next_run}")
    return is_running, running_time, hours_until_next_run

def get_job_scrape_dates() -> list:
    # Find dates from job scrape files
    job_scrape_dir = '.job_scrapes'
    all_scrape_dates = []
    for filename in os.listdir(job_scrape_dir):
        if not filename.endswith('.json'):
            continue
        file_date_str = filename.split('.')[0]  # Get the timestamp part
        try:
            file_date = datetime.datetime.strptime(file_date_str, '%m_%d_%Y_%H_%M_%S')
            all_scrape_dates.append(file_date.strftime('%m-%d-%Y'))
        except ValueError:
            pass
    scrape_dates = list(set(all_scrape_dates))
    scrape_dates.sort(reverse=True)
    return scrape_dates

def get_job_scrape_filename(date_str: str) -> str:
    job_scrape_dir = '.job_scrapes'
    json_filename = None
    for scrape in os.listdir(job_scrape_dir):
        if date_str in scrape:
            json_filename = scrape
    return json_filename

def get_latest_job_scrape_data(latest_date: str) -> list:
    if latest_date:
        json_filename = get_job_scrape_filename(latest_date)
        with open(os.path.join('.job_scrapes', json_filename), 'r') as f:
            latest_data = json.load(f)
    else:
        latest_data = []
    return latest_data

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
    job_scrape_dir = '.job_scrapes'
    file_date_str = selected_date.replace('-', '_')
    json_filename = get_job_scrape_filename(file_date_str)
    if not json_filename:
        return jsonify({'error': 'Data for the selected date not found.'})
    json_filepath = os.path.join(job_scrape_dir, json_filename)
    with open(json_filepath, 'r') as f:
        data = json.load(f)
        return jsonify(data)

if __name__ == '__main__':
    app.run(host="127.0.0.1", port=9090)
