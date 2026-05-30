"""Built-in YAML corpus for grammar coverage auto-discovery."""

CORPUS: str = """\
---
name: my-application
version: "1.0.0"
description: A sample application

settings:
  debug: false
  log_level: info
  max_retries: 3
  timeout: 30.0

database:
  host: localhost
  port: 5432
  name: mydb
  credentials:
    username: admin
    password: secret

services:
  - name: web
    image: nginx:latest
    ports:
      - "80:80"
      - "443:443"
    environment:
      NODE_ENV: production
      API_URL: https://api.example.com
    volumes:
      - ./config:/etc/nginx/conf.d

  - name: worker
    image: python:3.11
    command: ["python", "-m", "worker"]
    replicas: 2

tags:
  - production
  - stable

metadata:
  created_at: "2026-01-01"
  owner: devops-team
  labels:
    app: myapp
    tier: backend
"""
