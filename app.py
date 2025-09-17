from dotenv import load_dotenv
from flask import Flask, session, jsonify, request
import os
from cryptography.fernet import Fernet
import sqlite3
import bcrypt
from rag import build_faiss_index, combine_retrieved_chunks
import re
from scraper import scraper
import threading
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import Tool
from langchain.agents import initialize_agent
import json
import time 
import shutil 
import random 

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Encryption Key
key = Fernet.generate_key()
cipher = Fernet(key)

# scraping status
scraping_status = {"running":False, "progress":""}

# db and admin cred
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS knowledge
            (
                id INTEGER PRIMARY KEY,
                index_name TEXT, 
                page_url TEXT,
                content TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS users
            (
                id INTEGER PRIMARY KEY,
                email TEXT UNIQUE,
                password TEXT,
                name TEXT,
                email_enc BLOB,
                phone_enc BLOB,
                onboarded BOOLEAN DEFAULT FALSE,
                role TEXT DEFAULT 'user',
                phone TEXT UNIQUE
            )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_history
            (
                user_id INTEGER,
                message TEXT,
                is_bot BOOLEAN,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS config
            (
                key TEXT PRIMARY KEY,
                value TEXT
            )
    ''')
    c.execute('''
        INSERT OR IGNORE INTO config (key, value) VALUES ('active_index_name', '')
    ''')

    # admin cred
    hashed_pw = bcrypt.hashpw("admin@123".encode(), bcrypt.gensalt()).decode()
    c.execute('''
        INSERT OR IGNORE INTO users (email, password, role, name) VALUES (?, ?, ?, ?)
    ''', ("admin@email.com", hashed_pw, "admin", "Admin"))

    conn.commit()
    conn.close()

# calling db init
init_db()

# <----------------------------------------------------- HELper FUNCIONS ------------------------------------------------------------>

def get_active_index_name():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key='active_index_name'")
    result = c.fetchone()
    conn.close()
    return result[0] if result else ""


def set_active_index(index_name):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("REPLACE INTO config (key, value) VALUES ('active_index_name', ?)", (index_name,))
    conn.commit()
    conn.close()


def delete_index(index_name):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM knowledge WHERE index_name=?", (index_name,))
    conn.commit()
    conn.close()
    
    if os.path.exists(index_name) and os.path.isdir(index_name):
        try:
            shutil.rmtree(index_name)
            print(f"Deleted FAISS index folder: {index_name}")
        except Exception as e:
            print(f"Error deleting folder {index_name}: {e}")

    if get_active_index_name() == index_name:
        set_active_index("")
        print(f"Reset active index.")

def insert_knowledge(index_name, data_list):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    for item in data_list:
        c.execute("INSERT INTO knowledge (index_name, page_url, content) VALUES (?, ?, ?)", 
                  (index_name, item['url'], item['content']))
    conn.commit()
    conn.close()

def validate_email(email):
    if not isinstance(email, str):
        return False
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email))


def validate_phone(phone):
    return bool(phone) and len(phone) == 10 and phone.isdigit()


def store_pii(name, email, phone):
    # if not validate_email(email) or not validate_phone(phone):
    #     return None
    
    encrypted_email = cipher.encrypt(email.encode())
    encrypted_phone = cipher.encrypt(phone.encode())
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO users (name, email, email_enc, phone_enc, onboarded, role, phone, password) 
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
        ''', (name, email, encrypted_email, encrypted_phone, True, 'user', phone))
        user_id = c.lastrowid
        conn.commit()
        conn.close()
        return user_id
    except sqlite3.IntegrityError as e: 
        conn.close()
        print(f"Onboarding failed (Email or Phone likely exists): {e}")
        return "duplicate"
    except Exception as e:
        conn.close()
        print(f"Error in store_pii: {e}")
        return None
    

def get_user_name(user_id):
    if not user_id: return None
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT name FROM users WHERE id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None


def is_onboarded(user_id):
    if not user_id: return False
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT onboarded FROM users WHERE id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return bool(result[0]) if result else False


def log_chat(user_id, message, is_bot):
    if not user_id: return 
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO chat_history (user_id, message, is_bot) VALUES (?, ?, ?)", (user_id, message, is_bot))
    conn.commit()
    conn.close()


def trigger_onboarding_tool(query=""):
    return "ACTION_TRIGGER_ONBOARDING"

def fallback_response(query):
    links = {
        "services": "https://www.occamsadvisory.com/our-services",
        "about": "https://www.occamsadvisory.com/about",
        "contact": "https://www.occamsadvisory.com/contact",
        "occams_digital": "https://digital.occamsadvisory.com/"
    }
    if "service" in query.lower() or "services" in query.lower():
        return f"Sorry, our chatbot service is unavailable or not yet configured. Please check our services: {links['services']}"
    elif "about" in query.lower():
        return f"Sorry, our chatbot service is unavailable right now. Learn more about us: {links['about']}"
    elif "contact" in query.lower():
        return f"Sorry, our chatbot service is unavailable right now. Contact us: {links['contact']}"
    elif "digital" in query.lower() or "it" in query.lower() or "tech" in query.lower():
        return f"Sorry, our chatbot service is unavailable right now. Please check our digital services: {links['occams_digital']}"
    return f"Sorry, our chatbot service is unavailable or not yet configured. Please visit our site: {links['services']}"


def run_scraper_background():
    global scraping_status
    scraping_status["running"] = True
    scraping_status["progress"] = "Starting ....."
    try:
        scraped_data = scraper()
        if not scraped_data:
            scraping_status["progress"] = "Scraping completed, but no data found."
            scraping_status["running"] = False
            return
        
        new_index_name = f"faiss_{int(time.time())}"
        scraping_status["progress"] = f"Saving to DB under index: {new_index_name}"
        insert_knowledge(new_index_name, scraped_data)
        
        scraping_status["progress"] = f"Building FAISS index: {new_index_name}"
        build_faiss_index(new_index_name, scraped_data)
        
        scraping_status["progress"] = f"Completed. New index created: {new_index_name}. Admin must set it as active."
    
    except Exception as e:
        scraping_status["progress"] = f"ERROR: {str(e)}"
    finally:
        scraping_status["running"] = False


# <----------------------------------------------------- ROUTING ----------------------------------------------------->

def check_admin_auth(user_id):
    if not user_id: return False
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id=?", (user_id,))
    user_role = c.fetchone()
    conn.close()
    return user_role and user_role[0] == 'admin'

@app.route('/trigger_scrape', methods=['POST'])
def trigger_scrape():
    user_id = request.json.get('user_id')
    if not check_admin_auth(user_id):
        return jsonify({'error': 'Unauthorized'}), 401
    if scraping_status["running"]:
        return jsonify({'error': "Scraping in progress"}), 429
    threading.Thread(target=run_scraper_background).start()
    return jsonify({'status':"Scraping started"})


@app.route('/scrape_status', methods=['GET'])
def scrape_status():
    user_id = request.args.get('user_id')
    if not check_admin_auth(user_id):
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify(scraping_status)


@app.route('/indexes', methods=['GET'])
def get_indexes():
    user_id = request.args.get('user_id')
    if not check_admin_auth(user_id):
        return jsonify({'error': 'Unauthorized'}), 401
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT index_name FROM knowledge ORDER BY index_name DESC")
    indexes = [row[0] for row in c.fetchall()]
    conn.close()
    return jsonify({'indexes': indexes, 'active': get_active_index_name()})


@app.route('/set_active_index', methods=['POST'])
def set_active_index_route():
    user_id = request.json.get('user_id')
    if not check_admin_auth(user_id):
        return jsonify({'error': 'Unauthorized'}), 401
    index_name = request.json.get('index_name')
    if index_name is None:
        return jsonify({'error': 'Missing index_name'}), 400
    set_active_index(index_name)
    return jsonify({'status': 'Active index set', 'index_name': index_name})
    

@app.route('/delete_index', methods=['POST'])
def delete_index_route():
    user_id = request.json.get('user_id')
    if not check_admin_auth(user_id):
        return jsonify({'error': 'Unauthorized'}), 401
    index_name = request.json.get('index_name')
    if not index_name:
        return jsonify({'error': 'Missing index_name'}), 400
    delete_index(index_name)
    return jsonify({'status': 'Index deleted'})
    
# --- NEW OTP LOGIN FLOW ---

@app.route('/generate_otp', methods=['POST'])
def generate_otp():
    phone = request.json.get('phone')
    if not validate_phone(phone):
        return jsonify({'error': 'Invalid phone number format'}), 400
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE phone = ?", (phone,))
    user = c.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'error': 'Phone number not found. Please sign up first.'}), 404
    
    # Generate OTP and hash it
    otp = str(random.randint(100000, 999999))
    hashed_otp = bcrypt.hashpw(otp.encode(), bcrypt.gensalt()).decode()
    
    # Update the user's password to be this new OTP
    c.execute("UPDATE users SET password = ? WHERE phone = ?", (hashed_otp, phone))
    conn.commit()
    conn.close()
    
    # Return the OTP for demo purposes
    return jsonify({'status': 'OTP generated', 'otp_for_demo': otp})

@app.route('/login', methods=['POST'])
def login():
    # Supports both email (admin) and phone (user)
    login_identifier = request.json.get('login_identifier')
    password = request.json.get('password')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    # Find user by EITHER email OR phone
    c.execute('''
                SELECT id, name, role, password
                FROM users
                WHERE email = ? OR phone = ?
                ''', (login_identifier, login_identifier))
    result = c.fetchone()
    conn.close()

    if result and result[3] and bcrypt.checkpw(password.encode(), result[3].encode()):
        session['user_id'] = result[0]
        session['name'] = result[1]
        session['role'] = result[2]
        return jsonify({'status': 'Logged in', 'user_id': result[0], 'name': result[1], 'role': result[2]})
    
    return jsonify({'error': 'Invalid credentials'}), 401


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'status': 'Logged out'})


@app.route('/chat_history', methods=['GET'])
def get_chat_history():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'Missing user_id'}), 400
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT message, is_bot FROM chat_history WHERE user_id = ? ORDER BY timestamp ASC", (user_id,))
    history = [{'role': 'Bot' if row[1] else 'You', 'content': row[0]} for row in c.fetchall()]
    conn.close()
    return jsonify(history)


@app.route('/chat', methods=['POST'])
def chat():
    user_id = request.json.get('user_id') 
    message = request.json.get('message')
    name = get_user_name(user_id)
    onboarded = is_onboarded(user_id)

    active_index = get_active_index_name()
    if not active_index:
        print("Chat Fallback: No active index set.")
        response_text = fallback_response(message)
        log_chat(user_id, message, False)
        log_chat(user_id, response_text, True)
        return jsonify({'response': response_text})
    
    try:
        faiss_path = active_index
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        vectorstore = FAISS.load_local(faiss_path, embeddings, allow_dangerous_deserialization=True)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
    except Exception as e:
        print(f"Chat Fallback: Failed to load FAISS index {faiss_path}. Error: {e}")
        response_text = fallback_response(message)
        log_chat(user_id, message, False)
        log_chat(user_id, response_text, True)
        return jsonify({'response': response_text})
    
    # --- RAG Logic ---
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.3)
    tools = []
    
    # Only add onboarding tool for GUESTS (user_id is None)
    if not user_id: 
        tools = [Tool(
            name="trigger_onboarding",
            func=trigger_onboarding_tool,
            description="Use if user explicitly mentions onboarding/sign up (e.g., 'sign up', 'join', 'register') or conversation is ending (e.g., 'bye', 'thanks')."
        )]

    try:
        retrieved_docs = retriever.invoke(message)
        context_string = combine_retrieved_chunks(retrieved_docs)
    except Exception as e:
        print(f"ERROR: Retriever failed. Error: {e}")
        context_string = ""

    prompt = f"""You are a helpful assistant for Occams Advisory. 
    Answer using retrieved context. 
    Personalize with name if needed: {name or 'User'}. Query: {message}. Context: {context_string}"""
    
    # --- AGENT vs. LLM Call ---
    try:
        if tools:
            # --- PATH 1: Use Agent (for GUESTS) ---
            tool_priority_instructions = """
                            ---
                            IMPORTANT INSTRUCTIONS:
                            You have a special tool called 'trigger_onboarding'.
                            - If the user's query seems that better to sign him/her up  (e.g., 'i want to signup', 'join', 'register', 'am interested', 'onboard', '
                            - OR if the user is ending the conversation (e.g., 'bye', 'thanks', 'goodbye')
                            You MUST use the 'trigger_onboarding' tool.
                            For these specific cases, DO NOT use the retrieved context to answer.
                            """
            prompt += tool_priority_instructions
            
            agent = initialize_agent(tools, llm, agent_type="zero-shot-react-description", verbose=True)
            response_text = agent.run(prompt)

            
            onboarding_triggers = [
                "ACTION_TRIGGER_ONBOARDING",
                "onboarding process initiated",
                "sign-up process",
                "please complete the form",
                "ready to onboard",
                "let’s get you registered",
                "action_trigger_onboarding",
                "initiated",
            ]

            if any(trigger.lower() in response_text.lower() for trigger in onboarding_triggers):
                response_text = "I can help with that! Please complete the form below to sign up."
                log_chat(user_id, message, False)
                log_chat(user_id, response_text, True)
                return jsonify({'response': response_text, 'action': 'open_pii_dialog'})
        
        else:
            # --- PATH 2: Use direct LLM (for LOGGED-IN USERS) ---
            response = llm.invoke(prompt)
            response_text = response.content

    except Exception as e:
        print(f"CRITICAL: Agent/LLM failed to run. Error: {e}")
        response_text = fallback_response(message)

    log_chat(user_id, message, False)
    log_chat(user_id, response_text, True)
    return jsonify({'response': response_text})

@app.route('/onboard', methods=['POST'])
def onboard():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')

    if not name:
        return jsonify({'error': 'Name is required.'}), 400
    if not validate_email(email):
        return jsonify({'error': 'Invalid email address format.'}), 400
    if not validate_phone(phone):
        return jsonify({'error': 'Invalid phone number. Must be 10 digits.'}), 400

    user_id_or_error = store_pii(name, email, phone)
    
    if user_id_or_error == "duplicate":
        return jsonify({'error':'Email or phone number already exists.'}), 400
    
    if not user_id_or_error:
        return jsonify({'error':'An unknown error occurred during onboarding.'}), 500
    
    # successfully created user
    return jsonify({'user_id': user_id_or_error, 'status': 'Onboarded', 'name': name, 'role': 'user'})

if __name__ == '__main__':
    app.run(debug=True)