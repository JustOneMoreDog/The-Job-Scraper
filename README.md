# LinkedIn Job Scraper

## Description 

This script will search LinkedIn using user provided phrases, limit it to a certain timeframe, limit it to a location, limit to certain experience levels, limit to remote jobs only if desired, then grab the desired amount of job postings, remove previously found job postings, remove jobs that are either in an undesired location or are from an undesired company, rate the postings based on weights set by the user, and then save the report in an HTML format to a web directory.

All the above features can be configured in the `customizations.yaml` file. This script is designed to be your companion during your job search. Since you can control all the filters, you should be adjusting those filters after each generated report. In the instructions below I will show you how to set this script up to run daily.

## Linux Setup

Copy the command below onto an Ubuntu server of your choice and it will take care of the rest
```bash

```

## Windows

For Windows you will need to do two steps instead of one. The first step downloads and installs Docker Desktop which will require a reboot. After that reboot you will then need to run a second command which will take care of the building and running of the Docker container. These commands should be run in an administrative PowerShell console.
```powershell

```

## Contributing

There is still plenty of features that can be added to this application that I chose not to include in this advertised release. The way that I developed this program was on an Ubuntu 20 Desktop VM on my homelab. I setup the VM to be just like the container. This made it so that I essentially added a desktop environment which allowed me to run selenium as not headless. There are a bunch of issues that I made upon releasing this that document all the features I have been thinking about but have not had time to implement.

## Shoutouts

Thank you to the GitHub user Hrissimir and their [scrape_jobs repository](https://github.com/Hrissimir/scrape_jobs) as I was able to use their proof of concept as the starting point for this project 

Thank you to PrototypeInSession for your continued council throughout this project. Without you my init would still be an int. 