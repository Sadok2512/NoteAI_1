from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from pydantic.networks import EmailStr
from pymongo import MongoClient
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import requests

# Load environment variables from .env
load_dotenv()

# Initialize router
router = APIRouter()

# ---------------------------
# Configuration
# ---------------------------

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key-for-dev")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI must be set in environment")

try:
    client = MongoClient(MONGO_URI)
    db = client["noteai"]
    users_collection = db["users"]
except Exception as e:
    raise ConnectionError(f"Failed to connect to MongoDB: {str(e)}")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------
# Models
# ---------------------------

class AuthData(BaseModel):
    email: EmailStr
    password: str

class GoogleToken(BaseModel):
    credential: str

# ---------------------------
# Helpers
# ---------------------------

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ---------------------------
# Routes
# ---------------------------

@router.post("/register")
def register_user(data: AuthData):
    existing_user = users_collection.find_one({"email": data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = pwd_context.hash(data.password)
    user = {"email": data.email, "password": hashed_password}
    result = users_collection.insert_one(user)

    token = create_access_token({"sub": data.email})

    return {
        "user_id": str(result.inserted_id),
        "email": data.email,
        "token": token
    }

@router.post("/login")
def login_user(data: AuthData):
    user = users_collection.find_one({"email": data.email})
    if not user or not pwd_context.verify(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": data.email})
    return {
        "user_id": str(user["_id"]),
        "email": data.email,
        "token": token
    }

@router.post("/google")
def google_auth(token: GoogleToken):
    GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"
    response = requests.get(GOOGLE_TOKEN_INFO_URL, params={"id_token": token.credential})
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
