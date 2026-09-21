# Deployment

The repository is prepared for a split deployment:

- **Frontend:** Vercel, using `vercel.json` and the `frontend/` Vite project.
- **Backend:** Render, using `render.yaml` and the FastAPI application.

## Render backend

1. In Render, choose **New > Blueprint** and connect the GitHub repository.
2. Select the repository and apply `render.yaml`.
3. Render creates `fixproof-api` with:
   - Dockerfile: `./Dockerfile`
   - Docker build context: repository root
   - container command from the Dockerfile, using Render's `$PORT`
   - health check: `/healthz`
   - `APP_MODE=demo`
   - `MODEL_MODE=fake`
4. Copy the deployed service URL, for example `https://fixproof-api.onrender.com`.

This Render configuration is intentionally read-only. The live repair workflow launches Docker verifier containers, and a standard Render web service does not provide a host Docker daemon or privileged nested Docker. A production deployment that runs real repairs needs a host with Docker access, such as a VM or dedicated container runner, and should not use this demo configuration.

For a restricted CORS policy, replace `CORS_ORIGINS=*` in Render with the exact Vercel origin after the frontend is deployed, for example `https://fixproof.vercel.app`.

## Vercel frontend

1. In Vercel, choose **Add New > Project** and import the GitHub repository.
2. Keep the repository root as the project root. `vercel.json` runs the build from `frontend/` and publishes `frontend/dist`.
3. Add this environment variable:

   ```text
   VITE_API_URL=https://fixproof-api.onrender.com
   ```

4. Deploy or redeploy the project.

The frontend uses `VITE_API_URL` for JSON requests and the live Server-Sent Events stream. Without it, the frontend assumes the API is on the same origin, which is appropriate when FastAPI serves the built bundle locally but not for the Vercel/Render split.

## Verification

After both services are deployed:

```text
https://<vercel-project>.vercel.app
https://<render-service>.onrender.com/healthz
```

The Render health response should show `app_mode` as `demo`, `mutations_enabled` as `false`, and the frontend should display the read-only notice. `POST /runs` returning HTTP 403 is expected for this deployment mode.
