"""Guest-only QEMU runtime acceptance: UI and Agent restart independently.

The checks use fixed user-systemd units and read-only local HTTP endpoints.
They do not access host controls, reboot the VM or mutate a guest kernel.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

from aiws_guest_boundary import require_guest_runtime

URL="http://127.0.0.1:17640"
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def get(path):
    with OPENER.open(URL+path,timeout=4) as resp:
        return json.load(resp)

def pid(unit):
    r=subprocess.run(["systemctl","--user","show","--property=MainPID","--value",unit],
                     capture_output=True,text=True,timeout=6,check=True)
    number=int(r.stdout.strip())
    if number<=0:
        raise RuntimeError("Guest unit not running: "+unit)
    return number

def wait_healthy():
    for _ in range(100):
        try:
            health=get("/api/v1/health")
            if health.get("agentIndependentService") and health.get("guestOnly") and health.get("tasksPersistent"):
                audit=get("/api/v1/audit/verify")
                if audit.get("valid") is True:
                    return
        except (ValueError,OSError):
            pass
        time.sleep(.4)
    raise RuntimeError("Guest UI/Agent did not recover healthy state")

def main():
    require_guest_runtime()
    if os.geteuid()==0:
        raise RuntimeError("Guest lifecycle smoke may not run as root")
    if not Path("/etc/aiws/guest-managed").is_file():
        raise RuntimeError("Not a dedicated AIWS guest")
    wait_healthy()
    before={item["id"] for item in get("/api/v1/tasks")["tasks"]}
    if len(before)<2:
        raise RuntimeError("Expected both GUI-created DAG and kernel candidate evidence")
    agent_pid=pid("aiws-agent.service")
    ui_pid=pid("aiws-workbench.service")
    subprocess.run(["systemctl","--user","restart","aiws-workbench.service"],
                   check=True,timeout=14)
    wait_healthy()
    if pid("aiws-agent.service")!=agent_pid:
        raise RuntimeError("Guest Agent must survive a workbench restart")
    if pid("aiws-workbench.service")==ui_pid:
        raise RuntimeError("Workbench restart did not replace its process")
    after_ui={item["id"] for item in get("/api/v1/tasks")["tasks"]}
    if before!=after_ui:
        raise RuntimeError("Durable DAG changed after UI restart")
    subprocess.run(["systemctl","--user","restart","aiws-agent.service"],
                   check=True,timeout=14)
    wait_healthy()
    if pid("aiws-agent.service")==agent_pid:
        raise RuntimeError("Independent Agent restart did not replace its process")
    after_agent={item["id"] for item in get("/api/v1/tasks")["tasks"]}
    if after_agent!=before or not get("/api/v1/audit/verify")["valid"]:
        raise RuntimeError("Agent restart lost persistent DAG or audit integrity")
    print("AIWS_GUEST_LIFECYCLE_PASS "+json.dumps({
        "ui_restart":True,"agent_independent":True,"agent_restart":True,
        "persistent_task_ids":len(after_agent),"audit_chain_valid":True,
        "host_access":False},sort_keys=True),flush=True)

if __name__=="__main__":
    main()
