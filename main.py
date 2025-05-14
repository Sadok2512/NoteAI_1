from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import uuid
import datetime
import json
from typing import List, Optional, Dict, Any

# --- Pydantic Schemas (pour la validation et la documentation) ---
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

class NoteMetadataResponse(NoteMetadataBase): # Utilisé par la nouvelle route
    pass

class UploadResponse(BaseModel):
    message: str
    metadata: NoteMetadataBase

class HistoryItemResponse(NoteMetadataBase): # Utilisé par /history
    pass

class AskNoteRequest(BaseModel):
    user_email: str
    stored_as: str
    question: str

class AskNoteResponse(BaseModel):
    answer: str
# --- FIN Pydantic Schemas ---

# Simulation de la partie auth si le module n'est pas trouvé
try:
    from app import auth # Assurez-vous que ce chemin est correct
    USE_AUTH_ROUTER = True
    print("INFO: Module 'app.auth' chargé.")
except ImportError:
    USE_AUTH_ROUTER = False
    print("WARN: Module 'app.auth' non trouvé. Les routes d'authentification ne seront pas montées.")
    from fastapi import APIRouter
    class AuthRouterPlaceholder:
        router = APIRouter()
    auth = AuthRouterPlaceholder()

app = FastAPI(title="NoteAI Backend", version="1.0.6") # Version mise à jour

if USE_AUTH_ROUTER:
    app.include_router(auth.router, prefix="/auth")
else:
    print("INFO: Routeur d'authentification non inclus.")

# CORS Configuration
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

UPLOAD_DIR = Path("uploads_data") # Sur Railway, considérez les volumes persistants.
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Fonctions utilitaires simulées (remplacez par votre module app.utils si disponible)
def save_upload_file(file: UploadFile, destination: Path):
    try:
        with destination.open("wb") as buffer:
            buffer.write(file.file.read())
        print(f"UTIL: Fichier sauvegardé: {destination}")
    except Exception as e:
        print(f"UTIL: Erreur sauvegarde fichier {destination}: {e}")
        raise
def save_metadata_json(data: dict, destination: Path):
    try:
        with destination.open("w") as f:
            json.dump(data, f, indent=4)
        print(f"UTIL: Métadonnées sauvegardées: {destination}")
    except Exception as e:
        print(f"UTIL: Erreur sauvegarde JSON {destination}: {e}")
        raise
def get_file_duration_in_seconds(file_path_str: str) -> float:
    print(f"UTIL (SIM): Durée simulée pour {file_path_str}")
    return 60.0 # Durée simulée

@app.post("/upload-audio", response_model=UploadResponse)
async def upload_audio_endpoint(file: UploadFile = File(...), user_id: str = Form(...)):
    print(f"API /upload-audio: User={user_id}, Fichier={file.filename}")
    user_dir = UPLOAD_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    file_id_uuid = str(uuid.uuid4()) # UUID sans extension
    extension = Path(file.filename).suffix.lower() or ".bin"
    stored_as_filename = f"{file_id_uuid}{extension}" # Nom complet du fichier audio stocké
    file_path = user_dir / stored_as_filename

    try:
        save_upload_file(file, file_path)
        duration = get_file_duration_in_seconds(str(file_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur traitement fichier: {e}")

    metadata = {
        "id": file_id_uuid, # UUID pur
        "filename": file.filename, # Nom original
        "stored_as": stored_as_filename, # Nom avec extension sur le disque
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "duration_sec": duration,
        "transcription": f"Placeholder: Transcription pour {file.filename}", # Placeholder initial
        "summary": f"Placeholder: Résumé pour {file.filename}",       # Placeholder initial
        "tasks": [],
        "source": "Téléversement"
    }
    # Le fichier JSON est nommé d'après l'UUID pur
    metadata_json_path = user_dir / f"{file_id_uuid}.json"
    save_metadata_json(metadata, metadata_json_path)
    print(f"API /upload-audio: Succès pour {stored_as_filename}.")
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
            # Assurer la cohérence et les valeurs par défaut
            data["transcription"] = data.get("transcription", data.get("transcript", "")) # Prioriser 'transcription'
            if "transcript" in data and data["transcription"] != data.get("transcript"):
                 data.pop("transcript", None) # Nettoyer
            data.setdefault("summary", "")
            data.setdefault("tasks", [])
            data.setdefault("source", "Inconnue")
            data.setdefault("duration_sec", data.get("duration_sec", 0))
            base_name = Path(file_json_path).stem # Ceci est l'UUID
            data.setdefault("id", base_name)
            # Assurer que 'stored_as' est correct (uuid.extension)
            if 'stored_as' not in data or Path(data['stored_as']).stem != base_name:
                original_filename_for_ext = data.get('filename', f"{base_name}.bin")
                ext = Path(original_filename_for_ext).suffix.lower() or '.bin'
                data['stored_as'] = f"{base_name}{ext}"
            history.append(data)
        except Exception as e: print(f"API /history: Erreur lecture JSON {file_json_path}: {e}")
    return sorted(history, key=lambda x: x.get("uploaded_at", "1900-01-01T00:00:00Z"), reverse=True)

# ==============================================================================
# ✅ ROUTE API POUR OBTENIR LES DÉTAILS D'UNE NOTE SPÉCIFIQUE ✅
# ==============================================================================
@app.get("/get-note-details-by-stored-as/{user_id}/{stored_as_name}", response_model=NoteMetadataResponse)
async def get_specific_note_metadata_endpoint(user_id: str, stored_as_name: str):
    user_dir = UPLOAD_DIR / user_id
    # stored_as_name est le nom complet du fichier audio (ex: "uuid.webm")
    # Le fichier JSON correspondant aura le même nom de base mais avec .json
    base_name_of_audio = Path(stored_as_name).stem # Donne l'UUID (nom sans extension)
    metadata_file_path = user_dir / f"{base_name_of_audio}.json"

    print(f"API /get-note-details-by-stored-as: Recherche pour: {metadata_file_path}")

    if not metadata_file_path.exists():
        print(f"API: Fichier métadonnées NON TROUVÉ pour {user_id}/{stored_as_name} (chemin: {metadata_file_path})")
        raise HTTPException(status_code=404, detail=f"Les détails de la note '{stored_as_name}' n'ont pas été trouvés.")

    try:
        with open(metadata_file_path, "r") as f:
            metadata = json.load(f)
        
        # S'assurer que tous les champs attendus par Pydantic et le frontend sont présents
        # et que 'transcription' est la clé utilisée.
        metadata["transcription"] = metadata.get("transcription", metadata.get("transcript", f"Transcription pour {metadata.get('filename', stored_as_name)} en attente."))
        if "transcript" in metadata and metadata.get("transcription") == f"Transcription pour {metadata.get('filename', stored_as_name)} en attente.":
            # Si 'transcription' est le placeholder mais 'transcript' existe, on prend 'transcript'
             metadata["transcription"] = metadata.get("transcript")
        metadata.pop("transcript", None) # Supprimer l'ancienne clé 'transcript' de la réponse

        metadata.setdefault("summary", f"Résumé pour {metadata.get('filename', stored_as_name)} en attente.")
        metadata.setdefault("tasks", [])
        metadata.setdefault("id", base_name_of_audio) # Assurer que l'ID (UUID) est présent
        metadata.setdefault("filename", metadata.get("filename", stored_as_name)) # Nom d'affichage
        metadata.setdefault("stored_as", stored_as_name) # Nom de fichier stocké
        metadata.setdefault("uploaded_at", metadata.get("uploaded_at", datetime.datetime.now(datetime.timezone.utc).isoformat()))
        metadata.setdefault("duration_sec", metadata.get("duration_sec", 0))
        metadata.setdefault("source", metadata.get("source", "Inconnue"))

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
    summary_text = "Résumé non disponible."
    
    if metadata_file_path.exists():
        try:
            with open(metadata_file_path, "r") as f:
                metadata = json.load(f)
                transcription_text = metadata.get("transcription", transcription_text) # Utilise la clé "transcription"
                summary_text = metadata.get("summary", summary_text)
        except Exception as e: print(f"Erreur lecture métadonnées pour chatbot: {e}")
    
    # TODO: Implémentez votre logique de chatbot ici avec le LLM
    answer = f"Réponse simulée pour '{request.stored_as}'. Question: '{request.question}'. "
    if "résumé" in request.question.lower() or "summary" in request.question.lower():
        answer = f"Voici le résumé (simulé) pour {request.stored_as} : {summary_text}"
    elif "transcription" in request.question.lower():
        answer = f"Voici la transcription (simulée) : {transcription_text}"
    else:
        answer += "Je suis une IA en cours de développement pour répondre à ce type de question."
        
    return AskNoteResponse(answer=answer)

# Vous devez encore implémenter la logique RÉELLE pour les routes /transcribe et /summary
# pour qu'elles mettent à jour les fichiers JSON avec les vraies transcriptions/résumés.
# Actuellement, elles ne font que des simulations.
@app.post("/transcribe/{user_id}/{stored_as_name}")
async def transcribe_note_endpoint(user_id: str, stored_as_name: str):
    user_dir = UPLOAD_DIR / user_id
    base_name = Path(stored_as_name).stem
    metadata_file = user_dir / f"{base_name}.json"
    audio_file_path = user_dir / stored_as_name

    if not metadata_file.exists() or not audio_file_path.exists():
        raise HTTPException(status_code=404, detail="Fichier ou métadonnées non trouvés pour la transcription")
    
    # TODO: Ici, appelez votre service de transcription externe/local
    # exemple: actual_transcription_text = await call_your_transcription_service(audio_file_path)
    actual_transcription_text = f"VRAIE transcription pour {stored_as_name} générée à {datetime.datetime.now().isoformat()}."
    
    with open(metadata_file, "r+") as f:
        metadata = json.load(f)
        metadata["transcription"] = actual_transcription_text
        f.seek(0)
        json.dump(metadata, f, indent=4)
        f.truncate()
    return {"message": "Transcription mise à jour", "transcription": actual_transcription_text}

@app.post("/summary/{user_id}/{stored_as_name}")
async def summarize_note_endpoint(user_id: str, stored_as_name: str):
    user_dir = UPLOAD_DIR / user_id
    base_name = Path(stored_as_name).stem
    metadata_file = user_dir / f"{base_name}.json"

    if not metadata_file.exists():
        raise HTTPException(status_code=404, detail="Fichier de métadonnées non trouvé pour le résumé")
    
    with open(metadata_file, "r+") as f:
        metadata = json.load(f)
        # TODO: Appelez votre service de résumé ici, basé sur metadata.get("transcription")
        actual_summary_text = f"VRAI résumé pour {metadata.get('filename', stored_as_name)} généré à {datetime.datetime.now().isoformat()}."
        metadata["summary"] = actual_summary_text
        f.seek(0)
        json.dump(metadata, f, indent=4)
        f.truncate()
    return {"message": "Résumé mis à jour", "summary": actual_summary_text}


@app.get("/")
async def root_endpoint():
    return {"message": "NoteAI Backend is running! Version 1.0.5"}

# Si vous lancez avec uvicorn localement:
# import uvicorn
# if __name__ == "__main__":
#     uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
