import string
from hed_utils.selenium import SharedDriver, chrome_driver, FindBy
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium import webdriver
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


def http_429_error_check(driver):
    try:
        err = driver.find_element_by_xpath("//div[contains(@class, 'error-code')]")
        if err and "429" in err.text:
            logging.error("We got hit with the 429 timeout. Sleeping for 5 seconds")
            time.sleep(5)
            return True
        else:
            return False
    except selenium.common.exceptions.NoSuchElementException as e:
        return False


def get_job_content(url, driver, shared_driver, config):
    retries = config['max_retries']
    while True:
        driver.get(url)
        shared_driver.wait_for_page_load()
        time.sleep(.75)
        if not http_429_error_check(driver):
            break
        retries -= 1
        if retries == 0:
            return ''
    retries = config['max_retries']
    while True:
        if retries != config['max_retries']:
            driver.get(url)
            shared_driver.wait_for_page_load()
            time.sleep(.75)
        try:
            for b in driver.find_elements_by_xpath(config['job_description_show_more']):
                if b.text == 'Show more':
                    b.click()
                    break
            time.sleep(.75)
            job_description = driver.find_elements_by_xpath(config['job_description_xpath'])
            if job_description and len(job_description) > 0:
                return job_description[0].text
            else:
                return ''
        except: # Dont @ me
            retries -= 1
            if retries == 0:
                return ''
            else:
                time.sleep(1)
                continue


def get_job_posts(search: str, locations: list, max_jobs: int, driver, config):

    # Inner function that tries to prevent us from getting 429-ed by putting in sleep statements
    def wait_and_sleep(shared_driver):
        shared_driver.wait_for_page_load()
        time.sleep(.75)

    # Inner function that will move to an element and then press tab and then enter
    def send_tab_enter(e):
        ActionChains(driver).move_to_element(e).send_keys(Keys.TAB).send_keys(Keys.ENTER).perform()

    SharedDriver.set_instance(driver)
    known_tags = []
    valid_job_postings = 0
    complete_data = []
    # Still need to add the radius selector
    for location in locations:
        logging.info("(%s): starting job hunt for %s in %s" % (search, search, location))

        driver.get('https://www.linkedin.com/jobs')
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
        if driver.find_elements_by_xpath(config['more_filters_button']):
            driver.find_elements_by_xpath(config['more_filters_button'])[0].click()
            time.sleep(.25)
            driver.find_elements_by_xpath(config['exp_level_span_button'])[0].click()
            for job_level in driver.find_elements_by_xpath(config['ul_li_filter_list']):
                if any(x for x in [y for y in config['experience_levels'].keys() if config['experience_levels'][y]] if
                       x.lower() in job_level.text.lower()):
                    job_level.click()
        else:
            driver.find_elements_by_xpath(config['exp_level_button'])[0].click()
            job_levels = [j for j in driver.find_elements_by_xpath(config['div_filter_list']) if j.text and
                          len(j.text.split("(")) == 2]
            for job_level in job_levels:
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
            logging.warning("No results found for the keyword: %s" % search)
            return []

        last_height = 0
        # Handling the infinite scroll
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            wait_and_sleep(SharedDriver())
            newHeight = driver.execute_script("return document.body.scrollHeight")
            if newHeight == last_height:
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
            logging.info("(%s): %d total valid jobs found" % (search, len(valid_job_postings)))
            # The max jobs per search is more of a, stop after this point, kind of deal
            if valid_job_postings >= max_jobs:
                logging.info("(%s): Found more than or equal to max number jobs (%d). Breaking out" %
                             (search, valid_job_postings))
                break
            else:
                logging.info("(%s): We are now at %d valid job postings" % (search, valid_job_postings))
            last_height = newHeight

    return complete_data


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


# If you want the data to go somewhere else other than an excel file you can use this function
# For me I have it go to my var www folder so that I can just access it from the browser
# extra_steps(good_jobs+bad_jobs)
def extra_steps(data):
    from tabulate import tabulate
    import re
    import random
    import string
    keys = ["posted_time", "title", "company", "location", "rating", "keywords", "url", "content"]
    path = "/var/www/desktopdev/%s" % (str(datetime.today().date()))
    html = """
    <html>
    <head>
    <style>
    table { width: 100%; }
    table, th, td { border: 1px solid black; }
    </style>
    </head>
    <body>
    </body>
    </html>
    """
    os.mkdir(path)
    with open("/var/www/desktopdev/index.html", "r") as f:
        soup = BeautifulSoup(f, "html.parser")
        p = "/" + str(datetime.today().date()) + "/index.html"
        new_tag = soup.new_tag('a', href=p)
        new_tag.string = str(datetime.today().date())
        soup.body.append(soup.new_tag('br'))
        soup.body.append(new_tag)
    with open("/var/www/desktopdev/index.html", "w") as f:
        f.write(str(soup))
    with open(os.path.join(path, "index.html"), "w") as f:
        regex = re.compile('[^a-zA-Z]')
        ordered_data = [{k: d[k] for k in keys} for d in data]
        for d in ordered_data:
            if d['content']:
                #content_folder = str(d['posted_time'] + "-" +
                #                     regex.sub('', str(d['title'])[:15]).replace(" ", "_") + "_" +
                #                     str(d['company']).split(".")[0].replace(" ", "-")).lower() + \
                #                 ''.join(random.choices(string.ascii_lowercase, k=3))
                content_folder = d['url'].split("/")[-1]
                os.mkdir(os.path.join(path, content_folder))
                content_path = os.path.join(content_folder, "content.html")
                soup = BeautifulSoup(html, "html.parser")
                new_tag = soup.new_tag('p')
                new_tag.string = d['content']
                soup.body.append(new_tag)
                with open(os.path.join(path, content_path), "w") as g:
                    g.write(str(soup))
                a_tag = soup.new_tag('a', href=content_path)
                a_tag.string = "Content"
                d['content'] = a_tag
            post_link = soup.new_tag('a', href=d['url'])
            post_link.string = "Job Posting"
            d['url'] = post_link
        index_page = BeautifulSoup(html, "html.parser")
        data_table = BeautifulSoup(tabulate(ordered_data, headers="keys", tablefmt="html"), "html.parser")
        index_page.body.append(data_table)

        f.write(str(index_page))

    return None


if __name__ == '__main__':
    # Making sure config file exists
    config = None
    if os.path.exists("config.yaml"):
        config = {**load_yaml_data("config.yaml"), **load_yaml_data("customizations.yaml")}
    else:
        logging.error("Config file is missing")
        exit(-1)
    # If this is the first run then we will need to generate a all_jobs.json file
    if not os.path.exists("all_jobs.json"):
        save_json_data([], "all_jobs.json")

    # Loading user defined customizations
    searches = config['searches']
    locations = config['locations']
    max_jobs = config['max_jobs_per_search']
    excluded_locations = config['excluded_locations']
    excluded_companies = config['excluded_companies']
    excluded_title_keywords = config['excluded_title_keywords']
    word_weights = config['word_weights']

    driver = chrome_driver.create_instance(headless=config['headless'])
    driver.set_page_load_timeout(config['timeout'])
    logging.info("Loading previously found jobs")
    all_jobs = load_json_data("all_jobs.json") or []
    data = []
    logging.info("Scraping LinkedIn for jobs")

    for search in searches:
        logging.info("Scraping LinkedIn for jobs with the keyword %s" % search)
        data.append(get_job_posts(search=search, locations=locations, max_jobs=max_jobs, driver=driver, config=config))
    logging.info("Done scraping LinkedIn for jobs")
    processed_data = post_job_scrape_processing(data, all_jobs)
    logging.info("We previously had %d jobs found" % len(all_jobs))
    logging.info("We scraped %d new jobs from LinkedIn" % len(processed_data))
    logging.info("Backing up the scrape")
    save_json_data(processed_data, "scrape_backups/" + str(datetime.today().date()) + ".json")
    driver.close()

    logging.info("Getting content for jobs")
    start_content = int(time.time())
    options = webdriver.ChromeOptions()
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.headless = config['headless']
    driver = webdriver.Chrome(options=options)
    SharedDriver.set_instance(driver)
    for job in processed_data:
        logging.info("Parsing %s" % job['url'])
        job['content'] = get_job_content(job['url'], driver, SharedDriver(), config)
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
        # Or if the job is for a company we do not want to work for
        # Or if the job had an excluded keyword in the title
        rating = 0
        if any(l for l in excluded_locations if l.lower() in job['location'].lower()) or \
                any(l for l in excluded_companies if l.lower() in job['company'].lower()) or \
                any(l for l in excluded_title_keywords if l.lower() in job['title'].lower()):
            rating = -999
        else:
            for word in list(word_weights.keys()):
                if word.lower() in job['content'].lower():
                    keywords.append(word)
                    rating += word_weights[word]
        job['keywords'] = ','.join(keywords)
        job['rating'] = rating
        if rating < 0:
            bad_jobs.append(job)
        else:
            good_jobs.append(job)
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
    extra_steps(good_jobs + bad_jobs)
