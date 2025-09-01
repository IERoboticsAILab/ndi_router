.PHONY: setup host smoke docker-build docker-run docker-push
VENV?=.venv
PY?=$(VENV)/bin/python

setup:
	python3 -m venv $(VENV)
	. $(VENV)/bin/activate && pip install -r requirements.txt

host:
	$(PY) -m uvicorn orchestrator_host.host:app --host 0.0.0.0 --port 8080

smoke:
	$(PY) tools/publish.py /lab/orchestrator/ndi/cmd tools/sample_messages/start_ndi.json

docker-build:
	docker build -t ndi-orchestrator:latest .

docker-run:
	docker run --rm -p 8080:8080 --env MQTT__HOST=${MQTT_HOST:-10.205.10.7} --env MQTT__PORT=${MQTT_PORT:-1883} \
	  --env MQTT__USERNAME=${MQTT_USERNAME:-mqtt} --env MQTT__PASSWORD=${MQTT_PASSWORD:-123456789} \
	  ndi-orchestrator:latest

docker-push:
	# Example: docker tag and push to your registry
	@echo "Tag and push as needed, e.g.: docker tag ndi-orchestrator:latest myrepo/ndi-orchestrator:latest && docker push myrepo/ndi-orchestrator:latest"
