import streamlit as st
import requests
import time

st.set_page_config(page_title="Occams Advisory App", layout="wide")

# Session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "name" not in st.session_state:
    st.session_state.name = None
if "role" not in st.session_state:
    st.session_state.role = None
if "show_login" not in st.session_state:
    st.session_state.show_login = False
if "show_pii_form" not in st.session_state:
    st.session_state.show_pii_form = False
if "otp_for_demo" not in st.session_state:
    st.session_state.otp_for_demo = None

# CSS 
st.markdown("""
    <style>
    .stButton>button { width: 100%; margin: 5px 0; }
    .stTextInput>div>input { width: 100%; }
    .sidebar .stTextInput>div>input { width: 100%; }
    </style>
""", unsafe_allow_html=True)

# --- Sidebar: Chatbot (Always Available) ---
with st.sidebar:
    st.subheader("Chatbot")
    chat_box = st.container(height=300) 
    with chat_box:
        for msg in st.session_state.chat_history:
            st.write(f"{msg['role']}: {msg['content']}")

    # Onboarding (PII) form
    if st.session_state.show_pii_form:
        with st.form(key="pii_form"):
            st.write("Complete Onboarding:")
            name = st.text_input("Name")
            email = st.text_input("Email")
            phone = st.text_input("Phone (10 digits, e.g., 1234567890)")
            

            if st.form_submit_button("Submit"):
                onboard_resp = requests.post("http://127.0.0.1:5000/onboard", json={
                    'name': name, 'email': email, 'phone': phone
                }).json()
                if 'error' in onboard_resp:
                    st.error(onboard_resp['error'])
                else:
                    st.session_state.show_pii_form = False 
                    st.success("Onboarded! You can now log in using your phone number.")
                    st.rerun()

    # Chat input box
    if user_input := st.chat_input("Ask about Occams Advisory:"):
        try:
            st.session_state.chat_history.append({'role': 'You', 'content': user_input})
            response = requests.post("http://127.0.0.1:5000/chat", json={
                'user_id': st.session_state.user_id,
                'message': user_input
            }).json()
            
            st.session_state.chat_history.append({'role': 'Bot', 'content': response['response']})

            if 'action' in response and response['action'] == 'open_pii_dialog':
                st.session_state.show_pii_form = True 
                st.session_state.show_login = False 
            
            st.rerun()

        except Exception as e:
            st.error(f"Chat failed: {e}")

# --- Main Area: Login or Dashboard ---
st.title("Occams Advisory App")

# Load chat history from DB
def load_chat_history(user_id):
    try:
        history_resp = requests.get("http://127.0.0.1:5000/chat_history", 
                                    params={'user_id': user_id})
        if history_resp.ok:
            st.session_state.chat_history = history_resp.json()
        else:
            st.error("Could not load chat history.")
            st.session_state.chat_history = []
    except Exception as e:
        st.error(f"Failed to load history: {e}")
        st.session_state.chat_history = []


# Not Logged In View
if st.session_state.user_id is None:
    st.write("Welcome! Please log in to see your dashboard or chat with our assistant in the sidebar.")
    st.markdown("*:red[New users, please click 'Sign Up'. After signing up, you can log in using your registered **phone number** and the OTP we provide.]*")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login", use_container_width=True):
            st.session_state.show_login = True
            st.session_state.show_pii_form = False 
    with col2:
        if st.button("Sign Up", type="primary", use_container_width=True):
            st.session_state.show_login = False # Hide login form
            st.session_state.show_pii_form = True # Show PII form in sidebar

    if st.session_state.show_login:
        st.subheader("Login")
        with st.form(key="login_form"):
            login_identifier = st.text_input("Email (for Admin) or Phone (for User)")
            
            if st.form_submit_button("Send OTP (for Phone Login)"):
                try:
                    otp_resp = requests.post("http://127.0.0.1:5000/generate_otp", 
                                             json={'phone': login_identifier}).json()
                    if 'error' in otp_resp:
                        st.error(otp_resp['error'])
                    else:
                        st.session_state.otp_for_demo = otp_resp.get('otp_for_demo')
                        st.success("OTP generated and sent!")
                except Exception as e:
                    st.error(f"OTP generation failed: {e}")

            if st.session_state.otp_for_demo:
                st.info(f"DEMO ONLY: Your OTP is {st.session_state.otp_for_demo}")

            password = st.text_input("Password (for Admin) or OTP (for User)", type="password")
            
            if st.form_submit_button("Login"):
                try:
                    response = requests.post("http://127.0.0.1:5000/login", 
                                             json={'login_identifier': login_identifier, 'password': password}).json()
                    if 'error' in response:
                        st.error(response['error'])
                    else:
                        st.session_state.user_id = response.get('user_id')
                        st.session_state.name = response.get('name') or 'User'
                        st.session_state.role = response.get('role')
                        st.session_state.show_login = False
                        st.session_state.show_pii_form = False # Hide PII on login
                        st.session_state.otp_for_demo = None # Clear OTP
                        
                        load_chat_history(st.session_state.user_id)
                        
                        st.success(f"Logged in as {st.session_state.name} (Role: {st.session_state.role})")
                        st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")

# Logged In View
else:
    st.subheader(f"Welcome, {st.session_state.name}!")

    # --- ADMIN DASHBOARD ---
    if st.session_state.role == 'admin':
        st.subheader("Admin Dashboard")
        st.divider() 
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### Scraper Controls")
            if st.button("Trigger Scraper", key="trigger_scraper"):
                try:
                    response = requests.post("http://127.0.0.1:5000/trigger_scrape", 
                                            json={'user_id': st.session_state.user_id}).json()
                    st.write(response.get('status', response.get('error')))
                except Exception as e:
                    st.error(f"Scraper trigger failed: {e}")

        with col2:
            st.markdown("### Scraper Status")
            status_placeholder = st.empty()
            try:
                status = requests.get("http://127.0.0.1:5000/scrape_status", 
                                      params={'user_id': st.session_state.user_id}).json()
                status_placeholder.write(f"Scrape Status: {'Running' if status.get('running') else 'Idle'} - {status.get('progress', 'N/A')}")
                if status.get('running'):
                    time.sleep(3) 
                    st.rerun()
            except Exception as e:
                st.error(f"Status check failed: {e}")

        st.markdown("### Index Management")
        st.divider()
        try:
            idx_resp = requests.get("http://127.0.0.1:5000/indexes", 
                                    params={'user_id': st.session_state.user_id}).json()
            
            indexes = idx_resp.get('indexes', [])
            active_index = idx_resp.get('active', '')
            
            if indexes:
                st.write(f"**Active Index:** `{active_index if active_index else 'None'}`")
                col3, col4 = st.columns(2)
                with col3:
                    selected_index = st.selectbox("Select Active Index", indexes, 
                                                   index=indexes.index(active_index) if active_index in indexes else 0)
                    if st.button("Set as Active", key="set_active"):
                        try:
                            resp = requests.post("http://127.0.0.1:5000/set_active_index", 
                                                 json={'index_name': selected_index, 'user_id': st.session_state.user_id}).json()
                            st.write(resp.get('status', resp.get('error')))
                            st.rerun()
                        except Exception as e:
                            st.error(f"Set index failed: {e}")
                with col4:
                    del_index = st.selectbox("Delete an Index", indexes, key="delete_index")
                    if st.button("Delete Index", key="delete_index_btn", type="primary"):
                        try:
                            resp = requests.post("http://127.0.0.1:5000/delete_index", 
                                                 json={'index_name': del_index, 'user_id': st.session_state.user_id}).json()
                            st.write(resp.get('status', resp.get('error')))
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete index failed: {e}")
            else:
                st.write("No indexes available. Run the scraper to create one.")
        except Exception as e:
            st.error(f"Index fetch failed: {e}")

    # --- USER DASHBOARD ---
    elif st.session_state.role == 'user':
        st.subheader("User Dashboard")
        st.divider()
        st.write(f"Welcome to your Dashboard, {st.session_state.name}!")
        st.write("You can see your past chat history in the sidebar.")

    # --- LOGOUT BUTTON (for all logged-in users) ---
    if st.button("Logout", key="logout"):
        try:
            requests.post("http://127.0.0.1:5000/logout")
            st.session_state.clear()
            st.success("Logged out!")
            st.rerun()
        except Exception as e:
            st.error(f"Logout failed: {e}")