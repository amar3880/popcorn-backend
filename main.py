from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import re
from typing import Optional
import traceback

app = FastAPI(title="PopcornPlay API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TORRENTIO_BASE = "https://torrentio.strem.fun"


def parse_quality(title: str) -> str:
    """Extract quality from title"""
    if not title:
        return "Unknown"
    
    title_upper = title.upper()
    if "2160P" in title_upper or "4K" in title_upper or "UHD" in title_upper:
        return "4K"
    elif "1080P" in title_upper:
        return "1080p"
    elif "720P" in title_upper:
        return "720p"
    elif "480P" in title_upper:
        return "480p"
    else:
        return "Unknown"


def parse_size(title: str) -> str:
    """Extract file size from title"""
    if not title:
        return "Unknown"
    
    try:
        match = re.search(r'💾\s*(\d+\.?\d*)\s*(GB|MB)', title, re.IGNORECASE)
        if match:
            return f"{match.group(1)} {match.group(2).upper()}"
        
        # Try alternate format
        match2 = re.search(r'(\d+\.?\d*)\s*(GB|MB)', title, re.IGNORECASE)
        if match2:
            return f"{match2.group(1)} {match2.group(2).upper()}"
    except:
        pass
    
    return "Unknown"


def create_magnet(info_hash: str, title: str) -> str:
    """Create magnet link from info hash"""
    if not info_hash:
        return ""
    
    trackers = [
        "udp://tracker.opentrackr.org:1337/announce",
        "udp://open.stealth.si:80/announce",
        "udp://tracker.torrent.eu.org:451/announce",
        "udp://exodus.desync.com:6969/announce",
    ]
    
    tr_params = "&".join([f"tr={t}" for t in trackers])
    
    # Clean title for magnet link
    clean_title = title.split('\n')[0] if '\n' in title else title
    clean_title = clean_title[:100]  # Limit length
    encoded_title = clean_title.replace(" ", "+")
    
    return f"magnet:?xt=urn:btih:{info_hash}&dn={encoded_title}&{tr_params}"


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
    return {"status": "healthy", "service": "torrentio-proxy"}


@app.get("/movie/{imdb_id}")
async def get_movie(imdb_id: str):
    """Get movie torrent streams"""
    
    # Validate IMDB ID
    if not imdb_id.startswith("tt"):
        if imdb_id.isdigit():
            imdb_id = f"tt{imdb_id}"
        else:
            raise HTTPException(status_code=400, detail="Invalid IMDB ID format")
    
    try:
        # Build Torrentio URL with config
        config = "sort=qualitysize|qualityfilter=480p,scr,cam"
        url = f"{TORRENTIO_BASE}/{config}/stream/movie/{imdb_id}.json"
        
        print(f"📡 Requesting: {url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            
            print(f"📥 Response status: {response.status_code}")
            
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Movie not found in torrent database")
            
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Torrentio API error")
            
            data = response.json()
            streams = data.get("streams", [])
            
            if not streams:
                raise HTTPException(status_code=404, detail="No torrent streams available")
            
            print(f"✅ Found {len(streams)} raw streams")
            
            # Process streams
            results = []
            for stream in streams[:25]:  # Limit to 25 best
                try:
                    title = stream.get("title", "")
                    info_hash = stream.get("infoHash", "")
                    
                    if not info_hash or not title:
                        continue
                    
                    # Clean title (remove emoji and extra data)
                    clean_title = title.split("\n")[0] if "\n" in title else title
                    
                    quality = parse_quality(title)
                    size = parse_size(title)
                    magnet = create_magnet(info_hash, clean_title)
                    seeds = stream.get("seeders", 0)
                    
                    # Only add if we have minimum data
                    if quality != "Unknown" or seeds > 0:
                        results.append({
                            "title": clean_title[:80],  # Limit title length
                            "quality": quality,
                            "size": size,
                            "hash": info_hash,
                            "magnet": magnet,
                            "seeds": seeds,
                        })
                except Exception as e:
                    print(f"⚠️ Error processing stream: {e}")
                    continue
            
            # Sort by quality
            quality_order = {"4K": 0, "1080p": 1, "720p": 2, "480p": 3, "Unknown": 99}
            results.sort(key=lambda x: (quality_order.get(x["quality"], 99), -x["seeds"]))
            
            print(f"✅ Returning {len(results)} processed streams")
            
            return {
                "imdb": imdb_id,
                "count": len(results),
                "streams": results
            }
    
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timeout - Torrentio is slow")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/tv/{imdb_id}/{season}/{episode}")
async def get_tv(imdb_id: str, season: int, episode: int):
    """Get TV episode torrent streams"""
    
    if not imdb_id.startswith("tt"):
        if imdb_id.isdigit():
            imdb_id = f"tt{imdb_id}"
        else:
            raise HTTPException(status_code=400, detail="Invalid IMDB ID")
    
    try:
        config = "sort=qualitysize|qualityfilter=480p,scr,cam"
        url = f"{TORRENTIO_BASE}/{config}/stream/series/{imdb_id}:{season}:{episode}.json"
        
        print(f"📡 Requesting TV: {url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            
            print(f"📥 Response: {response.status_code}")
            
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Episode not found")
            
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Torrentio error")
            
            data = response.json()
            streams = data.get("streams", [])
            
            if not streams:
                raise HTTPException(status_code=404, detail="No streams for this episode")
            
            results = []
            for stream in streams[:20]:
                try:
                    title = stream.get("title", "")
                    info_hash = stream.get("infoHash", "")
                    
                    if not info_hash:
                        continue
                    
                    clean_title = title.split("\n")[0] if "\n" in title else title
                    
                    results.append({
                        "title": clean_title[:80],
                        "quality": parse_quality(title),
                        "size": parse_size(title),
                        "hash": info_hash,
                        "magnet": create_magnet(info_hash, clean_title),
                        "seeds": stream.get("seeders", 0),
                    })
                except:
                    continue
            
            quality_order = {"4K": 0, "1080p": 1, "720p": 2, "480p": 3, "Unknown": 99}
            results.sort(key=lambda x: (quality_order.get(x["quality"], 99), -x["seeds"]))
            
            return {
                "imdb": imdb_id,
                "season": season,
                "episode": episode,
                "count": len(results),
                "streams": results
            }
    
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Timeout")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/best/{imdb_id}")
async def get_best(imdb_id: str, quality: str = "1080p"):
    """Get best single stream for a quality"""
    
    result = await get_movie(imdb_id)
    streams = result.get("streams", [])
    
    # Find requested quality
    for stream in streams:
        if stream["quality"] == quality and stream["seeds"] > 0:
            return {"stream": stream}
    
    # Fallback to first available with seeds
    for stream in streams:
        if stream["seeds"] > 0:
            return {"stream": stream}
    
    # Last resort: return first
    if streams:
        return {"stream": streams[0]}
    
    raise HTTPException(status_code=404, detail="No streams available")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
