# Occams Advisory Chatbot Project

## Overview
This project is a Retrieval-Augmented Generation (RAG) chatbot for Occams Advisory. It scrapes content from the company's website, stores it in a SQLite database and FAISS vector store, and uses LangChain with Google Generative AI (Gemini) to provide context-aware responses. The backend is built with Flask, the frontend with Streamlit, and includes user authentication, admin controls for scraping/index management, and PII handling with encryption. Testing is done via Pytest.
Key features:

* Web scraping of occamsadvisory.com using Selenium.
* RAG pipeline for querying scraped content.
* User onboarding with PII encryption.
* Admin dashboard for managing FAISS indexes and scraping.
* Chat history persistence.
* Fallback responses for graceful degradation.

## Project Directory Structure
```
project/
├── .env                  # Environment variables (e.g., GOOGLE_API_KEY)
├── app.py                # Flask backend with RAG and API endpoints
├── database.db           # SQLite database
├── rag.py                # FAISS index building and chunk combining
├── scraper.py            # Selenium-based web scraper
├── streamlit_app.py      # Streamlit frontend UI
├── test_app.py           # Pytest test cases
├── web-scraper.ipynb     # Jupyter notebook for web scraping
├── rag.ipynb             # Jupyter notebook for rag based answering system
└── requirements.txt      # Dependency list 
```

## Architecture Diagram
Here's the representation of the system architecture:
```
+-------------------+     +-------------------+     +-------------------+
|   Streamlit UI    |     |    Flask Backend  |     |   SQLite DB       |
| - Login/Signup    |<--->| - API Endpoints   |<--->| - Users (PII enc) |
| - Chat Sidebar    |     | - RAG Logic       |     | - Knowledge       |
| - Admin Dashboard |     | - Scraping Trigger|     | - Chat History    |
+-------------------+     | - Onboarding      |     | - Config          |
                          +-------------------+     +-------------------+
                                    |                        ^
                                    v                        |
                           +-------------------+     +-------------------+
                           |   Selenium Scraper|     |   FAISS Index     |
                           | - BFS Crawling    |<--->| - Vector Store    |
                           | - Content Extract |     | - Embeddings      |
                           +-------------------+     +-------------------+
                                    ^
                                    |
                           +-------------------+
                           | occamsadvisory.com|
                           +-------------------+

External: Google Generative AI (LLM) for query responses.
```

* **Flow:** Users interact via Streamlit, which calls Flask APIs. Flask handles auth, RAG (retrieves from FAISS, augments with LLM), and DB ops. Scraping runs in background threads.

## ER Diagram
The SQLite database schema is as follows:
```
+-------------+       +-------------+       +----------------+
|   users     |       | chat_history|       |   knowledge    |
+-------------+       +-------------+       +----------------+
| id (PK)     |<--1:N-| user_id (FK)|       | id (PK)        |
| email       |       | message     |       | index_name     |
| password    |       | is_bot      |       | page_url       |
| name        |       | timestamp   |       | content        |
| email_enc   |       +-------------+       | timestamp      |
| phone_enc   |                             +----------------+
| onboarded   |       +-------------+
| role        |       |   config    |
| phone       |       +-------------+
+-------------+       | key (PK)    |
                      | value       |
                      +-------------+
```
* Relationships:

    * users 1:N chat_history (via user_id).
    * knowledge stores scraped data per index.
    * config holds key-value pairs (e.g., active_index_name).

* Admin user is seeded with email "admin@email.com" and password "admin@123" (hashed).

## Installation and Running Steps
1. Clone the Repository:
    ```
    git clone https://github.com/dsRitam/occams-app.git
    cd occams-app
    ```
2. Set Up Virtual Environment:
    ```
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```
3. Install Dependencies:
    ```
    pip install -r requirements.txt
    ```
4. Set Environment Variables: Create a `.env` file in the root and set gemini api key:
    ```
    GOOGLE_API_KEY=<your-google-generative-ai-key>
    ADMIN_KEY="this-is-admin-key"
    ```
5. Initialize Database:
The DB is auto-initialized on Flask startup, but you can run `app.py` to create `database.db`.

6. Run the Backend (Flask):
    ```
    python app.py
    ```
    Runs on http://127.0.0.1:5000 (debug mode).
7. Run the Frontend (Streamlit): In a new terminal (with venv activated):
    ```
    streamlit run streamlit_app.py
    ```
    Opens in browser at http://localhost:8501.

8. Usage:

* Login as admin: Email `admin@email.com`, Password `admin@123`.
* For users: Sign up via form (provides phone), then login with phone and generated OTP (demo OTP shown in UI).
* Admin: Trigger scrape, manage indexes.
* Chat: Ask questions in sidebar; uses active FAISS index for RAG.

9. Testing : In a new terminal
    ```
    pytest -v
    ```

## Key Design Choices & Trade-offs

### 1. RAG with FAISS and LangChain
We chose FAISS for vector storage due to its efficiency in similarity search for embeddings (using HuggingFace's all-MiniLM-L6-v2). LangChain handles the chain: retrieval (k=3 chunks), combination, and augmentation with Gemini LLM. Trade-offs: FAISS is local and fast but requires rebuilding indexes on new scrapes, increasing storage (each index is a folder). We opted for multiple indexes (timestamped) for versioning, allowing admins to switch/ delete without data loss. This adds admin overhead but prevents downtime during updates. Alternatives like Pinecone were avoided for simplicity (no cloud dependency), though scaling to large datasets might require it.

### 2. Authentication and PII Handling
User auth uses phone-based OTP for users (hashed storage) and email/password for admin. PII (email/phone) is encrypted with Fernet before DB storage. Trade-offs: Encryption key is generated per run (in-memory), so restarts lose decryption ability—suitable for demo but not production (key should be persisted securely). OTP is generated randomly and hashed with Bcrypt, but no real SMS/email sending (demo only). This keeps it simple but insecure for real use. Session-based auth in Flask is lightweight but vulnerable to session hijacking; JWT could be more secure but adds complexity.

### 3. Scraping with Selenium
Selenium in headless mode for dynamic JS content. BFS queue for internal links, skipping blogs/podcasts. Trade-offs: Selenium is robust for JS but slow/resource-intensive (15+ mins for site). BeautifulSoup extracts text post-load. No rate limiting/anti-bot evasion, risking blocks. Alternatives like Scrapy were considered but Selenium handles JS better. Data structured as list of {'url': str, 'content': str}, split into chunks for FAISS.

### 4. Frontend with Streamlit
Streamlit for rapid UI prototyping: sidebar chat, forms, dashboard. Trade-offs: Simple but less customizable than React; API calls to Flask add latency. Session state manages UI, but no real-time (polling for scrape status). Good for MVP, but production might need a full web framework.

## Threat Model (Brief)
PII (name, email, phone) flows from Streamlit form to Flask /onboard endpoint (JSON), encrypted with Fernet, stored in DB as blobs (email_enc, phone_enc). Plain phone stored for login lookup (trade-off for usability). Mitigation: Encryption prevents DB dumps from exposing PII; no decryption in code except if needed (not implemented). Risks: In-memory key vulnerable to memory dumps; no HTTPS assumed (add in prod). Auth: Bcrypt hashing for passwords/OTPs. Threats: SQL injection (mitigated by parametrized queries), session fixation (use secure cookies in prod). No PII to third parties (local LLM calls).

## Scraping Approach
Scraping starts from https://www.occamsadvisory.com/ using Selenium in headless Chrome. BFS traversal: queue internal links (urljoin for relative), skip anchors/emails/tels/blogs/podcasts. For each page: Load, wait for readyState=complete, extra 2s sleep for JS, parse with BeautifulSoup to get_text (stripped, \n separated). Output: List of dicts {'url': str, 'content': str}. Stored in DB under timestamped index_name, then chunked (1000 chars, 200 overlap) and indexed in FAISS. Admin triggers background thread; status polled.

## Failure Modes

* **Scraping Fails:** Background thread catches exceptions, sets status "ERROR: {e}". No data inserted; old index remains active. Graceful: Chat falls back to static links (e.g., "Check our services: [url]").
* **LLM/API Down:**  RAG catches exceptions, falls back to same static responses. No crash; user sees "Service unavailable".
* **DB Issues:** Parametrized queries prevent crashes; init_db() idempotent. If no active index, fallback activated.
* **Index Load Fails:** Chat catches, uses fallback.
* **Onboarding Duplicates:** Returns "duplicate" error, prevents overwrites.

## Additional Considerations
* **What did we not build and why?** Real OTP sending (e.g., via Twilio) not built to avoid third-party dependencies and costs in MVP. No user roles beyond admin/user; no audit logs for simplicity. No multi-tenancy or scaling (single DB).

* **How does our system behave if scraping fails or the LLM/API is down?** Scraping failure: Status updates, no new index; chat uses existing or fallback. LLM down: Direct fallback responses with links, no crash.

* **Where could this be gamed or produce unsafe answers?** Gaming: Prompt injection in chat to trigger onboarding tool misuse (mitigated by agent instructions). Scraping: If site changes, BFS might miss pages or infinite loop (queue/visited prevent). Unsafe: LLM hallucinations despite RAG; no content filtering for sensitive topics. PII leak if key compromised.

* **How would we extend this to support OTP verification without leaking PII to third parties?** Use local hashing only; generate OTP server-side, store hashed. For delivery: Integrate email/SMS via self-hosted service (e.g., SMTP for email) or encrypted channels. Avoid third-party APIs by using on-prem solutions. Verify by checking hashed input against stored hash; expire OTPs with timestamps in DB.
