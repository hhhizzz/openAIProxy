import os

from flask import Flask, request, Response, jsonify
from flask_cors import CORS
import requests
import json


from flask_httpauth import HTTPTokenAuth

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter


app = Flask(__name__)

if os.getenv('APPLICATIONINSIGHTS_CONNECTION_STRING'):
    tracer_provider = TracerProvider()
    trace.set_tracer_provider(tracer_provider)
    tracer = trace.get_tracer(__name__)
    # Configure Azure Monitor exporter
    # Replace 'your-connection-string-here' with your actual Azure Monitor Connection String
    azure_exporter = AzureMonitorTraceExporter(
        connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]
    )
    # Add the exporter to the tracer provider
    span_processor = BatchSpanProcessor(azure_exporter)
    trace.get_tracer_provider().add_span_processor(span_processor)

    FlaskInstrumentor().instrument_app(app)

CORS(app)

auth = HTTPTokenAuth(scheme='Bearer')

# format: ["token1","token2"]
# load list to json
authorization = json.loads(os.getenv('AUTHORIZATION'))
tokens = {token for token in authorization}

#  format of the resource_mapper is {"deployment name": "openai resource name"}, e.g. {"gpt-4": "azureopenai1"}
resource_mapper = json.loads(os.getenv('RESOURCE_MAPPER'))

#  format of the model_mapper is {"model name": "deployment name"}, e.g. {"gpt-4": "gpt-4"}
model_mapper = json.loads(os.getenv('MODEL_MAPPER'))

# format of the resource_keys is {"openai resource name": "api key"}, e.g. {"azureopenai1": "1234567890"}
resource_keys = json.loads(os.getenv('KEYS_MAPPER'))


@auth.verify_token
def verify_token(token):
    if token in tokens:
        return "openAIUser"
    return None


@auth.error_handler
def unauthorized():
    return jsonify({'error': 'Unauthorized access'}), 401


@app.route('/<path:path>', methods=['OPTIONS', 'POST'])
@auth.login_required
def handler(path):
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("completions"):
        if request.method == 'OPTIONS':
            return '', 204

        if request.method != 'POST':
            return 'Bad Request', 400

        body_str = request.get_data()

        deployment = "gpt-4o"
        api_version = "2024-02-15-preview"

        if path.startswith("//"):
            path = path[1:]

        try:
            data = json.loads(body_str)
        except json.JSONDecodeError:
            return 'Bad Request', 400

        if path == "v1/chat/completions":
            if 'media' in data:
                deployment = model_mapper[data['model']]
                data['max_tokens'] = 4096
                body_str = json.dumps(data)
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

        with tracer.start_as_current_span("request_to_openai"):
            return request_to_openai(body_str, deployment, path, api_version)


def request_to_openai(data, deployment, path, api_version):
    resource = resource_mapper[deployment]
    request_url = f"https://{resource}.openai.azure.com/openai/deployments/{
        deployment}/{path}?api-version={api_version}"

    headers = {'api-key': resource_keys[resource]}
    for key, value in request.headers.items():
        if key.lower() != 'authorization' and key.lower() != 'host' and key.lower() != "api-key":
            headers[key] = value

    # Stream the request to the target URL
    req = requests.request(
        method="POST",
        url=request_url,
        headers=headers,
        data=data,
        allow_redirects=False,
        stream=True
    )

    # Stream the response back to the client
    def generate():
        for chunk in req.iter_content(chunk_size=4096):
            yield chunk

    return Response(generate(), headers=dict(req.headers))


@app.route('/v1/models', methods=['GET'])
@auth.login_required
def get_models():
    # get values from model mapper and put to the response
    data = []
    for _, value in model_mapper.items():
        data.append({
            "id": value,
            "object": "model",
            "created": 1686935002,
            "owned_by": "openai"
        })

    response = {
        "object": "list",
        "data": data
    }

    return jsonify(response)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
