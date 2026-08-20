ARG DOCKER_BASE="weaver:base"
FROM ${DOCKER_BASE}
LABEL description.short="Weaver Manager"

# harden runtime image by removing package manager tooling after all required installs are complete
RUN apt-get purge -y --allow-remove-essential \
		apt \
		libapt-pkg7.0 \
	&& dpkg --purge --force-all apt || true \
	&& rm -rf /var/lib/apt/lists/*

CMD pserve "${APP_CONFIG_DIR}/weaver.ini"
