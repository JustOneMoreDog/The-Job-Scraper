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

# Setting up our log files
if not os.path.exists("logs"):
    os.mkdir("logs")
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
logging.info("Logging has been setup. Script is starting")

def parse(tag, config, search) -> Dict[str, Any]:
    job = {key: None for key in ["posted_time", "location", "title", "company", "url", "search"]}
    job["search"] = search
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
def validate_page(driver):
    parsed = urlparse.urlparse(driver.current_url)
    if 'session_redirect' in parse_qs(parsed.query):
        logging.warning("LinkedIn redirected us and so we need to sleep for a few seconds and then continue the search")
        time.sleep(3)
        driver.get(str(parse_qs(parsed.query)['session_redirect'][0]))
        return None
    if "sessionRedirect" in parse_qs(parsed.query):
        logging.warning("LinkedIn redirected us and so we need to sleep for a few seconds and then continue the search")
        time.sleep(3)
        driver.get(str(parse_qs(parsed.query)['sessionRedirect'][0]))
        return None


def get_job_posts(search: str, locations: list, minimum_threshold: int, driver, config):

    # Inner function that tries to prevent us from getting 429-ed by putting in sleep statements
    def wait_and_sleep(shared_driver):
        shared_driver.wait_for_page_load()
        validate_page(driver)
        time.sleep(1)

    # Inner function that will move to an element and then press tab and then enter
    def send_tab_enter(e):
        ActionChains(driver).move_to_element(e).send_keys(Keys.TAB).send_keys(Keys.ENTER).perform()

    SharedDriver.set_instance(driver)
    known_tags = []
    total_valid_job_postings = 0
    complete_data = []
    day = True
    week = False
    month = False
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
            # valid_job_postings = 0
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
            driver.find_elements_by_xpath(timespan_button)[0].click()
            time.sleep(1)
            send_tab_enter(driver.find_elements_by_xpath(config['past_day_button'])[0])
            wait_and_sleep(SharedDriver())

            if FindBy.XPATH(config['no_results']).is_present():
                logging.warning("No results found for the keyword: %s" % search)
                continue

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
                continue

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
                continue

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
                        #return []
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
                parsed_tags = [parse(tag, config, search) for tag in known_tags]
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
                if (week or month) and total_valid_job_postings >= minimum_threshold:
                    logging.info("(%s): %d is over our threshold so we can break out now" %
                                 (search, total_valid_job_postings))
                    break
                #else:
                #    logging.info("(%s): We are now at %d valid job postings" % (search, valid_job_postings))
                last_height = newHeight
            logging.info("(%s): finished job hunt in %s and are now at %d valid jobs" %
                         (search, location, total_valid_job_postings))
            # total_valid_job_postings += valid_job_postings
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
    for job_search in new_data:
        for job in job_search:
            if 'url' in job and job['url']:
                if not any(j for j in deduped_data if j['url'] == job['url']) and \
                        not any(j for j in old_data if j['url'] == job['url']):
                    deduped_data.append(job)
    return deduped_data


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
    # Adding an <a> tag that links to the job report
    with open(index_path, "r") as f:
        soup = BeautifulSoup(f, "html.parser")
        p = "/" + str(datetime.today().date()) + "/index.html"
        new_tag = soup.new_tag('a', href=p)
        new_tag.string = str(datetime.today().date())
        soup.body.append(soup.new_tag('br'))
        soup.body.append(new_tag)
    # Saving the new index.html file
    with open(index_path, "w") as f:
        f.write(str(soup))
    path = os.path.join(path, (str(datetime.today().date())))
    index_path = os.path.join(path, "index.html")
    # Making sure the HTML path exists
    if not os.path.exists(path):
        os.mkdir(path)
    # Making sure that there is an index.html in the HTML path and if not we make one
    if not os.path.exists(index_path):
        with open(index_path, "w") as f:
            soup = BeautifulSoup(html, "html.parser")
            f.write(str(soup))
    # Creating our job report table using tabulate
    with open(os.path.join(path, "index.html"), "w") as f:
        # We want our data to be in a certain order
        ordered_data = [{k: d[k] for k in keys} for d in data]
        for d in ordered_data:
            # Rather than having the content in the table, we make a different html page for it
            # This ensures that the table looks clean and is easy to read
            # We do not always need the content anyways
            if d['content']:
                # Since each job posting that we scrape is deemed unique by their url, and since each url will start
                # the same, then the last section of the url is guaranteed to be unique. This ensures that we do not
                # create a folder for a job posting that overwrites another job posting
                content_folder = d['url'].split("/")[-1]
                os.mkdir(os.path.join(path, content_folder))
                content_path = os.path.join(content_folder, "content.html")
                soup = BeautifulSoup(html, "html.parser")
                #new_tag = soup.new_tag('p')
                #new_tag.string = d['content']
                soup.body.append(d['content'])
                # Writing the content to its own file
                with open(os.path.join(path, content_path), "w", encoding='utf-8-sig') as g:
                    g.write(str(soup.prettify()))
                # This makes it so that it opens up in a new tab
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
        options.add_argument("--headless")
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
        logging.info("Scraping LinkedIn for jobs with the keyword %s" % search)
        i = config['max_retries']
        while i != 0:
            try:
                scraped_job_posts = get_job_posts(
                    search=search, locations=locations, minimum_threshold=minimum_threshold,
                    driver=driver, config=config
                )
                data.append(scraped_job_posts)
                break
            except Exception as e:
                logging.exception("There was an error with getting jobs for '%s'" % search)
                logging.warning("This is the URL that caused the error %s" % driver.current_url)
                logging.warning("We are going to sleep for 5 and then retry. We have %d tries left" % (i-1))
                time.sleep(5)
                i -= 1
    logging.info("Done scraping LinkedIn for new jobs")
    p_time = int(time.time())
    processed_data = post_job_scrape_processing(data, all_jobs)
    processing_time += int(time.time()) - p_time
    logging.info("Backing up the scrape")
    save_json_data(processed_data, "scrape_backups/" + str(datetime.today().date()) + ".json")
    end_scrape = int(time.time())
    driver.close()
    time.sleep(3)

    logging.info("Getting content for %d jobs" % len(processed_data))
    start_content = int(time.time())
    options = Options()
    if config['headless']:
        options.add_argument("--headless")
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
        # If the job is in a place we do not want to work
        # Or if the job is for a company we do not want to work for
        # Or if the job had an excluded keyword in the title
        rating = 0
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
                           start_content, processing_time, processed_data):
        write("We previously had %d jobs found" % len(all_jobs))
        total_scrape = reduce(lambda count, l: count + len(l), data, 0)
        write("Today we scraped %d jobs from LinkedIn" % total_scrape)
        write("It took us %d seconds to do the scrape, %d seconds to get content, and %d seconds to process the data" %
              ((end_scrape - start_scrape), (end_content - start_content), processing_time))
        write("%d of the %d scraped jobs are new" % (len(processed_data), total_scrape))
        write("Out of those new jobs, %d were good and %d were undesirable" % (len(good_jobs), len(bad_jobs)))
        write("In total we have scraped %d jobs to date" % (len(all_jobs + good_jobs + bad_jobs)))
    if config['post_script_console_report']:
        post_script_report(print, data, end_scrape, start_scrape, end_content,
                           start_content, processing_time, processed_data)
        post_script_report(logging.info, data, end_scrape, start_scrape, end_content,
                           start_content, processing_time, processed_data)
    else:
        post_script_report(logging.info, data, end_scrape, start_scrape, end_content,
                           start_content, processing_time, processed_data)
    logging.info("Daily job scrape complete!")
    driver.close()
