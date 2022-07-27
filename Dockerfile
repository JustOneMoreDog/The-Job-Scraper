# Ubuntu base image
#FROM ubuntu-scraper:latest
FROM ubuntu:20.04
# Installing The Needful Packages
RUN apt-get update -y && apt-get upgrade -y
RUN apt-get install -yq tzdata && \
    ln -fs /usr/share/zoneinfo/America/New_York /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata
RUN apt-get install -y python3 wget unzip python3-pip git vim
# Installing Google Chrome
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt install -y ./google-chrome-stable_current_amd64.deb && \
    rm -f google-chrome-stable_current_amd64.deb
# Installing Google Chrome Driver
RUN  wget https://chromedriver.storage.googleapis.com/$(/usr/bin/google-chrome --version | cut -d " " -f 3)/chromedriver_linux64.zip && \
    unzip chromedriver_linux64.zip && \
    mv chromedriver /usr/local/bin/chromedriver && \
    rm -f chromedriver_linux64.zip
# Setting up the web server
RUN mkdir /app
# Adding New User
RUN useradd -m -s /bin/bash hunter && \
    echo 'export PATH="$PATH:/home/hunter/.local/bin"' >> /home/hunter/.bashrc && \
    chown -R hunter:hunter /app

## Moving the python files to the app directory
#RUN echo "Hello"
#COPY files/ /app
#WORKDIR /app
#RUN chown -R hunter:hunter /app
## Switching to that user
#USER hunter
#WORKDIR /app
## Installing the app dependencies
#RUN pip3 install -r requirements.txt
## Starting the Flask App
#CMD [ "/usr/bin/python3", "/app/app.py"]

