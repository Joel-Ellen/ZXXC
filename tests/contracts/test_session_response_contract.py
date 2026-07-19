from src.api_models.session_response import SessionResponse
from src.domain.profile import DynamicLearningProfile, StudentProfile
from src.domain.session import LearningSession
from src.domain.path import LearningPath


def _response() -> SessionResponse:
    return SessionResponse(
        session=LearningSession(user_id="u", course_id="c"),
        profile=StudentProfile(user_id="u", course_id="c"),
        dynamic_profile=DynamicLearningProfile(),
        learning_path=LearningPath(),
        resources={},
    )


def test_session_response_dto_uses_canonical_shape():
    data = _response().to_dto_dict()
    assert "legacy" not in data
    assert "generated_resources" not in data
    assert "user_id" not in data
    assert data["session"]["user_id"] == "u"
    assert data["resource_contract_version"] == 2


def test_session_response_model_dump_matches_dto():
    response = _response()
    assert response.model_dump() == response.to_dto_dict()
