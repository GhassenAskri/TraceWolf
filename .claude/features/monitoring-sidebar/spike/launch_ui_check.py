"""The real app on the THROWAWAY database (port 5543) with an in-memory trace store (no MinIO)."""
import uvicorn

from app.db import create_engine, create_session_factory
from app.main import create_app
from app.storage.memory import InMemoryTraceStore

URL = "postgresql+psycopg://aicontrol:aicontrol@localhost:5543/aicontrol"
app = create_app(session_factory=create_session_factory(create_engine(URL)), trace_store=InMemoryTraceStore())
uvicorn.run(app, host="127.0.0.1", port=8011, log_level="warning")
