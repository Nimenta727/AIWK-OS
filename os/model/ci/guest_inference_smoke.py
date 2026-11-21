"""Actual held-out 2B inference inside the disposable, networkless Debian QEMU guest.

Started as guest user by the root-owned CI boot-smoke service with stdout
redirected to ttyS0. No model-proposed tool is ever dispatched.
"""
import json
from pathlib import Path
import subprocess
import time

from aiws_guest_boundary import require_guest_runtime
from aiws_local_model import LocalPlanner
from guest_benchmark import benchmark, load_cases

UNIT = "aiws-local-model.service"
BENCH = Path("/usr/local/lib/aiws/aiws_model_heldout.jsonl")
BENCH_V2 = Path("/usr/local/lib/aiws/aiws_model_heldout_v2.jsonl")   # release-candidate set; report only

def model_memory(pid):
    data = {"rssMiB": None, "peakRssMiB": None}
    try:
        for line in Path("/proc/" + str(pid) + "/status").read_text(encoding="ascii").splitlines():
            if line.startswith("VmRSS:"):
                data["rssMiB"] = round(int(line.split()[1]) / 1024, 2)
            elif line.startswith("VmHWM:"):
                data["peakRssMiB"] = round(int(line.split()[1]) / 1024, 2)
    except (ValueError, OSError, IndexError):
        pass
    return data

def main():
    require_guest_runtime()
    marker = Path("/etc/aiws/guest-model-acceptance")
    if marker.is_symlink() or not marker.is_file() or marker.read_text().strip() != "AIWS_MODEL_CI_ONLY=1":
        raise PermissionError("Only isolated real-model CI guests may run this test")
    manifest = Path("/usr/local/share/aiws/model-preload/manifest.json")
    if not manifest.is_file() or not BENCH.is_file():
        raise RuntimeError("Bundled model manifest or fixed held-out evaluation cases missing")
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    cases, heldout_sha = load_cases(BENCH)
    subprocess.run(["systemctl", "--user", "start", UNIT], timeout=20, check=True)
    try:
        planner = LocalPlanner(enabled=True, request_timeout=120)
        begin = time.monotonic()
        for _ in range(300):
            if planner.status()["online"]:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Guest model never became healthy")
        # The gate answers /health instantly and loads llama-server on the first real request, so warm the model
        # up first and read the true cold-start time and the llama-server PID (not the gate's) from /gate/status.
        planner.suggest("List the guest workspace files")
        with planner.opener.open(planner.url + "/gate/status", timeout=5) as response:
            gate = json.loads(response.read(8192))
        pid = gate.get("childPid")
        if not isinstance(pid, int) or pid <= 1:
            raise RuntimeError("The gate did not report a loaded llama-server PID")
        load_sec = gate.get("lastColdStartSeconds")
        if not isinstance(load_sec, (int, float)):
            load_sec = round(time.monotonic() - begin, 3)
        metrics = benchmark(planner, cases, heldout_sha, lambda: model_memory(pid))
        metrics.update({
            "realGuestModel": True,
            "model": metadata.get("modelId"),
            "modelSha256": metadata.get("sha256"),
            "provider": "llama.cpp",
            "cpuOnly": True,
            "networklessGuest": True,
            "serviceLoadSeconds": load_sec
        })
        print("AIWS_GUEST_MODEL_BENCHMARK " + json.dumps(metrics, sort_keys=True, ensure_ascii=True), flush=True)
        if BENCH_V2.is_file():
            # Report-only: the 242-case locked set covers file writes, multi-step plans and refusals.
            # It does not gate CI until a real baseline exists; failures are recorded, never hidden.
            cases2, sha2 = load_cases(BENCH_V2, require_release=True)
            v2 = benchmark(planner, cases2, sha2, lambda: model_memory(pid), release=True)
            v2.update({"realGuestModel": True, "modelSha256": metadata.get("sha256"), "gating": False})
            print("AIWS_GUEST_MODEL_BENCHMARK_V2 " + json.dumps(v2, sort_keys=True, ensure_ascii=True), flush=True)
        if not metrics["smokePassed"]:
            raise RuntimeError("Held-out QEMU inference quality/resource gate failed; inspect benchmark receipt")
        print("AIWS_GUEST_MODEL_INFERENCE_PASS " + json.dumps({
            "guest_only": True, "real_guest_model": True, "model_sha256": metadata.get("sha256"),
            "heldout_sha256": heldout_sha, "samples": len(cases), "smoke_passed": True,
            "service_load_seconds": load_sec, "tool_executed": False,
            "peak_rss_mib": metrics["peakModelRssMiB"],
            "p95_latency_seconds": metrics["p95LatencySeconds"]
        }, sort_keys=True), flush=True)
    finally:
        subprocess.run(["systemctl", "--user", "stop", UNIT], timeout=20, check=False)

if __name__ == "__main__":
    main()
