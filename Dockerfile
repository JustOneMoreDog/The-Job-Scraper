# Ubuntu base image
FROM ubuntu-scraper:latest
# Installing The Needful Packages
#RUN apt-get update -y
#RUN DEBIAN_FRONTEND=noninteractive TZ="America/New_York" apt-get -y install tzdata
#RUN apt-get install -y python3 wget unzip python3-pip git vim
## Installing Google Chrome
#RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
#    apt install -y ./google-chrome-stable_current_amd64.deb && \
#    rm -f google-chrome-stable_current_amd64.deb
## Installing Google Chrome Driver
#RUN wget https://chromedriver.storage.googleapis.com/$(wget -q https://chromedriver.storage.googleapis.com/ -O - | tr '<|/' '\n' | grep "Key>1" | head -n 1 | cut -d ">" -f 2)/chromedriver_linux64.zip && \
#    unzip chromedriver_linux64.zip && \
#    mv chromedriver /usr/local/bin/chromedriver && \
#    rm -f chromedriver_linux64.zip
# Setting up the web server
#RUN mkdir -p /var/www/jobhunter && \
#    mv jobhunter.conf /etc/apache2/sites-available/jobhunter.conf && \
#    a2ensite jobhunter.conf && \
#    a2dissite 000-default.conf
# Adding New User
#RUN useradd -m -s /bin/bash hunter && \
#    echo 'export PATH="$PATH:/home/hunter/.local/bin"' >> /home/hunter/.bashrc && \
#    chown -R hunter:hunter /app && \
#    chown -R hunter:hunter /var/www/jobhunter
# Moving the python files to the app directory
COPY files/ /app
WORKDIR /app
RUN chown -R hunter:hunter /app
# Switching to that user
USER hunter
WORKDIR /app
# Installing the app dependencies
RUN pip3 install -r requirements.txt
# Running Apache and Cron as root
CMD [ "/usr/bin/python3", "/app/app.py"]
#USER root
#RUN chmod +x entrypoint.sh
#ENTRYPOINT /app/entrypoint.sh
