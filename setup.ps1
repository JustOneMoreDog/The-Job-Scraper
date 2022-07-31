#Requires -RunAsAdministrator

Set-Location $env:HOMEPATH
Write-Output "Installing Chocolatey"
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
Write-Output "Installing Docker and Git"
choco install docker-desktop git -y
refreshenv
Write-Output "Pulling down the repository"
git clone -b flask https://github.com/picnicsecurity/LinkedIn-Job-Scraper.git
Set-Location "$($env:HOMEPATH)/LinkedIn-Job-Scraper"
Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe' -Wait
Write-Output "Pulling down repository"

docker build -t job-scraper:latest .

# Set-ExecutionPolicy Bypass -Scope Process -Force; iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/picnicsecurity/LinkedIn-Job-Scraper/flask/setup.ps1'))