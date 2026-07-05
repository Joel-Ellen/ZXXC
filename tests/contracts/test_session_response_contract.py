from src.api_models.session_response import SessionResponse
from src.domain.profile import DynamicLearningProfile, StudentProfile
from src.domain.session import LearningSession
from src.domain.path import LearningPath


def test_session_response_keeps_compatible_generated_resources():
    response = SessionResponse(
        session=LearningSession(user_id="u", course_id="c"),
        profile=StudentProfile(user_id="u", course_id="c"),
        dynamic_profile=DynamicLearningProfile(),
        learning_path=LearningPath(),
        resources={},
        legacy={"user_id": "u", "course_id": "c", "active_path": []},
    )
    data = response.to_compatible_dict()
    assert data["user_id"] == "u"
    assert data["course_id"] == "c"
    assert "session" in data
    assert "generated_resources" in data
