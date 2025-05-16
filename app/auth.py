from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId
import jwt
import os

router = APIRouter()

# Connexion MongoDB
client = MongoClient("mongodb+srv://sadokbenali:CuB9RsvafoZ2IZyj@noteai.odx94om.mongodb.net/?retryWrites=true&w=majority&appName=NoteAI")
db = client["noteai"]
users_collection = db["users"]

# Clé secrète JWT (à sécuriser dans un environnement réel)
SECRET_KEY = os.getenv("JWT_SECRET", "secret123")

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
async def login_user(data: LoginRequest):
    user = users_collection.find_one({"email": data.email, "password": data.password})  # ⚠️ En production, utilisez des mots de passe hashés !

    if not user:
        raise HTTPException(status_code=401, detail="Email ou mot de passe invalide.")

    user_id = str(user["_id"])
    token = jwt.encode({"user_id": user_id}, SECRET_KEY, algorithm="HS256")

    return {
        "token": token,
        "email": user["email"],
        "user_id": user_id
    }
