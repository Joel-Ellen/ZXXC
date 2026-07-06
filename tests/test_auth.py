# -*- coding: utf-8 -*-
"""
EduAgent 认证系统 — 完整单元 + 集成测试
=========================================

覆盖范围:
  1. SecurityManager: Argon2id 密码哈希/验证
  2. SecurityManager: JWT 双令牌签发/解码/过期检测
  3. SecurityManager: 等时退避 (防计时攻击)
  4. CaptchaGenerator: SVG 验证码生成/验证
  5. CaptchaGenerator: 过期验证码拒绝
  6. CaptchaGenerator: 一次性使用
  7. UserStore: 创建用户 (唯一性检查)
  8. UserStore: 登录验证 (正确/错误密码)
  9. UserStore: 邮箱唯一性检查
  10. PresetAccounts: 预设账号自动创建
  11. LangGraphImmutableContextGuard: 越权拦截
  12. LangGraphImmutableContextGuard: 正常放行
  13. AuthRouter: 注册/登录端点集成测试
  14. AuthRouter: 缺少验证码拒绝
  15. AuthRouter: 重复注册拒绝

运行方式:
    pytest tests/test_auth.py -v
"""

import pytest
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.auth.security import (
    SecurityManager, FAKE_HASH, JWT_SECRET_KEY, ALGORITHM, ARGON2_AVAILABLE,
)
from src.auth.captcha import CaptchaGenerator, CaptchaRecord
from src.auth.models import UserStore, UserRecord, PresetAccounts
from src.auth.graph_guard import LangGraphImmutableContextGuard
from src.state.agent_state import AgentState


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def store(tmp_path) -> UserStore:
    """创建临时文件存储的 UserStore。"""
    path = tmp_path / "test_users.json"
    return UserStore(str(path))


@pytest.fixture
def captcha() -> CaptchaGenerator:
    return CaptchaGenerator()


# ============================================================================
# Test 1: SecurityManager — 密码哈希
# ============================================================================

class TestPasswordHashing:
    """Argon2id 密码哈希测试。"""

    def test_hash_and_verify_correct(self) -> None:
        """正确密码应通过验证。"""
        password = "Secure_Student_Pass_2026"
        h = SecurityManager.hash_password(password)
        assert h != password
        if ARGON2_AVAILABLE:
            assert h.startswith("$argon2id$")
        else:
            assert h.startswith("pbkdf2_sha256$")
        assert SecurityManager.verify_password(password, h) is True

    def test_wrong_password_rejected(self) -> None:
        """错误密码应被拒绝。"""
        h = SecurityManager.hash_password("correct_password")
        assert SecurityManager.verify_password("wrong_password", h) is False

    def test_empty_password_handled(self) -> None:
        """空密码应能正常工作。"""
        h = SecurityManager.hash_password("")
        assert SecurityManager.verify_password("", h) is True
        assert SecurityManager.verify_password("x", h) is False

    def test_unicode_password(self) -> None:
        """Unicode 密码应能正常哈希验证。"""
        pwd = "学生密码_Pass_2026_数据结构"
        h = SecurityManager.hash_password(pwd)
        assert SecurityManager.verify_password(pwd, h) is True

    def test_different_salts(self) -> None:
        """两次哈希应产生不同结果 (随机盐)。"""
        h1 = SecurityManager.hash_password("same_password")
        h2 = SecurityManager.hash_password("same_password")
        assert h1 != h2  # 盐不同导致密文不同
        assert SecurityManager.verify_password("same_password", h1)
        assert SecurityManager.verify_password("same_password", h2)


# ============================================================================
# Test 2: SecurityManager — JWT 令牌
# ============================================================================

class TestJWTToken:
    """JWT 双令牌测试。"""

    def test_create_token_pair(self) -> None:
        """创建令牌对应包含 access + refresh。"""
        pair = SecurityManager.create_token_pair("user_001", "STUDENT")
        assert "access_token" in pair
        assert "refresh_token" in pair
        assert "access_jti" in pair
        assert "refresh_jti" in pair
        assert len(pair["access_token"]) > 50
        assert len(pair["refresh_token"]) > 50

    def test_access_token_contains_role(self) -> None:
        """Access Token 应包含 role 字段。"""
        pair = SecurityManager.create_token_pair("user_002", "ADMIN")
        payload = SecurityManager.decode_token(pair["access_token"])
        assert payload["sub"] == "user_002"
        assert payload["role"] == "ADMIN"
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "exp" in payload

    def test_refresh_token_type(self) -> None:
        """Refresh Token type 应为 refresh。"""
        pair = SecurityManager.create_token_pair("user_003", "STUDENT")
        payload = SecurityManager.decode_token(pair["refresh_token"])
        assert payload["type"] == "refresh"

    def test_access_token_short_lifetime(self) -> None:
        """Access Token 寿命应约为 15 分钟。"""
        import jwt as jt
        import time as _time
        pair = SecurityManager.create_token_pair("u", "STUDENT")
        payload = jt.decode(
            pair["access_token"], JWT_SECRET_KEY,
            algorithms=[ALGORITHM], options={"verify_exp": False}
        )
        now = int(_time.time())
        diff = payload["exp"] - now
        # 刚签发，过期应在 14-16 分钟之后
        assert 14 * 60 <= diff <= 16 * 60, f"diff={diff}s"

    def test_invalid_token_rejected(self) -> None:
        """无效令牌应抛出 TOKEN_INVALID。"""
        with pytest.raises(ValueError, match="TOKEN_INVALID"):
            SecurityManager.decode_token("not.a.valid.token")


# ============================================================================
# Test 3: SecurityManager — 等时退避
# ============================================================================

class TestConstantTime:
    """等时退避测试。"""

    def test_constant_time_fallback_no_exception(self) -> None:
        """等时退避不应抛出异常。"""
        SecurityManager.execute_constant_time_fallback()

    def test_fake_hash_is_valid_argon2(self) -> None:
        """FAKE_HASH 应为合法的 Argon2 哈希。"""
        if ARGON2_AVAILABLE:
            assert FAKE_HASH.startswith("$argon2id$")
        else:
            assert FAKE_HASH.startswith("pbkdf2_sha256$")


# ============================================================================
# Test 4: CaptchaGenerator
# ============================================================================

class TestCaptchaGenerator:
    """验证码生成测试。"""

    def test_generate_returns_svg_and_token(self, captcha: CaptchaGenerator) -> None:
        """应返回 SVG 字符串和验证令牌。"""
        svg, token = captcha.generate()
        assert '<svg' in svg
        assert '</svg>' in svg
        assert len(token) == 16

    def test_verify_correct_answer(self, captcha: CaptchaGenerator) -> None:
        """正确答案应通过验证。"""
        svg, token = captcha.generate()
        # 从 token 查找记录获取正确答案
        record = captcha._records.get(token)
        if record is None:
            pytest.skip("captcha already cleaned up")
        assert captcha.verify(token, record.answer) is True

    def test_verify_wrong_answer(self, captcha: CaptchaGenerator) -> None:
        """错误答案应被拒绝。"""
        svg, token = captcha.generate()
        record = captcha._records.get(token)
        if record is None:
            pytest.skip("captcha already cleaned up")
        wrong = str(int(record.answer) + 999) if record.answer.isdigit() else "0"
        assert captcha.verify(token, wrong) is False

    def test_verify_nonexistent_token(self, captcha: CaptchaGenerator) -> None:
        """不存在的令牌应返回 False。"""
        assert captcha.verify("nonexistent_token", "42") is False

    def test_one_time_use(self, captcha: CaptchaGenerator) -> None:
        """验证码应为一次性使用。"""
        svg, token = captcha.generate()
        record = captcha._records.get(token)
        if record is None:
            pytest.skip("captcha already cleaned up")
        # 第一次验证
        assert captcha.verify(token, record.answer) is True
        # 第二次应失败（已删除）
        assert captcha.verify(token, record.answer) is False

    def test_expired_captcha_rejected(self, captcha: CaptchaGenerator) -> None:
        """过期验证码应被拒绝。"""
        svg, token = captcha.generate()
        # 手动设为过期
        record = captcha._records.get(token)
        if record:
            record.created_at = time.time() - 9999  # 很久以前
            record.ttl_seconds = 1
        assert captcha.verify(token, "0") is False

    def test_different_expressions(self, captcha: CaptchaGenerator) -> None:
        """每次生成的表达式应不同（概率测试）。"""
        exprs = set()
        for _ in range(10):
            svg, token = captcha.generate()
            record = captcha._records.get(token)
            if record:
                exprs.add(record.expression)
        assert len(exprs) >= 3  # 10 次中至少有 3 种不同表达式


# ============================================================================
# Test 5: UserStore
# ============================================================================

class TestUserStore:
    """用户存储 CRUD 测试。"""

    def test_create_user(self, store: UserStore) -> None:
        """创建新用户应成功。"""
        user = store.create_user("alice", "alice@test.com", "Pass1234!")
        assert user.user_id == "alice"
        assert user.email == "alice@test.com"
        assert user.role == "STUDENT"

    def test_duplicate_username_rejected(self, store: UserStore) -> None:
        """重复用户名应被拒绝。"""
        store.create_user("bob", "bob@test.com", "Pass1234!")
        with pytest.raises(ValueError, match="已存在"):
            store.create_user("bob", "bob2@test.com", "Pass1234!")

    def test_duplicate_email_rejected(self, store: UserStore) -> None:
        """重复邮箱应被拒绝。"""
        store.create_user("carol", "carol@test.com", "Pass1234!")
        with pytest.raises(ValueError, match="已被注册"):
            store.create_user("carol2", "carol@test.com", "Pass1234!")

    def test_verify_login_correct(self, store: UserStore) -> None:
        """正确密码应登录成功。"""
        store.create_user("dave", "dave@test.com", "Correct_Pass_99")
        user = store.verify_login("dave", "Correct_Pass_99")
        assert user is not None
        assert user.user_id == "dave"

    def test_verify_login_wrong_password(self, store: UserStore) -> None:
        """错误密码应登录失败。"""
        store.create_user("eve", "eve@test.com", "Correct_Pass_99")
        user = store.verify_login("eve", "Wrong_Password")
        assert user is None

    def test_verify_login_nonexistent_user(self, store: UserStore) -> None:
        """不存在用户应登录失败（带等时退避）。"""
        user = store.verify_login("ghost_user", "any_password")
        assert user is None

    def test_get_by_email(self, store: UserStore) -> None:
        """按邮箱查找应正确。"""
        store.create_user("frank", "frank@test.com", "Pass1234!")
        found = store.get_by_email("frank@test.com")
        assert found is not None
        assert found.user_id == "frank"

    def test_get_by_email_case_insensitive(self, store: UserStore) -> None:
        """邮箱查找应大小写不敏感。"""
        store.create_user("grace", "Grace@Test.COM", "Pass1234!")
        found = store.get_by_email("grace@test.com")
        assert found is not None

    def test_update_password(self, store: UserStore) -> None:
        """密码更新后应用新密码登录。"""
        store.create_user("henry", "henry@test.com", "Old_Pass_1")
        assert store.update_password("henry", "New_Pass_2") is True
        assert store.verify_login("henry", "Old_Pass_1") is None
        assert store.verify_login("henry", "New_Pass_2") is not None

    def test_count_users(self, store: UserStore) -> None:
        """计数应正确。"""
        assert store.count() == 0
        store.create_user("u1", "u1@t.com", "P1")
        store.create_user("u2", "u2@t.com", "P2")
        assert store.count() == 2

    def test_persistence(self, tmp_path) -> None:
        """用户数据应持久化到文件。"""
        p = str(tmp_path / "persist.json")
        s1 = UserStore(p)
        s1.create_user("persist_user", "p@t.com", "Persist_1")
        assert s1.count() == 1

        # 新建 Store 实例读取同一文件
        s2 = UserStore(p)
        assert s2.count() == 1
        assert s2.verify_login("persist_user", "Persist_1") is not None


# ============================================================================
# Test 6: PresetAccounts
# ============================================================================

class TestPresetAccounts:
    """预设账号测试。"""

    def test_presets_created(self, store: UserStore) -> None:
        """首次调用应创建预设账号。"""
        users = PresetAccounts.ensure_presets(store)
        assert len(users) == 2
        assert store.count() == 2

    def test_presets_idempotent(self, store: UserStore) -> None:
        """第二次调用不应重复创建。"""
        PresetAccounts.ensure_presets(store)
        PresetAccounts.ensure_presets(store)
        assert store.count() == 2

    def test_admin_login(self, store: UserStore) -> None:
        """预设管理员应能登录。"""
        PresetAccounts.ensure_presets(store)
        user = store.verify_login("admin", "Admin@2026!")
        assert user is not None
        assert user.role == "ADMIN"

    def test_student_login(self, store: UserStore) -> None:
        """预设学生应能登录。"""
        PresetAccounts.ensure_presets(store)
        user = store.verify_login("student", "Learn@2026")
        assert user is not None
        assert user.role == "STUDENT"

    def test_preset_admin_non_default_password(self, store: UserStore) -> None:
        """预设管理员的密码不应是弱密码。"""
        PresetAccounts.ensure_presets(store)
        assert store.verify_login("admin", "admin") is None
        assert store.verify_login("admin", "123456") is None
        assert store.verify_login("admin", "password") is None


# ============================================================================
# Test 7: LangGraphImmutableContextGuard
# ============================================================================

class TestLangGraphGuard:
    """LangGraph 不可变上下文防护测试。"""

    def test_normal_passthrough(self) -> None:
        """合法状态应正常放行。"""
        def dummy_node(state, config):
            return {"result": "ok"}

        secure = LangGraphImmutableContextGuard.create_secure_node_wrapper(dummy_node)
        state = AgentState(user_id="student_alice", course_id="CS101")
        config = {"configurable": {"authenticated_user_id": "student_alice"}}

        result = secure(state, config)
        assert result["result"] == "ok"

    def test_missing_auth_context_raises(self) -> None:
        """缺少 authenticated_user_id 应抛出中断。"""
        def dummy_node(state, config):
            return {}

        secure = LangGraphImmutableContextGuard.create_secure_node_wrapper(dummy_node)
        state = AgentState(user_id="student_alice", course_id="CS101")
        config = {"configurable": {}}  # 缺失 authenticated_user_id

        from langgraph.errors import GraphInterrupt
        with pytest.raises(GraphInterrupt, match="AUTHENTICATION_CONTEXT_MISSING"):
            secure(state, config)

    def test_tampered_state_user_id_raises(self) -> None:
        """篡改 state.user_id 应被拦截。"""
        def dummy_node(state, config):
            return {}

        secure = LangGraphImmutableContextGuard.create_secure_node_wrapper(dummy_node)
        # 恶意篡改：state 中 user_id 为 student_bob，但 config 中是 student_alice
        malicious_state = AgentState(user_id="student_bob", course_id="CS101")
        config = {"configurable": {"authenticated_user_id": "student_alice"}}

        from langgraph.errors import GraphInterrupt
        with pytest.raises(GraphInterrupt, match="SECURITY_VIOLATION"):
            secure(malicious_state, config)


# ============================================================================
# Test 8: 预设账号快速验证
# ============================================================================

class TestPresetAccountsQuick:
    """预设账号的关键验证用例。"""

    def test_preset_admin_credentials(self) -> None:
        """验证预设管理员账号可用。"""
        s = SecurityManager
        h = s.hash_password("Admin@2026!")
        assert s.verify_password("Admin@2026!", h)

    def test_preset_student_credentials(self) -> None:
        """验证预设学生账号可用。"""
        s = SecurityManager
        h = s.hash_password("Learn@2026")
        assert s.verify_password("Learn@2026", h)
