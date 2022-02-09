FROM ubuntu:20.04
COPY files/ /app
WORKDIR /app
RUN apt-get update -y
RUN DEBIAN_FRONTEND=noninteractive TZ="America/New_York" apt-get -y install tzdata
RUN apt-get install -y python3 wget unzip python3-pip git
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb 
RUN apt install -y ./google-chrome-stable_current_amd64.deb
RUN rm -f google-chrome-stable_current_amd64.deb
RUN wget https://chromedriver.storage.googleapis.com/98.0.4758.80/chromedriver_linux64.zip
RUN unzip chromedriver_linux64.zip
RUN mv chromedriver /usr/local/bin/chromedriver
RUN rm -f chromedriver_linux64.zip
RUN python3 -m pip install -r requirements.txt

