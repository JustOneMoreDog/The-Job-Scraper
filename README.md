This is in Beta. Will continue to add documentation, fixes, and features as I test this.

# LinkedIn Job Scraper

Thank you to the GitHub user Hrissimir and their [scrape_jobs repository](https://github.com/Hrissimir/scrape_jobs) as I was able to use their proof of concept as the starting point for this project.

## Description 

This script will search LinkedIn using user provided phrases, limit it to the past week, limit it to a location, grab the desired amount of job postings, remove previously found job postings, rate the postings based on where the job is and if there are any keywords in the description, and then save the report to an Excel file.

All the above features can be configured in the `config.yaml` file. This script is designed to be your companion during your job search. Since you can control all the filters, you should be adjusting those filters after each generated report. In the instructions below I will show you how to set this script up to run daily.

For a detailed usage guide on this script and to see how I have used it for my job hunt check out my

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

