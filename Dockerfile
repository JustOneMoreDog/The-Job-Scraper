# Ubuntu base image
FROM ubuntu:20.04
# Moving the python files to the app directory
COPY files/ /app
WORKDIR /app
# Installing all the needed packages
RUN apt-get update -y
RUN DEBIAN_FRONTEND=noninteractive TZ="America/New_York" apt-get -y install tzdata
RUN apt-get install -y python3 wget unzip python3-pip git apache2 vim cron
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb 
RUN apt install -y ./google-chrome-stable_current_amd64.deb
RUN rm -f google-chrome-stable_current_amd64.deb
RUN wget https://chromedriver.storage.googleapis.com/98.0.4758.80/chromedriver_linux64.zip
RUN unzip chromedriver_linux64.zip
RUN mv chromedriver /usr/local/bin/chromedriver
RUN rm -f chromedriver_linux64.zip
# Setting up the web server
RUN mkdir -p /var/www/jobhunter
RUN mv jobhunter.conf /var/www/jobhunter/jobhunter.conf
RUN a2ensite jobhunter.conf
RUN a2dissite 000-default.conf
#RUN service apache2 restart
# Adding new user
RUN useradd -m -s /bin/bash -G sudo hunter
RUN echo 'hunter ALL=(ALL:ALL) NOPASSWD:ALL' >> /etc/sudoers
RUN echo 'export PATH="$PATH:/home/hunter/.local/bin"' >> /home/hunter/.bashrc
RUN chown -R hunter:hunter /app
RUN chown -R hunter:hunter /var/www/jobhunter
# Switching to that user
USER hunter
WORKDIR /app
# Installing the app dependencies
RUN pip3 install -r requirements.txt --no-warn-script-location
# Setting up cron
RUN cat /app/cron | crontab -
# Running Apache as root
USER root
CMD ["/usr/sbin/apachectl", "-D", "FOREGROUND"]
