import os

from flask import Flask, request, Response, jsonify
import requests
import json

from opentelemetry.instrumentation.flask import FlaskInstrumentor

app = Flask(__name__)

FlaskInstrumentor().instrument_app(app)

default_resource = "default_resource"

#  format of the resource_mapper is {"deployment name": "openai resource name"}, e.g. {"gpt-4": "azureopenai1"}
resource_mapper = json.loads(os.getenv('RESOURCE_MAPPER'))

#  format of the model_mapper is {"model name": "deployment name"}, e.g. {"gpt-4": "gpt-4"}
model_mapper = json.loads(os.getenv('MODEL_MAPPER'))

# format of the resource_keys is {"openai resource name": "api key"}, e.g. {"azureopenai1": "1234567890"}
resource_keys = json.loads(os.getenv('KEYS_MAPPER'))


@app.route('/<path:path>', methods=['OPTIONS', 'POST'])
def handler(path):
    if request.method == 'OPTIONS':
        return '', 204

    if request.method != 'POST':
        return 'Bad Request', 400

    body_bytes = request.get_data()
    auth = request.headers.get('Authorization')

    if "IloveJXY" not in auth:
        return 'Unauthorized', 401

    deployment = "gpt-4"
    api_version = "2024-02-15-preview"

    if path.startswith("//"):
        path = path[1:]

    try:
        data = json.loads(body_bytes)
    except json.JSONDecodeError:
        return 'Bad Request', 400

    if path == "v1/chat/completions":
        if 'media' in data:
            deployment = model_mapper[data['model']]
            data['max_tokens'] = 4096
            body_bytes = json.dumps(data)
            api_version = "2023-12-01-preview"
        else:
            deployment = model_mapper[data['model']]
        path = "chat/completions"

    elif path == "v1/images/generations":
        path = "images/generations"
        deployment = "dall-e-3"

    elif path == "v1/completions":
        path = "completions"

    elif path == "v1/models":
        return '', 204

    elif path == "v1/audio/speech":
        path = "audio/speech"
        deployment = "tts"

    elif path == "v1/audio/transcriptions":
        path = "audio/transcriptions"
        deployment = "whisper"

    else:
        return 'Not Found', 404

    if deployment not in resource_mapper:
        return 'Not Found', 404

    resource = resource_mapper[deployment]
    request_url = f"https://{resource}.openai.azure.com/openai/deployments/{deployment}/{path}?api-version={api_version}"

    headers = {'api-key': resource_keys[resource]}
    for key, value in request.headers.items():
        if key.lower() != 'authorization' and key.lower() != 'host':
            headers[key] = value

    # Stream the request to the target URL
    req = requests.request(
        method=request.method,
        url=request_url,
        headers=headers,
        data=body_bytes,
        allow_redirects=False,
        stream=True
    )

    # Stream the response back to the client
    def generate():
        for chunk in req.iter_content(chunk_size=4096):
            yield chunk

    return Response(generate(), headers=dict(req.headers))


@app.route('/v1/models', methods=['GET'])
def get_models():
    # Example data
    response = {
        "object": "list",
        "data": [
            {
                "id": "model-id-0",
                "object": "model",
                "created": 1686935002,
                "owned_by": "organization-owner"
            },
            {
                "id": "model-id-1",
                "object": "model",
                "created": 1686935002,
                "owned_by": "organization-owner",
            },
            {
                "id": "model-id-2",
                "object": "model",
                "created": 1686935002,
                "owned_by": "openai"
            },
        ],
    }

    return jsonify(response)


if __name__ == '__main__':
    if os.getenv('MODEL_MAPPER') is None or os.getenv('RESOURCE_MAPPER') is None:
        raise ValueError("MODEL_MAPPER and RESOURCE_MAPPER environment variables must be set")
    if os.getenv('KEYS_MAPPER') is None:
        raise ValueError("KEYS_MAPPER environment variable must be set")
    app.run(host='0.0.0.0', port=8081, debug=True)
