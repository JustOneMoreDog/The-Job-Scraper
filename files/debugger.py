from hed_utils.selenium import SharedDriver, chrome_driver, FindBy
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from datetime import datetime
from typing import Dict, Any
from bs4 import BeautifulSoup
import selenium.common.exceptions
import time
import requests
import logging
import logging.handlers
import json
import os
import yaml
from xlsxwriter import Workbook
from tabulate import tabulate


# Utility Functions
def load_yaml_data(filepath) -> dict:
    with open(filepath, "r") as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def load_json_data(filepath) -> dict:
    with open(filepath, "r") as f:
        return json.load(f)


def wait_and_sleep(shared_driver):
    shared_driver.wait_for_page_load()
    time.sleep(.75)


def send_tab_enter(e):
    ActionChains(driver).move_to_element(e).send_keys(Keys.TAB).send_keys(Keys.ENTER).perform()


def parse(tag, config) -> Dict[str, Any]:
    job = {key: None for key in ["posted_time", "location", "title", "company", "url"]}
    x = None
    x = tag.find('time')
    if x:
        job["posted_time"] = x.attrs['datetime']
    x = tag.find('span', class_=config["job_location"])
    if x:
        job["location"] = str(x.text).strip()
    x = tag.find('h3')
    if x:
        job["title"] = str(x.text).strip()
    x = tag.find('h4')
    if x:
        job["company"] = str(x.text).strip()
    x = tag.findNext('a')
    if x:
        url = str(x.attrs['href']).strip()
        job["url"] = url[:url.index("?")] if ("?" in url) else url
    return job


config = {**load_yaml_data("config.yaml"), **load_yaml_data("customizations.yaml")}
searches = config['searches']
location = config['locations']
max_jobs = config['minimum_jobs_per_search']
excluded_locations = config['excluded_locations']
excluded_companies = config['excluded_companies']
excluded_title_keywords = config['excluded_title_keywords']
word_weights = config['word_weights']
driver = chrome_driver.create_instance(headless=False)
driver.set_page_load_timeout(config['timeout'])
all_jobs = load_json_data("all_jobs.json") or []

search = searches[0]

# Here is where the scraping begins
driver.get('https://www.linkedin.com/jobs')
SharedDriver.set_instance(driver)
SharedDriver().wait_for_page_load()
wait_and_sleep(SharedDriver())

# Typing in our search
keywords_input = FindBy.NAME("keywords", visible_only=True)
keywords_input.click()
keywords_input.send_keys(search + Keys.ENTER)
wait_and_sleep(SharedDriver())

# Defining our location
location_input = FindBy.NAME("location", visible_only=True)
location_input.click()
location_input.clear()
location_input.send_keys(location + Keys.ENTER)
wait_and_sleep(SharedDriver())

# Limiting our search results to the past week
driver.find_elements_by_xpath(config['any_time_button'])[0].click()
driver.find_elements_by_xpath(config['past_week_button'])[0].click()
time.sleep(.5)
send_tab_enter(driver.find_elements_by_xpath(config['past_week_button'])[0])
wait_and_sleep(SharedDriver())

# Limiting our search to full time positions
driver.find_elements_by_xpath(config['job_type_button'])[0].click()
driver.find_elements_by_xpath(config['full_time_button'])[0].click()
time.sleep(.5)
for b in driver.find_elements_by_xpath(config['done_button']):
    if "done" in b.text.lower():
        b.click()
        break
wait_and_sleep(SharedDriver())

# Limiting our Experience level to only certain levels
driver.find_elements_by_xpath(config['more_filters_button'])[0].click()
time.sleep(.25)
driver.find_elements_by_xpath(config['exp_level_button'])[0].click()
time.sleep(.25)
for job_level in driver.find_elements_by_xpath(config['ul_li_filter_list']):
    if any(x for x in [y for y in config['experience_levels'].keys() if config['experience_levels'][y]] if
           x.lower() in job_level.text.lower()):
        job_level.click()
time.sleep(.25)
for b in driver.find_elements_by_xpath(config['done_button']):
    if "done" in b.text.lower():
        b.click()
        break
wait_and_sleep(SharedDriver())

if FindBy.XPATH(config['no_results']).is_present():
    print("No results found for the keyword: %s" % search)
else:
    lastHeight = 0
    known_tags = []
    valid_job_postings = 0
    complete_data = []
    no_jobs_found = False
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        wait_and_sleep(SharedDriver())
        newHeight = driver.execute_script("return document.body.scrollHeight")
        if newHeight == lastHeight:
            try:
                print("(%s): Reached bottom. Seeing if there are more jobs" % search)
                more_jobs = driver.find_elements_by_xpath(config['xpath_see_more_jobs_button'])
                if more_jobs[0].is_displayed():
                    print("(%s): More jobs found" % search)
                    more_jobs[0].click()
                    wait_and_sleep(SharedDriver())
                else:
                    print("(%s): No more jobs found" % search)
                    break
            except selenium.common.exceptions.NoSuchElementException as e:
                print("(%s): No more results" % search)
                break
            except IndexError as f:
                print("(%s): No job results found" % search)
                no_jobs_found = True
                break
        # Once it has loaded the new results we get the contents of the page and scrape the job postings
        page_soup = SharedDriver().page_soup
        tags = []
        for ul in page_soup.findAll('ul', class_=config['job_results_selector']):
            for li in ul.findAll('li'):
                tags.append(li)
        new_tags = [tag for tag in tags if tag not in known_tags] or []
        print("(%s): %d new jobs found" % (search, len(new_tags)))
        known_tags.extend(new_tags)
        print("(%s): %d total jobs found" % (search, len(known_tags)))
        # We can pre-filter some of the jobs we found by checking if they are in cities we do not want
        # This way we only stop our search once we have found X valid jobs
        # Now that we have all the subsections of HTML code containing the job posting, we can parse it to get the
        # information we need (ex. posted time, company, location, and job title)
        parsed_tags = [parse(tag, config) for tag in known_tags]
        for j in parsed_tags:
            if j["location"]:
                j["location"] = (str(j['location']).split(", United States"))[0]
            if not any(l for l in config['excluded_locations'] if l.lower() in j['location'].lower()) and \
                    not any(l for l in config['excluded_companies'] if l.lower() in j['company'].lower()) and \
                    not any(l for l in config['excluded_title_keywords'] if l.lower() in j['title'].lower()):
                valid_job_postings += 1
        complete_data.extend(parsed_tags)
        # The max jobs per search is more of a, stop after this point, kind of deal
        if valid_job_postings >= max_jobs:
            print("(%s): Found more than or equal to max number jobs. Breaking out" % search)
            break
        lastHeight = newHeight
    if not no_jobs_found:
        # Now that we have all the subsections of HTML code containing the job posting, we can parse it to get the
        # information we need (ex. posted time, company, location, and job title)
        parsed_tags = [parse(tag, config) for tag in known_tags]
        sorted_data = sorted(parsed_tags, key=lambda k: k['title'])
        # Now we print out our results
        print(tabulate(sorted_data, headers="keys", tablefmt="grid"))
    else:
        print("No jobs found")


'''
# I could get it to sign in just fine but it ended up adding more problems than it solved
# The main problem was theact that I would need to re-do the infinite scroll 
authenticated = False
    if config['LoginToLinkedIn']:
        driver.get('https://www.linkedin.com/jobs')
        SharedDriver().wait_for_page_load()
        time.sleep(1.5)
        login = driver.find_elements_by_xpath("//div/a[contains(text(), 'Sign in')]")
        if login:
            login[0].click()
            SharedDriver().wait_for_page_load()
            time.sleep(1.5)
            username = driver.find_element_by_id('username')
            username.click()
            username.send_keys(config['Username'])
            password = driver.find_element_by_id('password')
            password.click()
            password.send_keys(config['Password'] + Keys.ENTER)
            SharedDriver().wait_for_page_load()
            time.sleep(1.5)
            # Checking to make sure it was the right username and password
            if driver.current_url != 'https://www.linkedin.com/jobs/':
                logging.warning("Unable to sign into LinkedIn with the given credentials")
            else:
                logging.info("Logged into LinkedIn with given credentials")
                authenticated = True
        else:
            logging.warning("There was an error while trying to sign in")
    else:
        logging.info("Scraping LinkedIn as a guest user")
'''