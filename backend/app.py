import os, uuid, threading, traceback
from pathlib import Path
from flask import Flask, request, jsonify, send_file
import cv2, numpy as np

BASE=Path(__file__).resolve().parent
UPLOAD=BASE/"jobs"; UPLOAD.mkdir(exist_ok=True)
app=Flask(__name__)

jobs={}
lock=threading.Lock()

def process(job_id, src, subject, color):
    try:
        with lock: jobs[job_id]["status"]="processing"
        cap=cv2.VideoCapture(str(src))
        if not cap.isOpened(): raise RuntimeError("Could not open video")
        fps=cap.get(cv2.CAP_PROP_FPS) or 30
        w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if w<=0 or h<=0: raise RuntimeError("Invalid video")
        out=UPLOAD/job_id/"output.mp4"; out.parent.mkdir(exist_ok=True)
        writer=cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w,h))
        # Baseline local segmentation: GrabCut on a center ROI.
        # For production quality, replace segment_frame() with a GPU segmentation model.
        bg=np.array(tuple(int(color[i:i+2],16) for i in (1,3,5)),dtype=np.uint8)
        i=0
        while True:
            ok,frame=cap.read()
            if not ok: break
            mask=segment_frame(frame, subject)
            bgframe=np.empty_like(frame); bgframe[:]=bg[::-1]
            result=np.where(mask[...,None]>0, frame, bgframe)
            writer.write(result.astype(np.uint8)); i+=1
            if i%10==0:
                with lock:
                    jobs[job_id]["progress"]=round(i/max(frames,1)*100,1)
        cap.release(); writer.release()
        with lock:
            jobs[job_id].update(status="done",progress=100,file=f"/api/jobs/{job_id}/download")
    except Exception as e:
        traceback.print_exc()
        with lock: jobs[job_id].update(status="error",error=str(e))

def segment_frame(frame, subject):
    h,w=frame.shape[:2]
    mask=np.zeros((h,w),np.uint8)
    rect=(max(1,int(w*.08)),max(1,int(h*.05)),max(2,int(w*.84)),max(2,int(h*.90)))
    bgd=np.zeros((1,65),np.float64); fgd=np.zeros((1,65),np.float64)
    try:
        cv2.grabCut(frame,mask,rect,bgd,fgd,2,cv2.GC_INIT_WITH_RECT)
        m=np.where((mask==2)|(mask==0),0,255).astype(np.uint8)
        m=cv2.medianBlur(m,5)
        return m
    except Exception:
        # Safe fallback: keep center, replace outer area.
        m=np.zeros((h,w),np.uint8); cv2.ellipse(m,(w//2,h//2),(max(1,int(w*.34)),max(1,int(h*.43))),0,0,360,255,-1)
        return m

@app.get("/api/health")
def health(): return jsonify(ok=True)

@app.post("/api/video-screen")
def create():
    f=request.files.get("video")
    subject=request.form.get("subject","person")
    color=request.form.get("color","#00ff00")
    if not f: return jsonify(error="video is required"),400
    if not color.startswith("#") or len(color)!=7:
        return jsonify(error="invalid color"),400
    jid=uuid.uuid4().hex
    d=UPLOAD/jid; d.mkdir()
    src=d/"input"; f.save(src)
    with lock: jobs[jid]={"status":"queued","progress":0,"subject":subject,"color":color}
    threading.Thread(target=process,args=(jid,src,subject,color),daemon=True).start()
    return jsonify(job_id=jid),202

@app.get("/api/video-screen/<jid>")
def status(jid):
    with lock: j=jobs.get(jid)
    if not j: return jsonify(error="job not found"),404
    return jsonify(j)

@app.get("/api/jobs/<jid>/download")
def download(jid):
    p=UPLOAD/jid/"output.mp4"
    if not p.exists(): return jsonify(error="not ready"),404
    return send_file(p,as_attachment=True,download_name="fhd-video-screen.mp4",mimetype="video/mp4")

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","8080")))
