"""Domain errors. Each carries the HTTP status the API maps it to."""


class AppError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message, details=None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(AppError):
    status = 400
    code = "validation_error"


class NotFoundError(AppError):
    status = 404
    code = "not_found"


class ConflictError(AppError):
    status = 409
    code = "conflict"
