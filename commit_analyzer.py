#!/usr/bin/env python3
# commit_analyzer.py
import sys
import subprocess
import requests
import json
import sqlite3
import os
import time

# --- CONFIGURATION ---
# Get the absolute path of the directory where the script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Define the database file path relative to the script's directory
DATABASE_FILE = os.path.join(SCRIPT_DIR, "expertise.db")
MODEL_NAME = "mistral"
# --- END CONFIGURATION ---


# --- DATABASE FUNCTIONS ---
def init_database():
    """Creates the database and the new, more detailed table if they don't exist."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    # This new schema is designed to hold the more detailed analysis
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expertise_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            repo_name TEXT,
            commit_hash TEXT,
            primary_technologies TEXT,
            supporting_libraries TEXT,
            key_patterns_and_concepts TEXT,
            inferred_skills TEXT,
            analysis_summary TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_expertise(user_id, repo_name, commit_hash, analysis):
    """Saves the detailed analysis from a commit to the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO expertise_log (user_id, timestamp, repo_name, commit_hash, primary_technologies, supporting_libraries, key_patterns_and_concepts, inferred_skills, analysis_summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id,
        time.strftime('%Y-%m-%d %H:%M:%S'),
        repo_name,
        commit_hash,
        json.dumps(analysis.get('primary_technologies', [])),
        json.dumps(analysis.get('supporting_libraries', [])),
        json.dumps(analysis.get('key_patterns_and_concepts', [])),
        json.dumps(analysis.get('inferred_skills', [])),
        analysis.get('analysis_summary', '')
    ))
    conn.commit()
    conn.close()
    print("✅ Expertise analysis saved to database.")
# --- END DATABASE FUNCTIONS ---


def analyze_content_with_llm(content):
    """Sends the commit data to the local Ollama model for analysis."""
    print("🧠 Analyzing commit with AI...")

    prompt = f"""
    You are a Principal Software Architect. Your task is to perform a detailed analysis of the following code changes (a git diff) and the developer's commit message. Your goal is to map the developer's expertise.
    Your analysis must be highly specific and discriminating. Extract the following information into a structured JSON format.

    **JSON OUTPUT STRUCTURE:**
    - **primary_technologies**: A list of the main programming languages and major frameworks (e.g., "Python", "Flask", "React").
    - **supporting_libraries**: A list of specific libraries or packages being imported and used (e.g., "requests", "pandas", "sqlite3").
    - **key_patterns_and_concepts**: A list of specific software design patterns or programming concepts being implemented. Be specific (e.g., "REST API consumption", "Data transformation with DataFrame", "Database read operation").
    - **inferred_skills**: A list of high-level, resume-worthy skills that this code demonstrates (e.g., "API Integration", "Data Engineering", "Web Service Development").
    - **analysis_summary**: A concise, one-sentence technical summary of the code's function.

    **RULES:**
    1.  Be precise. Do not list generic concepts.
    2.  If a category is not applicable, you MUST return an empty list [].
    3.  Base your analysis ONLY on the provided context.

    **Analyze the following commit:**
    ---
    {content}
    ---
    """

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            },
            timeout=180 # Give it 3 minutes for potentially larger diffs
        )
        response.raise_for_status()
        return json.loads(response.json().get("response", "{}"))
    except requests.exceptions.RequestException as e:
        print(f"❌ Could not connect to Ollama. Is it running? Error: {e}")
        return None

def get_git_info():
    """Gets the staged diff, commit message, user, and repo info."""
    try:
        # Get the staged diff
        diff = subprocess.check_output(['git', 'diff', '--staged']).decode('utf-8')
        
        # Get the commit message from the temp file Git provides
        commit_msg_filepath = sys.argv[1]
        with open(commit_msg_filepath, 'r') as f:
            commit_message = f.read()

        # Get user and repo info
        user_name = subprocess.check_output(['git', 'config', 'user.name']).decode('utf-8').strip()
        repo_name = os.path.basename(subprocess.check_output(['git', 'rev-parse', '--show-toplevel']).decode('utf-8').strip())
        
        return diff, commit_message, user_name, repo_name
    except Exception as e:
        print(f"Error getting Git info: {e}")
        return None, None, None, None

# --- MAIN SCRIPT LOGIC ---
if __name__ == "__main__":
    print("🚀 Running Expertise Engine (Git Commit Hook)...")
    init_database()

    diff, commit_message, user_name, repo_name = get_git_info()

    if not diff.strip() or not commit_message.strip():
        print("No staged changes or commit message found. Skipping analysis.")
        sys.exit(0)

    # Combine the commit message and diff for a rich context
    analysis_content = f"Commit Message:\n{commit_message}\n\nCode Diff:\n{diff}"

    analysis = analyze_content_with_llm(analysis_content)

    if analysis:
        # We don't have the final commit hash yet, so we'll use a placeholder
        save_expertise(user_name, repo_name, "pre-commit-analysis", analysis)
    else:
        print("❌ Analysis failed. Commit will proceed without saving expertise.")

    # Exit with 0 to allow the commit to proceed
    sys.exit(0)
