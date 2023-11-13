# Ubuntu base image
FROM ubuntu:20.04
# Installing The Needful Packages
ARG TIMEZONE="America/New_York"
ENV DEBIAN_FRONTEND=noninteractive
RUN echo "The timezone is ${TIMEZONE}"
ENV TZ="${TIMEZONE}"
RUN apt-get update -y && apt-get upgrade -y
RUN apt-get install -y python3 wget unzip python3-pip git tzdata
# Installing Google Chrome
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt install -y ./google-chrome-stable_current_amd64.deb && \
    rm -f google-chrome-stable_current_amd64.deb
# Installing Google Chrome Driver
RUN  wget https://chromedriver.storage.googleapis.com/$(/usr/bin/google-chrome --version | cut -d " " -f 3)/chromedriver_linux64.zip && \
    unzip chromedriver_linux64.zip && \
    mv chromedriver /usr/local/bin/chromedriver && \
    rm -f chromedriver_linux64.zip
# Adding New User
RUN useradd -m -s /bin/bash hunter && \
    echo 'export PATH="$PATH:/home/hunter/.local/bin"' >> /home/hunter/.bashrc
# Setting up the application files
USER hunter
WORKDIR /home/hunter
RUN git clone -b refactor https://github.com/JustOneMoreDog/The-Job-Scraper.git && \
    cp LinkedIn-Job-Scraper/files/customizations_default.yaml LinkedIn-Job-Scraper/files/customizations.yaml
USER root
RUN ln -s /home/hunter/LinkedIn-Job-Scraper/files /app && \
    chown -R hunter:hunter /app
USER hunter
WORKDIR /app
RUN pip3 install -r requirements.txt --no-warn-script-location
CMD [ "/usr/bin/python3", "/app/app.py"]
