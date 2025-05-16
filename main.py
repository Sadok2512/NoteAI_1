from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from pymongo import MongoClient
from bson import ObjectId
from pydub.utils import mediainfo
import datetime, requests, os, gridfs

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

app = FastAPI(title="NoteAI + Replicate Whisper Final")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

client = MongoClient("mongodb+srv://sadokbenali:CuB9RsvafoZ2IZyj@noteai.odx94om.mongodb.net/?retryWrites=true&w=majority&appName=NoteAI")
db = client["noteai"]
fs = gridfs.GridFS(db)
notes_collection = db["notes"]

def get_audio_duration_seconds(path: str) -> float:
    try:
        return float(mediainfo(path)["duration"])
    except:
        return 0.0

class NoteMetadataResponse(BaseModel):
    id: str
    user_id: str
    filename: str
    uploaded_at: str
    content_type: Optional[str]
    transcription: Optional[str] = ""
    summary: Optional[str] = ""
    tasks: Optional[List[str]] = []
    size_bytes: Optional[int] = None
    custom_name: Optional[str] = None
    comment: Optional[str] = None
    source: Optional[str] = "WEB"
    duration_sec: Optional[float] = 0.0

@app.post("/transcribe-replicate", response_model=NoteMetadataResponse)
async def transcribe_replicate(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    custom_name: Optional[str] = Form(None),
    comment: Optional[str] = Form(None)
):
    try:
        content = await file.read()
        file_size = len(content)
        file_id = fs.put(content, filename=file.filename, content_type=file.content_type)
        file_id_str = str(file_id)

        temp_path = f"/tmp/{file_id_str}.webm"
        with open(temp_path, "wb") as f:
            f.write(content)

        duration_sec = get_audio_duration_seconds(temp_path)

        # ✅ Use public URL instead of base64
        audio_url = f"https://noteai1-production.up.railway.app/audio/{file_id_str}"

        headers = {
            "Authorization": f"Token {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers=headers,
            json={
                "version": "a8f5d465f5f5ad6c50413e4f5c3f73292f7e43e2c7e15c76502a89cbd8b6ec1e",
                "input": {
                    "audio": audio_url
                }
            },
            timeout=60
        )
        response.raise_for_status()
        prediction = response.json()
        transcription = prediction.get("output", "[Transcription non disponible]")

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
            "duration_sec": duration_sec,
            "transcription": transcription,
            "summary": "À traiter",
            "tasks": [],
            "source": "WEB"
        }

        notes_collection.insert_one(metadata)
        return NoteMetadataResponse(id=file_id_str, **metadata)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/audio/{file_id}")
def stream_audio(file_id: str):
    try:
        grid_out = fs.get(ObjectId(file_id))
        return StreamingResponse(grid_out, media_type=grid_out.content_type or "audio/webm")
    except:
        raise HTTPException(status_code=404, detail="Fichier audio non trouvé")

@app.get("/")
def root():
    return {"message": "Backend NoteAI avec transcription Replicate (via URL publique)"}
