class Problem(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status
