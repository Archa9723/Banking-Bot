import os
import io
import base64
import requests
import google.generativeai as genai

from config import (
    QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION_NAME,
    EMBEDDING_MODEL_NAME, SARVAM_TTS_API_URL
)

from sarvamai import AsyncSarvamAI
from qdrant_client import AsyncQdrantClient, models
from sentence_transformers import SentenceTransformer

sarvam_client = None
qdrant_client_instance = None
embedding_model = None
gemini_model = None

# --- Initialization Functions ---
def initialize_sarvam_client():
    global sarvam_client
    SARVAM_AI_API_KEY = os.getenv("SARVAM_AI_API_KEY")
    if not SARVAM_AI_API_KEY:
        raise RuntimeError("SARVAM_AI_API_KEY environment variable not set. Please set it in your .env file.")
    sarvam_client = AsyncSarvamAI(api_subscription_key=SARVAM_AI_API_KEY)
    print("Sarvam AI client initialized.")
    return sarvam_client

def initialize_qdrant_and_embedding_model():
    global qdrant_client_instance, embedding_model
    qdrant_client_instance = AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    print(f"Embedding model '{EMBEDDING_MODEL_NAME}' loaded.")
    print(f"Qdrant client initialized at {QDRANT_HOST}:{QDRANT_PORT}.")
    return qdrant_client_instance, embedding_model

def initialize_gemini_model():
    global gemini_model
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY environment variable not set. Please set it in your .env file.")
    genai.configure(api_key=GOOGLE_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    print("Google Gemini LLM configured.")
    return gemini_model

# --- Core Service Functions ---

async def perform_asr_and_translate(sarvam_client_instance, audio_file):
    """
    Performs ASR and identifies the source language.
    """
    try:
        audio_bytes = await audio_file.read()
        print(f"Received audio file for ASR-Translate: {audio_file.filename}")

        response = await sarvam_client_instance.speech_to_text.translate(
            file=(audio_file.filename, io.BytesIO(audio_bytes), audio_file.content_type),
            model="saaras:v2.5"
        )
        
        # The 'saaras:v2.5' model returns the transcribed text as 'transcript'.
        # We will use this as both the original text and the text for the LLM.
        original_text = response.transcript
        llm_text = response.transcript
        detected_language = response.language_code
        
        print(f"Original Transcribed Text: {original_text}")
        print(f"Text for LLM: {llm_text}")
        print(f"Detected Language: {detected_language}")

        return original_text, llm_text, detected_language
    except Exception as e:
        print(f"Error during ASR-Translate: {e}")
        raise

async def identify_language(sarvam_client_instance, text_input):
    """Identifies the language of the input text using Sarvam AI."""
    # This is still here for text input, but not used for the new voice workflow
    try:
        lang_id_response = await sarvam_client_instance.text.identify_language(input=text_input)
        detected_input_language_code = lang_id_response.language_code
        print(f"Detected input language: {detected_input_language_code}")
        return detected_input_language_code
    except Exception as e:
        print(f"Error during language identification: {e}. Defaulting to en-IN.")
        return "en-IN"

async def translate_text(sarvam_client_instance, text_input, source_lang, target_lang):
    """Translates text using Sarvam AI."""
    if source_lang == target_lang:
        print(f"No translation needed from {source_lang} to {target_lang}.")
        return text_input
    
    print(f"Translating '{text_input}' from {source_lang} to {target_lang}.")
    try:
        translate_response = await sarvam_client_instance.text.translate(
            input=text_input,
            source_language_code=source_lang,
            target_language_code=target_lang,
            model="mayura:v1"
        )
        translated_text = translate_response.translated_text
        print(f"Translated to {target_lang}: {translated_text}")
        return translated_text
    except Exception as e:
        print(f"Error during translation from {source_lang} to {target_lang}: {e}")
        return text_input # Fallback to original text on error

async def search_qdrant(qdrant_client_instance, embedding_model_instance, query_text, collection_name):
    """Searches Qdrant for relevant documents."""
    relevant_context = []
    try:
        if qdrant_client_instance and embedding_model_instance:
            query_vector = embedding_model_instance.encode(query_text).tolist()
            search_results = await qdrant_client_instance.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=2
            )
            for hit in search_results:
                if hit.payload and 'text' in hit.payload:
                    relevant_context.append(hit.payload['text'])
            print(f"Qdrant search found {len(relevant_context)} relevant documents.")
            if relevant_context:
                print("Retrieved context:", relevant_context)
        else:
            print("Qdrant client or embedding model not initialized.")
    except Exception as e:
        print(f"Error during Qdrant search: {e}")
        relevant_context = ["An error occurred while fetching banking information from Qdrant."]
    return relevant_context

def generate_llm_response(gemini_model_instance, user_question, context):
    """Generates LLM response using Gemini."""
    llm_response_english = "Sorry, I cannot answer that based on the provided information."

    try:
        llm_prompt = f"You are a helpful banking assistant. Answer the user's question based on the following information:\n\n"
        if context:
            llm_prompt += "Information:\n" + "\n".join(context) + "\n\n"
        llm_prompt += f"User's question: {user_question}\n\n"
        llm_prompt += "If the information provided does not contain the answer, state that you cannot answer based on the given information. Be concise and professional."

        print(f"Sending prompt to Gemini: \n{llm_prompt}")
        gemini_response = gemini_model_instance.generate_content(llm_prompt)
        llm_response_english = gemini_response.text
        print(f"Gemini LLM Response (English): {llm_response_english}")
    except Exception as e:
        print(f"Error during Gemini LLM generation: {e}")
        llm_response_english = "I apologize, but I encountered an error while processing your request with the AI. Please try again."
    return llm_response_english

async def synthesize_speech(sarvam_client_instance, text_to_speak, target_lang):
    """Synthesizes speech using Sarvam AI TTS."""
    response_audio_base64 = None
    try:
        ssml_final_response_text = f"<speak>{text_to_speak}<break time='0.5s'/></speak>"
        tts_payload = {
            "inputs": [ssml_final_response_text],
            "target_language_code": target_lang,
            "speaker": "anushka",
            "model": "bulbul:v2",
            "speaker_gender": "Female"
        }
        tts_headers = {
            "api-subscription-key": os.getenv("SARVAM_AI_API_KEY"),
            "Content-Type": "application/json"
        }

        print(f"TTS Request Payload: {tts_payload}")
        tts_api_response = requests.post(SARVAM_TTS_API_URL, json=tts_payload, headers=tts_headers)
        tts_api_response.raise_for_status()
        
        tts_result = tts_api_response.json()
        response_audio_base64 = tts_result.get('audios')[0] if tts_result.get('audios') else None

        if response_audio_base64:
            print("TTS API returned JSON with 'audios' key. Using it directly.")
        else:
            print(f"TTS API returned JSON but 'audios' key was empty or not found. Full JSON: {tts_result}")
            response_audio_base64 = None
    except requests.exceptions.HTTPError as errh:
        print(f"HTTP Error during TTS: {errh}")
        print(f"TTS API Response: {errh.response.text}")
        response_audio_base64 = None
    except requests.exceptions.ConnectionError as errc:
        print(f"Error Connecting to TTS: {errc}")
        response_audio_base64 = None
    except requests.exceptions.Timeout as errt:
        print(f"Timeout Error during TTS: {errt}")
        response_audio_base64 = None
    except requests.exceptions.RequestException as err:
        print(f"Unknown Error during TTS: {err}")
        response_audio_base64 = None
    except Exception as e:
        print(f"General Error during TTS generation: {e}")
        response_audio_base64 = None
    
    return response_audio_base64