from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import re
from typing import Optional

app = FastAPI(title="PopcornPlay API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TORRENTIO_BASE = "https://torrentio.strem.fun"
TORRENTIO_CONFIG = "sort=qualitysize|qualityfilter=480p,scr,cam"


def parse_quality(title: str) -> str:
    title = title.upper()
    if "2160P" in title or "4K" in title:
        return "4K"
    elif "1080P" in title:
        return "1080p"
    elif "720P" in title:
        return "720p"
    elif "480P" in title:
        return "480p"
    return "Unknown"


def parse_size(title: str) -> str:
    match = re.search(r'(\d+\.?\d*)\s*(GB|MB)', title, re.IGNORECASE)
    if match:
        return f"{match.group(1)} {match.group(2).upper()}"
    return "Unknown"


def create_magnet(info_hash: str, title: str) -> str:
    trackers = [
        "udp://tracker.opentrackr.org:1337/announce",
        "udp://tracker.openbittorrent.com:6969/announce",
        "udp://open.stealth.si:80/announce",
        "udp://exodus.desync.com:6969/announce",
    ]
    tr = "&".join([f"tr={t}" for t in trackers])
    name = title.replace(" ", "+")[:50]
    return f"magnet:?xt=urn:btih:{info_hash}&dn={name}&{tr}"


@app.get("/")
async def root():
    return {"status": "PopcornPlay API Active", "version": "2.0"}


@app.get("/movie/{imdb_id}")
async def get_movie(imdb_id: str):
    if not imdb_id.startswith("tt"):
        imdb_id = f"tt{imdb_id}"
    
    try:
        url = f"{TORRENTIO_BASE}/{TORRENTIO_CONFIG}/stream/movie/{imdb_id}.json"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            
            if response.status_code != 200:
                raise HTTPException(404, "Movie not found")
            
            data = response.json()
            streams = data.get("streams", [])
            
            if not streams:
                raise HTTPException(404, "No streams")
            
            results = []
            for s in streams[:20]:
                title = s.get("title", "")
                info_hash = s.get("infoHash", "")
                if not info_hash:
                    continue
                
                results.append({
                    "title": title.split("\n")[0][:60],
                    "quality": parse_quality(title),
                    "size": parse_size(title),
                    "hash": info_hash,
                    "magnet": create_magnet(info_hash, title),
                    "seeds": s.get("seeders", 0),
                })
            
            quality_order = ["4K", "1080p", "720p", "480p", "Unknown"]
            results.sort(key=lambda x: quality_order.index(x["quality"]) if x["quality"] in quality_order else 99)
            
            return {"imdb": imdb_id, "count": len(results), "streams": results}
    
    except httpx.TimeoutException:
        raise HTTPException(408, "Timeout")
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/tv/{imdb_id}/{season}/{episode}")
async def get_tv(imdb_id: str, season: int, episode: int):
    if not imdb_id.startswith("tt"):
        imdb_id = f"tt{imdb_id}"
    
    try:
        url = f"{TORRENTIO_BASE}/{TORRENTIO_CONFIG}/stream/series/{imdb_id}:{season}:{episode}.json"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            
            if response.status_code != 200:
                raise HTTPException(404, "Episode not found")
            
            data = response.json()
            streams = data.get("streams", [])
            
            if not streams:
                raise HTTPException(404, "No streams")
            
            results = []
            for s in streams[:15]:
                title = s.get("title", "")
                info_hash = s.get("infoHash", "")
                if not info_hash:
                    continue
                
                results.append({
                    "title": title.split("\n")[0][:60],
                    "quality": parse_quality(title),
                    "size": parse_size(title),
                    "hash": info_hash,
                    "magnet": create_magnet(info_hash, title),
                    "seeds": s.get("seeders", 0),
                })
            
            quality_order = ["4K", "1080p", "720p", "480p", "Unknown"]
            results.sort(key=lambda x: quality_order.index(x["quality"]) if x["quality"] in quality_order else 99)
            
            return {"imdb": imdb_id, "season": season, "episode": episode, "count": len(results), "streams": results}
    
    except:
        raise HTTPException(500, "Error")


@app.get("/best/{imdb_id}")
async def get_best(imdb_id: str, quality: str = "1080p"):
    result = await get_movie(imdb_id)
    streams = result.get("streams", [])
    
    for s in streams:
        if s["quality"] == quality:
            return {"stream": s}
    
    if streams:
        return {"stream": streams[0]}
    
    raise HTTPException(404, "No streams")
