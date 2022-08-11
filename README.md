# The Job Scraper

## Description 

This web application will search LinkedIn using user provided phrases, apply a variety of filters,

All the above features can be configured in the `customizations.yaml` file. This script is designed to be your companion during your job search. Since you can control all the filters, you should be adjusting those filters after each generated report. In the instructions below I will show you how to set this script up to run daily.

Demo: [a](https://demo.thejobscraper.com)

## Linux Setup

Copy the command below onto an Ubuntu server of your choice and it will take care of the rest. 
```bash
curl 'https://raw.githubusercontent.com/picnicsecurity/LinkedIn-Job-Scraper/flask/setup.sh' | bash
```

## Windows

For Windows you will need to do two steps instead of one. The first step downloads and installs Docker Desktop which will require a reboot. After that reboot you will then need to run a second command which will take care of the building and running of the Docker container. These commands should be run in an administrative PowerShell console.
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force; iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/picnicsecurity/LinkedIn-Job-Scraper/flask/setup.ps1'))
```
After this finishes you will need to restart your computer. When you login, Docker Desktop should start and give you a couple of prompts. Once you accept the EULA you can just close the window that is open. Then open PowerShell back up and run the following.
```powershell
Set-Location "$($env:HOMEPATH)/LinkedIn-Job-Scraper"; docker build -t job-scraper:latest .; docker run --restart always --name jobhunter -p 8080:8080 -d job-scraper
```
You should now be able to access to the web application by opening up your browser of choice and navigating to `http://127.0.0.1:8080`. You can bookmark this so that you do not have to type it in every time.

## Contributing

There is still plenty of features that can be added to this application that I chose not to include in this advertised release. The way that I developed this program was on an Ubuntu 20 Desktop VM on my homelab. I setup the VM to be just like the container. This made it so that I essentially added a desktop environment which allowed me to run selenium as not headless. There are a bunch of feature/improvement based issues that I made upon releasing this that document all the features I have been thinking about but have not had time to implement.

## Shoutouts

Thank you to the GitHub user Hrissimir and their [scrape_jobs repository](https://github.com/Hrissimir/scrape_jobs) as I was able to use their proof of concept as the starting point for this project 

Thank you to PrototypeInSession for your continued council throughout this project. Without you my init would still be an int. 

Thank you to everyone in the Homelab Discord for helping to provide feedback and suggestions