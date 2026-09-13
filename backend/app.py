import os
import uuid
import threading
import traceback
from pathlib import Path

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

import fal_client
import requests


BASE = Path(__file__).resolve().parent
UPLOAD = BASE / "jobs"
UPLOAD.mkdir(exist_ok=True)

app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "https://green-screen-app.onrender.com"
        }
    }
)

jobs = {}
lock = threading.Lock()

PUBLIC_BASE_URL = os.getenv(
    "PUBLIC_BASE_URL",
    "https://fhd-video-screen-mini-app.onrender.com"
)


def hex_to_rgb(color):
    color = color.strip()

    if not color.startswith("#") or len(color) != 7:
        raise ValueError("Invalid color")

    return {
        "r": int(color[1:3], 16),
        "g": int(color[3:5], 16),
        "b": int(color[5:7], 16)
    }


def process(job_id, src, subject, color):
    try:
        with lock:
            jobs[job_id]["status"] = "processing"
            jobs[job_id]["progress"] = 10

        if not os.getenv("FAL_KEY"):
            raise RuntimeError("FAL_KEY is not configured")

        rgb = hex_to_rgb(color)

        # IMPORTANT:
        # Do NOT upload through fal.storage.
        # Give fal.ai a public URL to our Render video.
        video_url = (
            f"{PUBLIC_BASE_URL}/api/jobs/{job_id}/input"
        )

        with lock:
            jobs[job_id]["progress"] = 20

        # Pixelcut AI video background removal
        result = fal_client.subscribe(
            "pixelcut/video-background-removal",
            arguments={
                "video_url": video_url,
                "background": "custom",
                "background_color": rgb,
                "output_format": "mp4_h264"
            },
            with_logs=True
        )

        with lock:
            jobs[job_id]["progress"] = 90

        if not result or "video" not in result:
            raise RuntimeError(
                f"Invalid fal.ai response: {result}"
            )

        output_url = result["video"]["url"]

        # Download processed video from fal.ai
        response = requests.get(
            output_url,
            timeout=600
        )

        response.raise_for_status()

        out = UPLOAD / job_id / "output.mp4"
        out.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(out, "wb") as f:
            f.write(response.content)

        with lock:
            jobs[job_id].update(
                status="done",
                progress=100,
                file=f"/api/jobs/{job_id}/download"
            )

    except Exception as e:
        traceback.print_exc()

        with lock:
            jobs[job_id].update(
                status="error",
                error=str(e)
            )


@app.get("/api/health")
def health():
    return jsonify(ok=True)


@app.post("/api/video-screen")
def create():

    f = request.files.get("video")

    subject = request.form.get(
        "subject",
        "person"
    )

    color = request.form.get(
        "color",
        "#00ff00"
    )

    if not f:
        return jsonify(
            error="video is required"
        ), 400

    if not color.startswith("#") or len(color) != 7:
        return jsonify(
            error="invalid color"
        ), 400

    jid = uuid.uuid4().hex

    d = UPLOAD / jid
    d.mkdir(
        parents=True,
        exist_ok=True
    )

    src = d / "input.mp4"

    f.save(src)

    with lock:
        jobs[jid] = {
            "status": "queued",
            "progress": 0,
            "subject": subject,
            "color": color
        }

    threading.Thread(
        target=process,
        args=(
            jid,
            src,
            subject,
            color
        ),
        daemon=True
    ).start()

    return jsonify(
        job_id=jid
    ), 202


@app.get("/api/video-screen/<jid>")
def status(jid):

    with lock:
        j = jobs.get(jid)

    if not j:
        return jsonify(
            error="job not found"
        ), 404

    return jsonify(j)


# Public input video URL for fal.ai
@app.get("/api/jobs/<jid>/input")
def input_video(jid):

    p = UPLOAD / jid / "input.mp4"

    if not p.exists():
        return jsonify(
            error="input not found"
        ), 404

    return send_file(
        p,
        mimetype="video/mp4",
        conditional=True
    )


@app.get("/api/jobs/<jid>/download")
def download(jid):

    p = UPLOAD / jid / "output.mp4"

    if not p.exists():
        return jsonify(
            error="not ready"
        ), 404

    return send_file(
        p,
        as_attachment=True,
        download_name="fhd-video-screen.mp4",
        mimetype="video/mp4"
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv("PORT", "8080")
        )
    )
