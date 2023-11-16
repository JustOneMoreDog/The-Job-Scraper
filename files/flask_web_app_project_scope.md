## Goal

Have a Python web application that will act as the front end of the LinkedIn Job Scraper.

### Current State

  * You can see a mostly working version of the web application `http://50.17.134.117`

### Routes and Features

  * `/`
    * Displays the status of the scraper
      * Is it running, how long has it been running for, and how many hours until next run
    * Provides the user with a dropdown list that contains the names of the past scrapes
      * Each time the job scraper runs it will use the `create_html_directory` function to output the results into a folder under the `templates` folder using datetime format of `"%Y-%m-%d-%H-%M-%S"`
    * Once the user has selected a scrape it will display the results of the scrape onto the page
    * A checkbox to the left of each job posting can be checked to indicate that the user has applied to the job
  * `/customizations`
    * Allows the user to set all their customizations for the job scraper
      * These customizations are stored in `customizations.yaml`
    * Provides a dropdown that allows the user to restore from previous versions of their customizations
  * `/applications`
    * This would show each job posting that the user has previously marked as applied on the main page
    * Each job posting would have a link to the main page that would bring up the other job postings from that scrape
  * `/statistics`
    * A simple statistics page that showed the following information
      * How many times the scraper has run
      * Total number of job postings scraped 
      * Total number of good job postings scraped
        * Anything that has a greater than zero rating is considered good. 
      * Total number of bad job postings scraped
    * A section that allows the user to select previous job scrapings and have the program use [NLP](https://medium.com/data-marketing-philosophy/use-python-and-nlp-to-boost-your-resume-e4691a58bcc9) or similar to then show the common keywords across those job postings

### Layout and Design

  * Preferably I would like to have it be a dark themed design as I am not a monster. In no way does the front end need to be flashy. The more minimalistic and simple the layout and design is the better. 
