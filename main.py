

# Ajout de la route transcribe avec logs de debug
from fastapi import HTTPException
import whisper

model = whisper.load_model("base")  # Charger le modèle Whisper une seule fois

@app.post("/transcribe/{user_id}/{stored_as}")
async def transcribe_audio(user_id: str, stored_as: str):
    audio_path = UPLOAD_DIR / user_id / stored_as
    json_path = UPLOAD_DIR / user_id / f"{Path(stored_as).stem}.json"

    print(f"[DEBUG] Reçu /transcribe pour: {user_id}/{stored_as}")
    print(f"[DEBUG] Chemin audio: {audio_path}")
    print(f"[DEBUG] Chemin JSON: {json_path}")
    print(f"[DEBUG] audio_path.exists(): {audio_path.exists()}")
    print(f"[DEBUG] json_path.exists(): {json_path.exists()}")

    if not audio_path.exists() or not json_path.exists():
        raise HTTPException(status_code=404, detail="Fichier audio ou métadonnées introuvables.")

    try:
        result = model.transcribe(str(audio_path))
        transcription_text = result["text"]

        with open(json_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        metadata["transcription"] = transcription_text

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)

        print(f"[DEBUG] Transcription terminée pour: {stored_as}")
        return {"message": "Transcription réussie", "transcription": transcription_text}
    except Exception as e:
        print(f"[ERROR] Erreur transcription: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur de transcription: {e}")
