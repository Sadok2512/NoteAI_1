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
    stored_as: str # Le nom du fichier stocké (uuid.extension)
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

app = FastAPI(title="NoteAI Backend", version="1.0.8") # Version mise à jour

if USE_AUTH_ROUTER and hasattr(auth, 'router'):
    app.include_router(auth.router, prefix="/auth")
else:
    print("INFO: Routeur d'authentification non inclus (module 'app.auth' ou 'auth.router' manquant).")

# CORS Configuration
origins = [
    "http://localhost:8000", "http://127.0.0.1:8000", "null", # Pour les tests locaux
    "https://noteai-frontend.vercel.app", # Exemple Vercel
    "https://noteai-frontend.netlify.app", # Exemple Netlify
    "https://noteai1-production.up.railway.app", # URL de votre backend (si différent du frontend)
    "https://noteai2512.netlify.app", # Votre frontend Netlify actif
    "https://noteai-205095.netlify.app", # Autre frontend Netlify
    # Ajoutez ici d'autres domaines frontend si nécessaire
]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# File Upload Setup
UPLOAD_DIR = Path("uploads_data") # Pour Railway, considérez les volumes persistants.
                                  # Pour les tests locaux, un dossier relatif est plus simple.
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
print(f"INFO: Dossier d'upload configuré à: {UPLOAD_DIR.resolve()}")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Fonctions utilitaires simulées (si app.utils n'est pas disponible ou configuré)
try:
    from app.utils import save_upload_file, save_metadata_json, get_file_duration_in_seconds
    print("INFO: Fonctions utilitaires de app.utils chargées.")
except ImportError:
    print("WARN: Module 'app.utils' non trouvé, simulation des fonctions utilitaires.")
    def save_upload_file(uploaded_file: UploadFile, destination: Path):
        try:
            with destination.open("wb") as buffer:
                buffer.write(uploaded_file.file.read())
            print(f"SIM_UTIL: Fichier '{uploaded_file.filename}' sauvegardé dans '{destination}'")
        except Exception as e:
            print(f"SIM_UTIL: Erreur sauvegarde fichier '{destination}': {e}")
            raise
    def save_metadata_json(data: dict, destination: Path):
        try:
            with destination.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"SIM_UTIL: Métadonnées sauvegardées dans '{destination}'")
        except Exception as e:
            print(f"SIM_UTIL: Erreur sauvegarde JSON '{destination}': {e}")
            raise
    def get_file_duration_in_seconds(file_path_str: str) -> float:
        print(f"SIM_UTIL: Durée simulée pour '{file_path_str}'")
        # Tenter d'utiliser une librairie si disponible, sinon fallback
        try:
            # Exemple avec pydub (nécessite ffmpeg/ffprobe installé)
            # from pydub import AudioSegment
            # audio = AudioSegment.from_file(file_path_str)
            # return audio.duration_seconds
            # Ou avec soundfile (pour wav principalement)
            # import soundfile as sf
            # data_sf, samplerate_sf = sf.read(file_path_str)
            # return len(data_sf) / samplerate_sf
            return 60.0 # Retourner une valeur par défaut
        except Exception as e_duration:
            print(f"SIM_UTIL: Impossible d'obtenir la durée réelle pour {file_path_str} ({e_duration}), retour de 30.0s")
            return 30.0

@app.post("/upload-audio", response_model=UploadResponse)
async def upload_audio_endpoint(file: UploadFile = File(...), user_id: str = Form(...)):
    print(f"API /upload-audio: Requête pour user_id='{user_id}', filename='{file.filename}'")
    user_dir = UPLOAD_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    file_id_uuid = str(uuid.uuid4()) # UUID pur, utilisé comme nom de base pour le JSON
    extension = Path(file.filename).suffix.lower()
    if not extension:
        extension = ".bin" # Fallback si pas d'extension
        print(f"WARN: Fichier '{file.filename}' sans extension, utilisation de '{extension}'")

    stored_as_filename = f"{file_id_uuid}{extension}" # Nom complet du fichier audio: uuid.extension
    file_path = user_dir / stored_as_filename

    try:
        save_upload_file(file, file_path)
        duration = get_file_duration_in_seconds(str(file_path))
    except Exception as e:
        print(f"API /upload-audio: Erreur sauvegarde/durée pour '{file_path}': {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du traitement du fichier: {e}")

    metadata = {
        "id": file_id_uuid,
        "filename": file.filename, # Nom original
        "stored_as": stored_as_filename, # Nom stocké avec extension
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "duration_sec": duration,
        "transcription": f"Transcription en attente pour {file.filename}.", # Placeholder initial
        "summary": f"Résumé en attente pour {file.filename}.",       # Placeholder initial
        "tasks": [],
        "source": "Téléversement"
    }
    metadata_json_path = user_dir / f"{file_id_uuid}.json" # Fichier JSON nommé avec l'UUID
    save_metadata_json(metadata, metadata_json_path)
    print(f"API /upload-audio: Succès pour '{stored_as_filename}'. Métadonnées: {metadata}")
    return {"message": "Upload successful", "metadata": metadata}

@app.get("/history/{user_id}", response_model=List[HistoryItemResponse])
async def get_history_endpoint(user_id: str):
    print(f"API /history: Requête pour user_id='{user_id}'")
    user_dir = UPLOAD_DIR / user_id
    if not user_dir.exists():
        print(f"API /history: Dossier utilisateur non trouvé: {user_dir}")
        return []
    history = []
    for file_json_path in user_dir.glob("*.json"): # Itérer sur les fichiers JSON
        try:
            with open(file_json_path, "r", encoding="utf-8") as f: data = json.load(f)
            
            # S'assurer que les champs attendus par le frontend sont présents
            data["transcription"] = data.get("transcription", data.get("transcript", ""))
            if "transcript" in data and data.get("transcription") != data.get("transcript"):
                 data.pop("transcript", None) # Nettoyer l'ancienne clé

            for key, default_value in [("summary",""), ("tasks",[]), ("source","Inconnue"), ("duration_sec",0.0)]:
                data.setdefault(key, default_value)
            
            # 'id' doit être l'UUID (nom du fichier JSON sans .json)
            base_name_json = Path(file_json_path).stem
            data.setdefault("id", base_name_json)
            
            # 'stored_as' doit être le nom du fichier audio correspondant (uuid.extension)
            # Si 'stored_as' est manquant ou incorrect, on essaie de le reconstruire.
            if 'stored_as' not in data or not data['stored_as'] or Path(data['stored_as']).stem != base_name_json:
                # Tenter de trouver le fichier audio correspondant avec n'importe quelle extension commune
                audio_file_found = None
                for audio_ext in ['.webm', '.wav', '.mp3', '.m4a', '.ogg', '.aac', '.bin']: # Extensions audio communes
                    potential_audio_file = user_dir / f"{base_name_json}{audio_ext}"
                    if potential_audio_file.exists():
                        audio_file_found = potential_audio_file.name
                        break
                if audio_file_found:
                    data['stored_as'] = audio_file_found
                else:
                    # Fallback si aucun fichier audio correspondant n'est trouvé
                    original_filename_for_ext = data.get('filename', f"{base_name_json}.bin")
                    ext = Path(original_filename_for_ext).suffix.lower() or '.bin'
                    data['stored_as'] = f"{base_name_json}{ext}"
                print(f"API /history: 'stored_as' mis à jour/vérifié pour {file_json_path.name} -> {data['stored_as']}")
            
            # S'assurer que 'filename' est présent
            data.setdefault("filename", data.get("stored_as", "Nom de fichier inconnu"))

            history.append(data)
        except Exception as e:
            print(f"API /history: Erreur lecture ou traitement JSON '{file_json_path}': {e}")
            continue # Ignorer ce fichier et passer au suivant
            
    sorted_history = sorted(history, key=lambda x: x.get("uploaded_at", "1900-01-01T00:00:00Z"), reverse=True)
    print(f"API /history: Retour de {len(sorted_history)} éléments pour {user_id}")
    return sorted_history

# --- ROUTE API POUR LES DÉTAILS D'UNE NOTE SPÉCIFIQUE ---
@app.get("/note-details/{user_id}/{stored_as_name}", response_model=NoteMetadataResponse)
async def get_note_details_endpoint(user_id: str, stored_as_name: str):
    user_dir = UPLOAD_DIR / user_id
    base_name_of_audio = Path(stored_as_name).stem # Ex: '0ae77058-ba9f-417f-920c-6643e6b370b3'
    metadata_file_path = user_dir / f"{base_name_of_audio}.json"

    print(f"API /note-details: Recherche pour: user='{user_id}', stored_as='{stored_as_name}', chemin JSON='{metadata_file_path}'")

    if not metadata_file_path.exists():
        print(f"API /note-details: Fichier métadonnées NON TROUVÉ: {metadata_file_path}")
        raise HTTPException(status_code=404, detail=f"Les détails pour la note '{stored_as_name}' n'ont pas été trouvés.")

    try:
        with open(metadata_file_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        
        # Assurer la cohérence et les valeurs par défaut
        metadata["transcription"] = metadata.get("transcription", metadata.get("transcript", f"Transcription pour {metadata.get('filename', stored_as_name)} est en attente."))
        if "transcript" in metadata and metadata.get("transcription") != metadata.get("transcript"):
             metadata.pop("transcript", None)

        metadata.setdefault("summary", f"Résumé pour {metadata.get('filename', stored_as_name)} est en attente.")
        metadata.setdefault("tasks", [])
        metadata.setdefault("id", metadata.get("id", base_name_of_audio))
        metadata.setdefault("filename", metadata.get("filename", stored_as_name))
        metadata.setdefault("stored_as", stored_as_name) 
        metadata.setdefault("uploaded_at", metadata.get("uploaded_at", datetime.datetime.now(datetime.timezone.utc).isoformat()))
        metadata.setdefault("duration_sec", metadata.get("duration_sec", 0.0))
        metadata.setdefault("source", metadata.get("source", "Inconnue"))

        print(f"API /note-details: Métadonnées trouvées et retournées pour '{stored_as_name}'")
        return NoteMetadataResponse(**metadata) # Valider avec Pydantic avant de retourner
    except json.JSONDecodeError as e:
        print(f"API /note-details: Erreur de décodage JSON pour {metadata_file_path}: {e}")
        raise HTTPException(status_code=500, detail="Erreur de format des métadonnées.")
    except Exception as e:
        print(f"API /note-details: Erreur inattendue pour {metadata_file_path}: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur.")

@app.post("/ask-note", response_model=AskNoteResponse)
async def ask_note_endpoint(request: AskNoteRequest):
    print(f"API /ask-note: Question='{request.question}' pour fichier='{request.stored_as}' user='{request.user_email}'")
    user_dir = UPLOAD_DIR / request.user_email
    base_name = Path(request.stored_as).stem
    metadata_file_path = user_dir / f"{base_name}.json"
    transcription_text = "Transcription indisponible."
    summary_text = "Résumé indisponible."
    
    if metadata_file_path.exists():
        try:
            with open(metadata_file_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                transcription_text = metadata.get("transcription", transcription_text)
                summary_text = metadata.get("summary", summary_text)
        except Exception as e: print(f"Erreur lecture métadonnées pour chatbot: {e}")
    
    # TODO: Implémentez votre VRAIE logique de chatbot ici avec un LLM
    answer = f"Réponse simulée pour '{request.stored_as}'. Votre question : '{request.question}'. "
    if "résumé" in request.question.lower() or "summary" in request.question.lower():
        answer = f"Le résumé (simulé) de '{request.stored_as}' est : {summary_text}"
    elif "transcription" in request.question.lower():
        answer = f"La transcription (simulée) de '{request.stored_as}' est : {transcription_text}"
    else:
        answer += "Je suis un bot en développement pour répondre à ce type de question."
        
    return AskNoteResponse(answer=answer)

# TODO: Mettez à jour les routes /transcribe et /summary pour :
# 1. Utiliser {stored_as_name} comme paramètre de chemin.
# 2. Lire le fichier JSON correspondant (nom_base.json).
# 3. Appeler votre service de transcription/résumé sur le fichier audio (user_id/stored_as_name).
# 4. Mettre à jour le champ "transcription" ou "summary" dans l'objet metadata lu.
# 5. Réécrire le fichier JSON COMPLET avec les métadonnées mises à jour.
# 6. Retourner les métadonnées mises à jour (ou juste la transcription/résumé).

@app.get("/")
async def root_endpoint():
    return {"message": "NoteAI Backend is running! Version 1.0.8"}

# Si vous utilisez uvicorn pour lancer localement (décommentez pour test) :
# import uvicorn
# if __name__ == "__main__":
#     uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
