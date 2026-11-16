"""Web API around the lead classifier, so n8n (or any system) can call it.

Run locally:  uvicorn api:app --port 8000
Interactive docs: http://localhost:8000/docs
"""
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from classifier import DEFAULT_MODEL, classify

app = FastAPI(
    title="Car enquiry classifier",
    description="Sorts a free-text car enquiry into fixed lead fields. "
                "The LLM extracts facts; fixed business rules decide.",
    version="2",
)


class Enquiry(BaseModel):
    message: str = Field(min_length=1, max_length=4000,
                         examples=["Need 5 used Hilux pickups for export to Tanzania, budget AED 400k."])


@app.get("/health")
def health():
    """Quick check that the service is running."""
    return {"status": "ok", "model": DEFAULT_MODEL}


@app.post("/classify")
def classify_enquiry(enquiry: Enquiry):
    """Sort one enquiry. Returns the lead fields plus the raw facts from the LLM."""
    try:
        return classify(enquiry.message)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"LLM not reachable: {e}")
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=502, detail=f"LLM returned unusable output: {e}")
