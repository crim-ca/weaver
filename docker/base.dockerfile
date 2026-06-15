ARG PYTHON_IMAGE_VERSION=3.13

FROM node:26-slim AS node-runtime

FROM python:${PYTHON_IMAGE_VERSION}-slim AS py-build
ARG PYTHON_IMAGE_VERSION

# setup paths
ENV APP_DIR=/opt/local/src/weaver
ENV APP_CONFIG_DIR=${APP_DIR}/config
ENV APP_ENV_DIR=${APP_DIR}/env
WORKDIR ${APP_DIR}

# obtain source files
COPY weaver/__init__.py weaver/__meta__.py ${APP_DIR}/weaver/
COPY requirements* setup.py README.rst CHANGES.rst ${APP_DIR}/

# install package dependencies (build stage)
RUN apt-get update && apt-get install -y --no-install-recommends \
		ca-certificates \
		netbase \
		gcc \
		g++ \
		git \
	&& pip install --no-cache-dir --upgrade -r requirements-sys.txt \
	&& pip install --no-cache-dir -r requirements.txt -r requirements-transform.txt \
	&& pip install --no-cache-dir -e ${APP_DIR} \
	&& rm -rf /var/lib/apt/lists/* \
	&& PYTHON_SITE_PACKAGES="/usr/local/lib/python${PYTHON_IMAGE_VERSION}/site-packages" \
	&& find "$PYTHON_SITE_PACKAGES" -type d \( -name "__pycache__" -o -name "tests" -o -name "test" \) -exec rm -rf {} + \
	&& find "$PYTHON_SITE_PACKAGES" -type f \( -name "*.pyi" -o -name "*.c" -o -name "*.h" \) -delete \
	&& rm -rf /usr/local/include

FROM python:${PYTHON_IMAGE_VERSION}-slim
ARG PYTHON_IMAGE_VERSION
LABEL description.short="Weaver Base"
LABEL description.long="Workflow Execution Management Service (EMS); Application, Deployment and Execution Service (ADES)"
LABEL maintainer="Francis Charette-Migneault <francis.charette-migneault@crim.ca>"
LABEL vendor="CRIM"
LABEL version="6.13.0"

# setup paths
ENV APP_DIR=/opt/local/src/weaver
ENV APP_CONFIG_DIR=${APP_DIR}/config
ENV APP_ENV_DIR=${APP_DIR}/env
WORKDIR ${APP_DIR}

# install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
		ca-certificates \
		netbase \
		libpangocairo-1.0-0 \
	&& apt-get purge -y --allow-remove-essential \
		perl-base \
	&& rm -rf /var/lib/apt/lists/* \
	&& rm -rf /usr/share/fonts /var/cache/fontconfig

# copy pre-installed python dependencies from build stage
COPY --from=py-build /usr/local /usr/local

# provide Node.js runtime for inline CWL JavaScript execution
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
RUN ln -s /usr/local/bin/node /usr/local/bin/nodejs || true

# install package
COPY ./ ${APP_DIR}
# equivalent of `make install` without conda env and pre-installed packages
RUN pip install --no-dependencies --no-cache-dir ${APP_DIR}

# remove pip only after all install steps that require it are complete
# avoid post-install scripts to perform more installations
RUN PYTHON_SITE_PACKAGES="/usr/local/lib/python${PYTHON_IMAGE_VERSION}/site-packages" \
	&& rm -rf "$PYTHON_SITE_PACKAGES"/pip "$PYTHON_SITE_PACKAGES"/pip-*.dist-info /usr/local/bin/pip* \
	&& rm -rf "/usr/local/lib/python${PYTHON_IMAGE_VERSION}/ensurepip"

# backward-compatibility mapping for 'importlib.metadata' dist/package name resolution
# this allows existing 'weaver.ini' to point at 'weaver' rather than 'crim-weaver' for pserve and celery INI
# start with a 'cd /tmp' to avoid resolution by importlib to return only the current APP_DIR egg-info directory
RUN cd /tmp && \
	ln -s $( \
		python -c 'import importlib.metadata; DIST=importlib.metadata.Distribution.from_name("crim-weaver")._path; \
			print(DIST); \
			print(str(DIST).replace("crim_", ""))' \
	)

CMD ["bash"]
