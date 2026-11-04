"""Errors the API can show to a user. Each carries the HTTP status it maps to and a message that is safe to display."""


class DebateError(Exception):
    status_code = 500
    public_message = "The debate could not be completed."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.public_message)
        self.public_message = message or self.public_message


class DataUnavailableError(DebateError):
    status_code = 404
    public_message = "No market data was found for that ticker."


class DataSourceError(DebateError):
    status_code = 503
    public_message = "The market data provider is not responding. Try again in a moment."


class LLMAuthError(DebateError):
    status_code = 401
    public_message = "The Gemini API key was rejected. Check that it is correct and has access to the model."


class LLMRateLimitError(DebateError):
    status_code = 429
    public_message = "The AI provider is rate limiting requests. Wait a minute and try again."


class LLMUnavailableError(DebateError):
    status_code = 503
    public_message = "Could not reach the AI model."


class LLMError(DebateError):
    status_code = 502
    public_message = "The AI model returned an error."
