This is in Beta. Will continue to add documentation, fixes, and features as I test this.

# LinkedIn Job Scraper

Thank you to the GitHub user Hrissimir and their [scrape_jobs repository](https://github.com/Hrissimir/scrape_jobs) as I was able to use that as a starting point for this project.

## Description 

This script will search LinkedIn using user provided phrases, limit it to the past week, limit it to a location, grab the desired amount of job postings, remove previously found job postings, rate the postings based on where the job is and if there are any keywords in the description, and then save the report to an Excel file.

All the above features can be configured in the `config.yaml` file. This script is designed to be your companion during your job search. Since you can control all the filters, you should be adjusting those filters after each generated report. In the instructions below I will show you how to set this script up to run daily.

## Installing Dependencies