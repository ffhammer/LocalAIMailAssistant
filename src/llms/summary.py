from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import OllamaLLM

from ..models import EmailChat
from ..settings import LLMSettings, Settings

llm_settings = LLMSettings()
ollama_model = OllamaLLM(model=llm_settings.summary_model)
gemini_model = ChatGoogleGenerativeAI(model=llm_settings.gemini_model)
parser = StrOutputParser()


def generate_summary_with_llm(email_chat: EmailChat, settings: Settings) -> str:
    model = ollama_model if settings.llm_provider == "ollama" else gemini_model

    prompt = PromptTemplate.from_template(
        "Your task is to generate a concise, single-sentence headline summary that captures the overall context "
        "of the conversation with emphasis on the final message.\n\n"
        "Do NOT start the summary with phrases like 'The last entry'.\n"
        "Return ONLY the summary text, without any introductory or concluding phrases.\n\n"
        "Chat:\n{chat}\n\nSummary:"
    )

    chain = prompt | model | parser
    return chain.invoke({"chat": email_chat.format_chat_for_llm()}).strip(' "')
