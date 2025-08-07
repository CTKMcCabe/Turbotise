# engine.py
import time
import requests
import json
import sqlite3
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- CONFIGURATION ---
# Tell the script which folder to watch.
# IMPORTANT: Change this to a real folder path on your Mac.
# An easy way to get the path is to drag the folder from Finder into your terminal.
FOLDER_TO_WATCH = "/Users/callummccabe/Downloads"
DATABASE_FILE = "expertise.db"

# The name of the local AI model you downloaded with Ollama.
MODEL_NAME = "mistral"
# --- END CONFIGURATION ---


# --- DATABASE FUNCTIONS ---
def init_database():
    """Creates the database and table if they don't exist."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
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
        json.dumps(analysis.get('technologies', [])), # Store lists as JSON strings
        json.dumps(analysis.get('core_concepts', [])),
        analysis.get('summary', '')
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


    # This is the "prompt" - the specific instruction we give the AI.
    # We're asking it to act like an expert and return a clean JSON object.
    prompt = f"""
    You are an expert technology analyst. Your task is to identify the key skills,
    technologies, and concepts demonstrated in the following text.
    Based ONLY on the text, what is this person working on?

    Summarize your findings in a JSON format with three keys:
    **RULES:**
    1.  **technologies**: List the specific programming languages, frameworks, and libraries used (e.g., "Python", "Flask", "sqlite3"). If none are present, return an empty list [].
    2.  **core_concepts**: List the main programming concepts demonstrated (e.g., "web server", "API endpoint", "database query"). If none are present, return an empty list [].
    3.  **summary**: Provide a single, concise sentence describing what the code does.

    Analyze the following code:
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
                "format": "json" # This tells Ollama to guarantee the output is JSON.
            },
            timeout=120 # Increased timeout to 2 minutes to give the model more time
        )
        response.raise_for_status() # This will raise an error if the request failed.

        # The actual result from the AI is a string, so we parse it into a proper JSON object.
        result_json = json.loads(response.json().get("response", "{}"))
        return result_json

    except requests.exceptions.RequestException as e:
        print(f"❌ Could not connect to Ollama. Is it running? Error: {e}")
        return None


# This object defines what happens when a file is changed.
class MyEventHandler(FileSystemEventHandler):
    def on_modified(self, event):
        # This function runs whenever a file is saved in the folder.
        if not event.is_directory:
            file_path = event.src_path
            print(f"👀 Detected a change in: {file_path}")

            # We'll read the content of the file that was just saved.
            try:
                # This part of the script is designed for text files, not PDFs.
                # Reading a PDF will result in garbled text.
                # For the MVP, test this with code files (.py, .js, .txt) instead of PDFs.
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Only analyze if the file has some content.
                if content.strip():
                    # Send the content to our AI function.
                    analysis = analyze_content_with_llm(content)
                    if analysis:
                        print("\n--- ✅ Expertise Analysis Complete ---")
                        print(f"Technologies: {analysis.get('technologies', 'N/A')}")
                        print(f"Concepts:     {analysis.get('core_concepts', 'N/A')}")
                        print(f"Summary:      {analysis.get('summary', 'N/A')}")
                        print("------------------------------------")
                        
                        # Get the current user and save the analysis
                        user_id = os.getlogin() # Gets the current macOS username
                        save_expertise(user_id, file_path, analysis)
                else:
                    print("File is empty, skipping analysis.")

            except Exception as e:
                print(f"Error reading file or analyzing: {e}")


# --- MAIN SCRIPT LOGIC ---
if __name__ == "__main__":
    print("🚀 Starting Expertise Engine...")
    
    # Initialize the database when the script starts
    init_database()
    print(f"✔️ Database '{DATABASE_FILE}' is ready.")

    print(f"🔥 Watching for file changes in: {FOLDER_TO_WATCH}")

    # This sets up the watchdog to monitor the folder.
    event_handler = MyEventHandler()
    observer = Observer()
    observer.schedule(event_handler, FOLDER_TO_WATCH, recursive=True)
    observer.start()

    # The script will run forever, watching for changes until you stop it.
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
