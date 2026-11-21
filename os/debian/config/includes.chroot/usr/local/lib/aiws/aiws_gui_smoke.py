"""In-guest browser click acceptance; no host access, no network adapter."""
from pathlib import Path
import os
import json
import urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

def main():
    if os.geteuid() == 0 or not os.environ.get("DISPLAY"):
        raise RuntimeError("GUI smoke must run as unprivileged graphical guest user")
    if not Path("/etc/aiws/guest-managed").is_file():
        raise RuntimeError("AIWS guest image marker missing")
    workspace = Path.home() / ".local/share/aiws/projects"
    workspace.mkdir(mode=0o700,parents=True,exist_ok=True)
    (workspace/"AIWS-GUEST-SMOKE.txt").write_text(
        "AIWS guest-only file manager acceptance fixture\n",encoding="utf-8")
    (workspace/"aiws-kernel.fragment").write_text(
        "CONFIG_VIRTIO=y\nCONFIG_SECCOMP=y\n",encoding="ascii")
    options=webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-proxy-server")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-first-run")
    options.add_argument("--window-size=1280,800")
    with webdriver.Chrome(service=Service("/usr/bin/chromedriver"),options=options) as browser:
        wait=WebDriverWait(browser,30)
        browser.set_page_load_timeout(30)
        browser.get("http://127.0.0.1:17640/")
        wait.until(lambda b:b.find_elements(By.XPATH,"//nav//button[contains(.,'AI 文件管理')]"))
        print("AIWS_GUI_BROWSER: React workbench rendered",flush=True)
        browser.find_element(By.XPATH,"//nav//button[contains(.,'AI 文件管理')]").click()
        wait.until(lambda b:b.find_elements(By.XPATH,
            "//div[contains(@class,'aiws-os-file-list')]//button[contains(.,'AIWS-GUEST-SMOKE.txt')]"))
        browser.find_element(By.XPATH,
            "//div[contains(@class,'aiws-os-file-list')]//button[contains(.,'AIWS-GUEST-SMOKE.txt')]").click()
        wait.until(lambda b:"guest-only file manager acceptance fixture" in
            b.find_element(By.CSS_SELECTOR,".aiws-os-file-detail pre").text)
        print("AIWS_GUI_BROWSER: guest file explorer click/read verified",flush=True)
        browser.find_element(By.XPATH,"//nav//button[contains(.,'持久任务与 DAG')]").click()
        wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,".aiws-os-studio input"))
        browser.find_element(By.CSS_SELECTOR,".aiws-os-studio input").send_keys("GUI guest smoke")
        browser.find_element(By.CSS_SELECTOR,".aiws-os-studio textarea").send_keys("List guest workspace")
        browser.find_element(By.XPATH,"//button[contains(.,'保存任务与 DAG')]").click()
        wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,".aiws-os-stage-status"))
        browser.find_element(By.XPATH,"//button[contains(.,'运行客户机阶段')]").click()
        wait.until(lambda b:"COMPLETED" in b.find_element(By.CSS_SELECTOR,".aiws-os-stage-status").text)
        print("AIWS_GUI_BROWSER: DAG stage executed",flush=True)
        browser.find_element(By.XPATH,"//nav//button[contains(.,'本地 AI 助手')]").click()
        wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,".aiws-os-studio"))
        assert "DISABLED" in browser.find_element(By.CSS_SELECTOR,".aiws-os-studio").text
        # A genuine guest-only *candidate* pipeline, not a running kernel edit.
        browser.find_element(By.XPATH,"//nav//button[contains(.,'系统与安全')]").click()
        wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,".aiws-os-system-console"))
        wait.until(lambda b:"CONFIG" not in b.find_element(By.CSS_SELECTOR,".aiws-os-system-console").text)
        browser.find_element(By.XPATH,"//button[contains(.,'提交候选验证和暂存审批')]").click()
        wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,".aiws-os-studio"))
        wait.until(lambda b:b.find_elements(By.XPATH,
            "//button[contains(@class,'aiws-os-task') and contains(.,'验证并暂存客户机内核配置候选')]"))
        browser.find_element(By.XPATH,
            "//button[contains(@class,'aiws-os-task') and contains(.,'验证并暂存客户机内核配置候选')]").click()
        wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,".aiws-os-stage-status"))
        browser.find_element(By.XPATH,"//button[contains(.,'批准客体写操作')]").click()
        wait.until(lambda b:b.find_elements(By.XPATH,"//button[contains(.,'运行客户机阶段')]"))
        browser.find_element(By.XPATH,"//button[contains(.,'运行客户机阶段')]").click()
        # Read the same live guest API that backs the UI; print exact state on failure.
        # A pass still requires both the GUI receipt and actual staged evidence.
        def kernel_stage_state():
            with urllib.request.urlopen(
                    "http://127.0.0.1:17640/api/v1/tasks", timeout=5) as reply:
                tasks=json.load(reply)["tasks"]
            selected=next((x for x in tasks if x["title"]==
                "验证并暂存客户机内核配置候选"), None)
            if not selected:
                return {"error":"kernel task not found"}
            with urllib.request.urlopen(
                    "http://127.0.0.1:17640/api/v1/tasks/"+selected["id"],
                    timeout=5) as reply:
                return json.load(reply)
        try:
            wait.until(lambda b:"COMPLETED" in b.find_element(
                By.CSS_SELECTOR,".aiws-os-stage-status").text)
            wait.until(lambda b:'"deployed": false' in b.find_element(
                By.CSS_SELECTOR,".aiws-os-stage-status").text)
            state=kernel_stage_state()
            assert state["stages"][0]["state"]=="completed",state
            assert state["stages"][0]["result"]["deployed"] is False,state
        except Exception:
            print("AIWS_GUI_KERNEL_DIAGNOSTIC: "+json.dumps(
                kernel_stage_state(),ensure_ascii=False,default=str)[:3500],flush=True)
            print("AIWS_GUI_KERNEL_DOM: "+browser.find_element(
                By.CSS_SELECTOR,".aiws-os-studio").text[-2500:],flush=True)
            raise
        print("AIWS_GUI_BROWSER: kernel candidate approved/staged without deployment",flush=True)
        print("AIWS_GUI_BROWSER_PASS: files=clicked dag=executed model=optional kernel=candidate-only",flush=True)

if __name__=="__main__":
    main()
