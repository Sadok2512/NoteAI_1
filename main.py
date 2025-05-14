from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import datetime, json, whisper
from pymongo import MongoClient
import gridfs
from bson import ObjectId

# --- Setup ---
app = FastAPI(title="NoteAI + MongoDB GridFS")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- MongoDB Connection ---
client = MongoClient("mongodb+srv://<your_username>:<your_password>@<cluster_url>/")
db = client["noteai"]
fs = gridfs.GridFS(db)
notes_collection = db["notes"]

# --- Whisper Model ---
model = whisper.load_model("base")

# --- Pydantic Models ---
class NoteMetadata(BaseModel):
    id: str
    filename: str
    uploaded_at: str
    transcription: Optional[str] = ""
    summary: Optional[str] = ""
    tasks: Optional[List[str]] = []

# --- Upload Route ---
@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    content = await file.read()
    file_id = fs.put(content, filename=file.filename, content_type=file.content_type)

    metadata = {
        "_id": str(file_id),
        "filename": file.filename,
        "uploaded_at": datetime.datetime.utcnow().isoformat(),
        "transcription": "En attente...",
        "summary": "",
        "tasks": []
    }
    notes_collection.insert_one(metadata)
    return {"message": "Fichier uploadé", "file_id": str(file_id)}

# --- Transcription Route ---
@app.post("/transcribe/{file_id}")
async def transcribe_audio(file_id: str):
    try:
        grid_out = fs.get(ObjectId(file_id))
        audio_data = grid_out.read()
        # Écrire dans un fichier temporaire pour Whisper
        temp_path = f"/tmp/{file_id}.webm"
        with open(temp_path, "wb") as f:
            f.write(audio_data)

        result = model.transcribe(temp_path)
        transcription = result["text"]

        # Mettre à jour la note
        notes_collection.update_one(
            {"_id": file_id},
            {"$set": {"transcription": transcription}}
        )

        return {"message": "Transcription réussie", "transcription": transcription}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Obtenir les métadonnées ---
@app.get("/note-details/{file_id}", response_model=NoteMetadata)
async def get_note_details(file_id: str):
    note = notes_collection.find_one({"_id": file_id})
    if not note:
        raise HTTPException(status_code=404, detail="Note introuvable")
    return {
        "id": note["_id"],
        "filename": note["filename"],
        "uploaded_at": note["uploaded_at"],
        "transcription": note.get("transcription", ""),
        "summary": note.get("summary", ""),
        "tasks": note.get("tasks", [])
    }

@app.get("/")
def root():
    return {"message": "NoteAI + MongoDB GridFS backend is running"}
