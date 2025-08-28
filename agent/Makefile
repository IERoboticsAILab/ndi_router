.PHONY: agent setup
VENV?=.venv
PY?=$(VENV)/bin/python

setup:
	python3 -m venv $(VENV)
	. $(VENV)/bin/activate && pip install -r requirements.txt

agent:
	PYTHONPATH=. $(PY) -m device.agent
