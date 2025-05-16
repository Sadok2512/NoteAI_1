from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from pymongo import MongoClient
from bson import ObjectId
from pydub.utils import mediainfo
import datetime, requests, os, gridfs, traceback

from app import auth

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

app = FastAPI(title="NoteAI Debug Transcribe Replicate")
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
    except Exception as e:
        print("Erreur durée audio:", e)
        return 0.0

def upload_temp_file_to_fileio(path: str) -> str:
    try:
        with open(path, "rb") as f:
            res = requests.post("https://file.io", files={"file": f})
        link = res.json().get("link")
        print("Lien file.io:", link)
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
        print("▶️ Début transcription replicate")

        if not REPLICATE_API_TOKEN:
            print("❌ Token Replicate manquant.")
            raise HTTPException(status_code=500, detail="Clé API Replicate manquante.")

        content = await file.read()
        file_size = len(content)
        print("📄 Taille fichier:", file_size)

        file_id = fs.put(content, filename=file.filename, content_type=file.content_type)
        file_id_str = str(file_id)

        temp_path = f"/tmp/{file_id_str}.webm"
        with open(temp_path, "wb") as f:
            f.write(content)

        duration_sec = get_audio_duration_seconds(temp_path)

        audio_url = upload_temp_file_to_fileio(temp_path)
        if not audio_url:
            raise HTTPException(status_code=500, detail="Échec de l'upload vers file.io")

        print("🔁 Envoi à Replicate:", audio_url)

        headers = {
            "Authorization": f"Token {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers=headers,
            json={
                "version": "a8f5d465f5f5ad6c50413e4f5c3f73292f7e43e2c7e15c76502a89cbd8b6ec1e",
                "input": {"audio": audio_url}
            },
            timeout=90
        )

        print("📬 Statut Replicate:", response.status_code, response.text)
        response.raise_for_status()
        prediction = response.json()
        transcription = prediction.get("output", "[Transcription non disponible]")

        if os.path.exists(temp_path):
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

    except requests.exceptions.RequestException as re:
        print("❌ Erreur API Replicate:", re)
        raise HTTPException(status_code=500, detail="Erreur lors de l'appel à Replicate API.")
    except Exception as e:
        tb = traceback.format_exc()
        print("❌ Erreur transcribe:\n", tb)
        raise HTTPException(status_code=500, detail="Erreur interne serveur.")

@app.get("/")
def root():
    return {"message": "NoteAI backend debug avec replicate + traceback"}
