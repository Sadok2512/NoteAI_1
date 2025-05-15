from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import datetime, whisper, os, requests
from pymongo import MongoClient
import gridfs
from bson import ObjectId
from fastapi.responses import StreamingResponse

OPENROUTER_API_KEY = "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"

app = FastAPI(title="NoteAI + OpenRouter Summary & Tasks")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

client = MongoClient("mongodb+srv://sadokbenali:CuB9RsvafoZ2IZyj@noteai.odx94om.mongodb.net/?retryWrites=true&w=majority&appName=NoteAI")
db = client["noteai"]
fs = gridfs.GridFS(db)
notes_collection = db["notes"]

model = whisper.load_model("base")

class NoteMetadata(BaseModel):
    id: str
    filename: str
    uploaded_at: str
    transcription: Optional[str] = ""
    summary: Optional[str] = ""
    tasks: Optional[List[str]] = []

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
async def upload_audio(file: UploadFile = File(...)):
    try:
        content = await file.read()
        file_id = fs.put(content, filename=file.filename, content_type=file.content_type)

        temp_path = f"/tmp/{file_id}.webm"
        with open(temp_path, "wb") as f:
            f.write(content)
        result = model.transcribe(temp_path)
        transcription = result["text"]
        os.remove(temp_path)

        summary = ask_openrouter(transcription, "Fais un résumé clair et concis de cette transcription.")
        tasks_text = ask_openrouter(transcription, "Liste les tâches/actions importantes détectées, sous forme de liste à puces.")

        tasks = [t.strip("- ").strip() for t in tasks_text.split("\n") if t.strip()]

        metadata = {
            "_id": str(file_id),
            "filename": file.filename,
            "uploaded_at": datetime.datetime.utcnow().isoformat(),
            "transcription": transcription,
            "summary": summary,
            "tasks": tasks
        }
        notes_collection.insert_one(metadata)
        print(f"✅ Upload + transcription + résumé + tâches : {file.filename}")
        return {
            "message": "Fichier traité avec succès",
            "file_id": str(file_id),
            "transcription": transcription,
            "summary": summary,
            "tasks": tasks
        }
    except Exception as e:
        print(f"❌ Erreur traitement complet : {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

@app.get("/history/{user_email}")
async def get_user_history(user_email: str):
    notes = list(notes_collection.find({"filename": {"$exists": True}}))
    return [
        {
            "id": str(note.get("_id", "")),
            "filename": note.get("filename", ""),
            "uploaded_at": note.get("uploaded_at", ""),
            "transcription": note.get("transcription", ""),
            "summary": note.get("summary", ""),
            "tasks": note.get("tasks", [])
        }
        for note in notes
    ]

@app.get("/audio/{file_id}")
def stream_audio(file_id: str):
    try:
        grid_out = fs.get(ObjectId(file_id))
        return StreamingResponse(grid_out, media_type="audio/webm")
    except:
        raise HTTPException(status_code=404, detail="Fichier audio non trouvé")

@app.get("/")
def root():
    return {"message": "NoteAI backend with OpenRouter summary + tasks"}
