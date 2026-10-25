# aicontrol (SDK)

Python SDK that captures LLM calls (OpenAI, including OpenAI-compatible servers) with OpenTelemetry and sends them to the AIControl API.

```python
import aicontrol
from openai import OpenAI

# Once at startup, with the slug of your project (or set AICONTROL_PROJECT).
aicontrol.init(project="my-project")

client = OpenAI()  # every call is traced from here on
client.responses.create(model="gpt-5-mini", input="What is the capital of France?")
```

- The project is required and must exist in AIControl (create it in the web UI): pass its **slug**, generated from its name and shown on the project's page, not the name; the API address is `endpoint=...`, else `AICONTROL_ENDPOINT`, else `http://localhost:8000`. `init()` takes keyword arguments only.
- If the project does not exist the calls are refused and one error is logged; the application is never affected.
- `aicontrol.volume("name")` groups calls into conversations, `aicontrol.trace("name")` and `aicontrol.step("name")` group and label the calls of one piece of work.

See the root `README.md` for the quickstart and the full usage.
