RELEASE := master

# Included custom configs change the value of MAKEFILE_LIST
# Extract the required reference beforehand so we can use it for help target
MAKEFILE_NAME := $(word $(words $(MAKEFILE_LIST)),$(MAKEFILE_LIST))
# Include custom config if it is available
-include Makefile.config

# Application
APP_ROOT    := $(abspath $(lastword $(MAKEFILE_NAME))/..)
APP_NAME    := $(shell basename $(APP_ROOT))
APP_VERSION ?= 6.6.0
APP_INI     ?= $(APP_ROOT)/config/$(APP_NAME).ini

# guess OS (Linux, Darwin,...)
OS_NAME := $(shell uname -s 2>/dev/null || echo "unknown")
CPU_ARCH := $(shell uname -m 2>/dev/null || uname -p 2>/dev/null || echo "unknown")

# conda
CONDA_CMD      ?= __EMPTY__
CONDA_ENV      ?= $(APP_NAME)
CONDA_HOME     ?= $(HOME)/.conda
CONDA_ENVS_DIR ?= $(CONDA_HOME)/envs
CONDA_ENV_PATH := $(CONDA_ENVS_DIR)/$(CONDA_ENV)
ifneq ($(CONDA_CMD),__EMPTY__)
  CONDA_CMD :=
  CONDA_BIN :=
  CONDA_ENV :=
  CONDA_ENV_MODE := [using overridden conda command]
else
  CONDA_CMD :=
  # allow pre-installed conda in Windows bash-like shell
  ifeq ($(findstring MINGW,$(OS_NAME)),MINGW)
    CONDA_BIN_DIR ?= $(CONDA_HOME)/Scripts
  else
    CONDA_BIN_DIR ?= $(CONDA_HOME)/bin
  endif
  CONDA_BIN ?= $(CONDA_BIN_DIR)/conda
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
    CONDA_CMD := source "$(CONDA_BIN_DIR)/activate" "$(CONDA_ENV)";
  endif
endif
DOWNLOAD_CACHE ?= $(APP_ROOT)/downloads
PYTHON_VERSION ?= `python -c 'import platform; print(platform.python_version())'`
PYTHON_VERSION_MAJOR := $(shell echo $(PYTHON_VERSION) | cut -f 1 -d '.')
PYTHON_VERSION_MINOR := $(shell echo $(PYTHON_VERSION) | cut -f 2 -d '.')
PYTHON_VERSION_PATCH := $(shell echo $(PYTHON_VERSION) | cut -f 3 -d '.' | cut -f 1 -d ' ')
PIP_USE_FEATURE := `python -c '\
	import pip; \
	try: \
		from packaging.version import Version \
	except ImportError: \
		from distutils.version import LooseVersion as Version \
	print(Version(pip.__version__) < Version("21.0"))'`
PIP_XARGS ?=
ifeq ("$(PIP_USE_FEATURE)", "True")
  PIP_XARGS := --use-feature=2020-resolver $(PIP_XARGS)
endif

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
ARCHIVE_DIR := $(APP_ROOT)/archive

# end of configuration

.DEFAULT_GOAL := help

## -- Informative targets ------------------------------------------------------------------------------------------- ##

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
	@echo "$(_SECTION)=======================================$(_NORMAL)"
	@echo "$(_SECTION) $(APP_NAME) help $(_NORMAL)"
	@echo "$(_SECTION)=======================================$(_NORMAL)"
	@echo "Please use 'make <target>' where <target> is one of below options."
	@echo ""
	@echo "NOTE:"
	@echo "  Targets suffixed '<target>-only' can be called as '<target> to run setup before their main operation."
	@echo ""
#	@grep -E '^[a-zA-Z_-]+:.*?\#\# .*$$' $(MAKEFILE_LIST) \
#		| awk 'BEGIN {FS = ":.*?\#\# "}; {printf "    $(_TARGET)%-24s$(_NORMAL) %s\n", $$1, $$2}'
	@grep -E '\#\#.*$$' "$(APP_ROOT)/$(MAKEFILE_NAME)" \
		| awk ' BEGIN {FS = "(:|\-\-\-)+.*?\#\# "}; \
			/\--/ {printf "$(_SECTION)%s$(_NORMAL)\n", $$1;} \
			/:/   {printf "    $(_TARGET)%-24s$(_NORMAL) %s\n", $$1, $$2} \
		'

.PHONY: targets
targets: help

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
	@echo "  Conda Activation   $(CONDA_ENV_MODE)"
	@echo "  Conda Command      $(CONDA_CMD)"
	@echo "  Application Name   $(APP_NAME)"
	@echo "  Application Root   $(APP_ROOT)"
	@echo "  Download Cache     $(DOWNLOAD_CACHE)"
	@echo "  Docker Repository  $(DOCKER_REPO)"

.PHONY: fixme-list-only
fixme-list-only: mkdir-reports  	## list all FIXME/TODO/HACK items that require attention in the code
	@echo "Listing code that requires fixes..."
	@echo '[MISCELLANEOUS]\nnotes=FIXME,TODO,HACK' > "$(REPORTS_DIR)/fixmerc"
	@bash -c '$(CONDA_CMD) \
		pylint \
			--disable=all,use-symbolic-message-instead --enable=miscellaneous,W0511 \
			--score n --persistent n \
			--rcfile="$(REPORTS_DIR)/fixmerc" \
			-f colorized \
			"$(APP_ROOT)/weaver" "$(APP_ROOT)/tests" \
		1> >(tee "$(REPORTS_DIR)/fixme.txt")'

.PHONY: fixme-list
fixme-list: install-dev fixme-list-only  ## list all FIXME/TODO/HACK items with pre-installation of dependencies

## -- Conda targets ------------------------------------------------------------------------------------------------- ##

.PHONY: conda-base
conda-base:		## obtain and install a missing conda distribution
	@echo "Validating conda installation..."
	@test -f "$(CONDA_BIN)" || test -d "$(DOWNLOAD_CACHE)" || \
		(echo "Creating download directory: $(DOWNLOAD_CACHE)" && mkdir -p "$(DOWNLOAD_CACHE)")
	@test -f "$(CONDA_BIN)" || test -f "$(DOWNLOAD_CACHE)/$(FN)" || \
		(echo "Fetching conda distribution from: $(CONDA_URL)/$(FN)" && \
		 curl "$(CONDA_URL)/$(FN)" --insecure --location --output "$(DOWNLOAD_CACHE)/$(FN)")
	@test -f "$(CONDA_BIN)" || \
		(bash "$(DOWNLOAD_CACHE)/$(FN)" -b -u -p "$(CONDA_HOME)" && \
		 echo "Make sure to add '$(CONDA_BIN_DIR)' to your PATH variable in '~/.bashrc'.")

.PHONY: conda-clean
conda-clean: 	## remove the conda environment
	@echo "Removing conda env '$(CONDA_ENV)'"
	@-test -d "$(CONDA_ENV_PATH)" && "$(CONDA_BIN)" remove -n "$(CONDA_ENV)" --yes --all

.PHONY: conda-config
conda-config: conda-base	## setup configuration of the conda environment
	@echo "Updating conda configuration..."
	@ "$(CONDA_BIN)" config --add envs_dirs "$(CONDA_ENVS_DIR)"
	@ "$(CONDA_BIN)" config --set ssl_verify true
	@ "$(CONDA_BIN)" config --set channel_priority true
	@ "$(CONDA_BIN)" config --set auto_update_conda false
	@ "$(CONDA_BIN)" config --add channels defaults
	@ "$(CONDA_BIN)" config --append channels conda-forge

.PHONY: conda-install
conda-install: conda-env
	@echo "Updating conda packages..."
	@bash -c '$(CONDA_CMD) conda install -y -c conda-forge proj'

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
	@echo "Exporting conda environment..."
	@test -d $(CONDA_ENV_PATH) && "$(CONDA_BIN)" env export -n $(CONDA_ENV) -f environment.yml

## -- Build targets ------------------------------------------------------------------------------------------------- ##

.PHONY: install
install: install-all    ## alias for 'install-all' target

.PHONY: install-run
install-run: conda-install install-sys install-pkg install-raw 	## install requirements and application to run locally

.PHONY: install-all
install-all: conda-install install-sys install-pkg install-pip install-dev  ## install application with all dependencies

.PHONY: install-doc
install-doc: install-pip	## install documentation dependencies
	@echo "Installing development packages with pip..."
	@bash -c '$(CONDA_CMD) pip install $(PIP_XARGS) -r "$(APP_ROOT)/requirements-doc.txt"'
	@echo "Install with pip complete. Run documentation generation with 'make docs' target."

.PHONY: install-dev
install-dev: install-pip	## install development and test dependencies
	@echo "Installing development packages with pip..."
	@bash -c '$(CONDA_CMD) pip install $(PIP_XARGS) -r "$(APP_ROOT)/requirements-dev.txt"'
	@echo "Install with pip complete. Test service with 'make test*' variations."

.PHONY: install-pkg
install-pkg: install-pip	## install application package dependencies
	@echo "Installing base packages with pip..."
	@bash -c "$(CONDA_CMD) pip install $(PIP_XARGS) -r "$(APP_ROOT)/requirements.txt" --no-cache-dir"
	@echo "Install with pip complete."

# don't use 'PIP_XARGS' in this case since extra features could not yet be supported by pip being installed/updated
.PHONY: install-sys
install-sys:	## install system dependencies and required installers/runners
	@echo "Installing system dependencies..."
	@bash -c '$(CONDA_CMD) pip install --upgrade -r "$(APP_ROOT)/requirements-sys.txt"'

.PHONY: install-pip
install-pip:	## install application as a package to allow import from another python package
	@echo "Installing package with pip..."
	@-bash -c '$(CONDA_CMD) pip install $(PIP_XARGS) --upgrade -e "$(APP_ROOT)" --no-cache'
	@echo "Install with pip complete."

.PHONY: install-raw
install-raw:	## install without any requirements or dependencies (suppose everything is setup)
	@echo "Installing package without dependencies..."
	@bash -c '$(CONDA_CMD) pip install $(PIP_XARGS) -e "$(APP_ROOT)" --no-deps'
	@echo "Install package complete."

# install locally to ensure they can be found by config extending them
.PHONY: install-npm
install-npm:	## install npm package manager and dependencies if they cannot be found
	@[ -f "$(shell which npm)" ] || ( \
		echo "Binary package manager npm not found. Attempting to install it."; \
		apt-get install npm \
	)

.PHONY: install-npm-stylelint
install-npm-stylelint: install-npm	## install stylelint dependency for 'check-css' target using npm
	@[ `npm ls 2>/dev/null | grep stylelint-config-standard | grep -v UNMET | wc -l` = 1 ] || ( \
		echo "Install required dependencies for CSS checks." && \
		npm install --save-dev \
	)

.PHONY: install-npm-remarklint
install-npm-remarklint: install-npm		## install remark-lint dependency for 'check-md' target using npm
	@[ `npm ls 2>/dev/null | grep remark-lint | grep -v UNMET | wc -l` = 1 ] || ( \
		echo "Install required dependencies for Markdown checks." && \
		npm install --save-dev \
	)

.PHONY: install-dev-npm
install-dev-npm: install-npm install-npm-remarklint install-npm-remarklint  ## install all npm development dependencies

## -- Cleanup targets ----------------------------------------------------------------------------------------------- ##

.PHONY: clean
clean: clean-all	## alias for 'clean-all' target

.PHONY: clean-all
clean-all: clean-archive clean-build clean-cache clean-docs-dirs clean-src clean-reports clean-test	## run all cleanup targets

.PHONY: clean-archive
clean-archive:	## remove archive files and directories
	@-echo "Removing archives..."
	@-rm "$(APP_ROOT)"/*.tar.gz
	@-rm "$(APP_ROOT)"/*.zip
	@-rm -fr "$(ARCHIVE_DIR)"

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
clean-docs:	clean-docs-dirs		## remove documentation artifacts
	@echo "Removing documentation build files..."
	@$(MAKE) -C "$(APP_ROOT)/docs" clean || true

# extensive cleanup is possible only using sphinx-build
# allow minimal cleanup when it could not *yet* be installed (dev)
.PHONY: clean-docs-dirs
clean-docs-dirs:	## remove documentation artifacts (minimal)
	@echo "Removing documentation directories..."
	@-rm -fr "$(APP_ROOT)/docs/_build"
	@-rm -fr "$(APP_ROOT)/docs/build"
	@-rm -fr "$(APP_ROOT)/docs/source/autoapi"
	@-rm -fr "$(APP_ROOT)/docs/html"
	@-rm -fr "$(APP_ROOT)/docs/xml"

.PHONY: clean-src
clean-src:		## remove all *.pyc files
	@echo "Removing python artifacts..."
	@-find "$(APP_ROOT)" -type f -name "*.pyc" -exec rm {} \;
	@-rm -rf "$(APP_ROOT)/build"
	@-rm -rf "$(APP_ROOT)/src"

.PHONY: clean-test
clean-test:		## remove files created by tests and coverage analysis
	@echo "Removing test/coverage/report files..."
	@-rm -f "$(APP_ROOT)/.coverage"
	@-rm -f "$(APP_ROOT)/coverage.*"
	@-rm -fr "$(APP_ROOT)/coverage"
	@-rm -fr "$(REPORTS_DIR)/coverage"
	@-rm -fr "$(REPORTS_DIR)/test-*.xml"

.PHONY: clean-reports
clean-reports:	## remove report files generated by code checks
	@-rm -fr "$(REPORTS_DIR)"

.PHONY: clean-dist
clean-dist: clean	## remove *all* files that are not controlled by 'git' except *.bak and makefile configuration
	@echo "Cleaning distribution..."
	@git diff --quiet HEAD || echo "There are uncommitted changes! Not doing 'git clean'..."
	@-git clean -dfx -e *.bak -e Makefile.config

## -- Testing targets ----------------------------------------------------------------------------------------------- ##
## -- [variants '<target>-only' without '-only' suffix are also available with pre-install setup]

# -v:  list of test names with PASS/FAIL/SKIP/ERROR/etc. next to it
# -vv: extended collection of stdout/stderr on top of test results
TEST_VERBOSITY ?= -v
override TEST_VERBOSE_FLAG := $(shell echo $(TEST_VERBOSITY) | tr ' ' '\n' | grep -E "^\-v+" || echo "")
override TEST_VERBOSE_CAPTURE := $(shell \
	test $$(echo "$(TEST_VERBOSE_FLAG)" | tr -cd 'v' | wc -c) -gt 1 && echo 1 || echo 0 \
)
ifeq ($(filter $(TEST_VERBOSITY),"--capture"),)
  ifeq ($(TEST_VERBOSE_CAPTURE),1)
    TEST_VERBOSITY := $(TEST_VERBOSITY) --capture tee-sys
  endif
endif

TEST_PROFILE ?= true
ifneq ($(filter "$(TEST_PROFILE)","true"),)
  override TEST_PROFILE_ARGS = --profile --profile-svg --pstats-dir "$(REPORTS_DIR)/profiling" --durations 100
endif

TEST_XARGS ?=
override TEST_XARGS := $(TEST_VERBOSITY) $(TEST_PROFILE_ARGS) $(TEST_XARGS)

# autogen tests variants with pre-install of dependencies using the '-only' target references
TESTS := unit func cli workflow online offline no-tb14 spec coverage
TESTS := $(addprefix test-, $(TESTS))

$(TESTS): test-%: install-dev test-%-only

define run_test =
	$(eval $@_PYTEST_JUNIT = --junitxml "$(REPORTS_DIR)/test-results.xml")
	$(eval $@_PYTEST_CASE = $(1))
	$(eval $@_PYTEST_CMD = pytest tests ${$@_PYTEST_CASE} $(TEST_XARGS) ${$@__PYTEST_JUNIT})
	@echo ">" '${$@_PYTEST_CMD}'
	@bash -c '${$@_PYTEST_CMD}'
endef

.PHONY: test
test: clean-test test-all   ## alias for 'test-all' target

.PHONY: test-all
test-all: install-dev test-only		## run all tests (including long running tests)

.PHONY: test-only
test-only: mkdir-reports			## run all tests but without prior validation of installed dependencies
	@echo "Running all tests (including slow and online tests)..."
	@$(call run_test,)

.PHONY: test-unit-only
test-unit-only: mkdir-reports 		## run unit tests (skip long running and online tests)
	@echo "Running unit tests (skip slow and online tests)..."
	@$(call run_test,-m "not slow and not online and not functional")

.PHONY: test-func-only
test-func-only: mkdir-reports   	## run functional tests (online and usage specific)
	@echo "Running functional tests..."
	@$(call run_test,-m "functional")

.PHONY: test-cli-only
test-cli-only: mkdir-reports   		## run WeaverClient and CLI tests
	@echo "Running CLI tests..."
	@$(call run_test,-m "cli")

.PHONY: test-workflow-only
test-workflow-only:	mkdir-reports	## run EMS workflow End-2-End tests
	@echo "Running workflow tests..."
	@$(call run_test,-m "workflow")

.PHONY: test-online-only
test-online-only: mkdir-reports  	## run online tests (running instance required)
	@echo "Running online tests (running instance required)..."
	@$(call run_test,-m "online")

.PHONY: test-offline-only
test-offline-only: mkdir-reports  	## run offline tests (not marked as online)
	@echo "Running offline tests (not marked as online)..."
	@$(call run_test,-m "not online")

.PHONY: test-no-tb14-only
test-no-tb14-only: mkdir-reports  	## run all tests except ones marked for 'Testbed-14'
	@echo "Running all tests except ones marked for 'Testbed-14'..."
	@$(call run_test,-m "not testbed14")

.PHONY: test-spec-only
test-spec-only:	mkdir-reports  ## run tests with custom specification (pytest format) [make SPEC='<spec>' test-spec]
	@echo "Running custom tests from input specification..."
	@[ "${SPEC}" ] || ( echo ">> 'SPEC' is not set"; exit 1 )
	@$(call run_test,-k "${SPEC}")

.PHONY: test-smoke
test-smoke: docker-test     ## alias to 'docker-test' executing smoke test of built docker images

.PHONY: test-docker
test-docker: docker-test    ## alias to 'docker-test' execution smoke test of built docker images

# NOTE:
#	if any test fails during coverage run, pytest exit code will be propagated to allow reporting of the failure
#	this will cause coverage analysis reporting to be skipped from early exit from the failure
#	if coverage reporting is still needed although failed tests occurred, call 'coverage-reports' target separately
.PHONY: test-coverage-only
test-coverage-only: mkdir-reports coverage-run coverage-reports  ## run all tests with coverage analysis and reports

.PHONY: coverage-run
coverage-run: mkdir-reports  ## run all tests using coverage analysis
	@echo "Running coverage analysis..."
	@bash -c '$(CONDA_CMD) coverage run --rcfile="$(APP_ROOT)/setup.cfg" \
		"$$(which pytest)" "$(APP_ROOT)/tests"  $(TEST_XARGS) --junitxml="$(REPORTS_DIR)/coverage-junit.xml"'

.PHONY: coverage-reports
coverage-reports: mkdir-reports  ## generate coverage reports
	@echo "Generate coverage reports..."
	@bash -c '$(CONDA_CMD) coverage xml --rcfile="$(APP_ROOT)/setup.cfg" -i -o "$(REPORTS_DIR)/coverage.xml"'
	@bash -c '$(CONDA_CMD) coverage report --rcfile="$(APP_ROOT)/setup.cfg" -i -m'
	@bash -c '$(CONDA_CMD) coverage html --rcfile="$(APP_ROOT)/setup.cfg" -d "$(REPORTS_DIR)/coverage"'

.PHONY: coverage
coverage: test-coverage  ## alias to run test with coverage analysis

## -- Static code check targets ------------------------------------------------------------------------------------- ##
## -- [variants '<target>-only' without '-only' suffix are also available with pre-install setup]

# autogen check variants with pre-install of dependencies using the '-only' target references
CHECKS := pep8 lint security security-code security-deps doc8 docf fstring docstring links imports
CHECKS := $(addprefix check-, $(CHECKS))

# items that should not install python dev packages should be added here instead
# they must provide their own target/only + with dependency install variants
CHECKS_NO_PY := css md
CHECKS_NO_PY := $(addprefix check-, $(CHECKS_NO_PY))
CHECKS_ALL := $(CHECKS) $(CHECKS_NO_PY)

$(CHECKS): check-%: install-dev check-%-only

.PHONY: mkdir-reports
mkdir-reports:
	@mkdir -p "$(REPORTS_DIR)"

.PHONY: check
check: check-all    ## alias for 'check-all' target

.PHONY: check-only
check-only: $(addsuffix -only, $(CHECKS_ALL))

.PHONY: check-all
check-all: install-dev $(CHECKS_ALL) 	## check all code linters

.PHONY: check-pep8-only
check-pep8-only: mkdir-reports 		## check for PEP8 code style issues
	@echo "Running PEP8 code style checks..."
	@-rm -fr "$(REPORTS_DIR)/check-pep8.txt"
	@bash -c '$(CONDA_CMD) \
		flake8 --config="$(APP_ROOT)/setup.cfg" --output-file="$(REPORTS_DIR)/check-pep8.txt" --tee'

.PHONY: check-lint-only
check-lint-only: mkdir-reports  	## check linting of code style
	@echo "Running linting code style checks..."
	@-rm -fr "$(REPORTS_DIR)/check-lint.txt"
	@bash -c '$(CONDA_CMD) \
		pylint \
			--load-plugins pylint_quotes \
			--rcfile="$(APP_ROOT)/.pylintrc" \
			--reports y \
			"$(APP_ROOT)/weaver" "$(APP_ROOT)/tests" \
		1> >(tee "$(REPORTS_DIR)/check-lint.txt")'

.PHONY: check-security-only
check-security-only: check-security-code-only check-security-deps-only  ## run security checks

# FIXME: safety ignore file (https://github.com/pyupio/safety/issues/351)
# ignored codes:
#	42194: https://github.com/kvesteri/sqlalchemy-utils/issues/166  # not fixed since 2015
#	42498: celery<5.2.0 bumps kombu>=5.2.1 with security fixes to {redis,sqs}  # mongo is used by default in Weaver
#	43738: celery<5.2.2 CVE-2021-23727: trusts the messages and metadata stored in backends
#	45185: pylint<2.13.0: unrelated doc extension (https://github.com/PyCQA/pylint/issues/5322)
SAFETY_IGNORE := 42194 42498 43738 45185
SAFETY_IGNORE := $(addprefix "-i ",$(SAFETY_IGNORE))

.PHONY: check-security-deps-only
check-security-deps-only: mkdir-reports  ## run security checks on package dependencies
	@echo "Running security checks of dependencies..."
	@-rm -fr "$(REPORTS_DIR)/check-security-deps.txt"
	@bash -c '$(CONDA_CMD) \
		safety check \
			--full-report \
			-r "$(APP_ROOT)/requirements.txt" \
			-r "$(APP_ROOT)/requirements-dev.txt" \
			-r "$(APP_ROOT)/requirements-doc.txt" \
			-r "$(APP_ROOT)/requirements-sys.txt" \
			$(SAFETY_IGNORE) \
		1> >(tee "$(REPORTS_DIR)/check-security-deps.txt")'

# FIXME: bandit excludes not working (https://github.com/PyCQA/bandit/issues/657), clean-src beforehand to avoid error
.PHONY: check-security-code-only
check-security-code-only: mkdir-reports clean-src ## run security checks on source code
	@echo "Running security code checks..."
	@-rm -fr "$(REPORTS_DIR)/check-security-code.txt"
	@bash -c '$(CONDA_CMD) \
		bandit -v --ini "$(APP_ROOT)/setup.cfg" -r \
		1> >(tee "$(REPORTS_DIR)/check-security-code.txt")'

.PHONY: check-doc8-only
check-doc8-only: mkdir-reports	  ## check documentation RST styles and linting
	@echo "Running doc8 doc style checks..."
	@-rm -fr "$(REPORTS_DIR)/check-doc8.txt"
	@bash -c '$(CONDA_CMD) \
		doc8 "$(APP_ROOT)/docs" \
		1> >(tee "$(REPORTS_DIR)/check-doc8.txt")'

.PHONY: check-docf-only
check-docf-only: mkdir-reports	## run PEP8 code documentation format checks
	@echo "Checking PEP8 doc formatting problems..."
	@-rm -fr "$(REPORTS_DIR)/check-docf.txt"
	@bash -c '$(CONDA_CMD) \
		docformatter --check --diff --recursive --config "$(APP_ROOT)/setup.cfg" "$(APP_ROOT)" \
		1>&2 2> >(tee "$(REPORTS_DIR)/check-docf.txt")'

# FIXME: no configuration file support
define FLYNT_FLAGS
--line-length 120 \
--verbose
endef
ifeq ($(shell test $(PYTHON_VERSION_MAJOR) -eq 3 && test $(PYTHON_VERSION_MINOR) -ge 8; echo $$?),0)
  FLYNT_FLAGS := $(FLYNT_FLAGS) --transform-concats
endif

.PHONY: check-fstring-only
check-fstring-only: mkdir-reports	## check f-string format definitions
	@echo "Running code f-string formats substitutions..."
	@-rm -f "$(REPORTS_DIR)/check-fstring.txt"
	@bash -c '$(CONDA_CMD) \
		flynt --dry-run --fail-on-change $(FLYNT_FLAGS) "$(APP_ROOT)" \
		1> >(tee "$(REPORTS_DIR)/check-fstring.txt")'

.PHONY: check-docstring-only
check-docstring-only: mkdir-reports  ## check code docstring style and linting
	@echo "Running docstring checks..."
	@-rm -fr "$(REPORTS_DIR)/check-docstring.txt"
	@bash -c '$(CONDA_CMD) \
		pydocstyle --explain --config "$(APP_ROOT)/setup.cfg" "$(APP_ROOT)" \
		1> >(tee "$(REPORTS_DIR)/check-docstring.txt")'

.PHONY: check-links-only
check-links-only:       	## check all external links in documentation for integrity
	@echo "Running link checks on docs..."
	@bash -c '$(CONDA_CMD) $(MAKE) -C "$(APP_ROOT)/docs" linkcheck'

.PHONY: check-imports-only
check-imports-only: mkdir-reports 	## check imports ordering and styles
	@echo "Running import checks..."
	@-rm -fr "$(REPORTS_DIR)/check-imports.txt"
	@bash -c '$(CONDA_CMD) \
		isort --check-only --diff --recursive $(APP_ROOT) \
		1> >(tee "$(REPORTS_DIR)/check-imports.txt")'

.PHONY: check-css-only
check-css-only: mkdir-reports  	## check CSS linting
	@echo "Running CSS style checks..."
	@npx --no-install stylelint \
		--config "$(APP_ROOT)/package.json" \
		--output-file "$(REPORTS_DIR)/check-css.txt" \
		"$(APP_ROOT)/**/*.css"

.PHONY: check-css
check-css: install-npm-stylelint check-css-only	## check CSS linting after dependency installation

# must pass 2 search paths because '<dir>/.<subdir>' are somehow not correctly detected with only the top-level <dir>
.PHONY: check-md-only
check-md-only: mkdir-reports 	## check Markdown linting
	@echo "Running Markdown style checks..."
	@npx --no-install remark \
		--inspect --frail \
		--silently-ignore \
		--stdout --color \
		--rc-path "$(APP_ROOT)/package.json" \
		--ignore-path "$(APP_ROOT)/.remarkignore" \
		"$(APP_ROOT)" "$(APP_ROOT)/.*/" \
		> "$(REPORTS_DIR)/check-md.txt"

.PHONY: check-md
check-md: install-npm-remarklint check-md-only	## check Markdown linting after dependency installation

# autogen fix variants with pre-install of dependencies using the '-only' target references
FIXES := imports lint docf fstring
FIXES := $(addprefix fix-, $(FIXES))
# items that should not install python dev packages should be added here instead
# they must provide their own target/only + with dependency install variants
FIXES_NO_PY := css md
FIXES_NO_PY := $(addprefix fix-, $(FIXES_NO_PY))
FIXES_ALL := $(FIXES) $(FIXES_NO_PY)

$(FIXES): fix-%: install-dev fix-%-only

.PHONY: fix
fix: fix-all 	## alias for 'fix-all' target

.PHONY: fix-only
fix-only: $(addsuffix -only, $(FIXES))	## run all automatic fixes without development dependencies pre-install

.PHONY: fix-all
fix-all: install-dev $(FIXES_ALL)  ## fix all code check problems automatically after install of dependencies

.PHONY: fix-imports-only
fix-imports-only: mkdir-reports	## apply import code checks corrections
	@echo "Fixing flagged import checks..."
	@-rm -fr "$(REPORTS_DIR)/fixed-imports.txt"
	@bash -c '$(CONDA_CMD) \
		isort --recursive $(APP_ROOT) \
		1> >(tee "$(REPORTS_DIR)/fixed-imports.txt")'

# FIXME: https://github.com/PyCQA/pycodestyle/issues/996
# Tool "pycodestyle" doesn't respect "# noqa: E241" locally, but "flake8" and other tools do.
# Because "autopep8" uses "pycodestyle", it is impossible to disable locally extra spaces (as in tests to align values).
# Override the codes here from "setup.cfg" because "autopep8" also uses the "flake8" config, and we want to preserve
# global detection of those errors (typos, bad indents), unless explicitly added and excluded for readability purposes.
# WARNING: this will cause inconsistencies between what 'check-lint' detects and what 'fix-lint' can actually fix
_DEFAULT_SETUP_ERROR := E126,E226,E402,F401,W503,W504
_EXTRA_SETUP_ERROR := E241,E731

.PHONY: fix-lint-only
fix-lint-only: mkdir-reports  ## fix some PEP8 code style problems automatically
	@echo "Fixing PEP8 code style problems..."
	@-rm -fr "$(REPORTS_DIR)/fixed-lint.txt"
	@bash -c '$(CONDA_CMD) \
		autopep8 \
		 	--global-config "$(APP_ROOT)/setup.cfg" \
		 	--ignore "$(_DEFAULT_SETUP_ERROR),$(_EXTRA_SETUP_ERROR)" \
			-v -j 0 -i -r $(APP_ROOT) \
		1> >(tee "$(REPORTS_DIR)/fixed-lint.txt")'

.PHONY: fix-docf-only
fix-docf-only: mkdir-reports  ## fix some PEP8 code documentation style problems automatically
	@echo "Fixing PEP8 code documentation problems..."
	@-rm -fr "$(REPORTS_DIR)/fixed-docf.txt"
	@bash -c '$(CONDA_CMD) \
		docformatter --in-place --diff --recursive --config "$(APP_ROOT)/setup.cfg" "$(APP_ROOT)" \
		1> >(tee "$(REPORTS_DIR)/fixed-docf.txt")'

.PHONY: fix-fstring-only
fix-fstring-only: mkdir-reports
	@echo "Fixing code string formats substitutions to f-string definitions..."
	@-rm -f "$(REPORTS_DIR)/fixed-fstring.txt"
	@bash -c '$(CONDA_CMD) \
		flynt $(FLYNT_FLAGS) "$(APP_ROOT)" \
		1> >(tee "$(REPORTS_DIR)/fixed-fstring.txt")'

.PHONY: fix-css-only
fix-css-only: mkdir-reports 	## fix CSS linting problems automatically
	@echo "Fixing CSS style problems..."
	@npx --no-install stylelint \
		--fix \
		--config "$(APP_ROOT)/package.json" \
		--output-file "$(REPORTS_DIR)/fixed-css.txt" \
		"$(APP_ROOT)/**/*.css"

.PHONY: fix-css
fix-css: install-npm-stylelint fix-css-only		## fix CSS linting problems after dependency installation

# must pass 2 search paths because '<dir>/.<subdir>' are somehow not correctly detected with only the top-level <dir>
.PHONY: fix-md-only
fix-md-only: mkdir-reports 	## fix Markdown linting problems automatically
	@echo "Running Markdown style checks..."
	@npx --no-install remark \
		--output --frail \
		--silently-ignore \
		--rc-path "$(APP_ROOT)/package.json" \
		--ignore-path "$(APP_ROOT)/.remarkignore" \
		"$(APP_ROOT)" "$(APP_ROOT)/.*/" \
		2>&1 | tee "$(REPORTS_DIR)/fixed-md.txt"

.PHONY: fix-md
fix-md: install-npm-remarklint fix-md-only	## fix Markdown linting problems after dependency installation

## -- Documentation targets ----------------------------------------------------------------------------------------- ##

.PHONY: docs-build
docs-build:		## generate HTML documentation with Sphinx
	@echo "Generating docs with Sphinx..."
	@bash -c '$(CONDA_CMD) $(MAKE) -C "$(APP_ROOT)/docs" html'
	@-echo "Documentation available: file://$(APP_ROOT)/docs/build/html/index.html"

.PHONY: docs-only
docs-only: docs-build	## generate HTML documentation with Sphinx (alias)

.PHONY: docs
docs: install-doc clean-docs docs-only	## generate HTML documentation with Sphinx after dependencies installation

## -- Versioning targets -------------------------------------------------------------------------------------------- ##

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

.PHONY: extract-changes
extract-changes: mkdir-reports	## uses the specified VERSION to extract its sub-section in CHANGES.rst
	@[ "${VERSION}" ] || ( echo ">> 'VERSION' is not set. It is required to extract changes."; exit 1 )
	@-echo "Extracting changes for ${VERSION} ..."
	@bash -c '\
		START=$$(cat "$(APP_ROOT)/CHANGES.rst" | grep -n "crim-ca/weaver/tree/${VERSION}" | cut -d ":" -f 1); \
		STOP=$$(tail -n +$$(($${START:-0} + 2)) "$(APP_ROOT)/CHANGES.rst" \
			| grep -n ".. _changes" \
			| cut -d ":" -f 1 | head -n 1); \
		tail -n +$${START:-0} "$(APP_ROOT)/CHANGES.rst" | head -n $${STOP:--1} \
			> "$(REPORTS_DIR)/CHANGES_${VERSION}.rst" \
	'
	@-echo "Generated changes: $(REPORTS_DIR)/CHANGES_${VERSION}.rst"

# note:
#	some text must be inserted before and between the first 'version heading' and the 'changes' sub-heading
#	otherwise headers levels are not parsed correctly (they are considered sections all using H1)
#	therefore, inject the contents needed to parse as desired, and remove the temp HTML content afterwards
.PHONY: generate-changes-html
generate-changes-html: extract-changes	## extract CHANGES.rst section as HTML using the specified VERSION
	@[ "${VERSION}" ] || ( echo ">> 'VERSION' is not set. It is required to extract changes."; exit 1 )
	@-echo "Checking necessary documentation dependency ..."
	@which rst2html >/dev/null || pip install docutils
	@-echo "Converting changes for ${VERSION} ..."
	@echo '%(body)s' > "$(REPORTS_DIR)/html-body-template.txt"
	@sed -i -e 's|Changes:|\\ \n\nChanges:|' "$(REPORTS_DIR)/CHANGES_${VERSION}.rst"
	@sed -i -e "s|^\`${VERSION}|   \n###\n\n\\ \n\n\`${VERSION}|" "$(REPORTS_DIR)/CHANGES_${VERSION}.rst"
	@rst2html \
		--template "$(REPORTS_DIR)/html-body-template.txt" \
		"$(REPORTS_DIR)/CHANGES_${VERSION}.rst" "$(REPORTS_DIR)/CHANGES_${VERSION}.html"
	@sed -i -e 's|<p>###</p>||' "$(REPORTS_DIR)/CHANGES_${VERSION}.html"
	@sed -i -e 's|<tt|<code|g' "$(REPORTS_DIR)/CHANGES_${VERSION}.html"
	@sed -i -e 's|</tt|</code|g' "$(REPORTS_DIR)/CHANGES_${VERSION}.html"
	@-echo "Generated changes: $(REPORTS_DIR)/CHANGES_${VERSION}.html"

.PHONY: generate-archive
generate-archive:	## generate ZIP and TAR.GZ archives using current contents
	@-echo "Generating archives"
	@tar \
		-C "$(APP_ROOT)" \
		--exclude-vcs \
		--exclude-vcs-ignores \
		--exclude=.git \
		--exclude=.github \
		--exclude=*.zip \
		--exclude=*.tar.gz \
		--exclude=node_modules \
		--exclude="$(APP_NAME)-$(APP_VERSION).tar.gz" \
		-cvzf "$(APP_NAME)-$(APP_VERSION).tar.gz" \
		--transform 's,^\.,$(APP_NAME)-$(APP_VERSION),' \
		--ignore-failed-read \
		.
	@cd "$(APP_ROOT)" && \
		mkdir -p "$(ARCHIVE_DIR)" && \
		cp "$(APP_NAME)-$(APP_VERSION).tar.gz" "$(ARCHIVE_DIR)/$(APP_NAME)-$(APP_VERSION).tar.gz" && \
		cd "$(ARCHIVE_DIR)" && \
		tar -xzf "$(APP_NAME)-$(APP_VERSION).tar.gz" && \
		rm "$(APP_NAME)-$(APP_VERSION).tar.gz" && \
		zip -r "$(APP_NAME)-$(APP_VERSION).zip" * && \
		mv "$(APP_NAME)-$(APP_VERSION).zip" "$(APP_ROOT)" && \
		cd "$(APP_ROOT)" && \
		rm -fr "$(ARCHIVE_DIR)"

## -- Docker targets ------------------------------------------------------------------------------------------------ ##

DOCKER_REPO ?= pavics/weaver
#DOCKER_REPO ?= docker-registry.crim.ca/ogc/weaver

# NOTE:
#	Because of the --push requirement when involving provenance/SBOM
#	only full '[registry.uri/]org/weaver:tag' can be passed as '-t' label
#	since the build must actively register the built image with a trusted authority.
#	Additional "alias" tags provided for convenience must be applied separately.
#	Also, any intermediate image used as base for derived ones must explicitly
#	employ the remote registry reference to provide the relevant traceability.

# whether to enable Provenance and SBOM tracking of built images
#	Disable by default to ensure that any operation that needs a local docker (eg: 'docker-test' target)
#	doesn't lead to an unintended push to the remote registry. This should be enabled explicitly only
#	for tagged releases for which we explicitly want traceability.
DOCKER_PROV ?= false
ifeq ($(DOCKER_PROV),true)
  DOCKER_BUILDER_STEP := docker-builder
  DOCKER_BUILDER_NAME ?= docker-prov
  DOCKER_BUILDER_BASE ?= $(DOCKER_REPO):$(APP_VERSION)
  DOCKER_BUILDER_ARGS ?= \
  	--provenance=true \
  	--sbom=true \
  	--builder="$(DOCKER_BUILDER_NAME)" \
  	--build-arg "DOCKER_BASE=$(DOCKER_BUILDER_BASE)" \
  	--push
  # tag aliases is not required since images are pushed directly to the registry
  # if explicitly required, they need to be pulled as they won't resolve locally
  DOCKER_BUILDER_PULL := docker pull
  DOCKER_TAG_ALIASES  ?= false
else
  # tag aliases is required to obtain the 'weaver:base' name used by derived images
  # use 'true' command to mute the arguments used in the other case
  override DOCKER_BUILDER_PULL := true
  override DOCKER_TAG_ALIASES  := true
endif

.PHONY: docker-builder
docker-builder:
	@echo "Checking docker-container builder required for Docker provenance..."
	@( \
		docker buildx inspect "$(DOCKER_BUILDER_NAME)" >/dev/null && \
		echo "Container Builder [$(DOCKER_BUILDER_NAME)] already exists." \
	) || ( \
		echo "Creating Docker Container [$(DOCKER_BUILDER_NAME)]..." && \
		docker buildx create --name "$(DOCKER_BUILDER_NAME)" --driver=docker-container \
	)

.PHONY: docker-info
docker-info:		## obtain docker image information
	@echo "Docker image will be built as: "
	@echo "$(APP_NAME):$(APP_VERSION)"
	@echo "Docker image will be pushed as:"
	@echo "$(DOCKER_REPO):$(APP_VERSION)"

.PHONY: docker-build-base
docker-build-base: $(DOCKER_BUILDER_STEP)	## build the base docker image
	docker build "$(APP_ROOT)" \
		$(DOCKER_BUILDER_ARGS) \
		-f "$(APP_ROOT)/docker/Dockerfile-base" \
		-t "$(DOCKER_REPO):$(APP_VERSION)"
	@[ "$(DOCKER_TAG_ALIASES)" = "true" ] && ( \
		( [ "$(APP_VERSION)" = "latest" ] || docker tag "$(DOCKER_REPO):$(APP_VERSION)" "$(DOCKER_REPO):latest" ) && \
		docker tag "$(DOCKER_REPO):$(APP_VERSION)" "$(APP_NAME):$(APP_VERSION)" && \
		docker tag "$(DOCKER_REPO):$(APP_VERSION)" "$(APP_NAME):latest" && \
		docker tag "$(DOCKER_REPO):$(APP_VERSION)" "$(APP_NAME):base" \
	) || true

.PHONY: docker-build-manager
docker-build-manager: $(DOCKER_BUILDER_STEP) docker-build-base		## build the manager docker image
	docker build "$(APP_ROOT)" \
		$(DOCKER_BUILDER_ARGS) \
		-f "$(APP_ROOT)/docker/Dockerfile-manager" \
		-t "$(DOCKER_REPO):$(APP_VERSION)-manager"
	@[ "$(DOCKER_TAG_ALIASES)" = "true" ] && ( \
		$(DOCKER_BUILDER_PULL) "$(DOCKER_REPO):$(APP_VERSION)-manager" && \
		docker tag "$(DOCKER_REPO):$(APP_VERSION)-manager" "$(DOCKER_REPO):latest-manager" && \
		docker tag "$(DOCKER_REPO):$(APP_VERSION)-manager" "$(APP_NAME):$(APP_VERSION)-manager" && \
		docker tag "$(DOCKER_REPO):$(APP_VERSION)-manager" "$(APP_NAME):latest-manager" \
	) || true

.PHONY: docker-build-worker
docker-build-worker: $(DOCKER_BUILDER_STEP) docker-build-base		## build the worker docker image
	docker build "$(APP_ROOT)" \
		$(DOCKER_BUILDER_ARGS) \
		-f "$(APP_ROOT)/docker/Dockerfile-worker" \
		-t "$(DOCKER_REPO):$(APP_VERSION)-worker"
	@[ "$(DOCKER_TAG_ALIASES)" = "true" ] && ( \
		$(DOCKER_BUILDER_PULL) "$(DOCKER_REPO):$(APP_VERSION)-worker" ] && \
		docker tag "$(DOCKER_REPO):$(APP_VERSION)-worker" "$(DOCKER_REPO):latest-worker" && \
		docker tag "$(DOCKER_REPO):$(APP_VERSION)-worker" "$(APP_NAME):$(APP_VERSION)-worker" && \
		docker tag "$(DOCKER_REPO):$(APP_VERSION)-worker" "$(APP_NAME):latest-worker" \
	) || true

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
docker-push: docker-push-base docker-push-manager docker-push-worker  ## push all docker images

# if compose up fails, print the logs and force stop
# if compose up succeeds, query weaver to get frontpage response
DOCKER_COMPOSE_CMD ?= docker compose
DOCKER_TEST_COMPOSES := -f "$(APP_ROOT)/tests/smoke/docker-compose.smoke-test.yml"
DOCKER_TEST_CURL_RETRY_COUNT ?= 10
DOCKER_TEST_CURL_RETRY_DELAY ?= 5
DOCKER_TEST_EXEC_ARGS ?=
.PHONY: docker-test
docker-test: docker-build stop	## execute smoke test of the built images (validate that they boots and reply)
	@echo "Smoke test of built application docker images"
	$(DOCKER_COMPOSE_CMD) $(DOCKER_TEST_COMPOSES) up -d
	@echo "Pinging Weaver API entrypoint to validate response..."
	@wget \
			-O - \
			--tries $(DOCKER_TEST_CURL_RETRY_COUNT) \
			--wait $(DOCKER_TEST_CURL_RETRY_DELAY) \
			--retry-connrefused \
			"http://localhost:4001" | \
		grep "Weaver Information" || \
		( $(DOCKER_COMPOSE_CMD) $(DOCKER_TEST_COMPOSES) logs weaver worker || true && \
		  $(DOCKER_COMPOSE_CMD) $(DOCKER_TEST_COMPOSES) stop; exit 1 )
	$(DOCKER_COMPOSE_CMD) $(DOCKER_TEST_COMPOSES) exec $(DOCKER_TEST_EXEC_ARGS) weaver bash /tests/run_tests.sh
	$(DOCKER_COMPOSE_CMD) $(DOCKER_TEST_COMPOSES) stop

.PHONY: docker-stat
docker-stat:  ## query docker-compose images status (from 'docker-test')
	$(DOCKER_COMPOSE_CMD) $(DOCKER_TEST_COMPOSES) ps

.PHONY: docker-clean
docker-clean:  ## remove all built docker images (only matching current/latest versions)
	$(DOCKER_COMPOSE_CMD) $(DOCKER_TEST_COMPOSES) down || true
	docker rmi -f "$(DOCKER_REPO):$(APP_VERSION)-manager" || true
	docker rmi -f "$(DOCKER_REPO):latest-manager" || true
	docker rmi -f "$(APP_NAME):$(APP_VERSION)-manager" || true
	docker rmi -f "$(APP_NAME):latest-manager" || true
	docker rmi -f "$(DOCKER_REPO):$(APP_VERSION)-worker" || true
	docker rmi -f "$(DOCKER_REPO):latest-worker" || true
	docker rmi -f "$(APP_NAME):$(APP_VERSION)-worker" || true
	docker rmi -f "$(APP_NAME):latest-worker" || true
	docker rmi -f "$(DOCKER_REPO):$(APP_VERSION)" || true
	docker rmi -f "$(DOCKER_REPO):latest" || true
	docker rmi -f "$(APP_NAME):$(APP_VERSION)" || true
	docker rmi -f "$(APP_NAME):latest" || true
	docker rmi -f "$(APP_NAME):base" || true

## -- Launchers targets --------------------------------------------------------------------------------------------- ##

.PHONY: start
start: install-run	## start application instance(s) with gunicorn (pserve)
	@echo "Starting $(APP_NAME)..."
	@bash -c '$(CONDA_CMD) exec pserve "$(APP_INI)" &'

.PHONY: stop
stop: 		## kill application instance(s) started with gunicorn (pserve)
	@(lsof -t -i :4001 | xargs kill) 2>/dev/null || echo "No $(APP_NAME) process to stop"

.PHONY: stat
stat: 		## display processes with PID(s) of gunicorn (pserve) instance(s) running the application
	@lsof -i :4001 || echo "No instance running"

# Reapply config if overrides were defined.
# Ensure overrides take precedence over targets and auto-resolution logic of variables.
-include Makefile.config
