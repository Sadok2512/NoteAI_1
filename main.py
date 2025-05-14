from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import uuid
import datetime
import json
from typing import List, Optional # Ajout pour les types optionnels et listes

# Import auth router
from app import auth # Assurez-vous que ce chemin est correct pour votre structure de projet
# Pour la base de données, si vous l'utilisez pour les métadonnées plus tard:
# from sqlalchemy.orm import Session
# from . import crud, models, schemas, database # Adaptez à votre structure

app = FastAPI()

# Mount authentication routes
app.include_router(auth.router, prefix="/auth")

# CORS Configuration
origins = [
    "http://localhost:8000", # Si votre frontend tourne localement sur ce port
    "http://127.0.0.1:8000",
    "https://noteai-frontend.vercel.app",
    "https://noteai-frontend.netlify.app",
    "https://noteai1-production.up.railway.app", # Votre backend
    "https://noteai2512.netlify.app",           # Votre Netlify actif
    "https://noteai-205095.netlify.app"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# File Upload Setup
UPLOAD_DIR = Path("uploads_data") # Changé pour un nom de dossier plus clair, et relatif au projet.
                                  # Sur Railway, vous devrez peut-être utiliser /tmp/uploads ou configurer un volume persistant.
                                  # Pour la simplicité des tests locaux, un dossier relatif est plus facile.
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Utility imports - Adaptez le chemin si nécessaire
# Assurez-vous que ce fichier utils.py existe et contient les fonctions.
# Pour l'instant, je vais les simuler si elles ne sont pas cruciales pour ce problème.
try:
    from app.utils import save_upload_file, save_metadata_json, get_file_duration_in_seconds
except ImportError:
    print("WARN: app.utils non trouvé, simulation des fonctions utilitaires.")
    def save_upload_file(file: UploadFile, destination: Path):
        try:
            with destination.open("wb") as buffer:
                buffer.write(file.file.read())
        except Exception as e:
            print(f"Erreur sauvegarde fichier: {e}")
            raise
    
    def save_metadata_json(data: dict, destination: Path):
        try:
            with destination.open("w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Erreur sauvegarde JSON: {e}")
            raise

    def get_file_duration_in_seconds(file_path_str: str) -> float:
        # Simulation simple, utilisez une vraie librairie comme librosa ou soundfile en production
        print(f"WARN: Simulation de la durée pour {file_path_str}")
        return 30.5 # Durée simulée
    
# --- Définitions de Schémas Pydantic (important pour la validation et la documentation) ---
from pydantic import BaseModel
from typing import Optional, List

class NoteMetadata(BaseModel):
    id: str
    filename: str
    stored_as: str
    uploaded_at: str # Ou datetime.datetime
    duration_sec: Optional[float] = None
    transcription: Optional[str] = "" # Utiliser 'transcription'
    summary: Optional[str] = ""
    tasks: Optional[List[str]] = [] # Pour la cohérence
    source: Optional[str] = None # Ajouté pour la cohérence avec le frontend

class UploadResponse(BaseModel):
    message: str
    metadata: NoteMetadata

class HistoryItem(NoteMetadata): # Peut être le même que NoteMetadata pour l'historique
    pass

class TranscriptionResponse(BaseModel):
    transcription: str # Utiliser 'transcription'

class SummaryResponse(BaseModel):
    summary: str

# --- FIN Définitions de Schémas Pydantic ---


@app.post("/upload-audio", response_model=UploadResponse)
async def upload_audio(file: UploadFile = File(...), user_id: str = Form(...)):
    user_dir = UPLOAD_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    file_id_uuid = str(uuid.uuid4()) # Garder l'UUID pur
    extension = Path(file.filename).suffix.lower() # Mettre en minuscule pour la cohérence
    
    # stored_as sera maintenant juste l'UUID + extension, pour correspondre à ce que le frontend attend
    stored_as_filename = f"{file_id_uuid}{extension}"
    file_path = user_dir / stored_as_filename

    try:
        save_upload_file(file, file_path)
        duration = get_file_duration_in_seconds(str(file_path))
    except Exception as e:
        print(f"Erreur lors de la sauvegarde ou de l'obtention de la durée: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du traitement du fichier: {e}")

    metadata = {
        "id": file_id_uuid, # UUID pur
        "filename": file.filename,
        "stored_as": stored_as_filename, # Nom du fichier sur le disque (uuid.ext)
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), # UTC est une bonne pratique
        "duration_sec": duration,
        "transcription": "", # Initialiser avec 'transcription'
        "summary": "",
        "tasks": [], # Initialiser comme une liste vide
        "source": "Téléversement" # Source par défaut pour les uploads directs
    }

    metadata_path = user_dir / f"{file_id_uuid}.json" # JSON basé sur l'UUID pur
    try:
        save_metadata_json(metadata, metadata_path)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des métadonnées JSON: {e}")
        # Optionnel: supprimer le fichier audio si les métadonnées ne peuvent être sauvegardées
        # if file_path.exists():
        #     file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la sauvegarde des métadonnées: {e}")

    return {"message": "Upload successful", "metadata": metadata}


@app.get("/history/{user_id}", response_model=List[HistoryItem])
async def get_history(user_id: str):
    user_dir = UPLOAD_DIR / user_id
    if not user_dir.exists():
        return []
    history = []
    for file_json_path in user_dir.glob("*.json"):
        try:
            with open(file_json_path, "r") as f:
                metadata = json.load(f)
                # Assurer la cohérence des champs attendus par le frontend
                metadata.setdefault("transcription", metadata.get("transcript", ""))
                if "transcript" in metadata and "transcription" not in metadata:
                     metadata["transcription"] = metadata.pop("transcript") # Renommer
                metadata.setdefault("summary", "")
                metadata.setdefault("tasks", [])
                metadata.setdefault("source", "Inconnue") # Ajouter une source par défaut si manquante
                history.append(metadata)
        except Exception as e:
            print(f"Erreur lors de la lecture du fichier JSON {file_json_path}: {e}")
            # Optionnel: ignorer ce fichier ou le logger plus en détail
            continue
            
    return sorted(history, key=lambda x: x.get("uploaded_at", ""), reverse=True)


# **** NOUVELLE ROUTE CORRIGÉE ****
@app.get("/get-note-details-by-stored-as/{user_id}/{stored_as_name}", response_model=NoteMetadata)
async def get_specific_note_metadata(user_id: str, stored_as_name: str):
    user_dir = UPLOAD_DIR / user_id
    
    # stored_as_name est le nom complet du fichier, ex: "uuid.webm"
    # le fichier JSON correspondant est "uuid.json"
    base_name = Path(stored_as_name).stem # Enlève l'extension (.webm, .wav, etc.)
    metadata_file_path = user_dir / f"{base_name}.json"

    print(f"API: Tentative de lecture de métadonnées: {metadata_file_path}")

    if not metadata_file_path.exists():
        print(f"API: Fichier de métadonnées non trouvé: {metadata_file_path}")
        raise HTTPException(status_code=404, detail="Détails de la note non trouvés (fichier JSON manquant).")

    try:
        with open(metadata_file_path, "r") as f:
            metadata = json.load(f)
        
        # Assurer la cohérence et ajouter les champs par défaut si manquants
        # Le frontend s'attend à 'transcription', 'summary', 'tasks'
        metadata["transcription"] = metadata.get("transcript", metadata.get("transcription", "")) # Priorise 'transcript' s'il existe
        if "transcript" in metadata and metadata["transcript"] != metadata["transcription"]:
            print(f"INFO: Champ 'transcript' utilisé pour 'transcription' pour {stored_as_name}")

        metadata.setdefault("summary", "")
        metadata.setdefault("tasks", [])
        metadata.setdefault("filename", stored_as_name) # Fallback pour filename si non présent dans JSON
        metadata.setdefault("id", base_name)
        metadata.setdefault("stored_as", stored_as_name)
        metadata.setdefault("uploaded_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
        metadata.setdefault("duration_sec", 0)

        return metadata
    except json.JSONDecodeError:
        print(f"API: Erreur de décodage JSON pour {metadata_file_path}")
        raise HTTPException(status_code=500, detail="Erreur de format des métadonnées.")
    except Exception as e:
        print(f"API: Erreur inattendue lors de la lecture des métadonnées {metadata_file_path}: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur.")


@app.post("/transcribe/{user_id}/{stored_as_name}", response_model=TranscriptionResponse) # stored_as_name au lieu de file_id
async def transcribe(user_id: str, stored_as_name: str):
    user_dir = UPLOAD_DIR / user_id
    base_name = Path(stored_as_name).stem
    metadata_file = user_dir / f"{base_name}.json"

    if not metadata_file.exists():
        raise HTTPException(status_code=404, detail="Fichier de métadonnées non trouvé pour la transcription")
    
    with open(metadata_file, "r+") as f: # Ouvrir en r+ pour lire et écrire
        metadata = json.load(f)
        # TODO: Intégrer ici votre logique de transcription réelle sur le fichier audio
        # audio_file_path = user_dir / stored_as_name
        # actual_transcription = your_transcription_function(audio_file_path)
        actual_transcription = f"Ceci est la VRAIE transcription pour le fichier {metadata.get('filename', stored_as_name)} après appel API."
        
        metadata["transcription"] = actual_transcription # Utiliser 'transcription'
        metadata["transcript"] = actual_transcription # Garder 'transcript' pour rétrocompatibilité si besoin
        
        f.seek(0) # Rembobiner au début du fichier
        json.dump(metadata, f, indent=4)
        f.truncate() # Supprimer le reste du fichier s'il était plus long
        
    return {"transcription": metadata["transcription"]}


@app.post("/summary/{user_id}/{stored_as_name}", response_model=SummaryResponse) # stored_as_name au lieu de file_id
async def summarize(user_id: str, stored_as_name: str):
    user_dir = UPLOAD_DIR / user_id
    base_name = Path(stored_as_name).stem
    metadata_file = user_dir / f"{base_name}.json"

    if not metadata_file.exists():
        raise HTTPException(status_code=404, detail="Fichier de métadonnées non trouvé pour le résumé")
    
    with open(metadata_file, "r+") as f:
        metadata = json.load(f)
        # TODO: Intégrer ici votre logique de résumé réelle
        # actual_summary = your_summary_function(metadata.get("transcription", ""))
        actual_summary = f"Ceci est le VRAI résumé généré pour le fichier {metadata.get('filename', stored_as_name)}."
        
        metadata["summary"] = actual_summary
        
        f.seek(0)
        json.dump(metadata, f, indent=4)
        f.truncate()
        
    return {"summary": metadata["summary"]}


# La route /download doit utiliser stored_as_name si c'est le nom complet avec extension
@app.get("/download/{user_id}/{stored_as_name_with_ext}")
async def download_export(user_id: str, stored_as_name_with_ext: str):
    user_dir = UPLOAD_DIR / user_id
    base_name = Path(stored_as_name_with_ext).stem
    metadata_file = user_dir / f"{base_name}.json"
    
    # Déterminer l'extension demandée pour l'exportation (ex: .txt)
    # Supposons que l'extension est passée dans stored_as_name_with_ext ou qu'on veut un .txt par défaut
    # Pour être plus précis, on pourrait avoir /download/{user_id}/{base_name}/export.{export_ext}
    # Ici, on va supposer que l'extension est dans le nom ou qu'on veut un .txt

    if not metadata_file.exists():
        raise HTTPException(status_code=404, detail="Métadonnées non trouvées pour l'export")
    
    with open(metadata_file, "r") as f:
        metadata = json.load(f)

    # Créer un fichier d'exportation temporaire ou en mémoire
    # Pour cet exemple, nous créons un fichier .txt
    export_filename_display = f"{Path(metadata.get('filename', base_name)).stem}_export.txt"
    export_content = f"Fichier: {metadata.get('filename', base_name)}\n"
    export_content += f"Date: {metadata.get('uploaded_at', 'N/A')}\n"
    export_content += f"Durée: {metadata.get('duration_sec', 'N/A')}s\n\n"
    export_content += f"Transcription:\n{metadata.get('transcription', metadata.get('transcript', 'N/A'))}\n\n"
    export_content += f"Résumé:\n{metadata.get('summary', 'N/A')}\n\n"
    export_content += f"Tâches:\n"
    if metadata.get('tasks'):
        for task in metadata['tasks']:
            export_content += f"- {task}\n"
    else:
        export_content += "Aucune tâche.\n"

    # Sauvegarder le contenu dans un fichier temporaire pour le FileResponse
    temp_export_path = user_dir / f"{base_name}_export_temp.txt"
    with open(temp_export_path, "w", encoding="utf-8") as f_export:
        f_export.write(export_content)
        
    return FileResponse(temp_export_path, filename=export_filename_display, media_type='text/plain')


@app.get("/")
async def root():
    return {"message": "NoteAI Backend is running!"}
