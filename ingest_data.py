import os
import json # Import the json module
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

# --- Qdrant Configuration ---
QDRANT_HOST = "localhost" # Or your Qdrant Cloud URL
QDRANT_PORT = 6333 # Default Qdrant port
QDRANT_COLLECTION_NAME = "banking_kb"
# QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") # Uncomment if using Qdrant Cloud

# --- Embedding Model ---
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)
VECTOR_SIZE = encoder.get_sentence_embedding_dimension() # Get vector dimension from the model

def ingest_data_to_qdrant():
    print(f"Initializing Qdrant client at {QDRANT_HOST}:{QDRANT_PORT}...")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    print(f"Checking collection '{QDRANT_COLLECTION_NAME}'...")
    # Always delete and recreate the collection for fresh ingestion during development
    if client.collection_exists(collection_name=QDRANT_COLLECTION_NAME):
        print(f"Collection '{QDRANT_COLLECTION_NAME}' already exists. Deleting and recreating...")
        client.delete_collection(collection_name=QDRANT_COLLECTION_NAME)
    
    print(f"Creating collection '{QDRANT_COLLECTION_NAME}' with vector size {VECTOR_SIZE} and COSINE distance...")
    client.create_collection(
        collection_name=QDRANT_COLLECTION_NAME,
        vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
    )
    print(f"Collection '{QDRANT_COLLECTION_NAME}' created.")

    # --- Load documents from the external JSON file ---
    BANKING_DOCUMENTS = []
    try:
        with open("banking_data.json", "r", encoding="utf-8") as f:
            BANKING_DOCUMENTS = json.load(f)
        print(f"Loaded {len(BANKING_DOCUMENTS)} documents from banking_data.json.")
    except FileNotFoundError:
        print("Error: 'banking_data.json' not found. Please ensure it's in the same directory as ingest_data.py.")
        return
    except json.JSONDecodeError as e:
        print(f"Error parsing 'banking_data.json': {e}. Please check JSON format.")
        return
    except Exception as e:
        print(f"An unexpected error occurred while loading banking_data.json: {e}")
        return

    points = []
    print(f"Encoding {len(BANKING_DOCUMENTS)} documents and preparing points...")
    for doc in BANKING_DOCUMENTS:
        # Ensure 'text' and 'id' exist for each document
        if "text" in doc and "id" in doc:
            vector = encoder.encode(doc["text"]).tolist()
            points.append(
                models.PointStruct(
                    id=doc["id"],
                    vector=vector,
                    payload={"text": doc["text"], "category": doc.get("category", "general")} # Use .get for category with default
                )
            )
        else:
            print(f"Warning: Skipping document missing 'id' or 'text' key: {doc}")


    if not points:
        print("No valid documents to upload. Please check your banking_data.json.")
        return

    print("Uploading points to Qdrant...")
    operation_info = client.upsert(
        collection_name=QDRANT_COLLECTION_NAME,
        wait=True,
        points=points
    )
    print(f"Data ingestion complete: {operation_info}")

if __name__ == "__main__":
    ingest_data_to_qdrant()
