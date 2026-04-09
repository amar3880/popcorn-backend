from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import re
import traceback

app = FastAPI(title="PopcornPlay API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def parse_quality(title: str) -> str:
    if not title:
        return "Unknown"
    title = title.upper()
    if "2160P" in title or "4K" in title or "UHD" in title:
        return "4K"
    elif "1080P" in title:
        return "1080p"
    elif "720P" in title:
        return "720p"
    elif "480P" in title:
        return "480p"
    return "Unknown"


def parse_size(title: str) -> str:
    if not title:
        return "Unknown"
    match = re.search(r'(\d+\.?\d*)\s*(GB|MB)', title, re.IGNORECASE)
    if match:
        return f"{match.group(1)} {match.group(2).upper()}"
    return "Unknown"


def create_magnet(info_hash: str, title: str) -> str:
    if not info_hash:
        return ""
    trackers = [
        "udp://tracker.opentrackr.org:1337/announce",
        "udp://open.stealth.si:80/announce",
        "udp://exodus.desync.com:6969/announce",
    ]
    tr = "&".join([f"tr={t}" for t in trackers])
    name = (title.split('\n')[0] if '\n' in title else title)[:50].replace(" ", "+")
    return f"magnet:?xt=urn:btih:{info_hash}&dn={name}&{tr}"


@app.get("/")
async def root():
    return {
        "status": "PopcornPlay API Active",
        "version": "2.0",
        "endpoints": {
            "movie": "/movie/{imdb_id}",
            "tv": "/tv/{imdb_id}/{season}/{episode}",
            "best": "/best/{imdb_id}?quality=1080p"
        }
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/movie/{imdb_id}")
async def get_movie(imdb_id: str):
    if not imdb_id.startswith("tt"):
        imdb_id = f"tt{imdb_id}"
    
    try:
        # ✅ FIXED: Correct Torrentio URL (no config prefix)
        url = f"https://torrentio.strem.fun/stream/movie/{imdb_id}.json"
        
        print(f"📡 Requesting: {url}")
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
                    "Accept": "application/json",
                }
            )
            
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code == 404:
                return {"imdb": imdb_id, "count": 0, "streams": [], "error": "Movie not found"}
            
            if response.status_code != 200:
                print(f"❌ Error response: {response.text[:500]}")
                return {"imdb": imdb_id, "count": 0, "streams": [], "error": "Torrentio unavailable"}
            
            data = response.json()
            streams = data.get("streams", [])
            
            if not streams:
                return {"imdb": imdb_id, "count": 0, "streams": [], "error": "No streams found"}
            
            print(f"✅ Found {len(streams)} streams")
            
            results = []
            for s in streams[:25]:
                try:
                    title = s.get("title", "") or s.get("name", "")
                    info_hash = s.get("infoHash", "")
                    
                    if not info_hash:
                        continue
                    
                    clean_title = title.split("\n")[0] if "\n" in title else title
                    
                    results.append({
                        "title": clean_title[:80],
                        "quality": parse_quality(title),
                        "size": parse_size(title),
                        "hash": info_hash,
                        "magnet": create_magnet(info_hash, clean_title),
                        "seeds": s.get("seeders", 0) or 0,
                    })
                except:
                    continue
            
            quality_order = {"4K": 0, "1080p": 1, "720p": 2, "480p": 3, "Unknown": 99}
            results.sort(key=lambda x: (quality_order.get(x["quality"], 99), -x["seeds"]))
            
            return {"imdb": imdb_id, "count": len(results), "streams": results}
    
    except httpx.TimeoutException:
        return {"imdb": imdb_id, "count": 0, "streams": [], "error": "Timeout"}
    except Exception as e:
        print(f"❌ Error: {e}")
        print(traceback.format_exc())
        return {"imdb": imdb_id, "count": 0, "streams": [], "error": str(e)}


@app.get("/tv/{imdb_id}/{season}/{episode}")
async def get_tv(imdb_id: str, season: int, episode: int):
    if not imdb_id.startswith("tt"):
        imdb_id = f"tt{imdb_id}"
    
    try:
        url = f"https://torrentio.strem.fun/stream/series/{imdb_id}:{season}:{episode}.json"
        
        print(f"📡 TV Request: {url}")
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
                    "Accept": "application/json",
                }
            )
            
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code != 200:
                return {"imdb": imdb_id, "season": season, "episode": episode, "count": 0, "streams": []}
            
            data = response.json()
            streams = data.get("streams", [])
            
            results = []
            for s in streams[:20]:
                try:
                    title = s.get("title", "") or s.get("name", "")
                    info_hash = s.get("infoHash", "")
                    
                    if not info_hash:
                        continue
                    
                    clean_title = title.split("\n")[0] if "\n" in title else title
                    
                    results.append({
                        "title": clean_title[:80],
                        "quality": parse_quality(title),
                        "size": parse_size(title),
                        "hash": info_hash,
                        "magnet": create_magnet(info_hash, clean_title),
                        "seeds": s.get("seeders", 0) or 0,
                    })
                except:
                    continue
            
            quality_order = {"4K": 0, "1080p": 1, "720p": 2, "480p": 3, "Unknown": 99}
            results.sort(key=lambda x: (quality_order.get(x["quality"], 99), -x["seeds"]))
            
            return {"imdb": imdb_id, "season": season, "episode": episode, "count": len(results), "streams": results}
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return {"imdb": imdb_id, "season": season, "episode": episode, "count": 0, "streams": [], "error": str(e)}


@app.get("/best/{imdb_id}")
async def get_best(imdb_id: str, quality: str = "1080p"):
    result = await get_movie(imdb_id)
    streams = result.get("streams", [])
    
    for s in streams:
        if s["quality"] == quality and s["seeds"] > 0:
            return {"stream": s}
    
    for s in streams:
        if s["seeds"] > 0:
            return {"stream": s}
    
    if streams:
        return {"stream": streams[0]}
    
    return {"stream": None, "error": "No streams"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
