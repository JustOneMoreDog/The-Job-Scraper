from hed_utils.selenium import SharedDriver, chrome_driver, FindBy
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from datetime import datetime
from typing import Dict, Any
from bs4 import BeautifulSoup
from tabulate import tabulate
from xlsxwriter import Workbook
from urllib.parse import parse_qs
from functools import reduce
import selenium.common.exceptions
import time
import logging
import logging.handlers
import json
import os
import yaml
import urllib.parse as urlparse
import schedule

# Setting up our log files
if not os.path.exists("logs"):
    os.mkdir("logs")
if not os.path.exists("scrape_backups"):
    os.mkdir("scrape_backups")
if not os.path.exists("daily_reports"):
    os.mkdir("daily_reports")
log_file_handler = logging.handlers.WatchedFileHandler(os.environ.get(
    "LOGFILE", os.path.join(os.getcwd(), "logs/" + str(datetime.today().date()) + "-" + str(datetime.today().time().hour) + "-" + str(datetime.today().time().minute) + ".log")
))
formatter = logging.Formatter(logging.BASIC_FORMAT)
log_file_handler.setFormatter(formatter)
root = logging.getLogger()
root.setLevel(os.environ.get("LOGLEVEL", "INFO"))
root.addHandler(log_file_handler)
logging.info("Logging has been setup. Script is starting")


def parse(tag, config, search, remote) -> Dict[str, Any]:
    job = {key: None for key in ["posted_time", "location", "title", "company", "url", "search", "remote"]}
    job["search"] = search
    job["remote"] = remote
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
        time.sleep(1)
        validate_page(shared_driver, config)
        if not http_429_error_check(driver):
            break
        retries -= 1
        if retries == 0:
            return BeautifulSoup()
    retries = config['max_retries']
    while True:
        if retries != config['max_retries']:
            driver.get(url)
            shared_driver.wait_for_page_load()
            time.sleep(1)
            validate_page(shared_driver, config)
        try:
            for b in driver.find_elements_by_xpath(config['job_description_show_more']):
                if b.text == 'Show more':
                    b.click()
                    break
            time.sleep(1)
            soup = shared_driver.page_soup
            job_description = soup.find(config['job_description_tag'], class_=config['job_description_class'])
            return BeautifulSoup(str(job_description), 'html.parser')
        except: # Dont @ me
            retries -= 1
            if retries == 0:
                return BeautifulSoup()
            else:
                time.sleep(1)
                continue


# This will check if we are getting dickled and LinkedIn redirected us to a login page
def validate_page(driver, config):
    # The different params where our original url can be stored
    checks = ["sessionRedirect", 'session_redirect']
    # Initial backoff set to 2 since that seems to be the number that works the best
    backoff = 2
    while True:
        backoff += 1
        # Both of these need to not have happened in order for the page to be considered valid
        if check_for_redirect(driver, checks, backoff, config) and check_for_429(driver, backoff, config):
            break


# Utility function for validate_page
def check_for_redirect(driver, checks, backoff, config):
    never_redirected = True
    while True:
        # Grabbing our current url and parsing all of its params
        parsed = urlparse.urlparse(driver.current_url)
        redirected = False
        for check in checks:
            # If one of the above params is in the url then we have been redirected
            if check in parse_qs(parsed.query):
                redirected = True
                never_redirected = False
                logging.warning("LinkedIn redirected us and so we need to sleep and then continue the search")
                time.sleep(backoff)
                # We now tell selenium to try and load the url we actually wanted to go to
                driver.get(str(parse_qs(parsed.query)[check][0]))
                # Then we tell it to wait for that page to load
                driver.wait_for_page_load()
                # Then we make sure that we have not been 429-ed
                check_for_429(driver, backoff, config)
                break
        if redirected:
            continue
        else:
            break
    return never_redirected


# Utility function for validate_page
def check_for_429(driver, backoff, config):
    never_429ed = True
    while True:
        http_429_check = driver.find_elements_by_xpath(config['http_429_xpath'])
        if not http_429_check:
            break
        else:
            logging.info("We have been 429-ed so we are going to sleep")
            never_429ed = False
            time.sleep(backoff)
            backoff += 1
            logging.info("Refreshing the page")
            driver.refresh()
            driver.wait_for_page_load()
            time.sleep(1)
    return never_429ed


def get_job_posts(location, timespan_button, config, driver, known_tags,
                  total_valid_job_postings, complete_data, day, search, remote, minimum_threshold):
    # Inner function that tries to prevent us from getting 429-ed by putting in sleep statements
    def wait_and_sleep(shared_driver):
        shared_driver.wait_for_page_load()
        validate_page(shared_driver, config)
        shared_driver.wait_for_page_load()
        time.sleep(1.5)

    # Inner function that will move to an element and then press tab and then enter
    def send_tab_enter(e):
        ActionChains(driver).move_to_element(e).send_keys(Keys.TAB).send_keys(Keys.ENTER).perform()

    # valid_job_postings = 0
    if remote:
        logging.info("(%s): starting job hunt for %s in %s with remote set to true" % (search, search, location))
    else:
        logging.info("(%s): starting job hunt for %s in %s with remote set to false" % (search, search, location))

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

    # Filtering by remote only jobs
    if remote:
        logging.info("(%s): Filtering in only remote jobs for %s in %s" % (search, search, location))
        driver.find_elements_by_xpath(config['remote_button'])[0].click()
        driver.find_elements_by_xpath(config['remote_label'])[0].click()
        for button in driver.find_elements_by_xpath(config['done_button']):
            try:
                button.click()
                break
            except selenium.common.exceptions.ElementNotInteractableException as e:
                continue
        wait_and_sleep(SharedDriver())

    # Limiting our search results to the past week
    driver.find_elements_by_xpath(config['any_time_button'])[0].click()
    timespan_buttons = driver.find_elements_by_xpath(timespan_button)
    if len(timespan_buttons) > 0:
        driver.find_elements_by_xpath(timespan_button)[0].click()
    else:
        logging.info("(%s): We could not find the timespan of %s" % (search, timespan_button))
    time.sleep(1)
    for button in driver.find_elements_by_xpath(config['done_button']):
        try:
            button.click()
            break
        except selenium.common.exceptions.ElementNotInteractableException as e:
            continue
    wait_and_sleep(SharedDriver())

    if FindBy.XPATH(config['no_results']).is_present():
        logging.warning("No results found for the keyword: %s" % search)
        return known_tags, total_valid_job_postings, complete_data

    # Limiting our search to full time positions
    if driver.find_elements_by_xpath(config['job_type_button']):
        driver.find_elements_by_xpath(config['job_type_button'])[0].click()
    else:
        driver.find_elements_by_xpath(config['more_filters_button'])[0].click()
        driver.find_element_by_xpath(config['job_type_nested_button']).click()
    driver.find_elements_by_xpath(config['full_time_button'])[0].click()
    time.sleep(1)
    for b in driver.find_elements_by_xpath(config['done_button']):
        if "done" in b.text.lower():
            b.click()
            break
    wait_and_sleep(SharedDriver())

    if FindBy.XPATH(config['no_results']).is_present():
        logging.warning("No results found for the keyword: %s" % search)
        return known_tags, total_valid_job_postings, complete_data

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
            if any(x for x in [y for y in config['experience_levels'].keys() if config['experience_levels'][y]]
                   if x.lower() in job_level.text.lower()):
                job_level.click()
    time.sleep(.5)
    for b in driver.find_elements_by_xpath(config['done_button']):
        if "done" in b.text.lower():
            b.click()
            break
    wait_and_sleep(SharedDriver())

    if FindBy.XPATH(config['no_results']).is_present():
        logging.warning("No results found for the keyword: %s" % search)
        return known_tags, total_valid_job_postings, complete_data

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
                break
                # return []
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
        # Transforming the HTML data into a proper format
        parsed_tags = [parse(tag, config, search, remote) for tag in known_tags]
        for j in parsed_tags:
            if j["location"]:
                j["location"] = (str(j['location']).split(", United States"))[0]
            if is_a_valid_job_posting(j, config):
                total_valid_job_postings += 1
        complete_data.extend(parsed_tags)
        logging.info("(%s): %d total valid jobs found" % (search, total_valid_job_postings))
        # The min jobs per search is more of a, stop after this point, kind of deal
        # Since scraping jobs for the past week or month can be intensive we will break out as soon as we
        # hit our threshold instead continuing down the endless postings
        # In config.yaml a user can force the script to get all jobs in the last 24 hours
        # By default this is turned off as it drastically increases the scrape time
        if day and config['scrape_all_last_day_jobs'] and location != 'United States' and \
                total_valid_job_postings < config['maximum_valid_job_postings']:
            logging.info("(%s): Continuing to scrape all last day jobs (Location = %s)" % (search, location))
            last_height = newHeight
            continue
        # Otherwise we will check if we have enough postings
        elif total_valid_job_postings >= minimum_threshold:
            logging.info("(%s): %d is over our threshold so we can break out now" %
                         (search, total_valid_job_postings))
            break
        # If we do not have enough then we will continue
        else:
            last_height = newHeight
            logging.info("(%s): We are now at %d valid job postings" % (search, total_valid_job_postings))
    logging.info("(%s): finished job hunt in %s and are now at %d valid jobs" %
                 (search, location, total_valid_job_postings))
    return known_tags, total_valid_job_postings, complete_data


def scrape_jobs(search: str, locations: list, minimum_threshold: int, driver, config):
    SharedDriver.set_instance(driver)

    known_tags = []
    total_valid_job_postings = 0
    complete_data = []
    day = True
    week = False
    month = False
    '''
    if remote only is true then we set our locations variable to be only the remote location
    if remote only is false then we append the locations list with the remote location
    then in the for loop that goes through the locations we can have a conditional that checks
    after we specify the time and location we would have a check that says 
    if remote only is false and the location is equal to the remote only location
    then activate the remote filter
    '''
    if config['include_remote']:
        locations.append(config['remote_location'])
    while True:
        timespan_button = None
        if day:
            logging.info("(%s): Timespan set to 24 hours" % search)
            timespan_button = config['past_day_button']
        elif week:
            logging.info("(%s): Timespan set to past week" % search)
            timespan_button = config['past_week_button']
        elif month:
            logging.info("(%s): Timespan set to past month" % search)
            timespan_button = config['past_month_button']
        else:
            logging.info("(%s): No more timespans to use. Breaking out." % search)
            break
        for location in locations:
            # First we do our basic search on the location
            if config['include_remote']:
                known_tags, total_valid_job_postings, complete_data = get_job_posts(
                    location, timespan_button, config, driver, known_tags,
                    total_valid_job_postings, complete_data, day, search, True, minimum_threshold
                )
            if not config['remote_only'] and location != config['remote_location']:
                known_tags, total_valid_job_postings, complete_data = get_job_posts(
                    location, timespan_button, config, driver, known_tags,
                    total_valid_job_postings, complete_data, day, search, False, minimum_threshold
                )
            # Next we do our search for only remote

        # Now we check if we have enough valid jobs scraped
        # If not, we escalate the timespan accordingly
        if total_valid_job_postings < minimum_threshold:
            if day:
                day = False
                week = True
                month = False
            elif week:
                day = False
                week = False
                month = True
            else:
                day = False
                week = False
                month = False
        else:
            logging.info("(%s): Not incrementing timespan since we are at %d valid jobs" %
                         (search, total_valid_job_postings))
            break
    logging.info("(%s): Finished scraping jobs and returning %d valid jobs" % (search, total_valid_job_postings))
    return complete_data


def is_a_valid_job_posting(j, config):
    # We can pre-filter some of the jobs we found by checking if they are in cities we do not want
    # This way we only stop our search once we have found X valid jobs
    # Now that we have all the subsections of HTML code containing the job posting,
    # we can parse it to get the information we need (ex. posted time, company, location, and job title)
    if not any(l for l in config['excluded_locations'] if l.lower() in j['location'].lower()) and \
            not any(l for l in config['excluded_companies'] if l.lower() in j['company'].lower()) and \
            not any(l for l in config['excluded_title_keywords'] if l.lower() in j['title'].lower()):
        return True
    else:
        return False


def post_job_scrape_processing(new_data, old_data):
    deduped_data = []
    scrape_dups = 0
    previously_found = 0
    scrape_duds = 0
    for job_search in new_data:
        for job in job_search:
            if 'url' in job and job['url']:
                # Sometimes we can scrape a job twice because two searches may overlap
                if any(j for j in deduped_data if j['url'].lower() == job['url'].lower()):
                    scrape_dups += 1
                # Sometimes a job shows up that we have already previously found
                elif any(j for j in old_data if j['url'].lower() == job['url'].lower()):
                    previously_found += 1
                else:
                    deduped_data.append(job)
                #if not any(j for j in deduped_data if j['url'] == job['url']) and \
                #        not any(j for j in old_data if j['url'] == job['url']):
                #    deduped_data.append(job)
            else:
                scrape_duds += 1
    return deduped_data, scrape_dups, previously_found, scrape_duds


def load_json_data(filepath) -> dict:
    with open(filepath, "r") as f:
        return json.load(f)


def save_json_data(data, filepath):
    with open(filepath, "w") as f:
        return json.dump(obj=data, fp=f, cls=BSEncoder)


# This allows us to export the jobs as json by telling json.dump how to serial the beautiful soup content object
class BSEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, BeautifulSoup):
            return str(o)
        else:
            return o.__dict__


def load_yaml_data(filepath) -> dict:
    with open(filepath, "r") as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def save_job_report_excel(jobs):
    headers = ["posted_time", "title", "company", "location", "rating", "keywords", "search", "url"]
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
def save_job_report_html(data, path):
    keys = ["posted_time", "title", "company", "location", "rating", "keywords", "search", "url", "content"]
    index_path = os.path.join(path, "index.html")
    # Our extremely basic HTML page
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
    # First we make sure the default landing page is there and if not we make it
    if not os.path.exists(index_path):
        with open(index_path, "w") as f:
            soup = BeautifulSoup(html, "html.parser")
            f.write(str(soup))
    # Then we add a link to today's job report on the main page
    with open(index_path, "r") as f:
        soup = BeautifulSoup(f, "html.parser")
        p = "/" + str(datetime.today().date()) + "-" + str(datetime.today().time().hour) + "-" + str(datetime.today().time().minute) + "/index.html"
        new_tag = soup.new_tag('a', href=p)
        new_tag.string = str(datetime.today().date()) + "-" + str(datetime.today().time().hour) + "-" + str(datetime.today().time().minute)
        soup.body.append(soup.new_tag('br'))
        soup.body.append(new_tag)
    # Then we save the updated main page to disk
    with open(index_path, "w") as f:
        f.write(str(soup))
    # Now we move our path into the directory for todays report
    path = os.path.join(path, (str(datetime.today().date()) + "-" + str(datetime.today().time().hour) + "-" + str(datetime.today().time().minute)))
    index_path = os.path.join(path, "index.html")
    # If the directory does not exist (it should not) we make it
    if not os.path.exists(path):
        os.mkdir(path)
    # Now we repeat the above process of making a basic index.html page for our report
    if not os.path.exists(index_path):
        with open(index_path, "w") as f:
            soup = BeautifulSoup(html, "html.parser")
            f.write(str(soup))
    # Except now we make a table for it instead
    with open(os.path.join(path, "index.html"), "w") as f:
        # We want our data to be in a certain order
        ordered_data = [{k: d[k] for k in keys} for d in data]
        for d in ordered_data:
            # Rather than having the content in the table, we make a different html page for it
            # This ensures that the table looks clean and is easy to read
            if d['content']:
                # Since each job posting that we scrape is deemed unique by their url, and since each url will start
                # the same, then the last section of the url is guaranteed to be unique. This ensures that we do not
                # create a folder for a job posting that overwrites another job posting
                content_folder = d['url'].split("/")[-1]
                os.mkdir(os.path.join(path, content_folder))
                content_path = os.path.join(content_folder, "content.html")
                soup = BeautifulSoup(html, "html.parser")
                soup.body.append(d['content'])
                # Writing the content to its own file
                with open(os.path.join(path, content_path), "w", encoding='utf-8') as g:
                    g.write(soup.prettify())
                # _blank makes it so that it opens up in a new tab
                a_tag = soup.new_tag('a', href=content_path, target="_blank", rel="noopener noreferrer")
                a_tag.string = "Content"
                d['content'] = a_tag
            post_link = soup.new_tag('a', href=d['url'], target="_blank", rel="noopener noreferrer")
            post_link.string = "Job Posting"
            d['url'] = post_link
        # Creating the table
        index_page = BeautifulSoup(html, "html.parser")
        data_table = BeautifulSoup(tabulate(ordered_data, headers="keys", tablefmt="html"), "html.parser")
        index_page.body.append(data_table)
        # Saving the table
        f.write(str(index_page))


def main():
    # Making sure config file exists
    config = None
    os.chdir("/app")
    if os.path.exists("config.yaml"):
        config = {**load_yaml_data("config.yaml"), **load_yaml_data("customizations.yaml")} 
    else:
        logging.error("Config file is missing")
        exit(-1)
    # If this is the first run then we will need to generate a all_jobs.json file
    if not os.path.exists("all_jobs.json"):
        save_json_data([], "all_jobs.json")
    # Checking if the user wants us to output html and if so making sure the folder exists
    if 'save_to_html' in config and config['save_to_html']:
        html_path = config['html_folder']
        if not os.path.exists(html_path):
            os.mkdir(html_path)
    else:
        html_path = None

    # Loading user defined customizations
    p_time = int(time.time())
    processing_time = 0
    searches = config['searches']
    locations = config['locations']
    minimum_threshold = config['minimum_jobs_per_search']
    excluded_locations = config['excluded_locations']
    excluded_companies = config['excluded_companies']
    excluded_title_keywords = config['excluded_title_keywords']
    word_weights = config['word_weights']

    # We are statically defining that the chrome window be 1920x1080 so that we can have consistency
    # If we always know that the window will X by Y size, then we will have an easier time finding the
    # elements we are looking for. We still put in the try catch to help catch the edge cases that we cannot predict

    options = Options()
    if config['headless']:
      for option in config['chrome_options']:
        options.add_argument(option)
    options.add_argument("window-size=%s" % config['window_size'])
    options.add_argument('--log-level=2')
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(config['timeout'])
    logging.info("Loading previously found jobs")
    all_jobs = load_json_data("all_jobs.json") or []
    save_json_data(all_jobs, "all_jobs.json.old")
    data = []
    logging.info("Scraping LinkedIn for jobs")

    processing_time += int(time.time()) - p_time
    start_scrape = int(time.time())
    for search in searches:
        search_start_time = int(time.time())
        logging.info("Scraping LinkedIn for jobs with the keyword %s" % search)
        i = config['max_retries']
        while i != 0:
            try:
                scraped_job_posts = scrape_jobs(
                    search=search, locations=locations, minimum_threshold=minimum_threshold,
                    driver=driver, config=config
                )
                data.append(scraped_job_posts)
                break
            except Exception as e:
                logging.exception("There was an error with getting jobs for '%s'" % search)
                logging.warning("This is the URL that caused the error %s" % driver.current_url)
                logging.warning("We are going to sleep for 5 and then retry. We have %d tries left" % (i-1))
                time.sleep(120)
                i -= 1
        search_stop_time = int(time.time())
        search_time = search_stop_time - search_start_time
        logging.info("(%s): Scrape took us %d seconds" % (search, search_time))
    logging.info("Done scraping LinkedIn for new jobs")
    p_time = int(time.time())
    processed_data, scrape_dups, previously_found, scrape_duds = post_job_scrape_processing(data, all_jobs)
    processing_time += int(time.time()) - p_time
    logging.info("Backing up the scrape")
    save_json_data(processed_data, "scrape_backups/" + str(datetime.today().date()) + "-" + str(datetime.today().time().hour) + "-" + str(datetime.today().time().minute) + ".json")
    end_scrape = int(time.time())
    driver.close()
    time.sleep(3)

    logging.info("Getting content for %d jobs" % len(processed_data))
    start_content = int(time.time())
    options = Options()
    if config['headless']:
      for option in config['chrome_options']:
        options.add_argument(option)
    options.add_argument("window-size=%s" % config['window_size'])
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    driver = webdriver.Chrome(options=options)
    SharedDriver.set_instance(driver)
    for job in processed_data:
        logging.info("Parsing %s" % job['url'])
        job['content'] = get_job_content(job['url'], driver, SharedDriver(), config)
    end_content = int(time.time())
    p_time = int(time.time())
    logging.info("Organizing results")
    blank_job = {"posted_time": "", "location": "", "title": "", "company": "",
                 "rating": "", "keywords": "", "url": "", "search": "", "content": ""}
    good_jobs = []
    bad_jobs = []
    # total_desired_words = len(word_weights)
    for job in processed_data:
        keywords = []
        if job['remote']:
            rating = 100
            if not config['remote_only']:
              keywords.append('REMOTE')
        else:
            rating = 0
        # If the job is in a place we do not want to work
        # Or if the job is for a company we do not want to work for
        # Or if the job had an excluded keyword in the title
        if any(l for l in excluded_locations if l.lower() in job['location'].lower()):
            keywords.append('LOC')
            rating = -999
        if any(l for l in excluded_companies if l.lower() in job['company'].lower()):
            keywords.append('COMP')
            rating = -999
        if any(l for l in excluded_title_keywords if l.lower() in job['title'].lower()):
            keywords.append('TITLE')
            rating = -999
        else:
            for word in list(word_weights.keys()):
                if word.lower() in str(job['content']).lower():
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
    logging.info("Formatting job report for output")
    for i in range(1, 5):
        good_jobs.append(blank_job)
    good_jobs.append({"posted_time": "Excluded Jobs", "location": "", "title": "", "company": "",
                      "rating": "", "keywords": "Note: LOCation, COMPany, TITLE",
                      "search": "", "url": "", "content": ""})
    logging.info("Saving job report to excel file")
    save_job_report_excel(good_jobs + bad_jobs)
    if html_path:
        logging.info("Saving job report to html file")
        save_job_report_html((good_jobs + bad_jobs), html_path)
    processing_time += int(time.time()) - p_time

    # Doing this as an inner function to keep it simple
    def post_script_report(write, data, end_scrape, start_scrape, end_content,
                           start_content, processing_time, processed_data,
                           scrape_dups, previously_found, scrape_duds):
        write("We previously had %d jobs found" % len(all_jobs))
        total_scrape = reduce(lambda count, l: count + len(l), data, 0)
        write("Today we scraped %d jobs from LinkedIn" % total_scrape)
        write("%d of those were duplicates" % scrape_dups)
        write("%d of those had already been previously found" % previously_found)
        write("%d of those were duds" % scrape_duds)
        write("It took us %d seconds to do the scrape, %d seconds to get content, and %d seconds to process the data" %
              ((end_scrape - start_scrape), (end_content - start_content), processing_time))
        write("%d of the %d scraped jobs are new" % (len(processed_data), total_scrape))
        write("Out of those new jobs, %d were good and %d were undesirable" % (len(good_jobs), len(bad_jobs)))
        write("In total we have scraped %d jobs to date" % (len(all_jobs + good_jobs + bad_jobs)))
    if config['post_script_console_report']:
        post_script_report(print, data, end_scrape, start_scrape, end_content,
                           start_content, processing_time, processed_data,
                           scrape_dups, previously_found, scrape_duds)
        post_script_report(logging.info, data, end_scrape, start_scrape, end_content,
                           start_content, processing_time, processed_data,
                           scrape_dups, previously_found, scrape_duds)
    else:
        post_script_report(logging.info, data, end_scrape, start_scrape, end_content,
                           start_content, processing_time, processed_data,
                           scrape_dups, previously_found, scrape_duds)
    logging.info("Daily job scrape complete!")
    driver.close()


if __name__ == '__main__':
    main()
    schedule.every(120).minutes.do(main)
    while True:
      #schedule.every().day.at(load_yaml_data("customizations.yaml")['run_time']).do(main)
      schedule.run_pending()  
      time.sleep(60)
      #schedule.clear()
