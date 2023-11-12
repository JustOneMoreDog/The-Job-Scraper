"""This module contains different JavaScript conditions that can be used with WebDriverWait,

    The wait_for_page_load(driver,timeout) method is not using WebDriverWait, and this is done
    to have better polling precision and reduce execution time to the minimum required amount.

    Worst-case execution time of '.wait_for_page_load()' method is 0.55s.
    The term 'worst-case' refers to the situation where all conditions were met prior calling the method.
    To prevent flakiness some conditions require several confirmations to be met.
    The table below shows (ordered) details for every check that is done:

        CONDITION                    CONFIRMATIONS    POLL_FREQUENCY    WORST_CASE
        -------------------------  ---------------  ----------------  ------------
        document_visible                         4             0.025         0.100
        document_ready                           4             0.025         0.100
        navigation_completed                     1             0.025         0.025
        jquery_defined                           1             0.005         0.005
        jquery_active_defined                    1             0.005         0.005
        jquery_not_active                       10             0.005         0.050
        jquery_animations_defined                1             0.005         0.005
        jquery_animations_ready                 10             0.005         0.050
        angular_defined                          1             0.005         0.005
        angular_ready                           10             0.005         0.050
        angular5_defined                         1             0.005         0.005
        angular5_ready                          10             0.005         0.050
        spinner_gone                             5             0.010         0.050
        no_new_elements                          5             0.010         0.050

        Worst-case total: 0.550s.
"""
import logging
from time import perf_counter

from selenium.common.exceptions import JavascriptException
from selenium.webdriver.remote.webdriver import WebDriver
from tabulate import tabulate

_log = logging.getLogger(__name__)
_log.addHandler(logging.NullHandler())

PAGE_LOAD_TIMEOUT = 60


class JsCondition:
    name: str
    script: str
    timeout: float
    poll_frequency: float
    confirmations_needed: int
    confirmations_received: int
    on_success: str
    on_fail: str

    def __init__(self):
        self.confirmations_received = 0

    def __call__(self, driver):
        if driver.execute_script(self.script):
            self.confirmations_received += 1
            return self.confirmations_received >= self.confirmations_needed
        else:
            self.confirmations_received = 0
            return False


class DocumentVisible(JsCondition):
    name = "document_visible"
    script = "return document.visibilityState == 'visible';"
    confirmations_needed = 4
    timeout = 5
    poll_frequency = 0.025
    on_success = "document_ready"
    on_fail = "document_ready"


class DocumentReady(JsCondition):
    name = "document_ready"
    script = "return document.readyState == 'complete';"
    confirmations_needed = 4
    timeout = 10
    poll_frequency = 0.025
    on_success = "navigation_completed"
    on_fail = "navigation_completed"


class NavigationCompleted(JsCondition):
    name = "navigation_completed"
    script = "return window.performance.timing.loadEventEnd - window.performance.timing.navigationStart > 0;"
    confirmations_needed = 1
    timeout = 10
    poll_frequency = 0.025
    on_success = "jquery_defined"
    on_fail = "jquery_defined"


class JqueryDefined(JsCondition):
    name = "jquery_defined"
    script = "return !(typeof jQuery === 'undefined' || jQuery === null);"
    confirmations_needed = 1
    timeout = 0.01
    poll_frequency = 0.005
    on_success = "jquery_active_defined"
    on_fail = "angular_defined"


class JqueryActiveDefined(JsCondition):
    name = "jquery_active_defined"
    script = "return !(typeof jQuery.active === 'undefined' || jQuery.active === null);"
    confirmations_needed = 1
    timeout = 0.01
    poll_frequency = 0.005
    on_success = "jquery_not_active"
    on_fail = "jquery_animations_defined"


class JqueryNotActive(JsCondition):
    name = "jquery_not_active"
    script = "return jQuery.active == 0;"
    confirmations_needed = 10
    timeout = 30
    poll_frequency = 0.005
    on_success = "jquery_animations_defined"
    on_fail = "jquery_animations_defined"


class JqueryAnimationsDefined(JsCondition):
    name = "jquery_animations_defined"
    script = "return !(typeof jQuery(':animated') === 'undefined' || jQuery(':animated') === null);"
    confirmations_needed = 1
    timeout = 0.01
    poll_frequency = 0.005
    on_success = "jquery_animations_ready"
    on_fail = "angular_defined"


class JqueryAnimationsReady(JsCondition):
    name = "jquery_animations_ready"
    script = "return jQuery(':animated').length == 0;"
    confirmations_needed = 10
    timeout = 10
    poll_frequency = 0.005
    on_success = "angular_defined"
    on_fail = "angular_defined"


class AngularDefined(JsCondition):
    name = "angular_defined"
    script = "return !(typeof angular === 'undefined' || angular === null);"
    confirmations_needed = 1
    timeout = 0.01
    poll_frequency = 0.005
    on_success = "angular_ready"
    on_fail = "angular5_defined"


class AngularReady(JsCondition):
    name = "angular_ready"
    script = "return angular.posting_element(document).injector().get('$http').pendingRequests.length == 0;"
    confirmations_needed = 10
    timeout = 10
    poll_frequency = 0.005
    on_success = "angular5_defined"
    on_fail = "angular5_defined"


class Angular5Defined(JsCondition):
    name = "angular5_defined"
    script = ("return (typeof getAllAngularRootElements !== 'undefined') "
              "&& (getAllAngularRootElements()[0].attributes['ng-version'] != undefined);")
    confirmations_needed = 1
    timeout = 0.01
    poll_frequency = 0.005
    on_success = "angular5_ready"
    on_fail = "spinner_gone"


class Angular5Ready(JsCondition):
    name = "angular5_ready"
    script = "return window.getAllAngularTestabilities().findIndex(x=>!x.isStable()) == -1;"
    confirmations_needed = 10
    timeout = 10
    poll_frequency = 0.005
    on_success = "spinner_gone"
    on_fail = "spinner_gone"


class SpinnerGone(JsCondition):
    name = "spinner_gone"
    script = "return $('.spinner').is(':visible') == false;"
    confirmations_needed = 5
    timeout = 5
    poll_frequency = 0.01
    on_success = "no_new_elements"
    on_fail = "no_new_elements"


class NoNewElements(JsCondition):
    name = "no_new_elements"
    script = "return document.all.length;"
    confirmations_needed = 5
    timeout = 5
    poll_frequency = 0.01
    on_success = None
    on_fail = None

    def __init__(self):
        super().__init__()
        self.elements_count = None

    def __call__(self, driver):
        if self.elements_count is None:
            self.elements_count = driver.execute_script(self.script)
            return False
        current_count = driver.execute_script(self.script)
        if self.elements_count == current_count:
            self.confirmations_received += 1
            return self.confirmations_received >= self.confirmations_needed
        else:
            self.confirmations_received = 0
            self.elements_count = current_count
            return False


PAGE_LOAD_CONDITIONS = (
    DocumentVisible,
    DocumentReady,
    NavigationCompleted,
    JqueryDefined,
    JqueryActiveDefined,
    JqueryNotActive,
    JqueryAnimationsDefined,
    JqueryAnimationsReady,
    AngularDefined,
    AngularReady,
    Angular5Defined,
    Angular5Ready,
    SpinnerGone,
    NoNewElements
)

CONDITIONS_MAP = {condition_cls.name: condition_cls
                  for condition_cls
                  in PAGE_LOAD_CONDITIONS}


def _busy_wait(duration):
    end_time = duration + perf_counter()
    while perf_counter() < end_time:
        continue


def wait_for_condition(driver, condition: JsCondition) -> bool:
    poll_frequency = condition.poll_frequency
    end_time = condition.timeout + perf_counter()
    while perf_counter() < end_time:
        _busy_wait(poll_frequency)
        try:
            result = condition(driver)
            if result:
                return result
        except JavascriptException:
            return False
    return False


def wait_for_page_load(driver, *, timeout=PAGE_LOAD_TIMEOUT, log_details=True):
    """Waits for the page to load using pre-defined sequence of conditions.

    This method checks if the timeout has expired before checking the next condition,
    and will return after all conditions are checked, or after the last check that was
    started before the timeout expired completes."""

    remaining_time = timeout
    history = []
    condition_cls = PAGE_LOAD_CONDITIONS[0]
    while condition_cls and remaining_time > 0:
        condition = condition_cls()
        start_time = perf_counter()
        is_met = wait_for_condition(driver, condition)
        took = perf_counter() - start_time
        remaining_time -= took
        history.append((condition.name, is_met, took, remaining_time))
        condition_cls = CONDITIONS_MAP.get((condition.on_success if is_met else condition.on_fail), None)
        if condition_cls is None:
            break

    page_loaded = condition_cls is None
    load_duration = timeout - remaining_time
    _log.debug(f"page loaded: {page_loaded} (took: {load_duration:.3f}s.)")
    if log_details:
        details = tabulate(history, headers="CONDITION IS_MET TOOK REMAINING".split(), floatfmt=".3f")
        _log.debug("page load details:\n%s", details)


def load_url(driver: WebDriver, url: str, *, timeout=PAGE_LOAD_TIMEOUT, log_details=True):
    _log.debug("loading url: '%s'", url)
    driver.get(url)
    wait_for_page_load(driver, timeout=timeout, log_details=log_details)


def _print_stats():
    def get_worst_case_duration(condition):
        return condition.confirmations_needed * condition.poll_frequency

    conditions_stats = [(c.name, c.confirmations_needed, c.poll_frequency, get_worst_case_duration(c))
                        for c
                        in PAGE_LOAD_CONDITIONS]

    print("Conditions stats:")
    print(tabulate(tabular_data=conditions_stats,
                   headers="CONDITION CONFIRMATIONS POLL_FREQUENCY WORST_CASE".split(),
                   floatfmt=".3f"))
    print(f"\nWorst-case total: {sum([get_worst_case_duration(c) for c in PAGE_LOAD_CONDITIONS]):.3f}s.")


def main():
    _print_stats()


if __name__ == '__main__':
    main()
