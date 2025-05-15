from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import datetime, os, requests
from pymongo import MongoClient
import gridfs
from bson import ObjectId
from fastapi.responses import StreamingResponse

OPENROUTER_API_KEY = "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"

app = FastAPI(title="NoteAI Split Processing (no Whisper)")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

try:
    from app import auth
    app.include_router(auth.router, prefix="/auth")
except ImportError:
    pass

client = MongoClient("mongodb+srv://sadokbenali:CuB9RsvafoZ2IZyj@noteai.odx94om.mongodb.net/?retryWrites=true&w=majority&appName=NoteAI")
db = client["noteai"]
fs = gridfs.GridFS(db)
notes_collection = db["notes"]

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
    custom_name: Optional[str] = None
    comment: Optional[str] = None
    source: Optional[str] = "WEB"

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
        return "Non disponible."

@app.post("/upload-audio")
async def upload_audio(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    custom_name: Optional[str] = Form(None),
    comment: Optional[str] = Form(None)
):
    try:
        content = await file.read()
        file_size = len(content)
        file_id_obj = fs.put(content, filename=file.filename, content_type=file.content_type, user_id=user_id)
        file_id_str = str(file_id_obj)

        temp_path = f"/tmp/{file_id_str}.webm"
        with open(temp_path, "wb") as f:
            f.write(content)

        transcription = "[Transcription désactivée pour test]"
        os.remove(temp_path)

        metadata = {
            "_id": file_id_str,
            "user_id": user_id,
            "filename": file.filename,
            "custom_name": custom_name,
            "comment": comment,
            "uploaded_at": datetime.datetime.utcnow().isoformat(),
            "content_type": file.content_type,
            "size_bytes": file_size,
            "transcription": transcription,
            "summary": "À traiter",
            "tasks": [],
            "source": "WEB"
        }

        notes_collection.insert_one(metadata)
        return {"message": "Fichier reçu sans transcription", "metadata": metadata}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process-summary/{file_id}")
def process_summary(file_id: str):
    note = notes_collection.find_one({"_id": file_id})
    if not note:
        raise HTTPException(status_code=404, detail="Note introuvable")
    transcription = note.get("transcription", "")
    if not transcription:
        raise HTTPException(status_code=400, detail="Pas de transcription trouvée.")

    summary = ask_openrouter(transcription, "Fais un résumé clair et concis de cette transcription.")
    tasks_text = ask_openrouter(transcription, "Liste les tâches/actions importantes détectées, sous forme de liste à puces.")
    tasks = [t.strip("- ").strip() for t in tasks_text.split("\n") if t.strip()]

    notes_collection.update_one(
        {"_id": file_id},
        {"$set": {"summary": summary, "tasks": tasks}}
    )

    return {"message": "Résumé et tâches générés.", "summary": summary, "tasks": tasks}

@app.get("/note-details/{file_id}", response_model=NoteMetadataResponse)
def get_note_details(file_id: str):
    note = notes_collection.find_one({"_id": file_id})
    if not note:
        raise HTTPException(status_code=404, detail="Note introuvable")
    return NoteMetadataResponse(**{**note, "id": str(note["_id"])})

@app.get("/history/{user_email}", response_model=List[NoteMetadataResponse])
def get_history(user_email: str):
    notes = notes_collection.find({"user_id": user_email}).sort("uploaded_at", -1)
    return [NoteMetadataResponse(**{**n, "id": str(n["_id"])}) for n in notes]

@app.get("/audio/{file_id}")
def stream_audio(file_id: str):
    try:
        grid_out = fs.get(ObjectId(file_id))
        return StreamingResponse(grid_out, media_type=grid_out.content_type or "audio/webm")
    except:
        raise HTTPException(status_code=404, detail="Fichier audio non trouvé")

@app.get("/")
def root():
    return {"message": "Backend NoteAI sans transcription active (test)"}
