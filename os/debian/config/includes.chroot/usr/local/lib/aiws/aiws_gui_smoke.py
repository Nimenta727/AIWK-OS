"""In-guest browser click acceptance; no host access, no network adapter."""
from pathlib import Path
import os
import json
import urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
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
        # The shell picks its language from the browser, and headless Chrome says en-US: the steps below click Chinese labels, so ask for Chinese.
        browser.execute_script("window.localStorage.setItem('aiws.lang','zh')")
        browser.get("http://127.0.0.1:17640/")
        wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,".app .tabs"))
        print("AIWS_GUI_BROWSER: React workbench rendered",flush=True)

        def go(label):
            """Open a view through the command palette (Ctrl+Shift+P), the shell's one uniform way to navigate. The labels are the view names of the VS Code style shell."""
            ActionChains(browser).key_down(Keys.CONTROL).key_down(Keys.SHIFT).send_keys("p").key_up(Keys.SHIFT).key_up(Keys.CONTROL).perform()
            box=wait.until(lambda b:b.find_element(By.CSS_SELECTOR,".pal input"))
            box.send_keys(label)
            wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,".pal li[role=option]"))
            box.send_keys(Keys.ENTER)
            wait.until(lambda b:not b.find_elements(By.CSS_SELECTOR,".pal"))

        go("AI 文件管理")
        wait.until(lambda b:b.find_elements(By.XPATH,
            "//div[contains(@class,'aiws-os-file-list')]//button[contains(.,'AIWS-GUEST-SMOKE.txt')]"))
        browser.find_element(By.XPATH,
            "//div[contains(@class,'aiws-os-file-list')]//button[contains(.,'AIWS-GUEST-SMOKE.txt')]").click()
        wait.until(lambda b:"guest-only file manager acceptance fixture" in
            b.find_element(By.CSS_SELECTOR,".aiws-os-file-detail pre").text)
        print("AIWS_GUI_BROWSER: guest file explorer click/read verified",flush=True)
        go("持久任务")
        wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,".aiws-os-studio input"))
        browser.find_element(By.CSS_SELECTOR,".aiws-os-studio input").send_keys("GUI guest smoke")
        browser.find_element(By.CSS_SELECTOR,".aiws-os-studio textarea").send_keys("List guest workspace")
        browser.find_element(By.XPATH,"//button[contains(.,'保存任务与 DAG')]").click()
        wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,".aiws-os-stage-status"))
        browser.find_element(By.XPATH,"//button[contains(.,'运行客户机阶段')]").click()
        wait.until(lambda b:"COMPLETED" in b.find_element(By.CSS_SELECTOR,".aiws-os-stage-status").text)
        print("AIWS_GUI_BROWSER: DAG stage executed",flush=True)
        go("本地模型开关")
        wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,".aiws-os-studio"))
        studio=browser.find_element(By.CSS_SELECTOR,".aiws-os-studio").text      # the image ships without weights
        assert "未启用" in studio and "Qwen3.5-9B" in studio, studio[:200]
        # A genuine guest-only *candidate* pipeline, not a running kernel edit.
        go("系统服务与内核")
        wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,".aiws-os-system-console"))
        wait.until(lambda b:"CONFIG" not in b.find_element(By.CSS_SELECTOR,".aiws-os-system-console").text)
        browser.find_element(By.XPATH,"//button[contains(.,'提交候选验证和暂存审批')]").click()
        # In the VS Code style shell the submit opens the plan review page; a high-risk step needs an explicit confirmation there.
        wait.until(lambda b:b.find_elements(By.XPATH,"//button[contains(.,'批准并运行')]"))
        browser.find_element(By.XPATH,"//button[contains(.,'批准并运行')]").click()
        wait.until(lambda b:b.find_elements(By.XPATH,"//button[contains(.,'我确认，运行')]"))
        browser.find_element(By.XPATH,"//button[contains(.,'我确认，运行')]").click()
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
            # The plan page does not print the result, so the proof is the live guest API: the stage completed and nothing was deployed.
            wait.until(lambda b:kernel_stage_state().get("stages",[{}])[0].get("state")=="completed")
            state=kernel_stage_state()
            assert state["stages"][0]["state"]=="completed",state
            assert state["stages"][0]["result"]["deployed"] is False,state
        except Exception:
            print("AIWS_GUI_KERNEL_DIAGNOSTIC: "+json.dumps(
                kernel_stage_state(),ensure_ascii=False,default=str)[:3500],flush=True)
            print("AIWS_GUI_KERNEL_DOM: "+browser.find_element(By.CSS_SELECTOR,"body").text[-2500:],flush=True)
            raise
        print("AIWS_GUI_BROWSER: kernel candidate approved/staged without deployment",flush=True)
        print("AIWS_GUI_BROWSER_PASS: files=clicked dag=executed model=optional kernel=candidate-only",flush=True)

if __name__=="__main__":
    main()
