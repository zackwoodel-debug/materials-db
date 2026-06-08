#!/bin/bash
ollama pull llama3.1:8b 2>/dev/null || true
ollama serve &
sleep 2
python launch.py
