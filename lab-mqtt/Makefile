.PHONY: agent smoke host

VENV?=.venv
PY?=$(VENV)/bin/python

setup:
	python3 -m venv $(VENV)
	. $(VENV)/bin/activate && pip install -r requirements.txt

agent:
	PYTHONPATH=. $(PY) -m device.agent

smoke:
	$(PY) tools/publish.py /lab/orchestrator/ndi/cmd tools/sample_messages/start_ndi.json

host:
	$(PY) -m uvicorn orchestrator_host.host:app --host 0.0.0.0 --port 8080
