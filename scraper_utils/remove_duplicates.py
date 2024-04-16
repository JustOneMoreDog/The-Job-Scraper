import os
import json

def is_a_duplicate(job_posting_url: str, all_jobs: list[dict]):
    if not job_posting_url:
        return True
    split_newly_found_job_url = job_posting_url.split("/view/")
    if len(split_newly_found_job_url) != 2:
        return True
    newly_found_job_url = split_newly_found_job_url[1].lower()
    for job in all_jobs:
        previously_found_job_url = job['url'].split("/view/")[1].lower()
        duplicate_job_posting_url = previously_found_job_url == newly_found_job_url
        if duplicate_job_posting_url:
            return True
    return False

total_duplicates = 0
scrapes = []
all_jobs = []
job_scrape_dir = 'scrapes'
for scrape in os.listdir(job_scrape_dir):
    filepath = os.path.join(job_scrape_dir, scrape)
    if filepath == "scrapes/.keep":
            continue
    scrapes.append(filepath)
scrapes.sort()
print(scrapes)
for filepath in scrapes:
    new_scrape_data = []
    duplicates_in_scrape = 0
    with open(filepath, 'r') as f:
        job_data = json.load(f)
        for job in job_data:
            if not job["url"]:
                continue
            if is_a_duplicate(job["url"], all_jobs):
                total_duplicates += 1
                duplicates_in_scrape += 1
                continue
            all_jobs.append(job)
            new_scrape_data.append(job)
    print(f"Total duplicates found in {filepath}: {duplicates_in_scrape}")
    with open(filepath, 'w') as f:
        json.dump(new_scrape_data, f)
print(f"Total duplicates found: {total_duplicates}")
with open("all_jobs.json", 'w') as f:
    json.dump(all_jobs, f)
