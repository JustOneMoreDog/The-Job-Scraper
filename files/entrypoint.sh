#!/bin/bash

/usr/sbin/apachectl start
sudo -u hunter /usr/bin/python3 /app/job_scraper.py
