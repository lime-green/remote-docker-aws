.PHONY: help prepare-dev test lint lint-check

VENV_NAME?=venv
VENV_ACTIVATE=. $(VENV_NAME)/bin/activate
PYTHON=${VENV_NAME}/bin/python3

.DEFAULT: help
help:
	@echo "make prepare-dev"
	@echo "       prepare development environment, use only once"
	@echo "make test"
	@echo "       run tests"
	@echo "make lint"
	@echo "       run linters"

prepare-dev:
	make venv

venv: $(VENV_NAME)/bin/activate
$(VENV_NAME)/bin/activate: setup.py
	test -d $(VENV_NAME) || python3 -m venv $(VENV_NAME)
	${PYTHON} -m pip install -U pip
	${PYTHON} -m pip install -e .[dev]
	touch $(VENV_NAME)/bin/activate

test: venv
	$(VENV_ACTIVATE) && ${PYTHON} -m pytest

lint: venv
	$(VENV_ACTIVATE) && ${PYTHON} -m black src/ tests/
	$(VENV_ACTIVATE) && ${PYTHON} -m flake8 src/ tests/ --max-line-length 88 --statistics --show-source


lint-check: venv
	$(VENV_ACTIVATE) && ${PYTHON} -m black --check src/ tests/
	$(VENV_ACTIVATE) && ${PYTHON} -m flake8 src/ tests/ --max-line-length 88 --statistics --show-source
