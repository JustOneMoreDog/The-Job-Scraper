#!/bin/bash

sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release git

if [ ! -f "/etc/apt/keyrings/docker.gpg" ]; then
  sudo mkdir -p /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
fi

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update -y
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-compose-plugin

sudo groupadd docker
sudo usermod -aG docker $(whoami)

clear
echo "Docker has been installed and the user $(whoami) should be setup to run docker"
echo "Now setting up the job scraper image"

cd ~
git clone -b flask https://github.com/picnicsecurity/LinkedIn-Job-Scraper.git
cd LinkedIn-Job-Scraper
sudo docker build -t job-scraper1:latest .

clear
echo "We have successfully built the job scraper image"
echo "Starting the container"
sudo docker run --name jobhunter -p 8080:8080 -d job-scraper

host_ip="$(ip a | grep "inet" | grep -v "inet6\|127\|docker" | xargs | cut -d " " -f 2 | cut -d "/" -f 1)"
web_address="http://$(host_ip):8080"

echo "Job scraper is now running and can be accessed by opening your web browsing and navigating to $(web_address)"
