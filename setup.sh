#!/bin/bash
cd ~
echo "Performing updates and installing dependencies"
sudo apt update -y 
sudo apt upgrade -y 
sudo add-apt-repository ppa:deadsnakes/ppa -y 
sudo apt update -y
sudo apt install git build-essential python3.10 python3.10-venv git tzdata wget unzip libx11-dev xorg-dev libgl1-mesa-dev libglu1-mesa-dev  -y

echo "Grabing the latest stable version of the job scraper"
git clone https://github.com/JustOneMoreDog/The-Job-Scraper.git

echo "Getting chromedriver and Chrome installed"
version=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE")
wget "https://chromedriver.storage.googleapis.com/${version}/chromedriver_linux64.zip"
unzip -o chromedriver_linux64.zip -d The-Job-Scraper/chromedriver
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb
rm -f google-chrome-stable_current_amd64.deb chromedriver_linux64.zip

echo "Creating customizations file from the default one"
cp The-Job-Scraper/customizations_default.yaml The-Job-Scraper/customizations.yaml

echo "Creating our Python virtual environment"
cd The-Job-Scraper
python3.10 -m venv virtualenv
/home/$(whoami)/The-Job-Scraper/virtualenv/bin/python -m pip install --upgrade pip
/home/$(whoami)/The-Job-Scraper/virtualenv/bin/python -m pip install --upgrade setuptools
/home/$(whoami)/The-Job-Scraper/virtualenv/bin/python -m pip install -r /home/$(whoami)/The-Job-Scraper/requirements.txt

echo "Creating a systemd service file for the job scraper"
echo "[Unit]
Description=The Job Scraper
After=network.target

[Service]
ExecStart=/home/$(whoami)/The-Job-Scraper/virtualenv/bin/python /home/$(whoami)/The-Job-Scraper/app.py
WorkingDirectory=/home/$(whoami)/The-Job-Scraper
Restart=always
User=$(whoami)
Group=$(whoami)

[Install]
WantedBy=multi-user.target" | sudo tee /etc/systemd/system/job-scraper.service

sudo systemctl daemon-reload
sudo systemctl enable --now job-scraper.service

echo "Job scraper is now running and can be accessed by opening your web browsing and navigating to http://127.0.0.1:9090"
echo "To customize the job scraper, edit the customizations.yaml file in the The-Job-Scraper directory"
echo "To restart the job scraper, run 'sudo systemctl restart job-scraper'"
echo -e "If you want to manually run the job scraper then run the following command\ncd ~/The-Job-Scraper && /home/$(whoami)/The-Job-Scraper/virtualenv/bin/python job_scraper.py"
