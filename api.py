import os
import shutil
import subprocess
import sys
import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler

# Import Engines
from hunter import ArxivHunter
from githuber import GitHuber
from openai import OpenAI

# =================================================================
# 💀 [TOMBSTONE PROTOCOL] 黑匣子与物理路径锁定
# =================================================================

# 1. 锁定真实的物理目录
if getattr(sys, 'frozen', False):
    TRUE_BASE_DIR = os.path.dirname(sys.executable)
else:
    TRUE_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. 封印虚空，建立本地黑匣子日志 (解决 --noconsole 崩溃的终极方案)
if getattr(sys, 'frozen', False) or sys.stdout is None:
    log_path = os.path.join(TRUE_BASE_DIR, "helix_blackbox.log")
    log_file = open(log_path, "a", encoding="utf-8")
    sys.stdout = log_file
    sys.stderr = log_file
else:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 3. 强制从物理目录读取环境变量
env_path = os.path.join(TRUE_BASE_DIR, '.env')
load_dotenv(env_path)
os.environ["NO_PROXY"] = "*"

# --- [核心定义] ---
app = FastAPI(title="Project Helix API", version="5.0.0")

# --- [金库防御与路径下发] ---
raw_path = os.getenv("OBSIDIAN_PATH", "").strip()
MASTER_VAULT = raw_path if raw_path else os.path.join(TRUE_BASE_DIR, "Vault")
os.makedirs(MASTER_VAULT, exist_ok=True)
os.environ["OBSIDIAN_PATH"] = MASTER_VAULT

print(f"\n[{sys.platform.upper()} SYSTEM] Engine Ignited. Path Locked: {MASTER_VAULT}")

# =================================================================
# 🛡️ 核心守护进程：双时区点火逻辑
# =================================================================
def scheduled_arxiv_mission():
    try:
        api_key = os.getenv("GLM_API_KEY")
        topic = os.getenv("TARGET_TOPIC", "Embodied AI")
        hunter = ArxivHunter(glm_api_key=api_key)
        papers = hunter.hunt_papers(query=topic, max_results=10)
        report = hunter.digest_papers(papers=papers)
        if report and not report.startswith("> [!error]"):
            hunter.save_report(content=report, vault_path=MASTER_VAULT)
            hunter.send_email(report)
            print("[DAEMON] Arxiv Mission Success.")
    except Exception as e:
        print(f"[DAEMON_ERROR] Arxiv Failed: {e}")

def scheduled_github_mission():
    try:
        githuber = GitHuber()
        lobster = githuber.hunt_top_lobster(query="")
        if lobster:
            report = githuber.evaluate_lobster(lobster)
            githuber.save_to_vault(report)
            githuber.send_email(report, lobster["name"])
            print("[DAEMON] GitHub Mission Success.")
    except Exception as e:
        print(f"[DAEMON_ERROR] GitHub Failed: {e}")

# 启动闹钟
scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_arxiv_mission, 'cron', hour=8, minute=30)
scheduler.add_job(scheduled_github_mission, 'cron', hour=19, minute=30)
scheduler.start()
print("[SYSTEM] Guardian Online: 08:30 Arxiv | 19:30 GitHub")

# --- [中间件配置] ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- [数据模型] ---
class HuntRequest(BaseModel):
    target_topic: str = "Embodied AI"

class ChatRequest(BaseModel):
    message: str
    history: list
    context_path: Optional[str] = None

# --- [API 路由] ---

@app.get("/api/health")
async def health_check():
    return {"status": "Helix Backend Online", "code": 200}

@app.post("/api/arxiv/ignite")
async def trigger_arxiv_hunter(request: HuntRequest):
    try:
        actual_topic = request.target_topic.strip() or os.getenv("TARGET_TOPIC")
        api_key = os.getenv("GLM_API_KEY")
        hunter = ArxivHunter(glm_api_key=api_key)
        papers = hunter.hunt_papers(query=actual_topic, max_results=10)
        report = hunter.digest_papers(papers=papers)
        if not report or report.startswith("> [!error]"):
            raise HTTPException(status_code=500, detail="LLM Error")
        hunter.save_report(content=report, vault_path=MASTER_VAULT)
        hunter.send_email(report)
        return {"status": "success", "payload": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/github/ignite") 
async def trigger_github_radar(request: HuntRequest):
    try:
        actual_topic = request.target_topic.strip()
        githuber = GitHuber()
        lobster = githuber.hunt_top_lobster(query=actual_topic) 
        if not lobster: raise HTTPException(status_code=404, detail="No Target")
        report = githuber.evaluate_lobster(lobster)
        githuber.save_to_vault(report)
        githuber.send_email(report, lobster["name"])
        return {"status": "success", "target": lobster["name"], "payload": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/vault/list")
async def list_vault_files():
    try:
        arxiv_path = Path(MASTER_VAULT) / "Arxiv_Papers"
        github_path = Path(MASTER_VAULT) / "GitHuber"
        arxiv_files = [{"name": f.name, "path": str(f)} for f in arxiv_path.glob("*.md")] if arxiv_path.exists() else []
        github_files = [{"name": f.name, "path": str(f)} for f in github_path.glob("*.md")] if github_path.exists() else []
        return {"arxiv_papers": sorted(arxiv_files, key=lambda x: x["name"], reverse=True), 
                "github_repos": sorted(github_files, key=lambda x: x["name"], reverse=True)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/vault/read")
async def read_vault_file(path: str):
    try:
        with open(path, 'r', encoding='utf-8') as f: content = f.read()
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def helix_chat(request: ChatRequest):
    try:
        client = OpenAI(api_key=os.getenv("GLM_API_KEY"), base_url="https://open.bigmodel.cn/api/paas/v4/")
        system_prompt = "You are SYNAPSE, the Helix AI assistant. Answer in Markdown."
        if request.context_path and os.path.exists(request.context_path):
            with open(request.context_path, 'r', encoding='utf-8') as f:
                system_prompt += f"\n\nContext:\n{f.read()}"
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(request.history)
        messages.append({"role": "user", "content": request.message})
        response = client.chat.completions.create(model="glm-4", messages=messages)
        return {"status": "success", "reply": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)