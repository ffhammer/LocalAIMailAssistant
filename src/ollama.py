from ollama import chat
from .accounts_loading import AccountSettings
from .data_formats import ProccesedMailMessage

def summarize_email(email_content : ProccesedMailMessage, settings : AccountSettings):
    """
    Summarizes the given email content using Llama 3.2 via the Ollama Python library.

    Parameters:
    - email_content (str): The content of the email to be summarized.

    Returns:
    - str: A brief summary of the email.
    """
    # Define the message to send to the model
    messages = [
        {
            "role": "system",
            "content": f"You are a helpful assistant that summarizes emails to the user {settings.user_for_mail} concisely."
        },
        {
            "role": "user",
            "content": f"Please summarize the following email content briefly:\n\n{email_content}"
        }
    ]
    
    try:
        # Call the chat method with Llama 3.2
        response = chat(model="llama3.2", messages=messages)
        
        # Extract and return the summary from the response
        return response.message.content.strip()
    except Exception as e:
        return f"An error occurred while summarizing the email: {e}"
