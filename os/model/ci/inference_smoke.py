"""Actual Qwen3.5-2B Q4 offline CPU inference, run inside networkless CI container.

Only synthetic prompts. The model response is never executed as an OS action.
Real resources and validation quality are recorded, not assumed.
"""
import json
import os
import resource
import subprocess
import time
import urllib.error
import urllib.request

URL="http://127.0.0.1:18080"
SHA="a8b50de00b780c0f3c16f07cb041a1ecd678b6e22fd8cde91e57fe4b5031523b"

def server_command(executable="/usr/local/bin/llama-server"):
    # Maintained in one place so CI can validate the pinned server's CLI
    # BEFORE attempting actual 2B GGUF loading on CPU.
    return [
        executable,"--model","/opt/aiws/model.gguf",
        "--alias","aiws-local","--host","127.0.0.1","--port","18080",
        "--ctx-size","2048","--gpu-layers","0","--threads","2",
        "--parallel","1"
    ]


def main():
    started=time.monotonic()
    with open("/tmp/aiws-llama.log","wb") as log:
        server=subprocess.Popen(server_command(),stdout=log,stderr=subprocess.STDOUT)
        try:
            healthy=False
            for i in range(240):
                if server.poll() is not None:
                    raise RuntimeError("Real llama-server exited before healthy")
                try:
                    with urllib.request.urlopen(URL+"/health",timeout=2) as answer:
                        if answer.status==200:
                            healthy=True
                            break
                except (OSError,urllib.error.URLError):
                    pass
                time.sleep(1)
            if not healthy:
                raise RuntimeError("Real llama-server did not reach healthy state")
            boot_sec=round(time.monotonic()-started,2)
            prompt={
                "model":"aiws-local","stream":False,"temperature":0,
                "max_tokens":128,"response_format":{"type":"json_object"},
                "messages":[
                    {"role":"system","content":
                     "AIWS OS guest-local planner. Return ONLY JSON object with exact keys tool, arguments, reason. "
                     "For listing files choose tool workspace.tree and arguments {\"path\":\".\"}. "
                     "Do not execute any commands or request host access."},
                    {"role":"user","content":"请查看我的客户机项目文件目录结构"}
                ]}
            req=urllib.request.Request(URL+"/v1/chat/completions",
                data=json.dumps(prompt,ensure_ascii=False).encode(),
                headers={"Content-Type":"application/json"},method="POST")
            begin=time.monotonic()
            with urllib.request.urlopen(req,timeout=240) as response:
                data=json.loads(response.read(1024*1024))
            latency=round(time.monotonic()-begin,2)
            content=data["choices"][0]["message"]["content"]
            parsed=None
            try:
                parsed=json.loads(content)
            except (TypeError,ValueError):
                pass
            valid=(isinstance(parsed,dict) and
                   set(parsed)=={"tool","arguments","reason"} and
                   parsed["tool"]=="workspace.tree" and
                   parsed["arguments"]=={"path":"."})
            rss_kb=None
            try:
                for line in open("/proc/"+str(server.pid)+"/status",encoding="utf-8"):
                    if line.startswith("VmRSS:"):
                        rss_kb=int(line.split()[1])
                        break
            except OSError:
                pass
            result={"realModel":True,"model":"Qwen3.5-2B-Q4_K_M",
                    "expected_sha256":SHA,"network":"disabled",
                    "cpu_only":True,"gpu_layers":0,"service":"llama-server",
                    "load_seconds":boot_sec,"one_prompt_latency_seconds":latency,
                    "server_rss_kb":rss_kb,"tool_proposal_correct":bool(valid),
                    "response_usage":data.get("usage",{}),
                    "validation":"real inference, synthetic one-case baseline",
                    "running_in_aiws_vm":False}
            print(json.dumps(result,ensure_ascii=False,sort_keys=True),flush=True)
            if not isinstance(content,str) or not content:
                raise RuntimeError("Real model returned no content")
        except Exception:
            # Always leave actionable offline loader diagnostic in CI, but
            # never write a prompt or model weights into artifacts.
            try:
                with open("/tmp/aiws-llama.log",encoding="utf-8",errors="replace") as stream:
                    logtext=stream.read()[-14000:]
                print("AIWS_REAL_MODEL_SERVER_DIAGNOSTIC_START",flush=True)
                print(logtext,flush=True)
                print("AIWS_REAL_MODEL_SERVER_DIAGNOSTIC_END",flush=True)
            except OSError as logerr:
                print("Could not read guest model loader diagnostic: "+type(logerr).__name__,flush=True)
            raise
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)

if __name__=="__main__":
    main()
