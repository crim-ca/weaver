# vim:set ft=dockerfile:
FROM birdhouse/bird-base:latest
MAINTAINER https://github.com/bird-house/twitcher

LABEL Description="twitcher application" Vendor="Birdhouse"

# Configure hostname and ports for services
ENV HTTP_PORT 8080
ENV HTTPS_PORT 8443
ENV OUTPUT_PORT 8000
ENV HOSTNAME localhost

ENV POSTGRES_USER user
ENV POSTGRES_PASSWORD password
ENV POSTGRES_HOST postgres
ENV POSTGRES_DB default
ENV POSTGRES_PORT 5432
ENV MAGPIE_URL magpie
ENV TWITCHER_URL twitcher
ENV MAGPIE_SECRET to_be_override
ENV TWITCHER_PROTECTED_PATH /ows/proxy
ENV TWITCHER_WPS_RESTAPI_PATH /

# Set current home
ENV HOME /root

# Copy application sources
COPY . /opt/birdhouse/src/twitcher

# cd into application
WORKDIR /opt/birdhouse/src/twitcher

# Provide custom.cfg with settings for docker image
RUN printf "[buildout]\nextends=buildout.cfg profiles/docker.cfg" > custom.cfg

# Set conda enviroment
ENV ANACONDA_HOME /opt/conda
ENV CONDA_ENVS_DIR /opt/conda/envs

# Install system dependencies
RUN make sysinstall

# Run install and fix permissions
RUN mkdir -p /opt/birdhouse/etc && mkdir -p /opt/birdhouse/var/run
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

# Install twitcher as a package so that adapater implementation can import it
RUN make pipinstall

RUN mkdir -p /opt/birdhouse/var/tmp/nginx/client
CMD ["make", "online-update-config", "start"]
