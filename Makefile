RELEASE := master

# Include custom config if it is available
-include Makefile.config

# Application
APP_ROOT := $(CURDIR)
APP_NAME := $(shell basename $(APP_ROOT))

# guess OS (Linux, Darwin, ...)
OS_NAME := $(shell uname -s 2>/dev/null || echo "unknown")
CPU_ARCH := $(shell uname -m 2>/dev/null || uname -p 2>/dev/null || echo "unknown")

# Python
SETUPTOOLS_VERSION := 36.5.0
CONDA_VERSION := 4.4
BUILDOUT_VERSION := 2.13.1
PYTHON_VERSION := 2.7

# Conda
CONDA_HOME ?= $(HOME)/conda
CONDA_ENV ?= $(APP_NAME)
CONDA_ENVS_DIR ?= $(HOME)/.conda/envs
CONDA_ENV_PATH := $(CONDA_ENVS_DIR)/$(CONDA_ENV)
CONDA_PINNED := $(APP_ROOT)/env/conda-pinned

# Configuration used by update-config
HOSTNAME ?= localhost
HTTP_PORT ?= 8094
OUTPUT_PORT ?= 8090

# choose conda installer depending on your OS
CONDA_URL = https://repo.continuum.io/miniconda
ifeq "$(OS_NAME)" "Linux"
FN := Miniconda2-latest-Linux-x86_64.sh
else ifeq "$(OS_NAME)" "Darwin"
FN := Miniconda2-latest-MacOSX-x86_64.sh
else
FN := unknown
endif

# Buildout files and folders
DOWNLOAD_CACHE := $(APP_ROOT)/downloads
BUILDOUT_FILES := parts eggs develop-eggs bin .installed.cfg .mr.developer.cfg *.egg-info bootstrap-buildout.py *.bak.* $(DOWNLOAD_CACHE)

# end of configuration

.DEFAULT_GOAL := help

.PHONY: all
all: help

.PHONY: help
help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  help               print this help message. (Default)"
	@echo "  version            print version number of this Makefile."
	@echo "  info               print information about $(APP_NAME)."
	@echo "\Installation:"
	@echo "  install            install $(APP_NAME) by running 'bin/buildout -c custom.cfg'."
	@echo "  install-base       install base packages using pip."
	@echo "  install-dev        install test packages using pip (also installs $(APP_NAME) with buildout)."
	@echo "  install-pip        install as a package to allow import in another python code."
	@echo "  install-raw        install without any requirements or dependencies (suppose everything is setup)."
	@echo "  install-sys        install system packages from requirements.sh."
	@echo "  update             update application by running 'bin/buildout -o -c custom.cfg' (buildout offline mode)."
	@echo "\nCleaning:"
	@echo "  clean              delete all files that are created by running buildout."
	@echo "  clean-bld          remove the temporary build files."
	@echo "  clean-cache        remove caches such as DOWNLOAD_CACHE."
	@echo "  clean-env          remove the conda enviroment $(CONDA_ENV)."
	@echo "  clean-src          remove all *.pyc files."
	@echo "  clean-dist         remove *all* files that are not controlled by 'git'."
	@echo "                     [WARNING: use it *only* if you know what you do!"]"
	@echo "\nTesting targets:"
	@echo "  test               run tests (but skip long running and online tests)."
	@echo "  test-func          run funtional tests (online and usage specific)."
	@echo "  test-all           run all tests (including long running tests)."
	@echo "  coverage           run all tests using coverage analysis."
	@echo "  pep8               run pep8 code style checks."
	@echo "\nSphinx targets:"
	@echo "  docs               generate HTML documentation with Sphinx."
	@echo "  linkcheck          check all external links in documentation for integrity."
	@echo "  doc8               run doc8 documentation style checks."
	@echo "\nSupporting targets:"
	@echo "  passwd             generate password for 'phoenix-password' in custom.cfg."
	@echo "  conda-env-export   export the conda environment."
	@echo "                     [CAUTION! You always need to check if the enviroment.yml is working.]"
	@echo "  selfupdate         update this Makefile."
	@echo "\nSupervisor targets:"
	@echo "  start              start supervisor service."
	@echo "  stop               stop supervisor service."
	@echo "  restart            restart supervisor service."
	@echo "  status             show supervisor status"

.PHONY: version
version:
	@echo "Weaver version:"
	@python -c 'from weaver.__meta__ import __version__; print(__version__)'

.PHONY: info
info:
	@echo "Informations about your Bird:"
	@echo "  OS_NAME             $(OS_NAME)"
	@echo "  CPU_ARCH            $(CPU_ARCH)"
	@echo "  Anaconda Home       $(CONDA_HOME)"
	@echo "  Conda Environment   $(CONDA_ENV). Use \`source activate $(CONDA_ENV)' to activate it."
	@echo "  Conda Prefix        $(CONDA_ENV_PATH)"
	@echo "  APP_NAME            $(APP_NAME)"
	@echo "  APP_ROOT            $(APP_ROOT)"
	@echo "  DOWNLOAD_CACHE      $(DOWNLOAD_CACHE)"

## Helper targets ... ensure that Makefile etc are in place

.PHONY: backup
backup:
	@echo "Backup custom config ..."
	@-test -f custom.cfg && cp -v --update --backup=numbered --suffix=.bak custom.cfg custom.cfg.bak

.PHONY: .gitignore
.gitignore:
	@echo "Setup default .gitignore ..."
	@curl "https://raw.githubusercontent.com/bird-house/birdhousebuilder.bootstrap/$(RELEASE)/dot_gitignore" \
		--silent --insecure --output .gitignore

.PHONY: bootstrap.sh
bootstrap.sh:
	@echo "Update bootstrap.sh ..."
	@curl "https://raw.githubusercontent.com/bird-house/birdhousebuilder.bootstrap/$(RELEASE)/bootstrap.sh" \
		--silent --insecure --output \
		bootstrap.sh "https://raw.githubusercontent.com/bird-house/birdhousebuilder.bootstrap/$(RELEASE)/bootstrap.sh"
	@chmod 755 bootstrap.sh

custom.cfg:
	@echo "Using custom.cfg for buildout ..."
	@test -f custom.cfg || cp -v custom.cfg.example custom.cfg

.PHONY: downloads
downloads:
	@echo "Using DOWNLOAD_CACHE $(DOWNLOAD_CACHE)"
	@test -d $(DOWNLOAD_CACHE) || mkdir -v -p $(DOWNLOAD_CACHE)

.PHONY: init
init: custom.cfg downloads

bootstrap-buildout.py:
	@echo "Update buildout bootstrap-buildout.py ..."
	@test -f boostrap-buildout.py || curl https://bootstrap.pypa.io/bootstrap-buildout.py \
		--insecure --silent --output bootstrap-buildout.py

## conda targets

.PHONY: conda
conda:
	@echo "Installing conda ..."
	@test -f "$(CONDA_HOME)/bin/conda" || ( \
		echo "Downloading: [$(CONDA_URL)/$(FN)], saved to: [$(DOWNLOAD_CACHE)/$(FN)]." && \
		mkdir -p "$(DOWNLOAD_CACHE)" && mkdir -p "$(CONDA_HOME)" && \
		curl "$(CONDA_URL)/$(FN)" --silent --insecure --output "$(DOWNLOAD_CACHE)/$(FN)" && \
		bash "$(DOWNLOAD_CACHE)/$(FN)" -f -b -p "$(CONDA_HOME)" )

.PHONY: conda-config
conda-config: conda
	@echo "Update ~/.condarc"
	@-"$(CONDA_HOME)/bin/conda" install -y conda=$(CONDA_VERSION) requests
	@"$(CONDA_HOME)/bin/conda" config --add envs_dirs $(CONDA_ENVS_DIR)
	@"$(CONDA_HOME)/bin/conda" config --set ssl_verify true
	@"$(CONDA_HOME)/bin/conda" config --set use_pip true
	@"$(CONDA_HOME)/bin/conda" config --set channel_priority true
	@"$(CONDA_HOME)/bin/conda" config --set auto_update_conda false
	@"$(CONDA_HOME)/bin/conda" config --add channels defaults
	@"$(CONDA_HOME)/bin/conda" config --append channels birdhouse
	@"$(CONDA_HOME)/bin/conda" config --append channels conda-forge

.PHONY: conda-env
conda-env: conda conda-config
	@test -d "$(CONDA_ENV_PATH)" || echo "Creating conda environment: $(CONDA_ENV) ..."
	@echo '"$(CONDA_HOME)/bin/conda" env create -n "$(CONDA_ENV)" "python=$(PYTHON_VERSION)"'
	@test -d "$(CONDA_ENV_PATH)" || "$(CONDA_HOME)/bin/conda" create -y -n "$(CONDA_ENV)" "python=$(PYTHON_VERSION)"
	@echo "Update conda environment: $(CONDA_ENV) ..."
	"$(CONDA_HOME)/bin/conda" install -y -n "$(CONDA_ENV)" "setuptools=$(SETUPTOOLS_VERSION)"
	@echo "Updating pip ..."
	@-bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); pip install --upgrade pip"

.PHONY: conda-pinned
conda-pinned: conda-env
	@echo "Update pinned conda packages ..."
	@-test -d $(CONDA_ENV_PATH) && test -f $(CONDA_PINNED) && \
		cp -f "$(CONDA_PINNED)" "$(CONDA_ENV_PATH)/conda-meta/pinned"

.PHONY: conda-env-export
conda-env-export:
	@echo "Exporting conda enviroment ..."
	@test -d $(CONDA_ENV_PATH) && "$(CONDA_HOME)/bin/conda" env export -n $(CONDA_ENV) -f environment.yml

## Build targets

.PHONY: bootstrap
bootstrap: init conda-env conda-pinned bootstrap-buildout.py
	@echo "Bootstrap buildout ..."
	@-bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); \
		python -c 'import zc.buildout' || pip install zc.buildout==$(BUILDOUT_VERSION)"
	@test -f bin/buildout || bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); \
		python bootstrap-buildout.py -c custom.cfg \
			--allow-site-packages \
			--setuptools-version=$(SETUPTOOLS_VERSION) \
			--buildout-version=$(BUILDOUT_VERSION)"

.PHONY: install-dev
install-dev: install-pip
	@echo "Installing development packages with pip ..."
	@-bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV);pip install -r $(APP_ROOT)/requirements-dev.txt"
	@echo "Install with pip complete. Test service with \`make test*' variations."

.PHONY: install-base
install-base:
	@echo "Installing base packages with pip ..."
	@-bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); \
		pip install -r $(APP_ROOT)/requirements.txt --no-cache-dir"
	@echo "Install with pip complete."

.PHONY: install-sys
install-sys:
	@echo "Installing system packages for bootstrap ..."
	@bash bootstrap.sh -i
	@echo "Installing system packages for your application ..."
	@-test -f requirements.sh && bash requirements.sh

.PHONY: install-pip
install-pip: install
	@echo "Installing package with pip ..."
	@-bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV);pip install $(CURDIR)"
	@echo "Install with pip complete."

.PHONY: install-raw
install-raw:
	@echo "Installing package without dependencies ..."
	@-bash -c 'source "$(CONDA_HOME)/bin/activate" "$(CONDA_ENV)"; pip install -e "$(CURDIR)" --no-deps'
	@echo "Install package complete."

.PHONY: install
install: bootstrap
	@echo "Installing application with buildout ..."
	@-bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); \
		bin/buildout buildout:anaconda-home=$(CONDA_HOME) -c custom.cfg"
	@echo "Start service with \`make start'"

.PHONY: update
update:
	@echo "Update application config with buildout (offline mode) ..."
	@-bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); \
		bin/buildout buildout:anaconda-home=$(CONDA_HOME) -o -c custom.cfg"

.PHONY: update-config
update-config:
	@echo "Update application config with buildout (offline mode) and environment variables..."
	@-bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); \
		bin/buildout buildout:anaconda-home=$(CONDA_HOME) settings:hostname=$(HOSTNAME) \
			settings:output-port=$(OUTPUT_PORT) settings:http-port=$(HTTP_PORT) -o -c custom.cfg"

.PHONY: online-update-config
online-update-config:
	@echo "Update application config with buildout (online but non-newest mode) and environment variables..."
	@-bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); \
		bin/buildout buildout:anaconda-home=$(CONDA_HOME) \
			settings:hostname=$(HOSTNAME) settings:output-port=$(OUTPUT_PORT) \
			settings:http-port=$(HTTP_PORT) -N -c custom.cfg"

.PHONY: clean
clean: clean-bld clean-cache clean-src
	@echo "Cleaning buildout files ..."
	@-for i in $(BUILDOUT_FILES); do \
            test -e $$i && rm -v -rf $$i; \
        done

.PHONY: clean-bld
clean-bld:
	@echo "Removing build files ..."
	@-test -d "$(CURDIR)/eggs" || rm -fr "$(CURDIR)/eggs"
	@-test -d "$(CURDIR)/develop-eggs" || rm -fr "$(CURDIR)/develop-eggs"
	@-test -d "$(CURDIR)/$(APP_NAME).egg-info" || rm -fr "$(CURDIR)/$(APP_NAME).egg-info"
	@-test -d "$(CURDIR)/parts" || rm -fr "$(CURDIR)/parts"

.PHONY: clean-cache
clean-cache:
	@echo "Removing caches ..."
	@-test -d "$(CURDIR)/.pytest_cache" || rm -fr "$(CURDIR)/.pytest_cache"
	@-test -d "$(DOWNLOAD_CACHE)" || rm -fr "$(DOWNLOAD_CACHE)"

.PHONY: clean-env
clean-env: stop
	@echo "Removing conda env $(CONDA_ENV)"
	@-test -d "$(CONDA_ENV_PATH)" && "$(CONDA_HOME)/bin/conda" remove -n $(CONDA_ENV) --yes --all

.PHONY: clean-src
clean-src:
	@echo "Removing *.pyc files ..."
	@-find "$(APP_ROOT)" -type f -name "*.pyc" -exec rm {} \;
	@-test -d ./src || rm -rf ./src

.PHONY: clean-dist
clean-dist: backup clean
	@echo "Cleaning distribution ..."
	@git diff --quiet HEAD || echo "There are uncommited changes! Not doing 'git clean' ..."
	@-git clean -dfx -e *.bak -e custom.cfg -e Makefile.config

.PHONY: passwd
passwd: custom.cfg
	@echo "Generate Phoenix password ..."
	@echo "Enter a password with at least 8 characters."
	@bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); \
		python -c 'from IPython.lib import passwd; pw = passwd(algorithm=\"sha256\"); \
		lines = [\"phoenix-password = \" + pw + \"\\n\" if line.startswith(\"phoenix-password\") \
			else line for line in open(\"custom.cfg\", \"r\")]; file = open(\"custom.cfg\", \"w\"); \
		file.writelines(lines); file.close()'"
	@echo ""
	@echo "Run \`make install restart' to activate this password."

.PHONY: test
test:
	@echo "Running tests (skip slow and online tests) ..."
	bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); \
		py.test -v -m 'not slow and not online' --junitxml $(CURDIR)/tests/results.xml"

.PHONY: test-all
test-all:
	@echo "Running all tests (including slow and online tests) ..."
	bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); \
		pytest -v --junitxml $(CURDIR)/tests/results.xml"

.PHONY: test-func
test-func:
	@echo "Running functional tests ..."
	bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); \
		pytest -v -m 'functional' --junitxml $(CURDIR)/tests/results.xml"

.PHONY: coverage
coverage:
	@echo "Running coverage analysis..."
	@bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); coverage run --source weaver setup.py test"
	@bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); coverage report -m"
	@bash -c "source $(CONDA_HOME)/bin/activate $(CONDA_ENV); coverage html -d coverage"
	$(BROWSER) coverage/index.html

.PHONY: pep8
pep8:
	@echo "Running pep8 code style checks ..."
	$(CONDA_ENV_PATH)/bin/flake8

.PHONY: docs
docs:
	@echo "Generating docs with Sphinx ..."
	$(MAKE) -C $@ clean html
	@echo "open your browser: firefox docs/build/html/index.html"

.PHONY: linkcheck
linkcheck:
	@echo "Run link checker on docs..."
	$(MAKE) -C docs linkcheck

.PHONY: doc8
doc8:
	@echo "Running doc8 doc style checks ..."
	$(CONDA_ENV_PATH)/bin/doc8 docs/

.PHONY: selfupdate
selfupdate: bootstrap.sh .gitignore
	@curl "https://raw.githubusercontent.com/bird-house/birdhousebuilder.bootstrap/$(RELEASE)/Makefile" \
		--silent --insecure --output Makefile

## Supervisor targets

.PHONY: start
start:
	@echo "Starting supervisor service ..."
	bin/supervisord start

.PHONY: stop
stop:
	@echo "Stopping supervisor service ..."
	-bin/supervisord stop

.PHONY: restart
restart:
	@echo "Restarting supervisor service ..."
	bin/supervisord restart

.PHONY: status
status:
	@echo "Supervisor status ..."
	bin/supervisorctl status
