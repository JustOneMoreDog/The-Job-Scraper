import json
import logging
import logging.handlers
import os
import random
import re
import time
import urllib.parse
from datetime import datetime
from time import sleep
from urllib.parse import parse_qs, urlparse
from html import escape
import us

import undetected_chromedriver as uc
import yaml
from fake_useragent import UserAgent
from selenium.common import (
    ElementNotInteractableException,
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebElement
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)
from undetected_chromedriver import Chrome, ChromeOptions

from scraper_utils import js_conditions

# Global configuration for our exponential backoff
debug = False
minimum_jitter = int(random.uniform(1, 3))
maximum_jitter = int(random.uniform(8, 10))
exponential_jitter_wait = wait_exponential_jitter(5, 7200, 2, random.uniform(minimum_jitter, maximum_jitter))
small_retry_attempts = stop_after_attempt(3)
max_retry_attempts = stop_after_attempt(10)
retry_if_any_exception = retry_if_exception_type(Exception)


class UnexpectedBehaviorException(Exception):
    pass


class RedirectedException(Exception):
    pass


class TooManyRequestsException(Exception):
    pass


class ElementNotFoundException(Exception):
    pass


class TheJobScraper:

    def __init__(self):
        self.request_counter = 0
        self.current_working_directory = os.path.dirname(os.path.abspath(__file__))
        self.original_url = ""
        self.current_date = datetime.now().strftime("%m_%d_%Y_%H_%M")
        self.setup_logging()
        self.app_config, self.customizations = self.initialize_config_files()
        self.all_jobs = self.initialize_data_files()
        self.driver = None
        self.start_a_fresh_chrome_driver()
        self.logging_number = 0
        self.new_job_scrapes = []
        self.good_jobs = []
        self.bad_jobs = []
        self.current_search = ""
        self.current_location = ""
        self.current_timespan = ""
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
        self.log("Saving new job scrapes for the frontend to ingest")
        self.save_new_job_scrapes()
        self.log("Adding to our new job scrapes to our main job scrape data file")
        self.save_job_scrape(self.new_job_scrapes + self.all_jobs, "all_jobs.json")

    def save_new_job_scrapes(self) -> None:
        self.add_blank_spaces_to_good_jobs()
        new_job_scrapes_filename = self.current_date + ".json"
        new_job_scrapes_path = os.path.abspath(os.path.join(self.current_working_directory, "scrapes", new_job_scrapes_filename))
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

    def iterate_over_searches(self) -> None:
        searches = list(set(self.customizations['searches']))
        for search in searches:
            self.log(f"Scraping LinkedIn for jobs with the keyword '{search}'")
            self.current_search = search
            self.new_good_job_scrapes_for_search = 0
            # For each search phrase in our customizations we will need to search for jobs at each location
            self.iterate_over_locations(search)

    def iterate_over_locations(self, search: str) -> None:
        locations = list(set(self.customizations['locations']))
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
            try:
                _ = self.get_job_postings(search, location, timespan, timespan_button_path)
            except RetryError as e:
                self.log(f"Failed to get job postings for '{search}' in '{location}' for the last '{timespan}'")
                self.log(f"Error: {e}")
                pass

    @retry(
        wait=exponential_jitter_wait,
        stop=max_retry_attempts,
        reraise=False
    )
    def get_job_postings(self, search: str, location: str, timespan: str, timespan_button_path: str) -> bool:
        # Quick breakout check that will prevent us from doing extra work should we already be over the min threshold
        if self.new_good_job_scrapes_for_search >= self.customizations['minimum_good_results_per_search_per_location']:
            self.log("Breaking out because we have found enough good jobs")
            return
        self.log(f"Attempt '{self.get_job_postings.retry.statistics['attempt_number']}' on getting job postings for '{search}' in '{location}' for the last '{timespan}'")
        if self.get_job_postings.retry.statistics['attempt_number'] == max_retry_attempts:
            self.log("!!!WARNING!!! This is our last attempt to do this. If it fails we will just move on")
        self.log("Loading a fresh browser session to start the job scraping process")
        self.start_a_fresh_chrome_driver()
        self.log("Inputting search phrase and location")
        self.input_search_phrase_and_location(search, location)
        if self.there_are_still_results():
            self.log(f"Filtering by timespan '{timespan}'")
            self.filter_results_timespan(timespan_button_path)
        if self.there_are_still_results():
            self.log("Filtering to full time positions")
            self.select_only_full_time_positions()
        if self.there_are_still_results():
            self.log("Filtering down based on remote job preferences")
            try:
                self.select_only_remote_jobs()
            except RetryError:
                self.log("Failed to select only remote jobs but this is not fatal so we will continue on")
                pass
        if self.there_are_still_results():
            self.log("Selecting experience levels")
            try:
                self.select_experience_levels()
            except RetryError:
                self.log("Failed to select experience levels but this is not fatal so we will continue on")
                pass
        if self.there_are_still_results():
            self.log("Getting all job postings that are displayed on the page")
            self.get_all_job_postings()
        return True

    def there_are_still_results(self) -> bool:
        try:
            _ = self.get_web_element(By.CLASS_NAME, self.app_config['no_results'], None, True, False)
            self.log("There are no results being displayed for us")
            return False
        except NoSuchElementException:
            return True
        
    def start_a_fresh_chrome_driver(self) -> None:
        if self.driver:
            self.driver.quit()
            time.sleep(random.uniform(minimum_jitter, maximum_jitter))
        self.driver = self.initialize_chrome_driver()
        self.load_url(self.app_config['starting_url'])

    @retry(
        retry=retry_if_any_exception,
        wait=exponential_jitter_wait,
        stop=small_retry_attempts,
        reraise=True
    )
    def input_search_phrase_and_location(self, search: str, location: str) -> None:
        attempt_number = self.input_search_phrase_and_location.retry.statistics['attempt_number']
        if attempt_number > 1:
            self.log(f"Caught an exception on attempt {attempt_number} of inputting search and location so we are reloading the entire browser")
            self.start_a_fresh_chrome_driver()
        # This is much easier than trying to deal with XPATH
        base_url_string = "https://www.linkedin.com/jobs/search?"
        search_params = f"keywords={search}&location={location}".replace(" ", "%20")
        url_string = base_url_string + search_params
        self.log(f"Loading the URL: '{url_string}'")
        self.load_url(url_string)

    @retry(
        retry=retry_if_any_exception,
        wait=exponential_jitter_wait,
        stop=small_retry_attempts,
        reraise=True
    )
    def filter_results_timespan(self, timespan_button_path: str) -> None:
        attempt_number = self.filter_results_timespan.retry.statistics['attempt_number']
        if attempt_number > 1:
            self.log(f"Caught an exception on attempt {attempt_number} of selecting timespan so we are reloading the entire browser and calling the input_search_phrase_and_location function")
            self.start_a_fresh_chrome_driver()
            self.input_search_phrase_and_location(self.current_search, self.current_location)
        filters_section = self.get_web_element(By.XPATH, self.app_config['filters_section'])
        timespan_dropdown = self.get_web_element(By.XPATH, self.app_config['any_time_button'], filters_section)
        timespan_dropdown.click()
        timespan_button = self.get_web_element(By.XPATH, timespan_button_path)
        timespan_button.click()
        self.find_and_press_done_button()
        self.load_url()

    def select_only_full_time_positions(self) -> None:
        try:
            filters_section = self.get_web_element(By.XPATH, self.app_config['filters_section'])
            job_type_button = self.get_web_element(By.XPATH, self.app_config['job_type_button'], filters_section)
            job_type_button.click()
            full_time_position_button = self.get_web_element(By.XPATH, self.app_config['full_time_button'])
            full_time_position_button.click()
            self.find_and_press_done_button()
            self.load_url()
        except (ElementNotInteractableException, ElementNotFoundException):
            self.log("Could not find the full time position button so we are just going to skip it")
            pass

    @retry(
        retry=retry_if_any_exception,
        wait=exponential_jitter_wait,
        stop=small_retry_attempts,
        reraise=False
    )
    def select_only_remote_jobs(self) -> None:
        attempt_number = self.select_only_remote_jobs.retry.statistics['attempt_number']
        self.log(f"Attempt {attempt_number} to select only remote jobs")
        if attempt_number > 1:
            self.driver.refresh()
            self.load_url()
        filters_section = self.get_web_element(By.XPATH, self.app_config['filters_section'])
        remote_button = self.get_web_element(By.XPATH, self.app_config['on_site_remote_button'], filters_section)
        remote_button.click()
        remote_checkbox = self.get_web_element(By.XPATH, self.app_config['remote_checkbox'])
        remote_checkbox.click()
        if self.customizations['include_hybrid_jobs']:
            self.log("Including hybrid and remote jobs")
            hybrid_checkbox = self.get_web_element(By.XPATH, self.app_config['hybrid_checkbox'])
            hybrid_checkbox.click()
        else:
            self.log("Including only remote jobs because RTO is cringe")
        self.find_and_press_done_button()
        self.load_url()

    @retry(
        retry=retry_if_any_exception,
        wait=exponential_jitter_wait,
        stop=small_retry_attempts,
        reraise=False
    )
    def select_experience_levels(self) -> None:
        attempt_number = self.select_experience_levels.retry.statistics['attempt_number']
        self.log(f"Attempt {attempt_number} to select experience levels")
        if attempt_number > 1:
            self.driver.refresh()
            self.load_url()
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
                exp_level_checkbox = self.get_web_element(
                    By.XPATH, 
                    f"//label[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{experience_level}')]",
                    None,
                    True,
                    False
                )
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
            self.annihilate_the_trackers()
            iteration += 1
            if iteration > 1:
                if self.is_page_sign_in_form():
                    self.log("get_all_job_postings: We have been redirected to the sign in form and we currently do not have a way around this yet")
                    break
            self.log(f"We are on iteration {iteration} with {self.new_good_job_scrapes_for_search} good posts")
            more_jobs_to_load = self.scroll_to_the_infinite_bottom()
            results_list = self.get_job_results_list()
            self.log(f"{len(results_list)} jobs have been loaded on the screen for the job posting scrape")
            self.get_all_job_posting_objects(previous_index)
            self.log(f"Updating the starting point from {previous_index} to {len(results_list)}")
            previous_index = len(results_list)
            if not more_jobs_to_load or (previous_index == len(results_list)):
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
                    self.log("There is a more jobs button and we are going to press it")
                    more_jobs_button.click()
                    self.log("Pressed the more jobs button and returning True")
                    return True
                except (NoSuchElementException, ElementNotInteractableException):
                    self.log("At the bottom and do not see the more jobs button and or cannot interact with it")
                    return False
        self.log("We have scrolled to the bottom 50 times and have not found the more jobs button so we are breaking out")
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
            self.annihilate_the_trackers()
            job_posting_object = JobPosting(job_posting, job_posting_number, self)
            try:
                if job_posting_object.is_a_duplicate():
                    self.log(f"Job posting {job_posting_number} was a duplicate")
                    duplicates += 1
                    continue
                if job_posting_object.is_a_excluded_title_or_company_or_location():
                    job_posting_details = f"'{job_posting_object.title}' at '{job_posting_object.company}' in '{job_posting_object.location}'"
                    self.log(f"Job posting {job_posting_number}, {job_posting_details}, in on the exclusion list")
                    excluded_jobs += 1
                    job_posting_object_json = job_posting_object.get_job_posting_json_data()
                    self.new_job_scrapes.append(job_posting_object_json)
                    continue
                job_posting_object.request_job_posting()
                if job_posting_object.is_a_excluded_industry():
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
            except Exception as e:
                self.annihilate_the_trackers()
                self.log(f"Job posting {job_posting_number} failed with error: {e}")
                if self.is_page_sign_in_form():
                    self.log("get_all_job_posting_objects: We have been redirected to the sign in form and we currently do not have a way around this yet")
                    break
                pass
        self.log("Finished getting the job posting data for this batch")
        self.log(f"Duplicates: {duplicates}, Exclusions: {excluded_jobs}, Valid: {valid_jobs}")
    
    def is_page_sign_in_form(self) -> bool:
        try:
            _ = self.get_web_element(By.XPATH, self.app_config['sign_in_form'])
            # temp debugging
            self.driver.save_screenshot("sign_in_form.png")
            # saving beautiful soup of page to file for debugging
            with open("sign_in_form.html", "w") as f:
                f.write(self.driver.page_source)
            return True
        except NoSuchElementException:
            return False

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
    
    def get_web_element(self, by: By, search_filter: str, element: WebElement = None, is_fatal: bool = True, log_if_not_found: bool = True) -> WebElement:
        try:
            if element:
                desired_web_element = element.find_element(by, search_filter)
            else:
                desired_web_element = self.driver.find_element(by, search_filter)
            return desired_web_element
        except NoSuchElementException as e:
            if log_if_not_found:
                self.log(f"Could not find the '{search_filter}' web element via '{by}'")
            if not is_fatal:
                return None
            raise e
        
    def annihilate_the_trackers(self) -> None:
        if not self.driver.current_url:
            return
        self.driver.delete_all_cookies()
        # TO-DO: Implement more privacy measures to ensure there are absolutely no possible ways I can be tracked client side
        # self.driver.execute_script("window.localStorage.clear();")     

    def load_url(self, url=None) -> None:
        self.request_counter += 1
        self.annihilate_the_trackers()
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
        wait=exponential_jitter_wait,
        stop=max_retry_attempts,
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
        wait=exponential_jitter_wait,
        stop=max_retry_attempts,
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

    def setup_logging(self) -> None:
        scraper_logs_directory = os.path.abspath(os.path.join(self.current_working_directory, "logs", "scraper"))
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
        all_jobs = self.load_json_data() or []
        all_jobs_backup_path = all_jobs_path + ".old"
        self.save_job_scrape(all_jobs, all_jobs_backup_path)
        return all_jobs
    
    def get_random_user_agent(self) -> str:
        agents = UserAgent()
        platforms_choices = [item for item in agents.platforms if item != "mobile" and item != "tablet"]
        os_choices = [item for item in agents.os if item != "android" and item != "ios"]
        user_agent = UserAgent(os=os_choices, platforms=platforms_choices)
        random_agent = user_agent.random
        logging.info(f"Setting user agent to be '{random_agent}'")
        return random_agent

    def initialize_chrome_driver(self) -> Chrome:
        options = ChromeOptions()
        logging.info(f"Setting chrome driver to have headless be '{self.app_config['headless']}'")
        options.headless = self.app_config['headless']
        options.add_argument(f'--user-agent={self.get_random_user_agent()}')
        # Statically defining the window size to ensure consistency and that elements always show up
        options.add_argument(f"--window-size={self.app_config['window_size']}")
        ublock_path = os.path.abspath(os.path.join(self.current_working_directory, "ublock"))
        options.add_argument('--load-extension=' + ublock_path)
        logging.info("uBlock extension added to Chrome driver")
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
    
    def get_web_element(self, by: By, search_filter: str, element: WebElement = None, is_fatal: bool = True, log_if_not_found: bool = True) -> WebElement:
        return self.job_scraper.get_web_element(by, search_filter, element, is_fatal, log_if_not_found)

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
        if not self.url:
            self.log("Could not get a valid URL for the job posting...skipping")
            return True
        split_newly_found_job_url = self.url.split("/view/")
        if len(split_newly_found_job_url) != 2:
            self.log(f"Failed to split the URL, '{self.url}', for the job posting...skipping")
            return True
        newly_found_job_url = split_newly_found_job_url[1].lower()
        self.log(f"Checking if the job posting URL, '{newly_found_job_url}', has been previously scraped")
        for job in (self.newly_scraped_jobs + self.previously_scraped_jobs):
            self.log(f"Previously found job url: '{job['url']}'")
            if not job['url']:
                continue
            previously_found_job_url = job['url'].split("/view/")[1].lower()
            duplicate_job_posting_url = previously_found_job_url == newly_found_job_url
            if duplicate_job_posting_url:
                self.log("Job posting has been previously scraped...skipping")
                return True
        return False

    def get_job_posting_url_pre_request(self) -> None:
        self.url_element = self.get_web_element(By.TAG_NAME, 'a', self.posting_element)
        full_url = self.url_element.get_property(name="href")
        self.log(f"Setting the job posting URL to '{full_url}'") 
        self.url = full_url.split("?")[0]

    def is_a_excluded_title_or_company_or_location(self) -> bool:
        try:
            self.parse_posting_element_text()
        except UnexpectedBehaviorException as e:
            self.log(f"Failed to parse the posting element text: {e}\nSkipping this job posting")
            return True
        if any(t for t in self.customizations['excluded_title_keywords'] if t.lower().strip() in self.title.lower()):
            self.keywords.append("TITLE")
            self.rating = -999
            self.log(f"Skipping as '{self.title}' is in our exclusion list")
            return True
        if any(c for c in self.customizations['excluded_companies'] if c.lower().strip() in self.company.lower()):
            self.keywords.append("COMPANY")
            self.rating = -999
            self.log(f"Skipping as '{self.company}' is in our exclusion list")
            return True
        if any(l for l in self.customizations['excluded_locations'] if l.lower().strip() in self.location.lower()):
            self.keywords.append("LOCATION")
            self.rating = -999
            self.log(f"Skipping as '{self.location}' is in our exclusion list")
            return True
        return False
    
    def parse_posting_element_text(self) -> None:
        posting_element_text = self.posting_element.text.strip().split("\n")
        if len(posting_element_text) == 0:
            raise UnexpectedBehaviorException("Could not find any text in the posting element")
        self.log(f"Parsing the posting element text for job title: '{posting_element_text}'")
        self.pop_title_from_posting_element_text(posting_element_text)
        self.log(f"Parsing the posting element text for unwanted elements: '{posting_element_text}'")
        self.pop_unwanted_elements_from_posting_element_text(posting_element_text)
        self.log(f"Parsing the posting element text for timespan: '{posting_element_text}'")
        self.pop_timespan_from_posting_element_text(posting_element_text)
        self.log(f"Parsing the posting element text for location: '{posting_element_text}'")
        self.pop_location_from_posting_element_text(posting_element_text)
        self.log(f"Parsing the posting element text for company name: '{posting_element_text}'")
        self.pop_company_from_posting_element_text(posting_element_text)

    def pop_company_from_posting_element_text(self, posting_element_text: list[str]) -> None:
        if len(posting_element_text) == 0:
            self.log("No elements left in the posting element text")
            self.company = "Unknown"
            return 
        company = posting_element_text.pop(0)
        self.company = self.clean_string(company)
        self.log(f"Job company has been set to '{self.company}'")
    
    def pop_timespan_from_posting_element_text(self, posting_element_text: list[str]) -> None:
        timespan_elements = [
            'minute',
            'hour',
            'day',
            'week',
            'month',
        ]
        # We do not need to set self.posting_time here because it gets properly set later on
        for timespan_element in timespan_elements:
            for i, element in enumerate(posting_element_text):
                if timespan_element.lower() in element.lower() and " ago" in element.lower():
                    _ = posting_element_text.pop(i)
                    return
    
    def pop_location_from_posting_element_text(self, posting_element_text: list[str]) -> None:
        location = "Unknown"
        # First we try and get an easy win by looking for the state abbreviation 
        location_pattern = r", ([A-Z][A-Z])$"
        states = us.states.STATES_AND_TERRITORIES
        us_state_abbreviations = [state.abbr for state in states]
        us_state_abbreviations.append("DC")
        for i, element in enumerate(posting_element_text):
            match = re.search(location_pattern, element)
            if not match:
                continue
            state_abbreviation = match.group(1)
            if state_abbreviation not in us_state_abbreviations:
                continue
            location = posting_element_text.pop(i)
            self.location = self.clean_string(location)
            self.log(f"Job location has been set to '{self.location}'")
            return
        self.log("Unable to find a location string using state abbreviations")
        # Maybe the locations is just ye ole United States
        for i, element in enumerate(posting_element_text):
            if "United States" in element:
                location = posting_element_text.pop(i)
                self.location = self.clean_string(location)
                self.log(f"Job location has been set to '{self.location}'")
                return
        self.log("Unable to find a location string using United States")
        # Next logical thing to try is our excluded locations and locations list from the customizations file
        for i, element in enumerate(posting_element_text):
            if any(l for l in (self.customizations['excluded_locations'] + self.customizations['locations']) if l.lower().strip() in element.lower()):
                location = posting_element_text.pop(i)
                self.location = self.clean_string(location)
                self.log(f"Job location has been set to '{self.location}'")
                return
        # Based off of testing one last ditch effort to determine the location is to see if there is an element that ends in 'Area'
        for i, element in enumerate(posting_element_text):
            if element.endswith(" Area"):
                location = posting_element_text.pop(i)
                self.location = self.clean_string(location)
                self.log(f"Job location has been set to '{self.location}'")
                return
        self.log("Unable to find a location string using the excluded locations list. This is bad.")
    
    def pop_unwanted_elements_from_posting_element_text(self, posting_element_text: list[str]) -> None:
        unwanted_elements = [
            'Actively Hiring',
            'Be an early applicant'
        ]
        for unwanted_element in unwanted_elements:
            for i, element in enumerate(posting_element_text):
                if unwanted_element.lower() in element.lower():
                    _ = posting_element_text.pop(i)
    
    def pop_title_from_posting_element_text(self, posting_element_text: list[str]) -> None:
        title = posting_element_text.pop(0)
        for i, element in enumerate(posting_element_text):
            if title.lower() in element.lower():
                _ = posting_element_text.pop(i)
        self.title = self.clean_string(title)
        self.log(f"Job title has been set to '{self.title}'")

    def clean_string(self, text: str) -> str:
        text = text.strip()
        text = text.replace('\n', ' ')
        text = ''.join(c for c in text if ord(c) < 128)
        text = text[:200]
        return text

    @retry(
        retry=retry_if_exception_type((TooManyRequestsException, NoSuchElementException)),
        wait=exponential_jitter_wait,
        stop=small_retry_attempts,
        reraise=False
    )
    def request_job_posting(self) -> None:
        self.log("Requesting the job posting details")
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

    def is_a_excluded_industry(self) -> bool:
        self.get_job_posting_industry()
        if any(i for i in self.customizations['excluded_industries'] if i.lower().strip() in self.industry.lower()):
            self.keywords.append("INDUSTRY")
            self.rating = -999
            self.log(f"Skipping as '{self.industry}' is in our exclusion list")
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
        stop=max_retry_attempts,
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
        job_posting_details_escaped = escape(job_posting_content_html)
        return str(job_posting_details_escaped)

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


if __name__ == '__main__':
    scraper = TheJobScraper
    try:
        scraper = TheJobScraper()
        scraper.scrape_jobs_from_linkedin()
        scraper.driver.quit()
        logging.info(f"Execution finished normally with a total of {scraper.request_counter} requests")
    except Exception as e:
        logging.info("!!! RAN INTO AN UNRECOVERABLE ERROR !!!")
        current_directory = os.path.dirname(os.path.abspath(__file__))
        latest_log_path = os.path.abspath(os.path.join(current_directory, "logs/latest/scraper.log"))
        logging.info(f"LOG: {latest_log_path}")
        if scraper.driver:
            screenshot_name = f"error_{str(int(time.time()))}.png"
            screenshot_path = os.path.abspath(os.path.join(current_directory, "logs/screenshots", screenshot_name))
            scraper.driver.save_screenshot(screenshot_path)
            latest_screenshot_path = os.path.abspath(os.path.join(current_directory, "logs/latest/screenshot.png"))
            logging.info(f"SCREENSHOT: {latest_screenshot_path}")
            logging.info(f"URL: {scraper.driver.current_url}")
        logging.exception(f"ERROR:\n{e}")
        raise e
    finally:
        try:
            scraper.driver.quit()
        except Exception:
            pass
