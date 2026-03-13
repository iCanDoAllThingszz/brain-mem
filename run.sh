#!/bin/bash
cd /root/.openclaw/workspace/projects/brain-memory
pip install -r requirements.txt -q
uvicorn server.app:app --host 0.0.0.0 --port 8100
