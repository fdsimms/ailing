from fastapi import FastAPI

app = FastAPI(title="ailing")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
