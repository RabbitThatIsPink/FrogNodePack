"""
Pre-push hook: updates README.md's ## Updated section with current datetime.
Called automatically by Claude Code's PreToolUse hook before any git push.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime


REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
README = os.path.join(REPO, "README.md")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cmd = (data.get("tool_input") or {}).get("command", "")
    if "git push" not in cmd:
        sys.exit(0)

    if not os.path.exists(README):
        sys.exit(0)

    with open(README, "r", encoding="utf-8") as f:
        content = f.read()

    now = datetime.now().strftime("%A, %B %d %Y - %H:%M")
    updated_block = f"## Updated\n\n{now}\n\n---\n\n"

    if "## Updated" in content:
        # Replace existing block (handles any previous timestamp)
        content = re.sub(
            r"## Updated\n\n.*?\n\n---\n\n",
            updated_block,
            content,
            flags=re.DOTALL,
        )
    else:
        # First run — insert above ## Author
        content = content.replace("## Author", updated_block + "## Author", 1)

    with open(README, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

    os.chdir(REPO)
    subprocess.run(["git", "add", "README.md"], check=False)

    status = subprocess.run(
        ["git", "status", "--porcelain", "README.md"],
        capture_output=True, text=True,
    )
    if status.stdout.strip():
        subprocess.run(
            ["git", "commit", "-m", "Update last-updated timestamp"],
            check=False,
        )


if __name__ == "__main__":
    main()
