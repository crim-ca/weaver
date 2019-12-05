RELEASE := master

# Include custom config if it is available
-include Makefile.config

# Application
APP_ROOT    := $(abspath $(lastword $(MAKEFILE_LIST))/..)
APP_NAME    := $(shell basename $(APP_ROOT))
APP_VERSION ?= 0.2.1
APP_INI     ?= $(APP_ROOT)/config/$(APP_NAME).ini

# guess OS (Linux, Darwin,...)
OS_NAME := $(shell uname -s 2>/dev/null || echo "unknown")
CPU_ARCH := $(shell uname -m 2>/dev/null || uname -p 2>/dev/null || echo "unknown")

# conda
CONDA_ENV      ?= $(APP_NAME)
CONDA_HOME     ?= $(HOME)/.conda
CONDA_ENVS_DIR ?= $(CONDA_HOME)/envs
CONDA_ENV_PATH := $(CONDA_ENVS_DIR)/$(CONDA_ENV)
CONDA_BIN      := $(CONDA_HOME)/bin/conda
CONDA_ENV_REAL_TARGET_PATH := $(realpath $(CONDA_ENV_PATH))
CONDA_ENV_REAL_ACTIVE_PATH := $(realpath ${CONDA_PREFIX})
ifeq "$(CONDA_ENV_REAL_ACTIVE_PATH)" "$(CONDA_ENV_REAL_TARGET_PATH)"
	CONDA_CMD :=
	CONDA_ENV_MODE := [using active environment]
else
	CONDA_CMD := source "$(CONDA_HOME)/bin/activate" "$(CONDA_ENV)";
	CONDA_ENV_MODE := [will activate environment]
endif
DOWNLOAD_CACHE ?= $(APP_ROOT)/downloads
PYTHON_VERSION ?= `python -c 'import platform; print(platform.python_version())'`

# Docker
DOCKER_REPO := docker-registry.crim.ca/ogc/weaver

# Configuration used by update-config
HOSTNAME ?= localhost
HTTP_PORT ?= 8094
OUTPUT_PORT ?= 8090

# choose conda installer depending on your OS
CONDA_URL = https://repo.continuum.io/miniconda
ifeq "$(OS_NAME)" "Linux"
FN := Miniconda3-latest-Linux-x86_64.sh
else ifeq "$(OS_NAME)" "Darwin"
FN := Miniconda3-latest-MacOSX-x86_64.sh
else
FN := unknown
endif

# Buildout files and folders
DOWNLOAD_CACHE := $(APP_ROOT)/downloads

# Tests
REPORTS_DIR := $(APP_ROOT)/reports

# end of configuration

.DEFAULT_GOAL := help

.PHONY: all
all: help

# Auto documented help from target comments
#	https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
.PHONY: help
help:	## print this help message (default)
	@echo "$(APP_NAME) help"
	@echo "Please use 'make <target>' where <target> is one of:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(word 1,$(MAKEFILE_LIST)) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'

.PHONY: version
version:	## display current version
	@-echo "$(APP_NAME) version: $(APP_VERSION)"

.PHONY: info
info:		## display make information
	@echo "Informations about your Bird:"
	@echo "  OS_NAME             $(OS_NAME)"
	@echo "  CPU_ARCH            $(CPU_ARCH)"
	@echo "  Conda Home          $(CONDA_HOME)"
	@echo "  Conda Environment   $(CONDA_ENV)"
	@echo "  Conda Prefix        $(CONDA_ENV_PATH)"
	@echo "  Conda Binary        $(CONDA_BIN)"
	@echo "  Conda Actication    $(CONDA_ENV_MODE)"
	@echo "  Conda Command       $(CONDA_CMD)"
	@echo "  APP_NAME            $(APP_NAME)"
	@echo "  APP_ROOT            $(APP_ROOT)"
	@echo "  DOWNLOAD_CACHE      $(DOWNLOAD_CACHE)"
	@echo "  DOCKER_REPO         $(DOCKER_REPO)"

## Helper targets

.PHONY: mkdir-reports
mkdir-reports:
	@mkdir -p "$(REPORTS_DIR)"

## conda targets

.PHONY: conda-base
conda-base:		## obtain and install a missing conda distribution
	@echo "Validating conda installation..."
	@test -f "$(CONDA_HOME)/bin/conda" || test -d "$(DOWNLOAD_CACHE)" || \
		(echo "Creating download directory: $(DOWNLOAD_CACHE)" && mkdir -p "$(DOWNLOAD_CACHE)")
	@test -f "$(CONDA_HOME)/bin/conda" || test -f "$(DOWNLOAD_CACHE)/$(FN)" || \
		(echo "Fetching conda distribution from: $(CONDA_URL)/$(FN)" && \
		 curl "$(CONDA_URL)/$(FN)" --insecure --output "$(DOWNLOAD_CACHE)/$(FN)")
	@test -f "$(CONDA_HOME)/bin/conda" || \
		(bash "$(DOWNLOAD_CACHE)/$(FN)" -b -u -p "$(CONDA_HOME)" && \
		 echo "Make sure to add '$(CONDA_HOME)/bin' to your PATH variable in '~/.bashrc'.")

.PHONY: conda-config
conda-config: conda-base	## setup configuration of the conda environment
	@echo "Updating conda configuration..."
	@"$(CONDA_BIN)" config --add envs_dirs $(CONDA_ENVS_DIR)
	@"$(CONDA_BIN)" config --set ssl_verify true
	#@"$(CONDA_BIN)" config --set use_pip true
	@"$(CONDA_BIN)" config --set channel_priority true
	@"$(CONDA_BIN)" config --set auto_update_conda false
	@"$(CONDA_BIN)" config --add channels defaults
	@"$(CONDA_BIN)" config --append channels conda-forge

.PHONY: conda-env
conda-env: conda-base conda-config	## create the conda environment
	@test -d "$(CONDA_ENV_PATH)" || \
		(echo "Creating conda environment at '$(CONDA_ENV_PATH)'..." && \
		 "$(CONDA_HOME)/bin/conda" create -y -n "$(CONDA_ENV)" python=$(PYTHON_VERSION))

.PHONY: conda-pinned
conda-pinned: conda-env		## pin the conda version
	@echo "Update pinned conda packages..."
	@-test -d $(CONDA_ENV_PATH) && test -f $(CONDA_PINNED) && \
		cp -f "$(CONDA_PINNED)" "$(CONDA_ENV_PATH)/conda-meta/pinned"

.PHONY: conda-env-export
conda-env-export:		## export the conda environment
	@echo "Exporting conda enviroment..."
	@test -d $(CONDA_ENV_PATH) && "$(CONDA_BIN)" env export -n $(CONDA_ENV) -f environment.yml

## Build targets

.PHONY: install
install: install-sys install-pip install-pkg  ## install application with all its dependencies

.PHONY: install-dev
install-dev: install-pip	## install developement and test dependencies
	@echo "Installing development packages with pip..."
	@-bash -c '$(CONDA_CMD) pip install -r $(APP_ROOT)/requirements-dev.txt'
	@echo "Install with pip complete. Test service with \`make test*' variations."

.PHONY: install-pkg
install-pkg: install-pip	## install application package dependencies
	@echo "Installing base packages with pip..."
	@-bash -c "$(CONDA_CMD) pip install -r $(APP_ROOT)/requirements.txt --no-cache-dir"
	@echo "Install with pip complete."

.PHONY: install-sys
install-sys: clean conda-env	## install system dependencies and required installers/runners
	@echo "Installing system dependencies..."
	@bash -c '$(CONDA_CMD) pip install --upgrade pip setuptools gunicorn'

.PHONY: install-pip
install-pip:	## install application as a package to allow import from another python package
	@echo "Installing package with pip..."
	@-bash -c '$(CONDA_CMD) pip install $(APP_ROOT)'
	@echo "Install with pip complete."

.PHONY: install-raw
install-raw:	## install without any requirements or dependencies (suppose everything is setup)
	@echo "Installing package without dependencies..."
	@-bash -c '$(CONDA_CMD) pip install -e "$(APP_ROOT)" --no-deps'
	@echo "Install package complete."

## Cleanup targets

.PHONY: clean
clean: clean-build clean-cache clean-src clean-test		## run all cleanup targets

.PHONY: clean-build
clean-build:		## remove the temporary build files
	@echo "Removing build files..."
	@-rm -fr "$(APP_ROOT)/eggs"
	@-rm -fr "$(APP_ROOT)/develop-eggs"
	@-rm -fr "$(APP_ROOT)/$(APP_NAME).egg-info"
	@-rm -fr "$(APP_ROOT)/parts"

.PHONY: clean-cache
clean-cache:		## remove caches such as DOWNLOAD_CACHE
	@echo "Removing caches..."
	@-rm -fr "$(APP_ROOT)/.pytest_cache"
	@-rm -fr "$(DOWNLOAD_CACHE)"

.PHONY: clean-env
clean-env: 		## remove the conda enviroment
	@echo "Removing conda env '$(CONDA_ENV)'"
	@-test -d "$(CONDA_ENV_PATH)" && "$(CONDA_BIN)" remove -n $(CONDA_ENV) --yes --all

.PHONY: clean-src
clean-src:		## remove all *.pyc files
	@echo "Removing *.pyc files..."
	@-find "$(APP_ROOT)" -type f -name "*.pyc" -exec rm {} \;
	@-rm -rf ./src

.PHONY: clean-test
clean-test:		## remove files created by code checks, tests, coverage and report
	@echo "Removing test/coverage/report files..."
	@-rm -f "$(APP_ROOT)/.coverage"
	@-rm -f "$(APP_ROOT)/coverage.*"
	@-rm -fr "$(APP_ROOT)/coverage"
	@-rm -fr "$(REPORTS_DIR)"

.PHONY: clean-dist
clean-dist: clean	## remove *all* files that are not controlled by 'git' except *.bak and makefile configuration
	@echo "Cleaning distribution..."
	@git diff --quiet HEAD || echo "There are uncommited changes! Not doing 'git clean'..."
	@-git clean -dfx -e *.bak -e Makefile.config

## Testing targets

.PHONY: test-unit
test-unit:		## run unit tests (skip long running and online tests)
	@echo "Running tests (skip slow and online tests)..."
	bash -c "$(CONDA_CMD) pytest tests -v -m 'not slow and not online and not functional' --junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: test-func
test-func:		## run funtional tests (online and usage specific)
	@echo "Running functional tests..."
	bash -c "$(CONDA_CMD) pytest tests -v -m 'functional' --junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: test-online
test-online:	## run online tests (running instance required)
	@echo "Running online tests (running instance required)..."
	bash -c "$(CONDA_CMD) pytest tests -v -m 'online' --junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: test-offline
test-offline:	## run offline tests (not marked as online)
	@echo "Running offline tests (not marked as online)..."
	bash -c "$(CONDA_CMD) pytest tests -v -m 'not online' --junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: test-no-tb14
test-no-tb14:	## run all tests except ones marked for 'Testbed-14'
	@echo "Running all tests except ones marked for 'Testbed-14'..."
	bash -c "$(CONDA_CMD) pytest tests -v -m 'not testbed14' --junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: test-all
test-all:	## run all tests (including long running tests)
	@echo "Running all tests (including slow and online tests)..."
	bash -c "$(CONDA_CMD) pytest tests -v --junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: test
test:	## run custom tests from input specification (make TESTS='<spec>' test) [ex: make TESTS='not functional' test]
	@echo "Running custom tests from input specification..."
	@[ "${TESTS}" ] || ( echo ">> 'TESTS' is not set"; exit 1 )
	bash -c "$(CONDA_CMD) pytest tests -v -m '${TESTS}' --junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: coverage
coverage: mkdir-reports		## run all tests using coverage analysis
	@echo "Running coverage analysis..."
	@bash -c '$(CONDA_CMD) coverage run -m pytest "$(APP_ROOT)/tests" || true'
	@bash -c '$(CONDA_CMD) coverage xml --rcfile="$(APP_ROOT)/setup.cfg" -i -o "$(REPORTS_DIR)/coverage.xml"'
	@bash -c '$(CONDA_CMD) coverage report --rcfile="$(APP_ROOT)/setup.cfg" -i -m'
	@bash -c '$(CONDA_CMD) coverage html --rcfile="$(APP_ROOT)/setup.cfg" -d "$(REPORTS_DIR)/coverage"'

## Documentation and code check targets

.PHONY: check-pep8
check-pep8: mkdir-reports		## run PEP8 code style checks
	@echo "Running pep8 code style checks..."
	@bash -c '$(CONDA_CMD) flake8 --config="$(APP_ROOT)/setup.cfg" --tee --output-file="$(REPORTS_DIR)/pep8.txt"'

.PHONY: check-lint
check-lint: mkdir-reports		## run linting code style checks
	@echo "Running linting code style checks..."
	@bash -c '$(CONDA_CMD) \
		pylint --rcfile="$(APP_ROOT)/setup.cfg" "$(APP_ROOT)/weaver" "$(APP_ROOT)/tests" --reports y \
		| tee "$(REPORTS_DIR)/lint.txt"'

.PHONY: check-imports
check-imports:					## run imports code checks
	@bash -c '$(CONDA_CMD) isort --check-only --diff --recursive $(APP_ROOT) | tee "$(REPORTS_DIR)/imports.txt"'

.PHONY: check-security
check-security: mkdir-reports	## run security code checks
	@echo "Running security code checks..."
	@bash -c '$(CONDA_CMD) bandit -v -r "$(APP_ROOT)/weaver" | tee "$(REPORTS_DIR)/secure.txt"'

.PHONY: checks
checks: check-pep8 check-lint check-security check-doc8 check-links	## run every code style checks

.PHONY: check-doc8
check-doc8:	## run doc8 documentation style checks
	@echo "Running doc8 doc style checks..."
	@bash -c '$(CONDA_CMD) doc8 "$(APP_ROOT)/docs"'

.PHONY: check-links
check-links:		## check all external links in documentation for integrity
	@echo "Run link checker on docs..."
	@bash -c '$(CONDA_CMD) (MAKE) -C "$(APP_ROOT)/docs" linkcheck'

.PHONY: docs
docs:	## generate HTML documentation with Sphinx
	@echo "Generating docs with Sphinx..."
	@bash -c '$(CONDA_CMD) $(MAKE) -C $@ clean html'
	@echo "open your browser:"
	@echo "		firefox '$(APP_ROOT)/docs/build/html/index.html'"

## Bumpversion targets

# Bumpversion 'dry' config
# if 'dry' is specified as target, any bumpversion call using 'BUMP_XARGS' will not apply changes
BUMP_XARGS ?= --verbose --allow-dirty
ifeq ($(filter dry, $(MAKECMDGOALS)), dry)
	BUMP_XARGS := $(BUMP_XARGS) --dry-run
endif
.PHONY: dry
dry: setup.cfg
	@-echo > /dev/null

.PHONY: bump
bump:
	@-echo "Updating package version ..."
	@[ "${VERSION}" ] || ( echo ">> 'VERSION' is not set"; exit 1 )
	@-bash -c '$(CONDA_CMD) bump2version $(BUMP_XARGS) --new-version "${VERSION}" patch;'

## Docker targets

.PHONY: docker-info
docker-info:		## obtain docker image information
	@echo "Docker image will be built, tagged and pushed as:"
	@echo "$(DOCKER_REPO):$(APP_VERSION)"

.PHONY: docker-build
docker-build:		## build the docker image
	@bash -c 'docker build "$(APP_ROOT)/docker" -f Dockerfile-manager -t "$(DOCKER_REPO):$(APP_VERSION)"'

.PHONY: docker-push
docker-push: docker-build	## push the docker image
	@bash -c 'docker push "$(DOCKER_REPO):$(APP_VERSION)"'

## Supervisor targets

.PHONY: start
start:	## start the application with gunicorn
	@echo "Starting application service..."
	@echo '>>  "$(APP_ROOT)/bin/gunicorn" --paste "$(APP_INI)" --preload'
	@-bash -c '$(CONDA_CMD) "$(APP_ROOT)/bin/gunicorn" --paste "$(APP_INI)" --preload'
