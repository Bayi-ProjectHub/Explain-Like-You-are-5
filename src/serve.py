from fastapi import FastAPI

app = FastAPI(
    title="Explain Like You're 5",
    description="Backend API for ELY5",
    version="0.1.0",
)

@app.get("/")
async def root():
    return {
        "message": "Welcome to Explain Like You're 5!",
        "status": "running",
    }