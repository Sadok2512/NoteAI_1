from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from pymongo import MongoClient
from bson import ObjectId
from pydub.utils import mediainfo
import datetime, requests, os, gridfs

from app import auth  # 🔐 auth router

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

app = FastAPI(title="NoteAI Final - Replicate + file.io + Auth")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth")

client = MongoClient("mongodb+srv://sadokbenali:CuB9RsvafoZ2IZyj@noteai.odx94om.mongodb.net/?retryWrites=true&w=majority&appName=NoteAI")
db = client["noteai"]
fs = gridfs.GridFS(db)
notes_collection = db["notes"]

def get_audio_duration_seconds(path: str) -> float:
    try:
        return float(mediainfo(path)["duration"])
    except:
        return 0.0

def upload_temp_file_to_fileio(path: str) -> str:
    try:
        with open(path, "rb") as f:
            res = requests.post("https://file.io", files={"file": f})
        link = res.json().get("link")
        if not link:
            raise Exception("file.io upload failed.")
        return link
    except Exception as e:
        print("Erreur upload file.io:", e)
        return None

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
        audio_url = upload_temp_file_to_fileio(temp_path)
        if not audio_url:
            raise HTTPException(status_code=500, detail="file.io upload failed")

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
            timeout=90
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

@app.get("/")
def root():
    return {"message": "NoteAI backend avec Replicate + Auth + Transcription réelle"}
