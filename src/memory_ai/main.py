from fastapi import FastAPI

app = FastAPI(title="Memory AI")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
