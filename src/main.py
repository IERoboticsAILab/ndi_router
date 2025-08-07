from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import List
import paramiko
from ndi_discovery import list_all_ndi_sources
import os
import json
import time

app = FastAPI()
templates = Jinja2Templates(directory="src/templates")

# Path to the output devices JSON file
DEVICES_FILE = os.path.join(os.path.dirname(__file__), "output_devices.json")

def load_output_devices():
    with open(DEVICES_FILE, "r") as f:
        return json.load(f)

@app.get("/api/ndi-sources")
def list_ndi_sources():
    sources = list_all_ndi_sources()
    return {"sources": sources}

@app.get("/api/output-devices")
def list_output_devices():
    return {"devices": load_output_devices()}

@app.post("/api/route")
def route_stream(stream_name: str = Form(...), devices: List[str] = Form(...)):
    """
    SSH into each selected device and run: yuri_simple ndi_input[stream={stream_name}] glx_window[fullscreen=True]
    Assumes SSH key auth is set up (no password prompt).
    """
    for device in load_output_devices():
        if device["host"] in devices:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(
                    hostname=device["host"],
                    username=device["user"],
                )
                # Kill any existing yuri_simple processes (optional, for idempotency)
                kill_cmd = "pkill -f 'yuri_simple'"
                ssh.exec_command(kill_cmd)
                time.sleep(0.1)
                # Start yuri_simple with the selected stream
                cmd = f'./run_yuri.sh "{stream_name}"'
                ssh.exec_command(cmd)
                ssh.close()
                print({"device": device["name"], "host": device["host"], "status": "ok"})
            except Exception as e:
                print({"device": device["name"], "host": device["host"], "status": "error", "error": str(e)})
        time.sleep(0.1)
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def web_ui(request: Request):
    sources = list_all_ndi_sources()
    devices = load_output_devices()
    return templates.TemplateResponse("index.html", {"request": request, "sources": sources, "devices": devices})