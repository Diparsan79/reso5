from fastapi import FastAPI, HTTPException, Depends, Header, Request, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import sqlite3
import secrets
import datetime
import os

def get_api_key_from_request(request: Request) -> str:
    return request.headers.get("x-api-key", "Unknown")

limiter = Limiter(key_func=get_api_key_from_request)
app = FastAPI(title="NEPALI LETTERBOXD API")
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate Limit Exceeded ;("}
    )

DB_FILE = "watchlist.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            owner TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_key TEXT NOT NULL,
            title TEXT NOT NULL,
            type TEXT NOT NULL,
            genre TEXT NOT NULL,
            watched INTEGER DEFAULT 0,
            rating INTEGER DEFAULT 0,
            review TEXT DEFAULT NULL,
            added_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

class RegisterBody(BaseModel):
    name: str

class WatchListBody(BaseModel):
    title: str
    type: str
    genre: str

class RateBody(BaseModel):
    rating: int
    review: str | None = None

async def verify_api_key(x_api_key: str = Header()):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys WHERE key = ?", (x_api_key,))
    result = cursor.fetchone()
    conn.close()
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid API KEY")
    return x_api_key

def log_activity(action: str, title: str, api_key: str):
    with open("activity.log", "a") as f:
        f.write(f"{datetime.datetime.now()} | {action} | {title} | key: {api_key}\n")

def row_to_dict(row):
    return {
        "id": row[0],
        "owner_key": row[1],
        "title": row[2],
        "type": row[3],
        "genre": row[4],
        "watched": bool(row[5]),
        "rating": row[6],
        "review": row[7],
        "added_at": row[8]
    }

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.post("/register", tags=["Auth"])
async def register(body: RegisterBody):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    key = secrets.token_hex(16)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO api_keys (key, owner) VALUES (?, ?)", (key, body.name))
    conn.commit()
    conn.close()
    return {"api_key": key, "message": "Save this key!!!!!"}

@app.get("/watchlist/search", tags=["Watchlist"], dependencies=[Depends(verify_api_key)])
@limiter.limit("20/minute")
async def search_watchlist(request: Request, q: str, x_api_key: str = Header()):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM watchlist WHERE owner_key = ? AND title LIKE ?",
        (x_api_key, f"%{q}%")
    )
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return {"message": "No results found", "results": []}
    return {"results": [row_to_dict(r) for r in rows]}

@app.get("/watchlist/stats", tags=["Watchlist"], dependencies=[Depends(verify_api_key)])
@limiter.limit("67/minute")
async def get_stats(request: Request, x_api_key: str = Header()):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM watchlist WHERE owner_key = ?", (x_api_key,))
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM watchlist WHERE owner_key = ? AND watched = 1", (x_api_key,))
    watched = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM watchlist WHERE owner_key = ? AND type = 'movie'", (x_api_key,))
    movies = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM watchlist WHERE owner_key = ? AND type = 'series'", (x_api_key,))
    series = cursor.fetchone()[0]
    cursor.execute("SELECT AVG(rating) FROM watchlist WHERE owner_key = ? AND rating > 0", (x_api_key,))
    avg_rating = cursor.fetchone()[0]
    cursor.execute(
        "SELECT genre, COUNT(*) as count FROM watchlist WHERE owner_key = ? GROUP BY genre ORDER BY count DESC LIMIT 1",
        (x_api_key,)
    )
    top_genre = cursor.fetchone()
    conn.close()
    return {
        "total": total,
        "watched": watched,
        "unwatched": total - watched,
        "movies": movies,
        "series": series,
        "average_rating": round(avg_rating, 2) if avg_rating else None,
        "top_genre": top_genre[0] if top_genre else None
    }

@app.get("/watchlist", tags=["Watchlist"], dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def get_watchlist(
    request: Request,
    x_api_key: str = Header(),
    watched: bool | None = None,
    type: str | None = None,
    genre: str | None = None
):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    query = "SELECT * FROM watchlist WHERE owner_key = ?"
    params = [x_api_key]
    if watched is not None:
        query += " AND watched = ?"
        params.append(1 if watched else 0)
    if type is not None:
        query += " AND type = ?"
        params.append(type.lower())
    if genre is not None:
        query += " AND genre = ?"
        params.append(genre.lower())
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

@app.post("/watchlist", tags=["Watchlist"], dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def add_to_watchlist(
    request: Request,
    body: WatchListBody,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header()
):
    if body.type.lower() not in ["movie", "series"]:
        raise HTTPException(status_code=400, detail="Type must be 'movie' or 'series'")
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO watchlist (owner_key, title, type, genre, watched, added_at) VALUES (?, ?, ?, ?, 0, ?)",
        (x_api_key, body.title, body.type.lower(), body.genre.lower(), datetime.datetime.now().isoformat())
    )
    conn.commit()
    new_id = cursor.lastrowid
    cursor.execute("SELECT * FROM watchlist WHERE id = ?", (new_id,))
    new_entry = cursor.fetchone()
    conn.close()
    background_tasks.add_task(log_activity, "ADDED", body.title, x_api_key)
    return row_to_dict(new_entry)

@app.patch("/watchlist/{item_id}/watched", tags=["Watchlist"], dependencies=[Depends(verify_api_key)])
@limiter.limit("20/minute")
async def mark_watched(
    request: Request,
    item_id: int,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header()
):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM watchlist WHERE id = ? AND owner_key = ?", (item_id, x_api_key))
    item = cursor.fetchone()
    if item is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    cursor.execute("UPDATE watchlist SET watched = 1 WHERE id = ?", (item_id,))
    conn.commit()
    cursor.execute("SELECT * FROM watchlist WHERE id = ?", (item_id,))
    updated = cursor.fetchone()
    conn.close()
    background_tasks.add_task(log_activity, "WATCHED", item[2], x_api_key)
    return row_to_dict(updated)

@app.patch("/watchlist/{item_id}/rate", tags=["Watchlist"], dependencies=[Depends(verify_api_key)])
@limiter.limit("67/minute")
async def rate_item(
    request: Request,
    item_id: int,
    body: RateBody,
    x_api_key: str = Header()
):
    if body.rating < 1 or body.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM watchlist WHERE id = ? AND owner_key = ?", (item_id, x_api_key))
    item = cursor.fetchone()
    if item is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    if not item[5]:
        conn.close()
        raise HTTPException(status_code=400, detail="Mark as watched before rating")
    cursor.execute("UPDATE watchlist SET rating = ?, review = ? WHERE id = ?", (body.rating, body.review, item_id))
    conn.commit()
    cursor.execute("SELECT * FROM watchlist WHERE id = ?", (item_id,))
    updated = cursor.fetchone()
    conn.close()
    return row_to_dict(updated)

@app.delete("/watchlist/{item_id}", tags=["Watchlist"], dependencies=[Depends(verify_api_key)])
@limiter.limit("67/minute")
async def delete_item(
    request: Request,
    item_id: int,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header()
):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM watchlist WHERE id = ? AND owner_key = ?", (item_id, x_api_key))
    item = cursor.fetchone()
    if item is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    cursor.execute("DELETE FROM watchlist WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    background_tasks.add_task(log_activity, "DELETED", item[2], x_api_key)
    return {"message": f"'{item[2]}' removed from your watchlist"}

def main():
    import uvicorn
    uvicorn.run("resolution_week5_flameX.main:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    main()