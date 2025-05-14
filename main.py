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
    id: str # L'UUID pur
    filename: str # Nom original du fichier
    stored_as: str # Nom du fichier sur le serveur (uuid.extension)
    uploaded_at: str
    duration_sec: Optional[float] = None
    transcription: Optional[str] = "" # Champ principal pour la transcription
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
    stored_as: str # Le nom du fichier stocké (uuid.extension)
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

app = FastAPI(title="NoteAI Backend", version="1.0.5") # Version mise à jour

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
    file_id_uuid = str(uuid.uuid4()) # UUID pur
    extension = Path(file.filename).suffix.lower() or ".bin"
    stored_as_filename = f"{file_id_uuid}{extension}" # Nom de fichier stocké: uuid.extension
    file_path = user_dir / stored_as_filename

    try:
        save_upload_file(file, file_path)
        duration = get_file_duration_in_seconds(str(file_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur traitement fichier: {e}")

    metadata = {
        "id": file_id_uuid,
        "filename": file.filename,
        "stored_as": stored_as_filename, # Crucial pour le frontend
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "duration_sec": duration,
        "transcription": f"Placeholder: Transcription pour {file.filename}", # Valeur initiale
        "summary": f"Placeholder: Résumé pour {file.filename}", # Valeur initiale
        "tasks": [], "source": "Téléversement"
    }
    # Le fichier JSON est nommé d'après l'UUID pur (sans l'extension du fichier audio)
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
            # Assurer la cohérence des champs pour le frontend
            data["transcription"] = data.get("transcript", data.get("transcription", ""))
            if "transcript" in data and data["transcription"] != data.get("transcript"): # Nettoyage si 'transcript' était l'ancien champ
                data.pop("transcript", None)
            data.setdefault("summary", "")
            data.setdefault("tasks", [])
            data.setdefault("source", "Inconnue")
            data.setdefault("duration_sec", 0)
            # Assurer que 'id' et 'stored_as' sont bien présents et corrects
            base_name = Path(file_json_path).stem # Ceci est l'UUID
            data.setdefault("id", base_name)
            # 'stored_as' doit être le nom du fichier audio (uuid.extension)
            # Si 'stored_as' n'est pas dans le JSON ou est incorrect, on essaie de le reconstruire
            if 'stored_as' not in data or Path(data['stored_as']).stem != base_name:
                original_filename_for_ext = data.get('filename', f"{base_name}.bin") # Utiliser filename pour l'extension
                ext = Path(original_filename_for_ext).suffix.lower() or '.bin'
                data['stored_as'] = f"{base_name}{ext}"
                print(f"API /history: 'stored_as' reconstruit ou vérifié pour {file_json_path.name} -> {data['stored_as']}")

            history.append(data)
        except Exception as e: print(f"API /history: Erreur lecture JSON {file_json_path}: {e}")
    return sorted(history, key=lambda x: x.get("uploaded_at", "1900-01-01T00:00:00Z"), reverse=True)

# --- ROUTE API POUR LES DÉTAILS D'UNE NOTE SPÉCIFIQUE ---
@app.get("/note-details/{user_id}/{stored_as_name}", response_model=NoteMetadataResponse) # Changement de nom de route
async def get_note_details_endpoint(user_id: str, stored_as_name: str): # Le frontend enverra stored_as (uuid.extension)
    user_dir = UPLOAD_DIR / user_id
    
    # stored_as_name est le nom complet du fichier audio (ex: "uuid.webm")
    # Le fichier JSON correspondant aura le même nom de base mais avec .json
    base_name_of_audio = Path(stored_as_name).stem # Enlève l'extension (.webm, .wav, etc.) -> donne l'UUID
    metadata_file_path = user_dir / f"{base_name_of_audio}.json"

    print(f"API /note-details: Recherche de métadonnées pour: {metadata_file_path}")

    if not metadata_file_path.exists():
        print(f"API: Fichier de métadonnées NON TROUVÉ: {metadata_file_path}")
        raise HTTPException(status_code=404, detail=f"Détails pour la note '{stored_as_name}' non trouvés.")

    try:
        with open(metadata_file_path, "r") as f: metadata = json.load(f)
        
        # Assurer la cohérence des champs pour le frontend
        metadata["transcription"] = metadata.get("transcript", metadata.get("transcription", "Transcription en attente ou non disponible."))
        if "transcript" in metadata and metadata["transcription"] != metadata.get("transcript"):
             metadata.pop("transcript", None)
        metadata.setdefault("summary", "Résumé en attente ou non disponible.")
        metadata.setdefault("tasks", [])
        metadata.setdefault("id", base_name_of_audio)
        metadata.setdefault("filename", metadata.get("filename", stored_as_name))
        metadata.setdefault("stored_as", stored_as_name) # Confirmer stored_as
        metadata.setdefault("uploaded_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
        metadata.setdefault("duration_sec", 0)
        metadata.setdefault("source", "Inconnue")

        print(f"API: Métadonnées trouvées pour {stored_as_name}")
        return metadata
    except json.JSONDecodeError:
        print(f"API: Erreur de décodage JSON pour {metadata_file_path}")
        raise HTTPException(status_code=500, detail="Erreur de format des métadonnées.")
    except Exception as e:
        print(f"API: Erreur inattendue pour {metadata_file_path}: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur.")

@app.post("/ask-note", response_model=AskNoteResponse)
async def ask_note_endpoint(request: AskNoteRequest):
    print(f"API /ask-note: Question='{request.question}' pour fichier='{request.stored_as}' user='{request.user_email}'")
    user_dir = UPLOAD_DIR / request.user_email
    base_name = Path(request.stored_as).stem
    metadata_file_path = user_dir / f"{base_name}.json"
    transcription_text = "Transcription non disponible pour ce fichier."
    summary_text = "Résumé non disponible pour ce fichier."
    
    if metadata_file_path.exists():
        try:
            with open(metadata_file_path, "r") as f:
                metadata = json.load(f)
                transcription_text = metadata.get("transcription", transcription_text)
                summary_text = metadata.get("summary", summary_text)
        except Exception as e: print(f"Erreur lecture métadonnées pour chatbot: {e}")
    
    # TODO: Implémentez votre logique de chatbot ici
    answer = f"Pour le fichier '{request.stored_as}', vous avez demandé : '{request.question}'. "
    if "résumé" in request.question.lower() or "summary" in request.question.lower():
        answer = f"Voici le résumé simulé pour {request.stored_as} : {summary_text}"
    elif "transcription" in request.question.lower():
        answer = f"Voici la transcription simulée : {transcription_text}"
    else:
        answer += "C'est une question intéressante à laquelle je n'ai pas encore de réponse spécifique. (Réponse simulée)"
        
    return AskNoteResponse(answer=answer)

# Les routes /transcribe, /summary, /download doivent aussi utiliser {stored_as_name}
# et mettre à jour/lire 'transcription' (au lieu de 'transcript')

@app.get("/")
async def root_endpoint():
    return {"message": "NoteAI Backend is running!"}

# Ligne pour lancer avec uvicorn si ce fichier est exécuté directement (pour tests locaux)
# import uvicorn
# if __name__ == "__main__":
#     uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
