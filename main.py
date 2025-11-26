import os
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from openai import AsyncAzureOpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Initialize Azure OpenAI Client
# Ensure environment variables are set
api_key = os.getenv("AZURE_OPENAI_API_KEY")
api_version = os.getenv("AZURE_OPENAI_API_VERSION")
azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

if not all([api_key, api_version, azure_endpoint, deployment_name]):
    print("Warning: Some Azure OpenAI environment variables are missing.")

client = AsyncAzureOpenAI(
    api_key=api_key,
    api_version=api_version,
    azure_endpoint=azure_endpoint
)

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    messages = body.get("messages")
    if not messages:
        raise HTTPException(status_code=400, detail="messages required")

    # Resolve the deployment name based on the requested model
    requested_model = body.get("model")
    
    # Load model mapping from environment variable
    # Format: {"gpt-3.5-turbo": "my-gpt35-deployment", ...}
    model_map_str = os.getenv("AZURE_MODEL_MAP", "{}")
    try:
        model_map = json.loads(model_map_str)
    except json.JSONDecodeError:
        print("Warning: AZURE_MODEL_MAP is not valid JSON. Using empty map.")
        model_map = {}

    # Determine which deployment to use
    if requested_model and requested_model in model_map:
        # Use mapped deployment name
        target_deployment = model_map[requested_model]
    elif requested_model:
        # Use requested model name directly (assume it matches deployment name)
        target_deployment = requested_model
    else:
        # Fallback to default deployment name if configured
        target_deployment = deployment_name
        
    if not target_deployment:
         raise HTTPException(status_code=400, detail="Model not specified and no default deployment configured.")

    # Construct arguments for the Azure OpenAI client
    kwargs = {
        "model": target_deployment,
        "messages": messages,
    }

    # Pass through optional parameters
    optional_params = ["temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty", "stop", "stream"]
    for param in optional_params:
        if param in body:
            kwargs[param] = body[param]

    try:
        if kwargs.get("stream"):
            response = await client.chat.completions.create(**kwargs)
            
            async def generate():
                async for chunk in response:
                    yield f"data: {chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
                
            return StreamingResponse(generate(), media_type="text/event-stream")
        else:
            response = await client.chat.completions.create(**kwargs)
            return JSONResponse(content=json.loads(response.model_dump_json()))
            
    except Exception as e:
        # Log the error for debugging (print to stdout for now)
        print(f"Error calling Azure OpenAI: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "ok"}
