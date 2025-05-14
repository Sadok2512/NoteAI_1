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
    id: str
    filename: str
    stored_as: str
    uploaded_at: str
    duration_sec: Optional[float] = None
    transcription: Optional[str] = "" # Doit correspondre à ce que le frontend attend
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
    stored_as: str # Le frontend enverra le nom du fichier stocké (uuid.extension)
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
    class AuthRouterPlaceholder: # Crée un placeholder pour éviter les erreurs si auth.router est appelé
        router = APIRouter()
    auth = AuthRouterPlaceholder()


app = FastAPI(title="NoteAI Backend", version="1.0.3") # Version mise à jour

if USE_AUTH_ROUTER:
    app.include_router(auth.router, prefix="/auth")
else:
    print("INFO: Routeur d'authentification non inclus car le module 'app.auth' est manquant ou factice.")


# CORS Configuration
origins = [
    "http://localhost:8000", "http://127.0.0.1:8000", "null",
    "https://noteai-frontend.vercel.app", "https://noteai-frontend.netlify.app",
    "https://noteai1-production.up.railway.app", # Votre backend
    "https://noteai2512.netlify.app", # Vos frontends Netlify
    "https://noteai-205095.netlify.app",
]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# File Upload Setup
UPLOAD_DIR = Path("uploads_data") # Pour Railway, considérez un volume persistant
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Fonctions utilitaires simulées (si app.utils n'est pas disponible)
try:
    from app.utils import save_upload_file, save_metadata_json, get_file_duration_in_seconds
    print("INFO: Fonctions utilitaires de app.utils chargées.")
except ImportError:
    print("WARN: app.utils non trouvé, simulation des fonctions utilitaires.")
    def save_upload_file(file: UploadFile, destination: Path):
        try:
            with destination.open("wb") as buffer:
                buffer.write(file.file.read())
            print(f"UTILS_SIM: Fichier sauvegardé dans {destination}")
        except Exception as e:
            print(f"UTILS_SIM: Erreur sauvegarde fichier: {e}")
            raise
    def save_metadata_json(data: dict, destination: Path):
        try:
            with destination.open("w") as f:
                json.dump(data, f, indent=4)
            print(f"UTILS_SIM: Métadonnées sauvegardées dans {destination}")
        except Exception as e:
            print(f"UTILS_SIM: Erreur sauvegarde JSON: {e}")
            raise
    def get_file_duration_in_seconds(file_path_str: str) -> float:
        print(f"UTILS_SIM: WARN: Simulation de la durée pour {file_path_str}")
        return 30.0 # Durée simulée en secondes

@app.post("/upload-audio", response_model=UploadResponse)
async def upload_audio_endpoint(file: UploadFile = File(...), user_id: str = Form(...)): # Renommé pour éviter conflit de nom
    print(f"API /upload-audio: Reçu pour user_id={user_id}, filename={file.filename}")
    user_dir = UPLOAD_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    file_id_uuid = str(uuid.uuid4())
    extension = Path(file.filename).suffix.lower()
    if not extension:
        extension = ".bin"
        print(f"WARN: Fichier {file.filename} n'a pas d'extension, utilisation de '.bin'")

    stored_as_filename = f"{file_id_uuid}{extension}"
    file_path = user_dir / stored_as_filename

    try:
        save_upload_file(file, file_path)
        duration = get_file_duration_in_seconds(str(file_path))
    except Exception as e:
        print(f"API /upload-audio: Erreur lors de la sauvegarde ou de l'obtention de la durée: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du traitement du fichier: {e}")

    metadata = {
        "id": file_id_uuid,
        "filename": file.filename,
        "stored_as": stored_as_filename,
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "duration_sec": duration,
        "transcription": f"Transcription initiale pour {file.filename}", # Valeur par défaut
        "summary": f"Résumé initial pour {file.filename}", # Valeur par défaut
        "tasks": [],
        "source": "Téléversement"
    }
    metadata_json_path = user_dir / f"{file_id_uuid}.json"
    save_metadata_json(metadata, metadata_json_path)
    print(f"API /upload-audio: Succès pour {stored_as_filename}. Métadonnées: {metadata}")
    return {"message": "Upload successful", "metadata": metadata}


@app.get("/history/{user_id}", response_model=List[HistoryItemResponse])
async def get_history_endpoint(user_id: str): # Renommé pour éviter conflit de nom
    print(f"API /history: Reçu pour user_id={user_id}")
    user_dir = UPLOAD_DIR / user_id
    if not user_dir.exists():
        print(f"API /history: Dossier utilisateur non trouvé pour {user_id}")
        return []
    history = []
    for file_json_path in user_dir.glob("*.json"):
        try:
            with open(file_json_path, "r") as f: data = json.load(f)
            data["transcription"] = data.get("transcript", data.get("transcription", ""))
            if "transcript" in data and "transcription" not in data : data["transcription"] = data.pop("transcript")
            for key, default in [("summary",""), ("tasks",[]), ("source","Inconnue"), ("duration_sec",0)]: data.setdefault(key, default)
            base_name = Path(file_json_path).stem
            data.setdefault("id", base_name)
            if 'stored_as' not in data or not Path(data['stored_as']).suffix:
                original_filename = data.get('filename', f"{base_name}.bin")
                ext = Path(original_filename).suffix.lower() or '.bin'
                data['stored_as'] = f"{base_name}{ext}"
            history.append(data)
        except Exception as e: print(f"API /history: Erreur lecture JSON {file_json_path}: {e}")
    
    sorted_history = sorted(history, key=lambda x: x.get("uploaded_at", "1970-01-01T00:00:00Z"), reverse=True)
    print(f"API /history: Retour de {len(sorted_history)} éléments pour {user_id}")
    return sorted_history


@app.get("/get-note-details-by-stored-as/{user_id}/{stored_as_name}", response_model=NoteMetadataResponse)
async def get_specific_note_metadata_endpoint(user_id: str, stored_as_name: str): # Renommé
    user_dir = UPLOAD_DIR / user_id
    base_name_of_audio = Path(stored_as_name).stem
    metadata_file_path = user_dir / f"{base_name_of_audio}.json"
    print(f"API Backend (get_specific_note_metadata): Recherche de métadonnées pour: {metadata_file_path}")

    if not metadata_file_path.exists():
        print(f"API Backend: Fichier de métadonnées NON TROUVÉ: {metadata_file_path}")
        raise HTTPException(status_code=404, detail=f"Détails de la note ({stored_as_name}) non trouvés.")

    try:
        with open(metadata_file_path, "r") as f: metadata = json.load(f)
        metadata["transcription"] = metadata.get("transcript", metadata.get("transcription", ""))
        if "transcript" in metadata and metadata["transcription"] != metadata["transcript"]:
             metadata.pop("transcript", None)
        for key, default_val in [("summary",""), ("tasks",[]), ("id",base_name_of_audio), 
                                 ("filename",stored_as_name), ("stored_as",stored_as_name), 
                                 ("uploaded_at",datetime.datetime.now(datetime.timezone.utc).isoformat()), 
                                 ("duration_sec",0), ("source","Inconnue")]:
            metadata.setdefault(key, default_val)
        print(f"API Backend: Métadonnées trouvées pour {stored_as_name}")
        return metadata
    except json.JSONDecodeError:
        print(f"API: Erreur de décodage JSON pour {metadata_file_path}")
        raise HTTPException(status_code=500, detail="Erreur de format des métadonnées.")
    except Exception as e:
        print(f"API: Erreur inattendue lors de la lecture de {metadata_file_path}: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur.")

@app.post("/ask-note", response_model=AskNoteResponse)
async def ask_note_endpoint(request: AskNoteRequest): # Renommé
    print(f"API /ask-note: Question='{request.question}' pour fichier='{request.stored_as}' user='{request.user_email}'")
    # TODO: Logique Chatbot ICI
    # 1. Lire le fichier JSON de métadonnées pour obtenir la transcription
    user_dir = UPLOAD_DIR / request.user_email
    base_name = Path(request.stored_as).stem
    metadata_file_path = user_dir / f"{base_name}.json"
    transcription_text = "Transcription non disponible pour ce fichier."
    if metadata_file_path.exists():
        try:
            with open(metadata_file_path, "r") as f:
                metadata = json.load(f)
                transcription_text = metadata.get("transcription", transcription_text)
        except Exception as e:
            print(f"Erreur lecture métadonnées pour chatbot: {e}")
    
    # 2. Envoyer `transcription_text` et `request.question` à votre LLM
    # response_from_llm = await your_llm_service.ask(context=transcription_text, question=request.question)
    
    # Simulation
    answer = f"Réponse simulée à '{request.question}' concernant '{request.stored_as}'. Contexte: {transcription_text[:100]}..."
    if "résumé" in request.question.lower():
        answer = f"Voici un résumé simulé pour {request.stored_as} : C'est une note très intéressante."
    
    return AskNoteResponse(answer=answer)


# Les autres routes comme /transcribe, /summary, /download doivent aussi être vérifiées pour utiliser stored_as_name
# et mettre à jour/lire 'transcription' (au lieu de 'transcript')

@app.get("/")
async def root_endpoint(): # Renommé
    return {"message": "NoteAI Backend is running!"}

# Si vous utilisez uvicorn pour lancer :
# import uvicorn
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8000) # Ou le port que Railway vous assigne via la variable PORT
