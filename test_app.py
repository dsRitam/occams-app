import pytest
import os
import sqlite3
from app import app, init_db, validate_email, validate_phone

# Setup Fixture

@pytest.fixture
def client():
    """
    A pytest fixture to set up a clean, temporary test environment for each test.
    This runs BEFORE each test function.
    """
    # 1. Define a separate database for testing
    db_path = "test_database.db"
    
    # 2. Make sure we're starting fresh (delete any old test db)
    if os.path.exists(db_path):
        os.remove(db_path)

    # 3. Temporarily "trick" the app by monkeypatching the connect() function 
    #    to use our test database instead of the real one.
    #    This is safer than deleting your real "database.db".
    original_connect = sqlite3.connect
    def patch_connect(db_name, *args, **kwargs):
        # Intercept the call and force it to use the test_database.db
        return original_connect(db_path, *args, **kwargs)

    # Apply the patch using pytest-mock's built-in 'monkeypatch' fixture
    # (We can just import it and use it)
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    mp.setattr(sqlite3, 'connect', patch_connect)

    # 4. Now that the patch is active, init_db() will create "test_database.db"
    init_db()
    
    # 5. Set the app to testing mode and yield the client
    app.config.update({"TESTING": True})
    with app.test_client() as client:
        yield client # This is the test client that our tests will use

    # 6. Teardown: Clean up the test database after the test is done
    mp.undo() # Remove the patch
    if os.path.exists(db_path):
        os.remove(db_path)


# Test Cases

## 1. Validation Tests
def test_email_validation():
    """Tests the validate_email helper function directly."""
    print("Running test: test_email_validation")
    assert validate_email("test@example.com") == True
    assert validate_email("test.user@domain.co") == True
    assert validate_email("invalid-email") == False
    assert validate_email("test@domain") == False
    assert validate_email("") == False
    assert validate_email(None) == False

def test_phone_validation():
    """Tests the validate_phone helper function directly."""
    print("Running test: test_phone_validation")
    assert validate_phone("1234567890") == True
    assert validate_phone("123456789") == False   # Too short
    assert validate_phone("12345678901") == False  # Too long
    assert validate_phone("abcdefghij") == False  # Not digits
    assert validate_phone("") == False
    assert validate_phone(None) == False

## 2. Fallback Test
def test_unknown_question_returns_fallback(client):
    """
    Tests if the chatbot returns a safe fallback when no vector index is active.
    The 'client' fixture provides a clean DB, so no index is active by default.
    """
    print("Running test: test_unknown_question_returns_fallback")
    # Send a chat message as a guest
    response = client.post('/chat', json={
        'user_id': None, 
        'message': 'What is the revenue?'
    })
    
    # Check the response
    assert response.status_code == 200
    json_data = response.get_json()
    assert 'response' in json_data
    # Check that it returned the safe fallback, NOT a RAG answer
    assert "Sorry, our chatbot service is unavailable" in json_data['response']
    assert 'action' not in json_data # No action should be triggered

## 3. Onboarding Nudge Test
def test_chat_nudges_user_to_onboard(client, mocker):
    """
    Tests that the chat correctly returns the 'open_pii_dialog' action.
    This requires mocking the entire agent chain to simulate the agent
    returning the special trigger phrase.
    """
    print("Running test: test_chat_nudges_user_to_onboard")
    
    # 1. We must simulate an active, working RAG setup to get to the agent.
    # Mock the function that checks the DB for the active index:
    mocker.patch('app.get_active_index_name', return_value="fake_index_123")
    # Mock the FAISS.load_local so it doesn't fail trying to load a file:
    mocker.patch('app.FAISS.load_local', return_value=mocker.MagicMock())
    # Mock the retriever functions (we don't care about the context for this test):
    mocker.patch('app.combine_retrieved_chunks', return_value="")
    
    # 2. Mock the agent itself.
    mock_agent = mocker.MagicMock()
    # Configure the mock agent's 'run' method to return our special trigger string.
    # This simulates the LLM deciding to use the tool.
    mock_agent.run.return_value = "You should sign up! ACTION_TRIGGER_ONBOARDING"
    
    # Patch 'initialize_agent' to return our mock_agent instead of building a real one.
    mocker.patch('app.initialize_agent', return_value=mock_agent)

    # 3. Send a chat message as a GUEST (user_id: None)
    response = client.post('/chat', json={
        'user_id': None, 
        'message': 'i want to signup' # This message goes into the prompt
    })
    
    # 4. Assert the result
    assert response.status_code == 200
    json_data = response.get_json()
    
    # Check that the response text was correctly replaced
    assert json_data['response'] == "I can help with that! Please complete the form below to sign up."
    # Check that the 'action' key was added, which tells Streamlit to open the dialog
    assert json_data['action'] == 'open_pii_dialog'