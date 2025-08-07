# engine.py
import time
import requests
import json
import sqlite3
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- CONFIGURATION ---
# Get the absolute path of the directory where the script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Define the database file path relative to the script's directory
DATABASE_FILE = os.path.join(SCRIPT_DIR, "expertise.db")

FOLDER_TO_WATCH = "/Users/callummccabe/Downloads"
MODEL_NAME = "mistral"
# --- END CONFIGURATION ---


# --- DATABASE FUNCTIONS ---
# This section will need to be updated to match the new JSON structure later.
# For now, it will only save the summary.
def init_database():
    """Creates the database and table if they don't exist."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    # Note: We will update this schema in a later step to match our new prompt.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expertise_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            file_path TEXT NOT NULL,
            technologies TEXT,
            core_concepts TEXT,
            summary TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_expertise(user_id, file_path, analysis):
    """Saves a single analysis record to the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO expertise_log (user_id, timestamp, file_path, technologies, core_concepts, summary)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        user_id,
        time.strftime('%Y-%m-%d %H:%M:%S'),
        file_path,
        # Using .get() with a default of [] handles cases where the key might be missing
        json.dumps(analysis.get('primary_technologies', []) + analysis.get('supporting_libraries', [])),
        json.dumps(analysis.get('key_patterns_and_concepts', []) + analysis.get('inferred_skills', [])),
        analysis.get('analysis_summary', '')
    ))
    conn.commit()
    conn.close()
    print(f"💾 Expertise from '{os.path.basename(file_path)}' saved to database.")
# --- END DATABASE FUNCTIONS ---


# This is the function that talks to your local AI.
def analyze_content_with_llm(content):
    """Sends file content to the local Ollama model for analysis."""
    print("\n🧠 Asking the AI to analyze the file...")
    print(f"   (Content length: {len(content)} characters)")


    # --- NEW SAAS-QUALITY PROMPT ---
    prompt = f"""
    You are a Principal Software Architect. Your task is to perform a detailed analysis of the following code snippet for the purpose of mapping developer expertise within an organization.
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
    3.  Base your analysis ONLY on the code provided.

    **Analyze the following code:**
    ---
    {content}
    ---
    """

    try:
        # This sends the request to the Ollama API running on your Mac.
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            },
            timeout=120
        )
        response.raise_for_status()

        result_json = json.loads(response.json().get("response", "{}"))
        return result_json

    except requests.exceptions.RequestException as e:
        print(f"❌ Could not connect to Ollama. Is it running? Error: {e}")
        return None


# This object defines what happens when a file is changed.
class MyEventHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory:
            file_path = event.src_path
            if os.path.basename(file_path).startswith('.'):
                return

            print(f"👀 Detected a change in: {file_path}")

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                if content.strip():
                    analysis = analyze_content_with_llm(content)
                    if analysis:
                        print("\n--- ✅ Expertise Analysis Complete ---")
                        # Print the new, more detailed structure
                        print(f"Primary Technologies: {analysis.get('primary_technologies', 'N/A')}")
                        print(f"Supporting Libraries: {analysis.get('supporting_libraries', 'N/A')}")
                        print(f"Key Patterns & Concepts: {analysis.get('key_patterns_and_concepts', 'N/A')}")
                        print(f"Inferred Skills: {analysis.get('inferred_skills', 'N/A')}")
                        print(f"Summary: {analysis.get('analysis_summary', 'N/A')}")
                        print("------------------------------------")
                        
                        user_id = os.getlogin()
                        save_expertise(user_id, file_path, analysis)
                else:
                    print("File is empty, skipping analysis.")

            except Exception as e:
                print(f"Error reading file or analyzing: {e}")


# --- MAIN SCRIPT LOGIC ---
if __name__ == "__main__":
    print("🚀 Starting Expertise Engine...")
    
    init_database()
    print(f"✔️ Database '{DATABASE_FILE}' is ready.")

    print(f"🔥 Watching for file changes in: {FOLDER_TO_WATCH}")

    event_handler = MyEventHandler()
    observer = Observer()
    observer.schedule(event_handler, FOLDER_TO_WATCH, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
