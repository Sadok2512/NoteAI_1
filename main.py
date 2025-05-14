from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import uuid
import datetime
import json
from typing import List, Optional
from pydantic import BaseModel
import whisper

app = FastAPI(title="NoteAI Backend", version="1.0.9")

# CORS setup
origins = ["*"]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Setup upload directory
UPLOAD_DIR = Path("uploads_data")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Whisper model
model = whisper.load_model("base")

# Pydantic schemas
class NoteMetadataBase(BaseModel):
    id: str
    filename: str
    stored_as: str
    uploaded_at: str
    duration_sec: Optional[float] = None
    transcription: Optional[str] = ""
    summary: Optional[str] = ""
    tasks: Optional[list] = []
    source: Optional[str] = None

class UploadResponse(BaseModel):
    message: str
    metadata: NoteMetadataBase

@app.post("/upload-audio", response_model=UploadResponse)
async def upload_audio(file: UploadFile = File(...), user_id: str = Form(...)):
    user_dir = UPLOAD_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix or ".webm"
    stored_as = f"{file_id}{ext}"
    audio_path = user_dir / stored_as

    with open(audio_path, "wb") as out_file:
        out_file.write(await file.read())

    metadata = {
        "id": file_id,
        "filename": file.filename,
        "stored_as": stored_as,
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "duration_sec": 60.0,
        "transcription": f"Transcription en attente pour {file.filename}",
        "summary": "",
        "tasks": [],
        "source": "Téléversement"
    }

    with open(user_dir / f"{file_id}.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return {"message": "Upload successful", "metadata": metadata}

@app.post("/transcribe/{user_id}/{stored_as}")
async def transcribe_audio(user_id: str, stored_as: str):
    audio_path = UPLOAD_DIR / user_id / stored_as
    json_path = UPLOAD_DIR / user_id / f"{Path(stored_as).stem}.json"

    print(f"[DEBUG] Reçu /transcribe pour: {user_id}/{stored_as}")
    print(f"[DEBUG] Chemin audio: {audio_path}")
    print(f"[DEBUG] Chemin JSON: {json_path}")
    print(f"[DEBUG] audio_path.exists(): {audio_path.exists()}")
    print(f"[DEBUG] json_path.exists(): {json_path.exists()}")

    if not audio_path.exists() or not json_path.exists():
        raise HTTPException(status_code=404, detail="Fichier audio ou métadonnées introuvables.")

    try:
        result = model.transcribe(str(audio_path))
        transcription_text = result["text"]

        with open(json_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        metadata["transcription"] = transcription_text

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)

        print(f"[DEBUG] Transcription terminée pour: {stored_as}")
        return {"message": "Transcription réussie", "transcription": transcription_text}
    except Exception as e:
        print(f"[ERROR] Erreur transcription: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur de transcription: {e}")

@app.get("/")
def root():
    return {"message": "NoteAI backend is running"}
