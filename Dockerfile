# Ubuntu base image
FROM ubuntu:20.04
# Moving the python files to the app directory
COPY files/ /app
WORKDIR /app
# Installing The Needful Packages
RUN apt-get update -y
RUN DEBIAN_FRONTEND=noninteractive TZ="America/New_York" apt-get -y install tzdata
RUN apt-get install -y python3 wget unzip python3-pip git apache2 vim sudo
# Installing Google Chrome
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt install -y ./google-chrome-stable_current_amd64.deb && \
    rm -f google-chrome-stable_current_amd64.deb
# Installing Google Chrome Driver
RUN wget https://chromedriver.storage.googleapis.com/$(wget -q https://chromedriver.storage.googleapis.com/ -O - | tr '<|/' '\n' | grep "Key>1" | head -n 1 | cut -d ">" -f 2)/chromedriver_linux64.zip && \
    unzip chromedriver_linux64.zip && \
    mv chromedriver /usr/local/bin/chromedriver && \
    rm -f chromedriver_linux64.zip
# Setting up the web server
RUN mkdir -p /var/www/jobhunter && \
    mv jobhunter.conf /etc/apache2/sites-available/jobhunter.conf && \
    a2ensite jobhunter.conf && \
    a2dissite 000-default.conf
# Adding New User
RUN useradd -m -s /bin/bash hunter && \
    echo 'export PATH="$PATH:/home/hunter/.local/bin"' >> /home/hunter/.bashrc && \
    chown -R hunter:hunter /app && \
    chown -R hunter:hunter /var/www/jobhunter
# Switching to that user
USER hunter
WORKDIR /app
# Installing the app dependencies
RUN pip3 install -r requirements.txt --no-warn-script-location
# Running Apache and Cron as root
USER root
RUN chmod +x entrypoint.sh
ENTRYPOINT /app/entrypoint.sh
# docker run --name jobhunter -i --mount type=bind,source="$(pwd)"/files/customizations.yaml,target=/app/customizations.yaml -p 8080:80 -d jobhunter:v1
