from fastapi import Request

@router.post("/google")
async def google_auth(request: Request):
    try:
        body = await request.json()
        print("📥 BODY REÇU PAR FASTAPI:", body)

        # Vérifie que le champ "credential" est bien là
        if "credential" not in body:
            raise HTTPException(status_code=400, detail="Champ 'credential' manquant")

        # Tu peux maintenant faire comme d'habitude
        credential = body["credential"]

        GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"
        response = requests.get(GOOGLE_TOKEN_INFO_URL, params={"id_token": credential})
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid Google token")

        user_info = response.json()
        email = user_info.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Email not found in Google token")

        user = users_collection.find_one({"email": email})
        if not user:
            new_user = {"email": email, "password": None}
            result = users_collection.insert_one(new_user)
            user_id = str(result.inserted_id)
        else:
            user_id = str(user["_id"])

        jwt_token = create_access_token({"sub": email})

        return {
            "user_id": user_id,
            "email": email,
            "token": jwt_token
        }

    except Exception as e:
        print("❌ ERREUR côté backend:", e)
        raise HTTPException(status_code=422, detail="Erreur lors de l’analyse du token Google")
