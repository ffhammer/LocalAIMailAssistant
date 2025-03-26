from ollama import chat
from .accounts_loading import AccountSettings
from .data_formats import ProccesedMailMessage

MODEL = "llama3.2"


def summarize_email(
    email_content: ProccesedMailMessage, settings: AccountSettings, stream=False
):
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
            "content": f"You are a helpful assistant that summarizes emails to the user {settings.user_for_mail} concisely. Start of directly with the summary and skip an introduction.",
        },
        {
            "role": "user",
            "content": f"Please summarize the following email content briefly:\n\n{email_content}",
        },
    ]

    try:
        # Call the chat method with Llama 3.2
        response = chat(model=MODEL, messages=messages, stream=stream)

        if stream:
            return response
        # Extract and return the summary from the response
        return response.message.content.strip()
    except Exception as e:
        return f"An error occurred while summarizing the email: {e}"


def generate_draft(
    email_content: ProccesedMailMessage, settings: AccountSettings, stream=False
):
    """
    Generates a concise draft email response using Llama 3.2 via the Ollama Python library.

    Parameters:
    - email_content (ProccesedMailMessage): The email content to respond to.
    - settings (AccountSettings): User settings for personalization.
    - stream (bool): If True, returns a streaming generator.

    Returns:
    - str or generator: A concise draft email or a streaming generator if `stream=True`.
    """
    # Define the message to send to the model
    messages = [
        {
            "role": "system",
            "content": f"You are an assistant helping the user {settings.user_for_mail} write email responses. "
            f"Generate a concise draft reply that aligns with Felix's writing style. "
            f"Be professional and polite, but succinct. Leave out any text before sucht as 'Here's a concise draft response in Felix's writing style:' or any possible subjects. Only generate the response content, nothing else.",
        },
        {
            "role": "user",
            "content": f"Write a draft response to the following email content:\n\n{email_content.Content}",
        },
    ]

    try:
        # Call the chat method with Llama 3.2
        response = chat(model=MODEL, messages=messages, stream=stream)

        if stream:
            return response
        # Extract and return the draft from the response
        return response.message.content.strip()
    except Exception as e:
        return f"An error occurred while generating the draft: {e}"
