import json
import logging
import logging.handlers
import os
import random
import time
from datetime import datetime
from time import sleep
from urllib.parse import parse_qs, urlparse

import undetected_chromedriver as uc
import yaml
from bs4 import BeautifulSoup
from scraper_utils import js_conditions
from selenium.common import (
    ElementNotInteractableException,
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebElement
from tabulate import tabulate
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    wait_fixed,
)
from undetected_chromedriver import Chrome, ChromeOptions
from fake_useragent import UserAgent

# Global configuration for our exponential backoff
debug = False
minimum_jitter = 2
maximum_jitter = 10
exponential_jitter_wait = wait_exponential_jitter(5, 1200, 5, random.uniform(minimum_jitter, maximum_jitter))
retry_attempts = stop_after_attempt(10)


class RedirectedException(Exception):
    pass


class TooManyRequestsException(Exception):
    pass


class ElementNotFoundException(Exception):
    pass


class TheJobScraper:

    def __init__(self):
        self.current_working_directory = os.path.dirname(os.path.abspath(__file__))
        self.original_url = ""
        self.current_date = datetime.now().strftime("%m_%d_%Y_%H_%M_%S")
        self.init_logging()
        self.app_config, self.customizations = self.initialize_config_files()
        self.all_jobs = self.initialize_data_files()
        self.driver = self.initialize_chrome_driver()
        self.logging_number = 0
        self.new_job_scrapes = []
        self.good_jobs = []
        self.bad_jobs = []
        self.html_output_directory = ""
        self.current_search = ""
        self.current_location = ""
        self.current_timespan = ""
        self.errors = []
        # For each search in each location we will break out if we go over the threshold that
        # is set by the customizations['minimum_good_results_per_search_per_location']
        # This helps lower the amount of work that needs to happen
        self.new_good_job_scrapes_for_search = 0
        self.log("Successfully initialized the job scraper")
        self.log(f"\n-----\nApplication Configuration:\n{self.app_config}\n-----")
        self.log(f"\n-----\nSearch Customizations:\n{self.customizations}\n-----")

    def log(self, message: str) -> None:
        prefix = f"{self.current_search}:{self.current_location}:{self.current_timespan}: "
        logging.info(f"{prefix} {message}")

    def scrape_jobs_from_linkedin(self):
        self.log("Beginning job scraping")
        self.iterate_over_searches()
        self.log("Finished job scraping and starting the post processing")
        self.organize_and_sort_new_job_postings()
        self.log(f"Good {len(self.good_jobs)}, Bad {len(self.bad_jobs)}, Total {len(self.new_job_scrapes)}")
        self.log("Saving new job scrapes into their new destination")
        self.save_new_job_scrapes()
        self.log("Finished post processing saving results")
        self.save_job_scrape(self.good_jobs + self.bad_jobs, "all_jobs.json")
        self.log("Creating HTML output")
        self.create_html_output()

    def save_new_job_scrapes(self) -> None:
        self.add_blank_spaces_to_good_jobs()
        new_job_scrapes_filename = self.current_date + ".json"
        new_job_scrapes_path = os.path.abspath(os.path.join(self.current_working_directory, ".job_scrapes", new_job_scrapes_filename))
        self.save_job_scrape(self.good_jobs + self.bad_jobs, new_job_scrapes_path)

    def organize_and_sort_new_job_postings(self) -> None:
        self.log("Organizing new job postings as either good or bad")
        for job_posting in self.new_job_scrapes:
            if job_posting['rating'] > 0:
                self.good_jobs.append(job_posting)
            else:
                self.bad_jobs.append(job_posting)
        self.log("Sorting the jobs by their rating")
        self.good_jobs.sort(key=lambda x: x['rating'], reverse=True)
        self.bad_jobs.sort(key=lambda x: x['rating'], reverse=True)

    def add_blank_spaces_to_good_jobs(self) -> None:
        blank_job = {"applied": False, "posted_time": "", "location": "", "title": "", "company": "", "industry": "", "rating": "", "keywords": "", "url": "", "search": "", "content": ""}
        for _ in range(0, 4):
            self.good_jobs.append(blank_job)
        self.good_jobs.append({
            "applied": False, "posted_time": "Excluded Jobs", "location": "", "title": "", "company": "", "industry": "", "rating": "", "keywords": "Note: LOCation, COMPany, TITLE", "search": "", "url": "", "content": ""
        })

    def create_html_output(self) -> None:
        self.create_html_directory()
        for job_posting in (self.good_jobs + self.bad_jobs):
            self.create_content_html_output(job_posting)
            self.change_url_to_href_tag(job_posting)
        self.add_blank_spaces_to_good_jobs()
        combined_list_of_job_postings = self.good_jobs + self.bad_jobs
        tabulate_of_job_postings = tabulate(combined_list_of_job_postings, headers="keys", tablefmt="unsafehtml")
        html_job_posting_table = BeautifulSoup(tabulate_of_job_postings, "html.parser")
        index_path = os.path.join(self.html_output_directory, "index.html")
        with open(index_path, "w") as f:
            f.write(str(html_job_posting_table.prettify()))

    def create_html_directory(self) -> None:
        templates_folder = os.path.abspath(os.path.join(self.current_working_directory, self.app_config['html_folder']))
        this_scrapes_folder = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        this_scrapes_folder_path = os.path.join(templates_folder, this_scrapes_folder)
        if not os.path.exists(this_scrapes_folder_path):
            os.mkdir(this_scrapes_folder_path)
        self.html_output_directory = this_scrapes_folder_path
        self.log(f"Output directory set to {this_scrapes_folder_path}")

    def change_url_to_href_tag(self, job_posting: dict) -> None:
        soup = BeautifulSoup(self.get_base_html(), "html.parser")
        post_link = soup.new_tag('a', href=job_posting['url'], target="_blank", rel="noopener noreferrer")
        post_link.string = "Job Posting"
        job_posting['url'] = str(post_link)

    def create_content_html_output(self, job_posting: dict) -> None:
        # Rather than having the content in the table, we make a different html page for it
        # This ensures that the table looks clean and is easy to read
        content_folder_name = job_posting['url'].split("/")[-1]
        content_folder_full_path = os.path.join(self.html_output_directory, content_folder_name)
        os.mkdir(content_folder_full_path)
        content_html_path = os.path.join(content_folder_full_path, "content.html")
        page_soup = BeautifulSoup(self.get_base_html(), "html.parser")
        content_soup = BeautifulSoup(job_posting['content'], "html.parser")
        page_soup.body.append(content_soup)
        with open(content_html_path, "w", encoding='utf-8') as f:
            f.write(page_soup.prettify())
        # Now we modify the content data to be a link to this newly created page
        relative_html_output_directory = self.html_output_directory.split("/")[-1]
        content_folder_relative_path = os.path.join(relative_html_output_directory, content_folder_name)
        a_tag = page_soup.new_tag('a', href=content_folder_relative_path, target="_blank", rel="noopener noreferrer")
        a_tag.string = "Content"
        job_posting['content'] = str(a_tag.prettify())

    @staticmethod
    def get_base_html() -> str:
        return """
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

    def iterate_over_searches(self) -> None:
        for search in self.customizations['searches']:
            self.log(f"Scraping LinkedIn for jobs with the keyword '{search}'")
            self.current_search = search
            self.new_good_job_scrapes_for_search = 0
            # For each search phrase in our customizations we will need to search for jobs at each location
            self.iterate_over_locations(search)

    def iterate_over_locations(self, search: str) -> None:
        locations = self.customizations['locations']
        # For each location we will take our search phrase and check for jobs across the three timespans
        for location in locations:
            self.current_location = location
            self.log(f"Scraping jobs for in '{location}'")
            self.iterate_over_timespans(search, location)
            self.log(f"Finished with '{location}' and got {self.new_good_job_scrapes_for_search} new good posts")
            self.new_good_job_scrapes_for_search = 0

    def iterate_over_timespans(self, search: str, location: str) -> None:
        # Now that we have our search phrase and our location we can actually start scraping jobs
        timespan_map = {
            "day": self.app_config['past_day_button'],
            "week": self.app_config['past_week_button'],
            "month": self.app_config['past_month_button']
        }
        for timespan, timespan_button_path in timespan_map.items():
            self.current_timespan = timespan
            self.log(f"Checking last '{timespan}' with {self.new_good_job_scrapes_for_search} good posts found so far")
            self.get_job_postings(search, location, timespan, timespan_button_path)

    def get_job_postings(self, search: str, location: str, timespan: str, timespan_button_path: str) -> None:
        # Quick breakout check that will prevent us from doing extra work should we already be over the min threshold
        if self.new_good_job_scrapes_for_search >= self.customizations['minimum_good_results_per_search_per_location']:
            self.log("Breaking out because we have found enough good jobs")
            return
        self.load_url(self.app_config['starting_url'])
        self.log("Inputting search phrase and location")
        self.input_search_phrase_and_location(search, location)
        if self.there_are_still_results():
            self.log(f"Filtering by timespan '{timespan}'")
            self.filter_results_timespan(timespan_button_path)
        if self.there_are_still_results():
            self.log("Filtering to full time positions")
            self.select_only_full_time_positions()
        if self.there_are_still_results():
            if self.customizations['include_hybrid_jobs']:
                self.log("Including hybrid and remote jobs")
            else:
                self.log("Including only remote jobs because RTO is cringe")
            try:
                self.select_only_remote_jobs()
            except NoSuchElementException:
                self.log("We could not find any remote jobs")
                return
        if self.there_are_still_results():
            self.log("Selecting experience levels")
            self.select_experience_levels()
        if self.there_are_still_results():
            self.log("Getting all job postings that are displayed on the page")
            self.get_all_job_postings()

    def there_are_still_results(self) -> bool:
        try:
            _ = self.get_web_element(By.CLASS_NAME, self.app_config['no_results'])
            self.log("There are now no results being displayed")
            return False
        except NoSuchElementException:
            return True

    def input_search_phrase_and_location(self, search: str, location: str) -> None:
        self.search_for_jobs_with_phrase(search)
        self.limit_search_results_to_location(location)
        self.load_url()

    def search_for_jobs_with_phrase(self, search: str) -> None:
        keywords_input_box = self.get_web_element(By.ID, self.app_config['keywords_input_box'])
        keywords_input_box.click()
        keywords_input_box.clear()
        keywords_input_box.send_keys(search)

    def limit_search_results_to_location(self, location: str) -> None:
        location_input = self.get_web_element(By.ID, self.app_config['location_input_box'])
        location_input.click()
        location_input.clear()
        location_input.send_keys(location + Keys.ENTER)

    @retry(
        retry=retry_if_exception_type(ElementNotInteractableException),
        wait=wait_fixed(2),
        stop=stop_after_attempt(3),
        reraise=True
    )
    def filter_results_timespan(self, timespan_button_path: str) -> None:
        filters_section = self.get_web_element(By.XPATH, self.app_config['filters_section'])
        timespan_dropdown = self.get_web_element(By.XPATH, self.app_config['any_time_button'], filters_section)
        timespan_dropdown.click()
        timespan_button = self.get_web_element(By.XPATH, timespan_button_path)
        timespan_button.click()
        self.find_and_press_done_button()
        self.load_url()

    @retry(
        retry=retry_if_exception_type(ElementNotInteractableException),
        wait=wait_fixed(2),
        stop=stop_after_attempt(3),
        reraise=True
    )
    def select_only_full_time_positions(self) -> None:
        filters_section = self.get_web_element(By.XPATH, self.app_config['filters_section'])
        job_type_button = self.get_web_element(By.XPATH, self.app_config['job_type_button'], filters_section)
        job_type_button.click()
        full_time_position_button = self.get_web_element(By.XPATH, self.app_config['full_time_button'])
        full_time_position_button.click()
        self.find_and_press_done_button()
        self.load_url()

    @retry(
        retry=retry_if_exception_type(ElementNotInteractableException),
        wait=wait_fixed(2),
        stop=stop_after_attempt(3),
        reraise=True
    )
    def select_only_remote_jobs(self) -> None:
        filters_section = self.get_web_element(By.XPATH, self.app_config['filters_section'])
        remote_button = self.get_web_element(By.XPATH, self.app_config['on_site_remote_button'], filters_section)
        remote_button.click()
        remote_checkbox = self.get_web_element(By.XPATH, self.app_config['remote_checkbox'])
        remote_checkbox.click()
        if self.customizations['include_hybrid_jobs']:
            hybrid_checkbox = self.get_web_element(By.XPATH, self.app_config['hybrid_checkbox'])
            hybrid_checkbox.click()
        self.find_and_press_done_button()
        self.load_url()

    def select_experience_levels(self) -> None:
        filters_section = self.get_web_element(By.XPATH, self.app_config['filters_section'])
        experience_level_button = self.get_web_element(By.XPATH, self.app_config['exp_level_button'], filters_section, False)
        if not experience_level_button:
            return
        experience_level_button.click()
        experience_levels = self.customizations['experience_levels']
        target_experience_levels = [y for y in experience_levels.keys() if experience_levels[y]]
        element_found = False
        for experience_level in target_experience_levels:
            try:
                exp_level_checkbox = self.get_web_element(By.XPATH, f"//label[contains(text(), '{experience_level}')]")
                exp_level_checkbox.click()
                element_found = True
            except NoSuchElementException:
                continue
        if element_found:
            self.find_and_press_done_button()
            self.load_url()
            return
        self.log("Could not find target experience levels checking if it was an error")
        for experience_level in experience_levels.keys():
            try:
                _ = self.get_web_element(By.XPATH, f"//label[contains(text(), '{experience_level}')]")
                self.log("Not an error we are fine")
                return
            except NoSuchElementException:
                continue
        raise ElementNotFoundException("Could not find any experience level checkboxes")

    def get_all_job_postings(self) -> None:
        previous_index = 0
        iteration = 0
        while self.new_good_job_scrapes_for_search < self.customizations['minimum_good_results_per_search_per_location']:
            iteration += 1
            self.log(f"We are on iteration {iteration} with {self.new_good_job_scrapes_for_search} good posts")
            more_jobs_to_load = self.scroll_to_the_infinite_bottom()
            results_list = self.get_job_results_list()
            self.log(f"{len(results_list)} jobs have been loaded on the screen for the job posting scrape")
            self.get_all_job_posting_objects(previous_index)
            self.log(f"Updating the starting point from {previous_index} to {len(results_list)}")
            previous_index = len(results_list)
            if not more_jobs_to_load:
                self.log("There are no more jobs to load")
                break

    def scroll_to_the_infinite_bottom(self) -> bool:
        # We do not use while true as a safety precaution against never ending scrolling
        for _ in range(0, 50):
            self.driver.execute_script(self.app_config['scroll_to_bottom_script'])
            self.load_url()
            page_height_script = self.driver.execute_script(self.app_config['page_height_script']) - 1
            total_scrolled_height = self.driver.execute_script(self.app_config['total_scrolled_height'])
            if page_height_script <= total_scrolled_height:
                try:
                    more_jobs_button = self.get_web_element(By.XPATH, self.app_config['see_more_jobs_button'])
                    more_jobs_button.click()
                    return True
                except (NoSuchElementException, ElementNotInteractableException):
                    self.log("At the bottom and do not see the more jobs button")
                    return False
        return True

    def get_job_results_list(self) -> list:
        all_job_postings_section = self.get_web_element(By.XPATH, self.app_config['job_results_list'])
        all_job_postings = all_job_postings_section.find_elements(By.TAG_NAME, "li")
        if not all_job_postings:
            raise ElementNotFoundException("Did not find any entries in job results list section")
        return all_job_postings

    def get_all_job_posting_objects(self, starting_index: int) -> None:
        all_job_postings = self.get_job_results_list()
        self.log(f"Checking results from {starting_index}->{len(all_job_postings)}")
        duplicates = 0
        excluded_jobs = 0
        valid_jobs = 0
        for job_posting_number, job_posting in enumerate(all_job_postings[starting_index:]):
            job_posting_object = JobPosting(job_posting, job_posting_number, self)
            try:
                if job_posting_object.is_a_duplicate():
                    self.log(f"Job posting {job_posting_number} was a duplicate")
                    duplicates += 1
                    continue
                if job_posting_object.is_a_excluded_title_or_company():
                    self.log(f"Job posting {job_posting_number}, '{job_posting_object.title}', on exclusion list")
                    excluded_jobs += 1
                    job_posting_object_json = job_posting_object.get_job_posting_json_data()
                    self.new_job_scrapes.append(job_posting_object_json)
                    continue
                job_posting_object.request_job_posting()
                if job_posting_object.is_a_excluded_industry_or_location():
                    self.log(f"Job posting {job_posting_number}, '{job_posting_object.industry}', on exclusion list")
                    excluded_jobs += 1
                    job_posting_object_json = job_posting_object.get_job_posting_json_data()
                    self.new_job_scrapes.append(job_posting_object_json)
                    continue
                job_posting_object.populate_job_posting_data()
                job_posting_object_json = job_posting_object.get_job_posting_json_data()
                self.new_job_scrapes.append(job_posting_object_json)
                self.new_good_job_scrapes_for_search += 1
                valid_jobs += 1
            except (TooManyRequestsException, NoSuchElementException, StaleElementReferenceException) as e:
                self.log(f"Job posting {job_posting_number} failed with error: {e}")
                self.process_exception(e)
                pass
        self.log("Finished getting the job posting data for this batch")
        self.log(f"Duplicates: {duplicates}, Exclusions: {excluded_jobs}, Valid: {valid_jobs}")

    def process_exception(self, e: Exception) -> None:
        self.errors.append(e)
        if len(self.errors) >= 10:
            self.log("Too many errors have occurred")
            for x, error in enumerate(self.errors):
                self.log(f"Error {x}:\n{error}")
            raise e
        pass

    def find_and_press_done_button(self) -> None:
        done_buttons = self.driver.find_elements(By.XPATH, self.app_config['done_button'])
        if not done_buttons:
            raise ElementNotFoundException("Could not find any done buttons")
        done_button = None
        for button in done_buttons:
            correct_accessible_name = 'done' in button.accessible_name.lower()
            correct_aria_role = 'button' in button.aria_role.lower()
            if correct_accessible_name and correct_aria_role:
                done_button = button
                break
        if not done_button:
            raise ElementNotFoundException("Could not find the correct done button")
        done_button.click()

    def get_web_element(self, by: By, search_filter: str, element: WebElement = None, is_fatal: bool = True) -> WebElement:
        try:
            if element:
                desired_web_element = element.find_element(by, search_filter)
            else:
                desired_web_element = self.driver.find_element(by, search_filter)
            return desired_web_element
        except NoSuchElementException as e:
            self.log(f"Could not find the '{search_filter}' web element via '{by}'")
            if not is_fatal:
                return None
            raise e

    def load_url(self, url=None) -> None:
        self.driver.delete_all_cookies()
        if url:
            self.driver.get(url)
        # Stolen code that performs a bunch of checks to verify the page has loaded
        self.wait_for_page_to_load()
        # Lastly we will need to check to make sure we have not been hit with a 429
        self.check_for_http_too_many_requests()
        # Next we have to check to make sure that we have not been redirected
        self.check_for_redirect()
        # Then we sprinkle in some random sleep to pretend we are human (we are not)
        sleep(random.uniform(minimum_jitter, maximum_jitter))

    def wait_for_page_to_load(self) -> None:
        js_conditions.wait_for_page_load(self.driver)

    @retry(
        retry=retry_if_exception_type(RedirectedException),
        wait=wait_exponential_jitter(5, 300, 3, random.uniform(2, 5)),
        stop=stop_after_attempt(5),
        reraise=True
    )
    def check_for_redirect(self) -> None:
        attempt_number = self.check_for_redirect.retry.statistics['attempt_number']
        if attempt_number > 1:
            self.driver.get(self.original_url)
            self.wait_for_page_to_load()
        current_url = self.driver.current_url
        parsed_url_queries = urlparse(current_url).query
        if not parsed_url_queries:
            raise RedirectedException("There were no url queries which means something is extremely off")
        for check in self.app_config['redirect_checks']:
            if check in parse_qs(parsed_url_queries):
                self.original_url = str(parse_qs(parsed_url_queries)[check][0])
                raise RedirectedException("LinkedIn redirected us and so we need to sleep")

    @retry(
        retry=retry_if_exception_type(TooManyRequestsException),
        wait=wait_exponential_jitter(5, 300, 3, random.uniform(2, 5)),
        stop=stop_after_attempt(5),
        reraise=True
    )
    def check_for_http_too_many_requests(self) -> None:
        attempt_number = self.check_for_http_too_many_requests.retry.statistics['attempt_number']
        if attempt_number > 1:
            self.driver.refresh()
            self.wait_for_page_to_load()
        http_429_check = self.driver.find_elements(By.XPATH, self.app_config['http_429_xpath'])
        if http_429_check:
            raise TooManyRequestsException("We have been hit with HTTP 429 and so we need to sleep")
        network_down_message = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Your LinkedIn Network Will Be Back Soon')]")
        if network_down_message:
            raise TooManyRequestsException("We have been hit with a network down message and so we need to sleep")

    def init_logging(self) -> None:
        scraper_logs_directory = os.path.abspath(os.path.join(self.current_working_directory, "scraper_logs"))
        scraper_backup_directory = os.path.abspath(os.path.join(self.current_working_directory, "scrape_backups"))
        if not os.path.exists(scraper_logs_directory):
            os.mkdir(scraper_logs_directory)
        if not os.path.exists(scraper_backup_directory):
            os.mkdir(scraper_logs_directory)
        if debug:
            log_filename = "ide_debug_logs.log"
            # Clears the file
            with open(os.path.join(scraper_logs_directory, log_filename), 'w') as _:
                pass
        else:
            log_filename = self.current_date + ".log"
        log_filepath = os.path.join(scraper_logs_directory, log_filename)
        logging.basicConfig(filename=log_filepath, level=logging.INFO, filemode="w")
        logging.info("Logging has been setup for job scraper")

    @staticmethod
    def save_job_scrape(data: list, filepath: str) -> None:
        with open(filepath, "w") as f:
            json.dump(obj=data, fp=f)

    def load_json_data(self) -> dict:
        with open(self.app_config['jobs_filepath'], "r") as f:
            return json.load(f)

    @staticmethod
    def initialize_config_files() -> tuple[dict, dict]:
        if not os.path.exists("config.yaml"):
            logging.error("Config file is missing")
            exit(-1)
        if not os.path.exists("customizations.yaml"):
            logging.error("Customizations file is missing")
            exit(-1)
        with open("config.yaml", "r") as f:
            app_config = yaml.load(f, Loader=yaml.FullLoader)
        with open("customizations.yaml", "r") as f:
            customizations = yaml.load(f, Loader=yaml.FullLoader)
        return app_config, customizations

    def initialize_data_files(self) -> list:
        # Makes sure that our JSON and HTML data files are created and ready for use
        all_jobs_path = self.app_config['jobs_filepath']
        if not os.path.exists(all_jobs_path):
            self.save_job_scrape([], all_jobs_path)
        html_path = os.path.abspath(os.path.join(self.current_working_directory, self.app_config['html_folder']))
        if not os.path.exists(html_path):
            os.mkdir(html_path)
        all_jobs = self.load_json_data() or []
        all_jobs_backup_path = all_jobs_path + ".old"
        self.save_job_scrape(all_jobs, all_jobs_backup_path)
        return all_jobs

    def initialize_chrome_driver(self) -> Chrome:
        options = ChromeOptions()
        user_agent = UserAgent()
        logging.info(f"Setting chrome driver to have headless be '{self.app_config['headless']}'")
        options.headless = self.app_config['headless']
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f'user-agent={user_agent.random}')
        # Statically defining the window size to ensure consistency and that elements always show up
        options.add_argument(f"--window-size={self.app_config['window_size']}")
        chrome_driver_executable_path = os.path.abspath(os.path.join(self.current_working_directory, self.app_config['chrome_driver_executable_path']))
        logging.info(f"Chrome driver executable path is '{chrome_driver_executable_path}'")
        return uc.Chrome(executable_path=chrome_driver_executable_path, options=options)


class JobPosting:

    def __init__(self, element: WebElement, element_index: int, job_scraper_object: TheJobScraper):
        # Properties from the job scraper
        self.job_scraper = job_scraper_object
        self.posting_element = element
        self.element_index = element_index
        self.previously_scraped_jobs = job_scraper_object.all_jobs
        self.newly_scraped_jobs = job_scraper_object.new_job_scrapes
        self.driver = job_scraper_object.driver
        self.app_config = job_scraper_object.app_config
        self.customizations = job_scraper_object.customizations
        self.current_search = job_scraper_object.current_search
        # Actual job posting properties
        self.url_element = WebElement
        self.url = ""
        self.title = ""
        self.company = ""
        self.content = ""
        self.posted_time = ""
        self.industry = ""
        self.location = ""
        self.keywords = []
        self.rating = 0

    def log(self, message):
        self.job_scraper.log(message)

    def get_job_posting_json_data(self) -> dict:
        return {
            "Applied": False,
            "posted_time": self.posted_time,
            "title": self.title,
            "company": self.company,
            "industry": self.industry,
            "location": self.location,
            "rating": self.rating,
            "keywords": ','.join(self.keywords),
            "search": self.current_search,
            "url": self.url,
            "content": self.content,
        }

    def is_a_duplicate(self) -> bool:
        self.get_job_posting_url_pre_request()
        for job in (self.previously_scraped_jobs + self.newly_scraped_jobs):
            duplicate = job['url'] == self.url
            if duplicate:
                self.log("Job posting has been previously scraped...skipping")
                return True
        return False

    def get_job_posting_url_pre_request(self) -> None:
        self.url_element = self.get_web_element(By.TAG_NAME, 'a', self.posting_element)
        full_url = self.url_element.get_property(name="href")
        self.url = full_url.split("?")[0]

    def is_a_excluded_title_or_company(self) -> bool:
        self.get_job_posting_title_pre_request()
        if any(t for t in self.customizations['excluded_title_keywords'] if t.lower().strip() in self.title.lower()):
            self.keywords.append("TITLE")
            self.rating = -999
            self.log(f"Skipping as '{self.title}' is in our exclusion list")
            return True
        self.get_job_posting_company_pre_request()
        if any(c for c in self.customizations['excluded_companies'] if c.lower().strip() in self.company.lower()):
            self.keywords.append("COMPANY")
            self.rating = -999
            self.log(f"Skipping as '{self.company}' is in our exclusion list")
            return True
        return False

    def get_job_posting_title_pre_request(self) -> None:
        self.url_element = self.get_web_element(By.TAG_NAME, 'a', self.posting_element)
        self.title = self.url_element.text.strip()

    def get_job_posting_company_pre_request(self) -> None:
        hidden_company_tags = self.driver.find_elements(By.XPATH, self.app_config["company_name_pre_request"])
        if not hidden_company_tags:
            raise ElementNotFoundException("Could not find the hidden company name tags")
        if len(hidden_company_tags) <= self.element_index:
            raise ElementNotFoundException("Could not find the hidden company name tag")
        hidden_company_tag = hidden_company_tags[self.element_index]
        self.company = hidden_company_tag.text.strip()

    @retry(
        retry=retry_if_exception_type((TooManyRequestsException, NoSuchElementException)),
        wait=exponential_jitter_wait,
        stop=retry_attempts,
        reraise=True
    )
    def request_job_posting(self) -> None:
        attempt_number = self.request_job_posting.retry.statistics["attempt_number"]
        if attempt_number > 1:
            self.log(f"This is attempt {attempt_number} to request the job posting details")
        self.url_element = self.get_web_element(By.TAG_NAME, 'a', self.posting_element)
        self.url_element.click()
        sleep(random.uniform(minimum_jitter, maximum_jitter))
        try:
            self.check_job_posting_is_loaded()
        except (TooManyRequestsException, NoSuchElementException) as e:
            self.log(f"Attempt {attempt_number} to get job posting details failed")
            self.refresh_element_selection()
            # Now that we have refreshed our posting_element we can have the retry class start the function over
            raise e

    def is_a_excluded_industry_or_location(self) -> bool:
        self.get_job_posting_industry()
        if any(i for i in self.customizations['excluded_industries'] if i.lower().strip() in self.industry.lower()):
            self.keywords.append("INDUSTRY")
            self.rating = -999
            self.log(f"Skipping as '{self.industry}' is in our exclusion list")
            return True
        self.get_job_posting_location()
        if any(m for m in self.customizations['excluded_locations'] if m.lower().strip() in self.location.lower()):
            self.keywords.append("LOCATION")
            self.rating = -999
            self.log(f"Skipping as '{self.location}' is in our exclusion list")
            return True
        return False

    def check_job_posting_is_loaded(self) -> None:
        job_posting_section = self.get_web_element(By.XPATH, self.app_config['job_posting_div_area'])
        company_name_check = self.get_web_element(By.XPATH, self.app_config['company_name_check'], job_posting_section)
        job_posting_company_text = company_name_check.text.strip()
        if not job_posting_company_text:
            # The section that is supposed to load will just be a blank white space and not actually tell us
            # that it is because we have been 429-ed, so we check for empty string and the raise accordingly
            raise TooManyRequestsException("Could not find the job posting company name")

    def refresh_element_selection(self) -> None:
        # We can sometimes go too fast and end up with a Too Many Requests exception
        # We can usually correct the situation by simply taking a pause and reloading the posting_element
        sleep(random.uniform(minimum_jitter, maximum_jitter))
        all_job_postings_section = self.get_web_element(By.XPATH, self.app_config['job_results_list'])
        all_job_postings = all_job_postings_section.find_elements(By.TAG_NAME, "li")
        if self.element_index == 0:
            different_element_index = 1
        else:
            different_element_index = self.element_index - 1
        different_job_posting = all_job_postings[different_element_index]
        different_url_element = self.get_web_element(By.TAG_NAME, 'a', different_job_posting)
        different_url_element.click()
        sleep(random.uniform(minimum_jitter, maximum_jitter))

    @retry(
        retry=retry_if_exception_type(StaleElementReferenceException),
        wait=exponential_jitter_wait,
        stop=retry_attempts,
        reraise=True
    )
    def populate_job_posting_data(self) -> None:
        # By the time we have reached this function we should have the following
        # title, industry, company, location, and url
        # This leaves us with only needing to get
        # content, keywords, posted time, and rating
        try:
            self.content = self.get_job_posting_content()
            self.posted_time = self.get_job_posting_date()
            self.get_job_posting_keywords_and_rating()
        except StaleElementReferenceException as e:
            self.log(f"'{self.title}' at '{self.company}' triggered the follow error\n{e}")
            self.refresh_element_selection()
            # Now that we have refreshed our posting_element we can have the retry class start the function over
            raise e

    def get_web_element(self, by: By, search_filter: str, element: WebElement = None) -> WebElement:
        try:
            if element:
                desired_web_element = element.find_element(by, search_filter)
            else:
                desired_web_element = self.driver.find_element(by, search_filter)
            return desired_web_element
        except NoSuchElementException as e:
            self.log(f"Could not find the '{search_filter}' web element via '{by}'")
            raise e

    def get_job_posting_keywords_and_rating(self) -> None:
        # Iterate through the job content and see if there are any keywords we care about
        job_content_lower = self.content.lower()
        for keyword, rating in self.customizations['word_weights'].items():
            if keyword.lower() in job_content_lower:
                self.keywords.append(keyword)
                self.rating += rating

    def get_job_posting_content(self) -> str:
        job_posting_details = self.get_web_element(By.XPATH, self.app_config['job_posting_details_section'])
        job_posting_content_html = job_posting_details.get_attribute('innerHTML')
        job_posting_details_soup = BeautifulSoup(job_posting_content_html, "html.parser")
        return str(job_posting_details_soup.prettify())

    def get_job_posting_date(self) -> str:
        job_posting_date_element = self.get_web_element(
            By.XPATH, self.app_config['job_posting_date'], self.posting_element
        )
        job_posting_date = job_posting_date_element.get_attribute(name="datetime")
        return job_posting_date

    def get_job_posting_industry(self) -> None:
        job_posting_industry_section = self.driver.find_elements(By.XPATH, self.app_config['job_posting_industry'])
        if not job_posting_industry_section:
            raise ElementNotFoundException("Could not find the job industry section")
        for sub_section in job_posting_industry_section:
            sub_section_title = self.get_web_element(By.TAG_NAME, "h3", sub_section)
            if not sub_section_title.text.strip() == "Industries":
                continue
            sub_section_name = self.get_web_element(By.TAG_NAME, "span", sub_section)
            sub_section_text = sub_section_name.text.strip()
            self.industry = sub_section_text

    def get_job_posting_location(self) -> None:
        job_posting_location = self.get_web_element(
            By.XPATH, self.app_config['job_posting_location'], self.posting_element
        )
        job_posting_location_text = job_posting_location.text.strip()
        self.location = job_posting_location_text


if __name__ == '__main__':
    scraper = TheJobScraper
    try:
        scraper = TheJobScraper()
        scraper.scrape_jobs_from_linkedin()
        scraper.driver.close()
    except Exception as e:
        screenshot_name = f"error_{str(int(time.time()))}.png"
        current_directory = os.path.dirname(os.path.abspath(__file__))
        screenshot_path = os.path.abspath(os.path.join(current_directory, "scraper_logs/screenshots", screenshot_name))
        scraper.driver.save_screenshot(screenshot_path)
        logging.info("!!! RAN INTO A NEW ERROR THAT WE HAVE NOT SEEN BEFORE !!!")
        logging.info(f"Saving screenshot of the session at {screenshot_path}")
        raise e
    finally:
        try:
            scraper.driver.close()
        except Exception:
            pass
