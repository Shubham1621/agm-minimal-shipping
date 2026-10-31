# Makefile
PYTHON ?= python3
VENV ?= .venv
VPY := $(VENV)/bin/python
VPIP := $(VENV)/bin/pip

.PHONY: install test day15 task-sample clean

install:
	$(PYTHON) -m venv $(VENV)
	$(VPY) -m pip install --upgrade pip
	$(VPIP) install -r requirements.txt

test:
	@test -x "$(VPY)" || (echo "Run 'make install' first." && exit 2)
	$(VPY) -m pytest -q tests --ignore=tests/test_day15_smoke.py

day15:
	@test -x "$(VPY)" || (echo "Run 'make install' first." && exit 2)
	@test -n "$(AGM_GCP_PROJECT)" || (echo "ERROR: set AGM_GCP_PROJECT to your personal GCP project" && exit 2)
	@test -n "$(AGM_HMAC_KEY)" || (echo "ERROR: set AGM_HMAC_KEY to a private random secret" && exit 2)
	AGM_GCP_PROJECT="$(AGM_GCP_PROJECT)" AGM_BQ_DATASET="$${AGM_BQ_DATASET:-agm_sandbox}" AGM_BQ_LOCATION="$${AGM_BQ_LOCATION:-US}" AGM_HMAC_KEY="$(AGM_HMAC_KEY)" $(VPY) -m pytest -q -s tests/test_day15_smoke.py

task-sample:
	$(VPY) -m src.task_generator 20261018 matched

clean:
	rm -rf $(VENV) .pytest_cache
