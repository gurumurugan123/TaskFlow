"""Redis queue names and worker retry settings."""

PENDING_QUEUE = "queue:pending"
PROCESSING_QUEUE = "queue:processing"
DELAYED_QUEUE = "queue:delayed"
DEAD_LETTER_QUEUE = "queue:dead"

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2
MAX_BACKOFF_SECONDS = 60
