from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config import QDRANT_COLLECTION_NAME

from services import (
    initialize_sarvam_client,
    initialize_qdrant_and_embedding_model,
    initialize_gemini_model,
    perform_asr_and_translate,
    identify_language,
    translate_text,
    search_qdrant,
    generate_llm_response,
    synthesize_speech
)

app = FastAPI()

origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://localhost:3000",
    "http://127.0.0.1",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:3000",
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sarvam_client = initialize_sarvam_client()
qdrant_client_instance, embedding_model = initialize_qdrant_and_embedding_model()
gemini_model = initialize_gemini_model()

@app.get("/")
async def read_root():
    return {"message": "Hello, Banking Chatbot Backend!"}

@app.post("/chat")
async def chat_endpoint(text_input: str = Form(None), audio_file: UploadFile = File(None)):
    user_message_text = ""
    processed_text_for_llm = ""
    response_audio_base64 = None
    detected_input_language_code = "en-IN"

    if audio_file:
        try:
            user_message_text, processed_text_for_llm, detected_input_language_code = await perform_asr_and_translate(sarvam_client, audio_file)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to process audio: {e}")
    elif text_input:
        user_message_text = text_input
        print(f"Received text input: {text_input}")
        detected_input_language_code = await identify_language(sarvam_client, user_message_text)
        processed_text_for_llm = await translate_text(
            sarvam_client, user_message_text, detected_input_language_code, "en-IN"
        )
    else:
        raise HTTPException(status_code=400, detail="No text or audio input provided.")

    relevant_context = await search_qdrant(
        qdrant_client_instance, embedding_model, processed_text_for_llm, QDRANT_COLLECTION_NAME
    )

    llm_response_english = generate_llm_response(gemini_model, processed_text_for_llm, relevant_context)

    final_response_text_for_user = await translate_text(
        sarvam_client, llm_response_english, "en-IN", detected_input_language_code
    )
    
    try:
        response_audio_base64 = await synthesize_speech(sarvam_client, final_response_text_for_user, detected_input_language_code)
    except Exception as e:
        print(f"Error generating TTS audio: {e}")
        final_response_text_for_user += "\n(Audio response could not be generated.)"
        response_audio_base64 = None

    return JSONResponse({
        "user_message_text": user_message_text,
        "response_text": final_response_text_for_user,
        "response_audio": response_audio_base64
    })