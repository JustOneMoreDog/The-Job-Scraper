import json
import os
import re
from job_scraper import JobPosting
import yaml


def rate_jobs():
    pass


def iterate_through_scrapes(func):
    scrapes = []
    job_scrape_dir = 'scrapes'
    for scrape in os.listdir(job_scrape_dir):
        filepath = os.path.join(job_scrape_dir, scrape)
        if filepath == "scrapes/.keep":
                continue
        scrapes.append(filepath)
    scrapes.sort()
    for filepath in scrapes:
        with open(filepath, 'r') as f:
            job_data = json.load(f)
            for job in job_data:
                func(job)

iterate_through_scrapes(rate_jobs)
