from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import datetime, whisper, os, requests
from pymongo import MongoClient
import gridfs
from bson import ObjectId
from fastapi.responses import StreamingResponse

# --- OpenRouter API Key ---
OPENROUTER_API_KEY = "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"

# --- Setup ---
app = FastAPI(title="NoteAI + MongoDB GridFS + Auth + OpenRouter")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- Auth Router ---
try:
    from app import auth
    app.include_router(auth.router, prefix="/auth")
    print("✅ Module auth chargé.")
except ImportError:
    print("⚠️ Module 'auth' non trouvé. Auth désactivée.")

# --- MongoDB ---
MONGO_CONNECTION_STRING = "mongodb+srv://sadokbenali:CuB9RsvafoZ2IZyj@noteai.odx94om.mongodb.net/?retryWrites=true&w=majority&appName=NoteAI"
client = MongoClient(MONGO_CONNECTION_STRING)
db = client["noteai"]
fs = gridfs.GridFS(db)
notes_collection = db["notes"]

# --- Whisper Model ---
model = whisper.load_model("base")

# --- Pydantic Models ---
class NoteMetadataResponse(BaseModel):
    id: str
    user_id: str
    filename: str
    uploaded_at: str
    content_type: Optional[str] = None
    transcription: Optional[str] = ""
    summary: Optional[str] = ""
    tasks: Optional[List[str]] = []
    size_bytes: Optional[int] = None

def ask_openrouter(transcription: str, prompt: str) -> str:
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        body = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "Tu es un assistant médical et organisationnel."},
                {"role": "user", "content": f"{prompt}\n\nTexte :\n{transcription}"}
            ]
        }
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=body, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"⚠️ Erreur OpenRouter : {e}")
        return "Non disponible."

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...), user_id: str = Form(...)):
    try:
        content = await file.read()
        file_size = len(content)
        file_id_obj = fs.put(content, filename=file.filename, content_type=file.content_type, user_id=user_id)
        file_id_str = str(file_id_obj)

        temp_path = f"/tmp/{file_id_str}.webm"
        with open(temp_path, "wb") as f:
            f.write(content)
        result = model.transcribe(temp_path)
        transcription = result["text"]
        os.remove(temp_path)

        summary = ask_openrouter(transcription, "Fais un résumé clair et concis de cette transcription.")
        tasks_text = ask_openrouter(transcription, "Liste les tâches/actions importantes détectées, sous forme de liste à puces.")
        tasks = [t.strip("- ").strip() for t in tasks_text.split("\n") if t.strip()]

        metadata = {
            "_id": file_id_str,
            "user_id": user_id,
            "filename": file.filename,
            "uploaded_at": datetime.datetime.utcnow().isoformat(),
            "content_type": file.content_type,
            "size_bytes": file_size,
            "transcription": transcription,
            "summary": summary,
            "tasks": tasks
        }

        notes_collection.insert_one(metadata)
        return {
            "message": "Fichier téléversé et traité",
            "metadata": {
                "id": file_id_str,
                "user_id": user_id,
                "filename": file.filename,
                "uploaded_at": metadata["uploaded_at"],
                "content_type": file.content_type,
                "size_bytes": file_size,
                "transcription": transcription,
                "summary": summary,
                "tasks": tasks
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history/{user_email}", response_model=List[NoteMetadataResponse])
async def get_user_history(user_email: str):
    notes = notes_collection.find({"user_id": user_email}).sort("uploaded_at", -1)
    return [NoteMetadataResponse(
        id=str(note["_id"]),
        user_id=note["user_id"],
        filename=note["filename"],
        uploaded_at=note["uploaded_at"],
        content_type=note.get("content_type"),
        transcription=note.get("transcription", ""),
        summary=note.get("summary", ""),
        tasks=note.get("tasks", []),
        size_bytes=note.get("size_bytes")
    ) for note in notes]

@app.get("/note-details/{file_id}", response_model=NoteMetadataResponse)
async def get_note_details(file_id: str):
    note = notes_collection.find_one({"_id": file_id})
    if not note:
        raise HTTPException(status_code=404, detail="Note introuvable")
    return NoteMetadataResponse(
        id=file_id,
        user_id=note["user_id"],
        filename=note["filename"],
        uploaded_at=note["uploaded_at"],
        content_type=note.get("content_type"),
        transcription=note.get("transcription", ""),
        summary=note.get("summary", ""),
        tasks=note.get("tasks", []),
        size_bytes=note.get("size_bytes")
    )

@app.get("/audio/{file_id}")
def stream_audio(file_id: str):
    try:
        grid_out = fs.get(ObjectId(file_id))
        return StreamingResponse(grid_out, media_type=grid_out.content_type or "audio/webm")
    except gridfs.errors.NoFile:
        raise HTTPException(status_code=404, detail="Fichier audio non trouvé")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {"message": "NoteAI backend complet avec Auth, Whisper, OpenRouter, MongoDB"}
