1. Démarrer le backend (API)
Ouvrez un premier terminal PowerShell :


cd c:\Users\flore\azgbis\backend
.\.venv\Scripts\uvicorn.exe app.main:app --port 8000
Vous devez voir Application startup complete. Laissez ce terminal ouvert.

Vérification rapide (dans un autre terminal ou navigateur) : ouvrez http://localhost:8000/api/health → doit répondre {"status":"ok","version":"0.1.0"}.

2. Démarrer le frontend
Ouvrez un second terminal PowerShell (ne fermez pas le premier) :


cd c:\Users\flore\azgbis\frontend
npm run dev
Vous devez voir une ligne du type Local: http://localhost:5173/.

3. Ouvrir l'outil
Allez sur http://localhost:5173 dans votre navigateur habituel.
