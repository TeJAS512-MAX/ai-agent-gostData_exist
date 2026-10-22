from pathlib import Path
import json
from datetime import datetime

def export_transcript():
    app_data = Path(r"C:\Users\sathw\.gemini\antigravity\brain\6534e3fa-f7a1-409b-8963-9e67ee73c35d\.system_generated\logs\transcript.jsonl")
    output_dir = Path(__file__).resolve().parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_file = output_dir / "chat_transcript.md"
    log_txt = output_dir / "log.txt"

    lines_out = [
        "# HackerRank Orchestrate AI Collaboration Transcript\n",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        "**AI Pair Programming Assistant:** Google Antigravity / DeepMind Advanced Agentic Engine\n",
        "**Project:** Autonomous AI Triage Agent Architecture\n",
        "---\n\n"
    ]

    plain_logs = []

    if app_data.exists():
        with open(app_data, "r", encoding="utf-8") as f:
            step_idx = 1
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    role = entry.get("source", "SYSTEM")
                    step_type = entry.get("type", "")
                    content = entry.get("content", "")

                    if step_type == "USER_INPUT":
                        lines_out.append(f"### [Step {step_idx}] User Prompt ({entry.get('created_at', '')})\n")
                        lines_out.append(f"> {content}\n\n")
                        plain_logs.append(f"USER: {content}")
                        step_idx += 1
                    elif step_type == "PLANNER_RESPONSE" and content:
                        lines_out.append(f"### [Step {step_idx}] Assistant Action & Strategy\n")
                        lines_out.append(f"{content}\n\n---\n\n")
                        plain_logs.append(f"ASSISTANT: {content[:200]}...")
                        step_idx += 1
                except Exception:
                    pass

    out_file.write_text("".join(lines_out), encoding="utf-8")
    log_txt.write_text("\n".join(plain_logs), encoding="utf-8")
    print(f"Exported AI Chat Transcript successfully to:\n- {out_file}\n- {log_txt}")

if __name__ == "__main__":
    export_transcript()

