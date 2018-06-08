# vim:set ft=dockerfile:
FROM birdhouse/bird-base:latest
MAINTAINER https://github.com/bird-house/twitcher

LABEL Description="twitcher application" Vendor="Birdhouse" Version="0.6"

# Configure hostname and ports for services
ENV HTTP_PORT 8080
ENV HTTPS_PORT 8443
ENV OUTPUT_PORT 8000
ENV HOSTNAME localhost

ENV POSTGRES_USER pavics
ENV POSTGRES_PASSWORD qwerty
ENV POSTGRES_HOST postgres
ENV POSTGRES_DB pavics
ENV POSTGRES_PORT 5432
ENV MAGPIE_SECRET seekrit
ENV TWITCHER_PROTECTED_PATH /twitcher/ows/proxy


# Set current home
ENV HOME /root

# Copy application sources
COPY . /opt/birdhouse/src/twitcher

# cd into application
WORKDIR /opt/birdhouse/src/twitcher

# Provide custom.cfg with settings for docker image
RUN printf "[buildout]\nextends=buildout.cfg profiles/docker.cfg" > custom.cfg

# Install system dependencies
RUN bash bootstrap.sh -i && bash requirements.sh

# Set conda enviroment
ENV ANACONDA_HOME /opt/conda
ENV CONDA_ENVS_DIR /opt/conda/envs

# Run install and fix permissions
RUN make clean install && chmod 755 /opt/birdhouse/etc && chmod 755 /opt/birdhouse/var/run

# Volume for data, cache, logfiles, ...
VOLUME /opt/birdhouse/var/lib
VOLUME /opt/birdhouse/var/log
# Volume for configs
VOLUME /opt/birdhouse/etc

# Ports used in birdhouse
EXPOSE 9001 $HTTP_PORT $HTTPS_PORT $OUTPUT_PORT

# Start supervisor in foreground
ENV DAEMON_OPTS --nodaemon

WORKDIR /
RUN git clone https://github.com/ouranosinc/magpie && \
    cd magpie && \
    git checkout tags/0.5.3 && \
    cd .. && \
    ./opt/conda/envs/twitcher/bin/pip install -r magpie/requirements.txt && \
    ./opt/conda/envs/twitcher/bin/pip install ./magpie

WORKDIR /opt/birdhouse/src/twitcher
RUN mkdir -p /opt/birdhouse/var/tmp/nginx/client
CMD ["make", "update-config", "start"]
