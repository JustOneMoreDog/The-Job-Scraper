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

# Setting up our log files
if not os.path.exists("logs"):
    os.mkdir("path")
if not os.path.exists("scrape_backups"):
    os.mkdir("scrape_backups")
if not os.path.exists("daily_reports"):
    os.mkdir("daily_reports")
log_file_handler = logging.handlers.WatchedFileHandler(os.environ.get(
    "LOGFILE", os.path.join(os.getcwd(), "logs/" + str(datetime.today().date()) + ".log")
))
formatter = logging.Formatter(logging.BASIC_FORMAT)
log_file_handler.setFormatter(formatter)
root = logging.getLogger()
root.setLevel(os.environ.get("LOGLEVEL", "INFO"))
root.addHandler(log_file_handler)


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


def get_job_content(url, retries, descript_attr):
    r = None
    while retries != 0:
        try:
            r = requests.get(url)
            break
        except requests.exceptions.ConnectionError as e:
            logging.error("The connection got reset so we are sleeping and trying again")
            time.sleep(1)
            retries -= 1
    if retries == 0:
        logging.error("The connection got reset too many times so we are giving up on this one")
        return ""
    soup = BeautifulSoup(r.text, 'html.parser')
    descript_div = soup.find_all(attrs=descript_attr)
    result = []
    for tag in descript_div:
        for t in tag.find_all('li'):
            result.append(t.get_text())
    time.sleep(.5)
    return " ".join(result)


def get_job_posts(search: str, location: str, max_jobs: int, driver, config):

    # Inner function that tries to prevent us from getting 429-ed by putting in sleep statements
    def wait_and_sleep(shared_driver):
        shared_driver.wait_for_page_load()
        time.sleep(.75)

    # Inner function that will move to an element and then press tab and then enter
    def send_tab_enter(e):
        ActionChains(driver).move_to_element(e).send_keys(Keys.TAB).send_keys(Keys.ENTER).perform()

    logging.info("(%s): starting job hunt for %s" % (search, search))

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

    if FindBy.XPATH(config['no_results']).is_present():
        logging.warning("No results found for the keyword: %s" % search)
        return []

    lastHeight = 0
    known_tags = []
    # Handling the infinite scroll
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        wait_and_sleep(SharedDriver())
        newHeight = driver.execute_script("return document.body.scrollHeight")
        if newHeight == lastHeight:
            try:
                logging.info("(%s): Reached bottom. Seeing if there are more jobs" % search)
                more_jobs = driver.find_elements_by_xpath(config['xpath_see_more_jobs_button'])
                if more_jobs[0].is_displayed():
                    logging.info("(%s): More jobs found" % search)
                    more_jobs[0].click()
                    wait_and_sleep(SharedDriver())
                else:
                    logging.info("(%s): No more jobs found" % search)
                    break
            except selenium.common.exceptions.NoSuchElementException as e:
                logging.info("(%s): No more results" % search)
                break
            except IndexError as f:
                logging.warning("(%s): No job results found" % search)
                return []
        # Once it has loaded the new results we get the contents of the page and scrape the job postings
        page_soup = SharedDriver().page_soup
        tags = []
        for ul in page_soup.findAll('ul', class_=config['job_results_selector']):
            for li in ul.findAll('li'):
                tags.append(li)
        new_tags = [tag for tag in tags if tag not in known_tags] or []
        logging.info("(%s): %d new jobs found" % (search, len(new_tags)))
        known_tags.extend(new_tags)
        logging.info("(%s): %d total jobs found" % (search, len(known_tags)))
        # The max jobs per search is more of a, stop after this point, kind of deal
        if len(known_tags) >= max_jobs:
            logging.info("(%s): Found more than or equal to max number jobs. Breaking out" % search)
            break
        lastHeight = newHeight

    # Now that we have all the subsections of HTML code containing the job posting, we can parse it to get the
    # information we need (ex. posted time, company, location, and job title)
    parsed_tags = [parse(tag, config) for tag in known_tags]
    sorted_data = sorted(parsed_tags, key=lambda k: k['title'])
    for t in sorted_data:
        if t["location"]:
            t["location"] = (str(t['location']).split(", United States"))[0]
        if len(t["title"]) > 35:
            t["title"] = str(t["title"])[:35] + "..."

    return sorted_data


def post_job_scrape_processing(new_data, old_data):
    deduped_data = []
    for job_search in new_data:
        for job in job_search:
            if 'url' in job and job['url']:
                if not any(j for j in deduped_data if j['url'] == job['url']) and \
                        not any(j for j in old_data if j['url'] == job['url']):
                    deduped_data.append(job)
    sorted_data = sorted(deduped_data, key=lambda x: (x['posted_time'], x['title']))
    return sorted_data


def load_json_data(filepath) -> dict:
    with open(filepath, "r") as f:
        return json.load(f)


def save_json_data(data, filepath):
    with open(filepath, "w") as f:
        return json.dump(data, f)


def load_yaml_data(filepath) -> dict:
    with open(filepath, "r") as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def save_job_report(jobs):
    headers = ["posted_time", "title", "company", "location", "rating", "keywords", "url"]
    path = os.path.join(os.getcwd(), "daily_reports", str(datetime.today().date()) + ".xlsx")
    wb = Workbook(path)
    ws = wb.add_worksheet("Daily Job Report")
    ws.write_row(row=0, col=0, data=headers)
    for index, item in enumerate(jobs):
        row = map(lambda field_id: item.get(field_id, ''), headers)
        ws.write_row(row=index + 1, col=0, data=row)
    wb.close()


if __name__ == '__main__':
    # Making sure config file exists
    config = None
    if os.path.exists("config.yaml"):
        config = load_yaml_data("config.yaml")
    else:
        logging.error("Config file is missing")
        exit(-1)
    # If this is the first run then we will need to generate a all_jobs.json file
    if not os.path.exists("all_jobs.json"):
        save_json_data([], "all_jobs.json")

    # Making sure the critical stuff is not missing from the config
    if any(x for x in ['headless', 'timeout', 'max_retries', 'xpath_see_more_jobs_button',
                       'any_time_button', 'past_week_button', 'no_results',
                       'job_results_selector', 'job_location', 'job_description'] if x not in config):
        logging.error("Required params in config file are missing")
        exit(-1)
    # Loading user defined customizations
    searches = config['searches']
    location = config['location']
    max_jobs = config['max_jobs_per_search']
    excluded_locations = config['excluded_locations']
    word_weights = config['word_weights']

    driver = chrome_driver.create_instance(headless=config['headless'])
    driver.set_page_load_timeout(config['timeout'])
    logging.info("Loading previously found jobs")
    all_jobs = load_json_data("all_jobs.json") or []
    data = []
    logging.info("Scraping LinkedIn for jobs")

    for search in searches:
        logging.info("Scraping LinkedIn for jobs with the keyword %s" % search)
        data.append(get_job_posts(search=search, location=location, max_jobs=max_jobs, driver=driver, config=config))
    logging.info("Done scraping LinkedIn for jobs")
    processed_data = post_job_scrape_processing(data, all_jobs)
    logging.info("We previously had %d jobs found" % len(all_jobs))
    logging.info("We scraped %d new jobs from LinkedIn" % len(processed_data))
    logging.info("Backing up the scrape")
    save_json_data(processed_data, "scrape_backups/" + str(datetime.today().date()) + ".json")
    driver.close()

    logging.info("Getting content for jobs")
    start_content = int(time.time())
    for job in processed_data:
        logging.info("Parsing %s" % job['url'])
        job['content'] = get_job_content(job['url'], config['max_retries'], config['job_description'])
    end_content = int(time.time())
    logging.info("It took us %d seconds to get all the job posting content" % (end_content-start_content))

    logging.info("Organizing results")
    blank_job = {"posted_time": "", "location": "", "title": "", "company": "",
                 "rating": "", "keywords": "", "url": "", "content": ""}
    good_jobs = []
    bad_jobs = []
    # total_desired_words = len(word_weights)
    for job in processed_data:
        keywords = []
        # If the job is in a place we do not want to work
        if any(l for l in excluded_locations if l.lower() in job['location'].lower()):
            job["rating"] = -999
            job['keywords'] = ''
            bad_jobs.append(job)
            continue
        rating = 0
        for word in list(word_weights.keys()):
            if word in job['content']:
                keywords.append(word)
                rating += word_weights[word]
        if rating < 0:
            bad_jobs.append(job)
        else:
            good_jobs.append(job)
        job['keywords'] = ','.join(keywords)
        job['rating'] = rating
    logging.info("Sorting the jobs by their rating")
    good_jobs.sort(key=lambda x: x['rating'], reverse=True)
    bad_jobs.sort(key=lambda x: x['rating'], reverse=True)
    logging.info("Adding newly found results to master list")

    save_json_data(all_jobs + good_jobs + bad_jobs, "all_jobs.json")
    for i in range(1, 5):
        good_jobs.append(blank_job)
    good_jobs.append({"posted_time": "Excluded Jobs", "location": "", "title": "", "company": "",
                      "rating": "", "keywords": "", "url": "", "content": ""})
    logging.info("Saving job report to excel file")
    save_job_report(good_jobs + bad_jobs)
    logging.info("Daily job scrape complete!")
