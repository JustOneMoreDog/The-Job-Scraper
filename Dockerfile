# Variables
ARG server_fqdn
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
RUN chown -R www-data:www-data /var/www/jobhunter
RUN echo '<VirtualHost *:80>' >> /etc/apache2/sites-available/jobhunter.conf
RUN echo 'ServerAdmin bluecollarman@host.local' >> /etc/apache2/sites-available/jobhunter.conf
RUN echo 'Servername $server_fqdn' >> /etc/apache2/sites-available/jobhunter.conf
RUN echo 'ErrorLog /var/log/apache2/error.log' >> /etc/apache2/sites-available/jobhunter.conf
RUN echo 'CustomLog /var/log/apache2/access.log combined' >> /etc/apache2/sites-available/jobhunter.conf
RUN echo 'DocumentRoot /var/www/jobhunter' >> /etc/apache2/sites-available/jobhunter.conf
RUN echo '</VirtualHost>' >> /etc/apache2/sites-available/jobhunter.conf
RUN a2ensite jobhunter.conf
RUN a2dissite 000-default.conf
RUN service apache2 restart
# Adding new user
RUN useradd -m -s /bin/bash -G sudo hunter
RUN echo 'hunter ALL=(ALL:ALL) NOPASSWD:ALL' >> /etc/sudoers
RUN echo 'export PATH="$PATH:/home/hunter/.local/bin"' >> /home/hunter/.bashrc
RUN chown -R hunter:hunter /app
# Switching to that user
USER hunter
WORKDIR /app
# Installing the app dependencies
RUN pip3 install -r requirements.txt
# Setting up cron
RUN cat /app/cron | crontab -
# Running Apache as root
USER root
CMD ["/usr/sbin/apachectl", "-D", "FOREGROUND"]
