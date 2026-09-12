# FHD Video Screen — complete starter

This package contains a Telegram Mini App frontend and a Flask video-processing backend.

Run backend:
1. `cd backend`
2. `pip install -r requirements.txt`
3. `python app.py`

Deploy backend on a server with enough CPU/RAM and FFmpeg/OpenCV support.

Important:
- The backend currently uses OpenCV GrabCut as a CPU baseline. It is NOT production-grade AI segmentation and will not reliably identify arbitrary people/animals/vehicles.
- For high-quality hair/edge tracking and object-specific selection, replace `segment_frame()` with a GPU video segmentation model/service.
- The frontend is ready for that API and polls job progress.
- Existing FHD Wallpapers Bot is untouched by this package.
