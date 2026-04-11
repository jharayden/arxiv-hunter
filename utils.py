# utils.py — Project Helix Shared Utilities
# V1.0: DRY consolidation of storage, email, and network resilience

import os
import re
import time
import smtplib
import datetime
import functools
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Callable, Any, Tuple


# =================================================================
# 🛡️ Network Resilience
# =================================================================

def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Callable:
    """
    Decorator: retry a function with exponential backoff.
    Retries on specified exceptions, sleeping progressively longer each attempt.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        print(f"[RETRY] {func.__name__} failed after {max_retries} attempts: {e}")
                        raise
                    print(f"[RETRY] {func.__name__} attempt {attempt}/{max_retries} failed ({e}). "
                          f"Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                    delay *= backoff_factor
            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
        return wrapper
    return decorator


def check_github_rate_limit(response_headers: dict) -> Tuple[bool, int]:
    """
    Inspects GitHub API response headers for rate limit status.
    Returns (is_limited, remaining).
    """
    remaining = int(response_headers.get("X-RateLimit-Remaining", 999))
    if remaining < 5:
        print(f"[RATE LIMIT] GitHub API nearly exhausted: {remaining} requests left.")
        return True, remaining
    return False, remaining


# =================================================================
# 💾 Storage Layer
# =================================================================

class ObsidianFileStorage:
    """
    V1.0: Unified file storage with auto-increment filenames.
    Used by both Arxiv Hunter and GitHuber.
    """
    def __init__(self, vault_path: Optional[str] = None, subfolder: str = ""):
        # [TOMBSTONE FIX] 强制读取在 api.py 中被暴力注入的真理路径
        env_vault = os.getenv("OBSIDIAN_PATH")
        
        if vault_path:
            self.base_dir = Path(vault_path).resolve()
        elif env_vault:
            # 无论你是谁，只要在 Tombstone 架构下，都给我滚回这个物理路径
            self.base_dir = Path(env_vault).resolve()
        else:
            # 最后的防线：如果所有配置都失效，强制写在当前终端运行的物理目录下
            self.base_dir = Path.cwd() / "Vault"

        self.target_dir = self.base_dir / subfolder if subfolder else self.base_dir
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        try:
            self.target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[STORAGE ERROR] Cannot create directory {self.target_dir}: {e}")
            raise

    def save(self, content: str, prefix: str) -> Path:
        """
        Write content to a file with auto-incrementing name.
        e.g. Arxiv_Hunter_2026-04-06_1.md
        """
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        counter = 1
        while True:
            filename = f"{prefix}_{today_str}_{counter}.md"
            full_path = self.target_dir / filename
            if not full_path.exists():
                break
            counter += 1

        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[STORAGE] Saved: {full_path}")
            return full_path
        except Exception as e:
            print(f"[STORAGE ERROR] Write failed: {e}")
            raise

    def read(self, filename: str) -> str:
        """Read a file from the vault."""
        full_path = self.target_dir / filename
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()


# =================================================================
# 📧 Email Dispatch Layer
# =================================================================

class EmailDispatcher:
    """
    V1.0: Unified email dispatcher.
    Strips Obsidian callout syntax for clean plain-text delivery.
    """
    def __init__(self):
        self.sender = os.getenv("SENDER_EMAIL")
        self.password = os.getenv("EMAIL_PASSWORD")
        self.receiver = os.getenv("RECEIVER_EMAIL")
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.163.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "465"))

    def _validate_credentials(self) -> bool:
        if not all([self.sender, self.password, self.receiver]):
            print("[EMAIL ERROR] Missing credentials in .env. Aborting dispatch.")
            return False
        return True

    def _slice_obsidian_syntax(self, content: str) -> str:
        """
        Strip Obsidian callout markers for clean plain-text emails.
        e.g. '> [!info] 🎯 Target Locked' → '--- 🎯 Target Locked ---'
        """
        sliced = re.sub(r'^> \[\!.*?\] (.*?)$', r'--- \1 ---', content, flags=re.MULTILINE)
        sliced = re.sub(r'^> ', '', sliced, flags=re.MULTILINE)
        return sliced

    def send(self, content: str, subject: str) -> None:
        """Send a plain-text email, stripping Obsidian syntax first."""
        if not self._validate_credentials():
            return

        clean_text = self._slice_obsidian_syntax(content)

        msg = MIMEMultipart()
        msg['From'] = self.sender
        msg['To'] = self.receiver
        msg['Subject'] = subject
        msg.attach(MIMEText(clean_text, 'plain', 'utf-8'))

        try:
            server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, local_hostname="localhost")
            server.login(self.sender, self.password)
            server.sendmail(self.sender, self.receiver, msg.as_string())
            server.quit()
            print(f"[EMAIL] Dispatched to {self.receiver}: {subject}")
        except Exception as e:
            print(f"[EMAIL ERROR] SMTP transmission failed: {e}")
            raise
