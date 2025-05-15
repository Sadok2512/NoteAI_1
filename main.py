from fastapi import FastAPI, UploadFile, File, HTTPException, Form # Assurez-vous que Form est importé
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel # Nécessaire pour response_model
from typing import Optional, List
import datetime, json, whisper
from pymongo import MongoClient
import gridfs
from bson import ObjectId
from fastapi.responses import StreamingResponse

# --- Setup ---
app = FastAPI(title="NoteAI + MongoDB GridFS + Auth")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- Auth Router (si disponible) ---
try:
    from app import auth # Si vous avez un module d'authentification
    app.include_router(auth.router, prefix="/auth")
    print("✅ Module auth chargé.")
except ImportError:
    print("⚠️ Module 'auth' non trouvé. Auth désactivée pour l'instant.") # Ou considérez de le rendre obligatoire

# --- MongoDB Connection ---
# Assurez-vous que la chaîne de connexion est sécurisée (par ex. variables d'environnement)
MONGO_CONNECTION_STRING = "mongodb+srv://sadokbenali:CuB9RsvafoZ2IZyj@noteai.odx94om.mongodb.net/?retryWrites=true&w=majority&appName=NoteAI"
client = MongoClient(MONGO_CONNECTION_STRING)
db = client["noteai"]
fs = gridfs.GridFS(db)
notes_collection = db["notes"] # Collection pour les métadonnées des notes

# --- Whisper Model ---
# model = whisper.load_model("base") # Chargez-le si nécessaire, ou à la demande.

# --- Pydantic Models ---
class NoteMetadataResponse(BaseModel): # Renommé pour clarté, utilisé pour les réponses
    id: str # C'est le file_id de GridFS, aussi _id dans notes_collection
    user_id: str # Ajouté
    filename: str
    uploaded_at: str # Devrait être datetime, mais string si c'est ce que vous stockez/renvoyez
    content_type: Optional[str] = None # Ajouté
    transcription: Optional[str] = ""
    summary: Optional[str] = ""
    tasks: Optional[List[str]] = []
    size_bytes: Optional[int] = None # Ajouté

@app.post("/upload-audio")
async def upload_audio(
    file: UploadFile = File(...),
    user_id: str = Form(...) # (1) RECEVOIR user_id du formulaire
):
    print(f"➡️ /upload-audio REQUÊTE Reçue pour user_id: {user_id}, fichier: {file.filename}")
    try:
        content = await file.read()
        file_size = len(content) # Obtenir la taille du fichier

        # Sauvegarder le fichier dans GridFS
        file_id_obj = fs.put(
            content,
            filename=file.filename,
            content_type=file.content_type,
            user_id=user_id # (Optionnel) Vous pouvez aussi stocker user_id dans les métadonnées de GridFS
        )
        file_id_str = str(file_id_obj)
        print(f"💾 Fichier sauvegardé dans GridFS avec ID: {file_id_str}")

        # Préparer les métadonnées pour la collection 'notes'
        metadata = {
            "_id": file_id_str,  # Utiliser l'ID de GridFS comme _id dans la collection notes
            "user_id": user_id,       # (2) INCLURE user_id
            "filename": file.filename,
            "uploaded_at": datetime.datetime.utcnow().isoformat(),
            "content_type": file.content_type, # Stocker le type de contenu
            "size_bytes": file_size, # Stocker la taille du fichier
            "transcription": "En attente...",
            "summary": "",
            "tasks": []
        }
        print(f"📝 Métadonnées préparées pour MongoDB: {metadata}")

        # Insérer les métadonnées dans la collection 'notes'
        result = notes_collection.insert_one(metadata)
        # 'result.inserted_id' sera le même que 'file_id_str' car nous l'avons défini pour '_id'
        print(f"✅ Métadonnées insérées dans 'notes' avec _id={result.inserted_id} (devrait être {file_id_str})")

        # Renvoyer une réponse détaillée
        return {
            "message": "Fichier téléversé et note créée avec succès",
            "metadata": { # Renvoyer les métadonnées pour que le frontend puisse les afficher
                "id": file_id_str,
                "user_id": user_id,
                "filename": file.filename,
                "uploaded_at": metadata["uploaded_at"],
                "content_type": file.content_type,
                "size_bytes": file_size,
                "transcription": metadata["transcription"]
            }
        }
    except Exception as e:
        print(f"❌ Erreur critique dans /upload-audio pour user_id {user_id}, fichier {file.filename}: {e}")
        import traceback
        traceback.print_exc() # Imprimer la trace complète de l'erreur pour un meilleur débogage
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur lors du téléversement: {str(e)}")

@app.get("/history/{user_email}", response_model=List[NoteMetadataResponse]) # (3) Utiliser le modèle de réponse
async def get_user_history(user_email: str):
    print(f"➡️ /history REQUÊTE Reçue pour user_email: {user_email}")
    try:
        # (4) FILTRER par user_id (qui est user_email ici)
        user_notes_cursor = notes_collection.find({"user_id": user_email}).sort("uploaded_at", -1) # Trier par date, plus récent en premier
        
        history_list = []
        for note in user_notes_cursor:
            history_list.append(NoteMetadataResponse(
                id=str(note["_id"]), # Assurez-vous que c'est une chaîne
                user_id=note["user_id"],
                filename=note["filename"],
                uploaded_at=note["uploaded_at"], # Assurez-vous que le format est correct ou convertissez
                content_type=note.get("content_type"),
                transcription=note.get("transcription", ""),
                summary=note.get("summary", ""),
                tasks=note.get("tasks", []),
                size_bytes=note.get("size_bytes")
            ))
        
        print(f"✅ /history pour {user_email}: {len(history_list)} notes trouvées.")
        return history_list
    except Exception as e:
        print(f"❌ Erreur critique dans /history pour {user_email}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur lors de la récupération de l'historique: {str(e)}")

# ... (vos autres routes, en vous assurant qu'elles utilisent correctement les _id et gèrent les erreurs)

@app.get("/note-details/{file_id}", response_model=NoteMetadataResponse) # Utiliser le modèle de réponse
async def get_note_details(file_id: str):
    print(f"➡️ /note-details REQUÊTE Reçue pour file_id: {file_id}")
    try:
        # file_id est déjà une chaîne (venant de l'URL), il correspond à _id dans notes_collection
        note = notes_collection.find_one({"_id": file_id})
        if not note:
            print(f"⚠️ Note non trouvée pour _id={file_id} dans /note-details")
            raise HTTPException(status_code=404, detail="Note introuvable")
        
        print(f"✅ Note trouvée pour _id={file_id}: {note.get('filename')}")
        return NoteMetadataResponse(
            id=str(note["_id"]),
            user_id=note["user_id"], # Assurez-vous que ce champ existe après les modifs
            filename=note["filename"],
            uploaded_at=note["uploaded_at"],
            content_type=note.get("content_type"),
            transcription=note.get("transcription", ""),
            summary=note.get("summary", ""),
            tasks=note.get("tasks", []),
            size_bytes=note.get("size_bytes")
        )
    except Exception as e:
        print(f"❌ Erreur critique dans /note-details pour file_id {file_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur lors de la récupération des détails de la note: {str(e)}")


@app.get("/audio/{file_id}") # file_id ici est l'_id de GridFS (et de la collection notes)
async def stream_audio(file_id: str):
    print(f"➡️ /audio REQUÊTE Reçue pour file_id: {file_id}")
    try:
        # Convertir file_id (chaîne) en ObjectId pour GridFS
        grid_out = fs.get(ObjectId(file_id))
        print(f"✅ Fichier audio trouvé dans GridFS pour ID: {file_id}, type: {grid_out.content_type}")
        # Le frontend s'attend à 'audio/webm', mais il est mieux de renvoyer le type réel
        return StreamingResponse(grid_out, media_type=grid_out.content_type or "application/octet-stream")
    except gridfs.errors.NoFile:
        print(f"⚠️ Aucun fichier dans GridFS pour ID: {file_id}")
        raise HTTPException(status_code=404, detail="Fichier audio non trouvé dans GridFS")
    except Exception as e:
        print(f"❌ Erreur critique dans /audio pour file_id {file_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur lors du streaming audio: {str(e)}")


# Endpoint racine
@app.get("/")
def root():
    return {"message": "NoteAI + MongoDB GridFS backend is running"}

# Si vous exécutez avec uvicorn directement (pour test local)
# import uvicorn
# if __name__ == "__main__":
# uvicorn.run(app, host="0.0.0.0", port=8000)
