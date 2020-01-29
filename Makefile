RELEASE := master

# Included custom configs change the value of MAKEFILE_LIST
# Extract the required reference beforehand so we can use it for help target
MAKEFILE_NAME := $(word $(words $(MAKEFILE_LIST)),$(MAKEFILE_LIST))
# Include custom config if it is available
-include Makefile.config

# Application
APP_ROOT    := $(abspath $(lastword $(MAKEFILE_NAME))/..)
APP_NAME    := $(shell basename $(APP_ROOT))
APP_VERSION ?= 1.0.0
APP_INI     ?= $(APP_ROOT)/config/$(APP_NAME).ini
DOCKER_REPO ?= docker-registry.crim.ca/ogc/weaver

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
# environment already active - use it directly
ifneq ("$(CONDA_ENV_REAL_ACTIVE_PATH)", "")
	CONDA_ENV_MODE := [using active environment]
	CONDA_ENV := $(notdir $(CONDA_ENV_REAL_ACTIVE_PATH))
	CONDA_CMD :=
endif
# environment not active but it exists - activate and use it
ifneq ($(CONDA_ENV_REAL_TARGET_PATH), "")
	CONDA_ENV := $(notdir $(CONDA_ENV_REAL_TARGET_PATH))
endif
# environment not active and not found - create, activate and use it
ifeq ("$(CONDA_ENV)", "")
	CONDA_ENV := $(APP_NAME)
endif
# update paths for environment activation
ifeq ("$(CONDA_ENV_REAL_ACTIVE_PATH)", "")
	CONDA_ENV_MODE := [will activate environment]
	CONDA_CMD := source "$(CONDA_HOME)/bin/activate" "$(CONDA_ENV)";
endif
DOWNLOAD_CACHE ?= $(APP_ROOT)/downloads
PYTHON_VERSION ?= `python -c 'import platform; print(platform.python_version())'`

# choose conda installer depending on your OS
CONDA_URL = https://repo.continuum.io/miniconda
ifeq ("$(OS_NAME)", "Linux")
FN := Miniconda3-latest-Linux-x86_64.sh
else ifeq ("$(OS_NAME)", "Darwin")
FN := Miniconda3-latest-MacOSX-x86_64.sh
else
FN := unknown
endif

# Tests
REPORTS_DIR := $(APP_ROOT)/reports

# end of configuration

.DEFAULT_GOAL := help

## --- Informative targets --- ##

.PHONY: all
all: help

# Auto documented help targets & sections from comments
#	- detects lines marked by double octothorpe (#), then applies the corresponding target/section markup
#   - target comments must be defined after their dependencies (if any)
#	- section comments must have at least a double dash (-)
#
# 	Original Reference:
#		https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
# 	Formats:
#		https://misc.flogisoft.com/bash/tip_colors_and_formatting
_SECTION := \033[34m
_TARGET  := \033[36m
_NORMAL  := \033[0m
.PHONY: help
# note: use "\#\#" to escape results that would self-match in this target's search definition
help:	## print this help message (default)
	@echo "$(_SECTION)=== $(APP_NAME) help ===$(_NORMAL)"
	@echo "Please use 'make <target>' where <target> is one of:"
#	@grep -E '^[a-zA-Z_-]+:.*?\#\# .*$$' $(MAKEFILE_LIST) \
#		| awk 'BEGIN {FS = ":.*?\#\# "}; {printf "    $(_TARGET)%-24s$(_NORMAL) %s\n", $$1, $$2}'
	@grep -E '\#\#.*$$' "$(APP_ROOT)/$(MAKEFILE_NAME)" \
		| awk ' BEGIN {FS = "(:|\-\-\-)+.*?\#\# "}; \
			/\--/ {printf "$(_SECTION)%s$(_NORMAL)\n", $$1;} \
			/:/   {printf "    $(_TARGET)%-24s$(_NORMAL) %s\n", $$1, $$2} \
		'

.PHONY: version
version:	## display current version
	@-echo "$(APP_NAME) version: $(APP_VERSION)"

.PHONY: info
info:		## display make information
	@echo "Makefile configuration details:"
	@echo "  OS Name            $(OS_NAME)"
	@echo "  CPU Architecture   $(CPU_ARCH)"
	@echo "  Conda Home         $(CONDA_HOME)"
	@echo "  Conda Prefix       $(CONDA_ENV_PATH)"
	@echo "  Conda Env Name     $(CONDA_ENV)"
	@echo "  Conda Env Path     $(CONDA_ENV_REAL_ACTIVE_PATH)"
	@echo "  Conda Binary       $(CONDA_BIN)"
	@echo "  Conda Actication   $(CONDA_ENV_MODE)"
	@echo "  Conda Command      $(CONDA_CMD)"
	@echo "  Application Name   $(APP_NAME)"
	@echo "  Application Root   $(APP_ROOT)"
	@echo "  Donwload Cache     $(DOWNLOAD_CACHE)"
	@echo "  Docker Repository  $(DOCKER_REPO)"

## -- Conda targets -- ##

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

.PHONY: conda-clean
clean-clean: 	## remove the conda enviroment
	@echo "Removing conda env '$(CONDA_ENV)'"
	@-test -d "$(CONDA_ENV_PATH)" && "$(CONDA_BIN)" remove -n $(CONDA_ENV) --yes --all

.PHONY: conda-config
conda-config: conda-base	## setup configuration of the conda environment
	@echo "Updating conda configuration..."
	@"$(CONDA_BIN)" config --add envs_dirs $(CONDA_ENVS_DIR)
	@"$(CONDA_BIN)" config --set ssl_verify true
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

## -- Build targets -- ##

.PHONY: install
install: install-all	## alias for 'install-all' target

.PHONY: install-all
install-all: install-sys install-pip install-pkg install-dev  ## install application with all its dependencies

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
install-sys: conda-env	## install system dependencies and required installers/runners
	@echo "Installing system dependencies..."
	@bash -c '$(CONDA_CMD) pip install --upgrade pip setuptools'

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

## -- Cleanup targets -- ##

.PHONY: clean
clean: clean-all	## alias for 'clean-all' target

.PHONY: clean-all
clean-all: clean-build clean-cache clean-docs-dirs clean-src clean-reports clean-test	## run all cleanup targets

.PHONY: clean-build
clean-build:	## remove the temporary build files
	@echo "Removing build files..."
	@-rm -fr "$(APP_ROOT)/eggs"
	@-rm -fr "$(APP_ROOT)/develop-eggs"
	@-rm -fr "$(APP_ROOT)/$(APP_NAME).egg-info"
	@-rm -fr "$(APP_ROOT)/parts"

.PHONY: clean-cache
clean-cache:	## remove caches such as DOWNLOAD_CACHE
	@echo "Removing caches..."
	@-rm -fr "$(APP_ROOT)/.pytest_cache"
	@-rm -fr "$(DOWNLOAD_CACHE)"

.PHONY: clean-docs
clean-docs:	install-dev clean-docs-dirs		## remove documentation artefacts
	@echo "Removing documenation build files..."
	@$(MAKE) -C "$(APP_ROOT)/docs" clean

# extensive cleanup is possible only using sphinx-build
# allow minimal cleanup when it could not *yet* be installed (dev)
.PHONY: clean-docs-dirs
clean-docs-dirs:	## remove documentation artefacts (minimal)
	@echo "Removing documenation directories..."
	@-rm -fr "$(APP_ROOT)/docs/build"
	@-rm -fr "$(APP_ROOT)/docs/html"
	@-rm -fr "$(APP_ROOT)/docs/xml"

.PHONY: clean-src
clean-src:		## remove all *.pyc files
	@echo "Removing python artifacts..."
	@-find "$(APP_ROOT)" -type f -name "*.pyc" -exec rm {} \;
	@-rm -rf ./src

.PHONY: clean-test
clean-test:		## remove files created by tests and coverage analysis
	@echo "Removing test/coverage/report files..."
	@-rm -f "$(APP_ROOT)/.coverage"
	@-rm -f "$(APP_ROOT)/coverage.*"
	@-rm -fr "$(APP_ROOT)/coverage"

.PHONY: clean-reports
clean-reports:	## remove report files genereated by code checks
	@-rm -fr "$(REPORTS_DIR)"

.PHONY: clean-dist
clean-dist: clean	## remove *all* files that are not controlled by 'git' except *.bak and makefile configuration
	@echo "Cleaning distribution..."
	@git diff --quiet HEAD || echo "There are uncommited changes! Not doing 'git clean'..."
	@-git clean -dfx -e *.bak -e Makefile.config

## -- Testing targets -- ##

.PHONY: test
test: clean-test test-all	## alias for 'test-all' target

.PHONY: test-all
test-all: install-dev		## run all tests (including long running tests)
	@echo "Running all tests (including slow and online tests)..."
	@bash -c "$(CONDA_CMD) pytest tests -v --junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: test-unit
test-unit: install-dev		## run unit tests (skip long running and online tests)
	@echo "Running tests (skip slow and online tests)..."
	@bash -c "$(CONDA_CMD) pytest tests -v -m 'not slow and not online and not functional' \
	 	--junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: test-func
test-func: install-dev		## run funtional tests (online and usage specific)
	@echo "Running functional tests..."
	@bash -c "$(CONDA_CMD) pytest tests -v -m 'functional' --junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: test-online
test-online: install-dev 	## run online tests (running instance required)
	@echo "Running online tests (running instance required)..."
	@bash -c "$(CONDA_CMD) pytest tests -v -m 'online' --junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: test-offline
test-offline: install-dev	## run offline tests (not marked as online)
	@echo "Running offline tests (not marked as online)..."
	@bash -c "$(CONDA_CMD) pytest tests -v -m 'not online' --junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: test-no-tb14
test-no-tb14: install-dev	## run all tests except ones marked for 'Testbed-14'
	@echo "Running all tests except ones marked for 'Testbed-14'..."
	@bash -c "$(CONDA_CMD) pytest tests -v -m 'not testbed14' --junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: test-spec
test-spec: install-dev		## run tests with custom input specification (pytest format) [make TESTS='<spec>' test-spec]
	@echo "Running custom tests from input specification..."
	@[ "${TESTS}" ] || ( echo ">> 'TESTS' is not set"; exit 1 )
	@bash -c "$(CONDA_CMD) pytest tests -v -m '${TESTS}' --junitxml $(APP_ROOT)/tests/results.xml"

.PHONY: coverage
coverage: mkdir-reports install-dev		## run all tests using coverage analysis
	@echo "Running coverage analysis..."
	@bash -c '$(CONDA_CMD) coverage run -m pytest "$(APP_ROOT)/tests" || true'
	@bash -c '$(CONDA_CMD) coverage xml --rcfile="$(APP_ROOT)/setup.cfg" -i -o "$(REPORTS_DIR)/coverage.xml"'
	@bash -c '$(CONDA_CMD) coverage report --rcfile="$(APP_ROOT)/setup.cfg" -i -m'
	@bash -c '$(CONDA_CMD) coverage html --rcfile="$(APP_ROOT)/setup.cfg" -d "$(REPORTS_DIR)/coverage"'

## -- Static code check targets -- ##

.PHONY: mkdir-reports
mkdir-reports:
	@mkdir -p "$(REPORTS_DIR)"

.PHONY: check
check: check-all	## alias for 'check-all' target

.PHONY: check-all
check-all: install-dev check-pep8 check-lint check-security check-doc8 check-links	## run every code style checks

.PHONY: check-pep8
check-pep8: mkdir-reports install-dev 	## run PEP8 code style checks
	@echo "Running pep8 code style checks..."
	@-rm -fr "$(REPORTS_DIR)/check-pep8.txt"
	@bash -c '$(CONDA_CMD) \
		flake8 --config="$(APP_ROOT)/setup.cfg" --output-file="$(REPORTS_DIR)/check-pep8.txt" --tee'

.PHONY: check-lint
check-lint: mkdir-reports install-dev	## run linting code style checks
	@echo "Running linting code style checks..."
	@-rm -fr "$(REPORTS_DIR)/check-lint.txt"
	@bash -c '$(CONDA_CMD) \
		pylint \
			--load-plugins pylint_quotes \
			--rcfile="$(APP_ROOT)/.pylintrc" "$(APP_ROOT)/weaver" "$(APP_ROOT)/tests" \
			--reports y \
		1> >(tee "$(REPORTS_DIR)/check-lint.txt")'

.PHONY: check-security
check-security: mkdir-reports install-dev	## run security code checks
	@echo "Running security code checks..."
	@-rm -fr "$(REPORTS_DIR)/check-security.txt"
	@bash -c '$(CONDA_CMD) \
		bandit -v --ini "$(APP_ROOT)/setup.cfg" -r \
		1> >(tee "$(REPORTS_DIR)/check-security.txt")'

.PHONY: check-doc8
check-doc8: mkdir-reports install-dev	## run doc8 documentation style checks
	@echo "Running doc8 doc style checks..."
	@-rm -fr "$(REPORTS_DIR)/check-doc8.txt"
	@bash -c '$(CONDA_CMD) \
		doc8 "$(APP_ROOT)/docs" \
		1> >(tee "$(REPORTS_DIR)/check-doc8.txt")'

.PHONY: check-links
check-links: install-dev	## check all external links in documentation for integrity
	@echo "Running link checks on docs..."
	@bash -c '$(CONDA_CMD) $(MAKE) -C "$(APP_ROOT)/docs" linkcheck'

.PHONY: check-imports
check-imports: mkdir-reports install-dev	## run imports code checks
	@echo "Running import checks..."
	@-rm -fr "$(REPORTS_DIR)/check-imports.txt"
	@bash -c '$(CONDA_CMD) \
		isort --check-only --diff --recursive $(APP_ROOT) \
		1> >(tee "$(REPORTS_DIR)/check-imports.txt")'

.PHONY: fix-imports
fix-imports: mkdir-reports install-dev	## apply import code checks corrections
	@echo "Fixing flagged import checks..."
	@-rm -fr "$(REPORTS_DIR)/fixed-imports.txt"
	@bash -c '$(CONDA_CMD) \
		isort --recursive $(APP_ROOT) \
		1> >(tee "$(REPORTS_DIR)/fixed-imports.txt")'

## -- Documentation targets -- ##

.PHONY: docs
docs: install-dev clean-docs 	## generate HTML documentation with Sphinx
	@echo "Generating docs with Sphinx..."
	@bash -c '$(CONDA_CMD) $(MAKE) -C $@ html'

## -- Versionning targets -- ##

# Bumpversion 'dry' config
# if 'dry' is specified as target, any bumpversion call using 'BUMP_XARGS' will not apply changes
BUMP_XARGS ?= --verbose --allow-dirty
ifeq ($(filter dry, $(MAKECMDGOALS)), dry)
	BUMP_XARGS := $(BUMP_XARGS) --dry-run
endif
.PHONY: dry
dry: setup.cfg	## run 'bump' target without applying changes (dry-run) [make VERSION=<x.y.z> bump dry]
	@-echo > /dev/null

.PHONY: bump
bump:  ## bump version using VERSION specified as user input [make VERSION=<x.y.z> bump]
	@-echo "Updating package version ..."
	@[ "${VERSION}" ] || ( echo ">> 'VERSION' is not set"; exit 1 )
	@-bash -c '$(CONDA_CMD) bump2version $(BUMP_XARGS) --new-version "${VERSION}" patch;'

## -- Docker targets -- ##

.PHONY: docker-info
docker-info:		## obtain docker image information
	@echo "Docker image will be built as: "
	@echo "$(APP_NAME):$(APP_VERSION)"
	@echo "Docker image will be pushed as:"
	@echo "$(DOCKER_REPO):$(APP_VERSION)"

.PHONY: docker-build-base
docker-build-base:							## build the base docker image
	docker build "$(APP_ROOT)" -f "$(APP_ROOT)/docker/Dockerfile-base" -t "$(APP_NAME):$(APP_VERSION)"
	docker tag "$(APP_NAME):$(APP_VERSION)" "$(DOCKER_REPO):$(APP_VERSION)"
	docker tag "$(APP_NAME):$(APP_VERSION)" "$(DOCKER_REPO):latest"

.PHONY: docker-build-manager
docker-build-manager: docker-build-base		## build the manager docker image
	docker build "$(APP_ROOT)" -f "$(APP_ROOT)/docker/Dockerfile-manager" -t "$(APP_NAME):$(APP_VERSION)-manager"
	docker tag "$(APP_NAME):$(APP_VERSION)-manager" "$(DOCKER_REPO):$(APP_VERSION)-manager"
	docker tag "$(APP_NAME):$(APP_VERSION)-manager" "$(DOCKER_REPO):latest-manager"

.PHONY: docker-build-worker
docker-build-worker: docker-build-base		## build the worker docker image
	docker build "$(APP_ROOT)" -f "$(APP_ROOT)/docker/Dockerfile-worker" -t "$(APP_NAME):$(APP_VERSION)-worker"
	docker tag "$(APP_NAME):$(APP_VERSION)-worker" "$(DOCKER_REPO):$(APP_VERSION)-worker"
	docker tag "$(APP_NAME):$(APP_VERSION)-worker" "$(DOCKER_REPO):latest-worker"

.PHONY: docker-build
docker-build: docker-build-base docker-build-manager docker-build-worker		## build all docker images

.PHONY: docker-push-base
docker-push-base: docker-build-base			## push the base docker image
	docker push "$(DOCKER_REPO):$(APP_VERSION)"
	docker push "$(DOCKER_REPO):latest"

.PHONY: docker-push-manager
docker-push-manager: docker-build-manager	## push the manager docker image
	docker push "$(DOCKER_REPO):$(APP_VERSION)-manager"
	docker push "$(DOCKER_REPO):latest-manager"

.PHONY: docker-push-worker
docker-push-worker: docker-build-worker		## push the worker docker image
	docker push "$(DOCKER_REPO):$(APP_VERSION)-worker"
	docker push "$(DOCKER_REPO):latest-worker"

.PHONY: docker-push
docker-push: docker-push-base docker-push-manager docker-push-worker	## push all docker images

## --- Launchers targets --- ##

.PHONY: start
start: install	## start application instance(s) with gunicorn (pserve)
	@echo "Starting $(APP_NAME)..."
	@bash -c '$(CONDA_CMD) exec pserve "$(APP_INI)" &'

.PHONY: stop
stop: 		## kill application instance(s) started with gunicorn (pserve)
	@(lsof -t -i :4001 | xargs kill) 2>/dev/null || echo "No $(APP_NAME) process to stop"

.PHONY: stat
stat: 		## display processes with PID(s) of gunicorn (pserve) instance(s) running the application
	@lsof -i :4001 || echo "No instance running"
