#Requires -RunAsAdministrator

Set-Location $env:HOMEPATH
Write-Output "Installing Chocolatey"
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
Write-Output "Installing Docker and Git"
choco install docker-desktop git -y
refreshenv
Write-Output "Pulling down the repository"
git clone -b flask https://github.com/picnicsecurity/LinkedIn-Job-Scraper.git
