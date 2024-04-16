import os
import json

scrapes = []
all_jobs = []
job_scrape_dir = 'scrapes'
for scrape in os.listdir(job_scrape_dir):
    filepath = os.path.join(job_scrape_dir, scrape)
    if filepath == "scrapes/.keep":
            continue
    scrapes.append(filepath)
scrapes.sort()
for filepath in scrapes:
    new_scrape_data = []
    duplicates_in_scrape = 0
    with open(filepath, 'r') as f:
        job_data = json.load(f)
        for job in job_data:
            all_jobs.append(job)
with open("all_jobs.json", 'w') as f:
    json.dump(all_jobs, f)
