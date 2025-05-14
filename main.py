from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import uuid
import datetime
import json
from typing import List, Optional, Dict, Any

# --- Pydantic Schemas ---
from pydantic import BaseModel

class NoteMetadataBase(BaseModel):
    id: str
    filename: str
    stored_as: str
    uploaded_at: str
    duration_sec: Optional[float] = None
    transcription: Optional[str] = "" # Frontend s'attend à 'transcription'
    summary: Optional[str] = ""
    tasks: Optional[List[str]] = []
    source: Optional[str] = None

class NoteMetadataResponse(NoteMetadataBase):
    pass

class UploadResponse(BaseModel):
    message: str
    metadata: NoteMetadataBase

class HistoryItemResponse(NoteMetadataBase):
    pass

class AskNoteRequest(BaseModel):
    user_email: str
    stored_as: str
    question: str

class AskNoteResponse(BaseModel):
    answer: str
# --- FIN Pydantic Schemas ---

try:
    from app import auth
    USE_AUTH_ROUTER = True
    print("INFO: Module 'app.auth' chargé.")
except ImportError:
    USE_AUTH_ROUTER = False
    print("WARN: Module 'app.auth' non trouvé. Simulant un routeur vide.")
    from fastapi import APIRouter
    class AuthRouterPlaceholder:
        router = APIRouter()
    auth = AuthRouterPlaceholder()

app = FastAPI(title="NoteAI Backend", version="1.0.4")

if USE_AUTH_ROUTER:
    app.include_router(auth.router, prefix="/auth")

origins = [
    "http://localhost:8000", "http://127.0.0.1:8000", "null",
    "https://noteai-frontend.vercel.app", "https://noteai-frontend.netlify.app",
    "https://noteai1-production.up.railway.app",
    "https://noteai2512.netlify.app", "https://noteai-205095.netlify.app",
]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads_data")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Fonctions utilitaires (simulées si app.utils n'est pas là)
try:
    from app.utils import save_upload_file, save_metadata_json, get_file_duration_in_seconds
except ImportError:
    def save_upload_file(file: UploadFile, destination: Path):
        with destination.open("wb") as buffer: buffer.write(file.file.read())
        print(f"SIM_UTIL: Fichier sauvegardé: {destination}")
    def save_metadata_json(data: dict, destination: Path):
        with destination.open("w") as f: json.dump(data, f, indent=4)
        print(f"SIM_UTIL: Métadonnées sauvegardées: {destination}")
    def get_file_duration_in_seconds(file_path_str: str) -> float:
        print(f"SIM_UTIL: Durée simulée pour {file_path_str}")
        return 45.0

@app.post("/upload-audio", response_model=UploadResponse)
async def upload_audio_endpoint(file: UploadFile = File(...), user_id: str = Form(...)):
    print(f"API /upload-audio: User={user_id}, Fichier={file.filename}")
    user_dir = UPLOAD_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    file_id_uuid = str(uuid.uuid4())
    extension = Path(file.filename).suffix.lower() or ".bin"
    stored_as_filename = f"{file_id_uuid}{extension}"
    file_path = user_dir / stored_as_filename

    try:
        save_upload_file(file, file_path)
        duration = get_file_duration_in_seconds(str(file_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur traitement fichier: {e}")

    metadata = {
        "id": file_id_uuid, "filename": file.filename, "stored_as": stored_as_filename,
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "duration_sec": duration,
        "transcription": f"Transcription placeholder pour {file.filename}", # Valeur initiale
        "summary": f"Résumé placeholder pour {file.filename}", # Valeur initiale
        "tasks": [], "source": "Téléversement"
    }
    metadata_json_path = user_dir / f"{file_id_uuid}.json"
    save_metadata_json(metadata, metadata_json_path)
    return {"message": "Upload successful", "metadata": metadata}

@app.get("/history/{user_id}", response_model=List[HistoryItemResponse])
async def get_history_endpoint(user_id: str):
    print(f"API /history: Requête pour user_id={user_id}")
    user_dir = UPLOAD_DIR / user_id
    if not user_dir.exists(): return []
    history = []
    for file_json_path in user_dir.glob("*.json"):
        try:
            with open(file_json_path, "r") as f: data = json.load(f)
            # S'assurer que les champs clés sont présents pour le frontend
            data["transcription"] = data.get("transcript", data.get("transcription", "")) # Gérer ancien nom
            if "transcript" in data and "transcription" not in data: data["transcription"] = data.pop("transcript")
            data.setdefault("summary", "")
            data.setdefault("tasks", [])
            data.setdefault("source", "Inconnue")
            data.setdefault("duration_sec", 0)
            base_name = Path(file_json_path).stem
            data.setdefault("id", base_name)
            if 'stored_as' not in data or not Path(data['stored_as']).suffix:
                ext = Path(data.get('filename', f"{base_name}.bin")).suffix.lower() or '.bin'
                data['stored_as'] = f"{base_name}{ext}"
            history.append(data)
        except Exception as e: print(f"API /history: Erreur JSON {file_json_path}: {e}")
    return sorted(history, key=lambda x: x.get("uploaded_at", "1900-01-01T00:00:00Z"), reverse=True)

# --- ROUTE API POUR LES DÉTAILS D'UNE NOTE SPÉCIFIQUE ---
@app.get("/get-note-metadata/{user_id}/{stored_as_name}", response_model=NoteMetadataResponse)
async def get_specific_note_metadata_endpoint(user_id: str, stored_as_name: str):
    user_dir = UPLOAD_DIR / user_id
    base_name_of_audio = Path(stored_as_name).stem
    metadata_file_path = user_dir / f"{base_name_of_audio}.json"
    print(f"API /get-note-metadata: Recherche pour: {metadata_file_path}")

    if not metadata_file_path.exists():
        print(f"API: Fichier métadonnées NON TROUVÉ: {metadata_file_path}")
        raise HTTPException(status_code=404, detail=f"Détails pour {stored_as_name} non trouvés.")
    try:
        with open(metadata_file_path, "r") as f: metadata = json.load(f)
        metadata["transcription"] = metadata.get("transcript", metadata.get("transcription", ""))
        if "transcript" in metadata and metadata["transcription"] != metadata["transcript"]:
             metadata.pop("transcript", None)
        for key, default_val in [("summary",""), ("tasks",[]), ("id",base_name_of_audio), 
                                 ("filename",metadata.get("filename", stored_as_name)), # Utiliser le filename du JSON s'il existe
                                 ("stored_as",stored_as_name), 
                                 ("uploaded_at",datetime.datetime.now(datetime.timezone.utc).isoformat()), 
                                 ("duration_sec",0), ("source","Inconnue")]:
            metadata.setdefault(key, default_val)
        print(f"API: Métadonnées trouvées pour {stored_as_name}")
        return metadata
    except Exception as e:
        print(f"API: Erreur lecture métadonnées {metadata_file_path}: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne serveur.")

@app.post("/ask-note", response_model=AskNoteResponse)
async def ask_note_endpoint(request: AskNoteRequest):
    print(f"API /ask-note: Question='{request.question}' pour fichier='{request.stored_as}' user='{request.user_email}'")
    user_dir = UPLOAD_DIR / request.user_email
    base_name = Path(request.stored_as).stem
    metadata_file_path = user_dir / f"{base_name}.json"
    transcription_text = "Transcription non disponible."
    if metadata_file_path.exists():
        try:
            with open(metadata_file_path, "r") as f:
                metadata = json.load(f)
                transcription_text = metadata.get("transcription", transcription_text)
        except Exception as e: print(f"Erreur lecture métadonnées pour chatbot: {e}")
    
    answer = f"Réponse simulée à '{request.question}'. Contexte: {transcription_text[:100]}..."
    if "résumé" in request.question.lower():
        answer = f"Voici un résumé simulé pour {request.stored_as} : C'est une note très intéressante."
    return AskNoteResponse(answer=answer)

@app.get("/")
async def root_endpoint():
    return {"message": "NoteAI Backend is running!"}
