# LinkedIn Job Scraper

Thank you to the GitHub user Hrissimir and their [scrape_jobs repository](https://github.com/Hrissimir/scrape_jobs) as I was able to use their proof of concept as the starting point for this project.

## Description 

This script will search LinkedIn using user provided phrases, limit it to a certain timeframe, limit it to a location, limit to certain experience levels, limit to remote jobs only if desired, then grab the desired amount of job postings, remove previously found job postings, remove jobs that are either in an undesired location or are from an undesired company, rate the postings based on weights set by the user, and then save the report in an HTML format to a web directory.

All the above features can be configured in the `customizations.yaml` file. This script is designed to be your companion during your job search. Since you can control all the filters, you should be adjusting those filters after each generated report. In the instructions below I will show you how to set this script up to run daily.


## Installing Dependencies

```
# Making sure our system is up to date
sudo apt update -y && sudo apt upgrade -y 

# Installing Chrome
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
rm -f google-chrome-stable_current_amd64.deb

# Getting the Chrome driver for Selenium
wget https://chromedriver.storage.googleapis.com/90.0.4430.24/chromedriver_linux64.zip
unzip chromedriver_linux64.zip
sudo mv chromedriver /usr/local/bin/chromedriver
rm -f chromedriver_linux64.zip

# Cloning the repository and installing dependencies
git clone https://github.com/picnicsecurity/LinkedIn-Job-Scraper.git
cd LinkedIn-Job-Scraper
python3 -m pip install -r requirements.txt
```

## Setting Up Cron

I personally use cron to setup daily runs of this in the morning. The code takes about an hour and half on average to finish running. This is mainly due to LinkedIn constantly trying to prevent bots like mine. Their protection only gets more aggressive if I do not sleep for a bit after being detected. Having it run at 5am every morning means that I am never waiting on it to finish. By the time I wake up and browse to the web server, it is done scraping and has a report for me.

```
SHELL=/bin/bash
PATH=/home/sandwich/.local/bin:/sbin:/bin:/usr/bin:/usr/local/bin:/snap/bin
0 5 * * * cd /home/sandwich/PycharmProjects/jobhunter/ && /usr/bin/python3 /home/sandwich/PycharmProjects/jobhunter/main.py 2>&1
```

## To-Do

Turn this into a container. Would be nice.