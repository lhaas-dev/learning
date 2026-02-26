# API ENDPOINTS – MVP

## Auth
POST /auth/register  
POST /auth/login  

## Study Packs
POST /packs  
GET /packs  
GET /packs/{id}

## Upload
POST /packs/{id}/upload

## Concepts
GET /packs/{id}/concepts  
PATCH /concepts/{id}  
DELETE /concepts/{id}

## Session
POST /sessions/start  
POST /sessions/answer  

## Dashboard
GET /dashboard/overview
