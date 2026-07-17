import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _Logger:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


if "loguru" not in sys.modules:
    loguru_module = types.ModuleType("loguru")
    loguru_module.logger = _Logger()
    sys.modules["loguru"] = loguru_module


if "openai" not in sys.modules:
    openai_module = types.ModuleType("openai")

    class _DummyOpenAI:
        def __init__(self, *args, **kwargs):
            pass

    openai_module.OpenAI = _DummyOpenAI
    openai_module.AsyncOpenAI = _DummyOpenAI
    sys.modules["openai"] = openai_module


if "argon2" not in sys.modules:
    argon2_module = types.ModuleType("argon2")
    argon2_exceptions = types.ModuleType("argon2.exceptions")

    class VerifyMismatchError(Exception):
        pass

    class PasswordHasher:
        def __init__(self, *args, **kwargs):
            pass

        def hash(self, password):
            return f"stub-hash::{password}"

        def verify(self, hashed_password, plain_password):
            if hashed_password == f"stub-hash::{plain_password}":
                return True
            raise VerifyMismatchError()

    argon2_module.PasswordHasher = PasswordHasher
    argon2_exceptions.VerifyMismatchError = VerifyMismatchError
    sys.modules["argon2"] = argon2_module
    sys.modules["argon2.exceptions"] = argon2_exceptions


if "fastapi" not in sys.modules:
    fastapi_module = types.ModuleType("fastapi")
    fastapi_security = types.ModuleType("fastapi.security")
    fastapi_responses = types.ModuleType("fastapi.responses")

    class HTTPException(Exception):
        def __init__(self, status_code=500, detail="", headers=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
            self.headers = headers or {}

    class _Status:
        HTTP_400_BAD_REQUEST = 400
        HTTP_401_UNAUTHORIZED = 401
        HTTP_403_FORBIDDEN = 403
        HTTP_404_NOT_FOUND = 404
        HTTP_409_CONFLICT = 409

    class APIRouter:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda func: func

        def post(self, *args, **kwargs):
            return lambda func: func

    class HTMLResponse:
        def __init__(self, content="", *args, **kwargs):
            self.content = content

    class OAuth2PasswordBearer:
        def __init__(self, *args, **kwargs):
            pass

    def Depends(dependency):
        return dependency

    fastapi_module.Depends = Depends
    fastapi_module.HTTPException = HTTPException
    fastapi_module.status = _Status()
    fastapi_module.APIRouter = APIRouter
    fastapi_security.OAuth2PasswordBearer = OAuth2PasswordBearer
    fastapi_responses.HTMLResponse = HTMLResponse

    sys.modules["fastapi"] = fastapi_module
    sys.modules["fastapi.security"] = fastapi_security
    sys.modules["fastapi.responses"] = fastapi_responses


from frontend.server import app
import uvicorn


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8800, log_level="info")
