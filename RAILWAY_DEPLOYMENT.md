# Railway Deployment Guide for Alzemora Backend

This guide outlines how to deploy the FastAPI backend and its required ML models to [Railway](https.railway.app). The repository is already configured with `railway.toml` and an updated `Dockerfile` to handle the dynamic port allocation required by Railway serverless environments.

## 1. Prerequisites

- A [Railway Account](https://railway.app/).
- A GitHub repository containing this codebase (if you intend to deploy via GitHub integration).
- A MongoDB cluster (e.g., MongoDB Atlas) because Railway's container is ephemeral, and data should be stored externally.

## 2. Setting Up the Database

Since MongoDB in Docker Compose (`mongo_data`) won't transfer its data to the cloud automatically:
1. Create a free cluster on [MongoDB Atlas](https://www.mongodb.com/cloud/atlas).
2. Get your connection string (e.g., `mongodb+srv://<user>:<password>@cluster0...`).
3. Make sure you allow access from anywhere (`0.0.0.0/0`) in Atlas Network Access, as Railway IPs are dynamic.

## 3. Deploying to Railway

1. Go to the **Railway Dashboard** and click **New Project**.
2. Select **Deploy from GitHub repo** and choose your `ALzemora-Grad` repository.
3. Railway will automatically detect the **root directory** and read `railway.toml`.
4. It will begin building the application using `Backend/Dockerfile`.

## 4. Environment Variables Configuration

In your Railway project, click on your Backend service, go to the **Variables** tab, and add the following required variables:

- `PORT`: (Optional) Railway sets this automatically, but defaults to `8000` via our Docker config if omitted.
- `MONGODB_URL`: Your MongoDB connection string (e.g., from MongoDB Atlas).
- `MONGODB_DB_NAME`: The database name (e.g., `Alzemora`).
- `FIREBASE_CREDENTIALS_PATH`: Only if using a custom Service Account JSON.
- `GOOGLE_APPLICATION_CREDENTIALS`: If using Firebase Admin SDK JSON. (Tip: you can encode your JSON as Base64 in a variable, then decode it in `main.py`, or paste the raw JSON text if supported).
- `INSIGHTFACE_CTX_ID`: `-1` (Forces CPU for face recognition since Railway provides CPU instances by default).

## 5. Exposing the Service to the Public
1. In your Railway service settings, go to the **Networking** tab.
2. Click **Generate Domain**.
3. Use the generated `*.up.railway.app` URL in your Frontend application (update `frontend/.env` or `ALZEMORA_API_URL`).

## 6. Important Notes about Railway & AI Models

- **Persistent Storage**: All images, cached faces, and SQLite temp files in `/app/data` will be LOST when the Railway app restarts. To keep registered faces persistent, consider saving face embeddings and images to your MongoDB database or AWS S3 instead of local directories.
- **Memory Requirements**: AI models (insightface, speech recognition, tts) use a significant amount of RAM. Be aware that Railway's free tier has a 500MB memory limit, which might cause Out-Of-Memory (OOM) crashes. If it crashes on build or start, you may need a Hobby/Pro plan with at least 2GB of RAM.
