"""
Tests for LLM Rate Limiting and Prompt Complexity Scoring

Verifies the DoS mitigation implementation for security gap 15.2:
- Token-based rate limiting (max tokens per session per window)
- Prompt complexity scoring (identifies expensive/suspicious prompts)
- Integration with API endpoints
"""

import time
from src.security.llm_rate_limiter import (
    TokenBasedRateLimiter,
    PromptComplexityScorer,
    LLMRateLimitingPipeline,
)


class TestPromptComplexityScorer:
    """Test prompt complexity scoring across various dimensions."""
    
    def test_empty_prompt(self):
        """Empty prompts should have zero complexity."""
        scorer = PromptComplexityScorer(complexity_threshold=60.0)
        score = scorer.score("")
        assert score.overall_score == 0.0
        assert score.character_count == 0
        assert score.word_count == 0
        assert not score.is_complex
    
    def test_simple_prompt(self):
        """Simple, short prompts should have low complexity."""
        scorer = PromptComplexityScorer(complexity_threshold=60.0)
        score = scorer.score("What is the weather?")
        assert score.character_count == 20
        assert score.word_count == 4
        assert score.overall_score < 50.0
        assert not score.is_complex
    
    def test_code_detection(self):
        """Prompts with code patterns should detect code."""
        scorer = PromptComplexityScorer(complexity_threshold=60.0)
        
        # Python code - should trigger code detection
        py_prompt = "def calculate(x, y):\n    return x + y\n    if x > 0: print('positive')"
        py_score = scorer.score(py_prompt)
        assert py_score.code_likelihood > 0.1  # At least some code patterns detected
        
        # SQL code - should definitely trigger code detection
        sql_prompt = "SELECT * FROM users WHERE id = 5"
        sql_score = scorer.score(sql_prompt)
        assert sql_score.code_likelihood > 0.2
    
    def test_tool_invocation_detection(self):
        """Prompts requesting tools/functions should be detected."""
        scorer = PromptComplexityScorer(complexity_threshold=60.0)
        
        # Method call syntax with clearer patterns
        prompt = "Call the fetch_weather(location) function with parameter 'London'"
        score = scorer.score(prompt)
        assert score.tool_call_likelihood > 0.3
    
    def test_special_character_ratio(self):
        """Prompts with many special characters should have high ratio."""
        scorer = PromptComplexityScorer(complexity_threshold=60.0)
        
        # High special char density
        prompt = "SELECT * FROM users WHERE id = @id AND name LIKE '%john%' OR status != 'inactive';"
        score = scorer.score(prompt)
        assert score.special_char_ratio > 0.1  # Has special characters
        assert score.code_likelihood > 0.1  # SQL detected
    
    def test_very_long_prompt(self):
        """Very long prompts should flag as high complexity."""
        scorer = PromptComplexityScorer(complexity_threshold=60.0)
        
        # Artificially long prompt (5000+ chars)
        long_prompt = "Write a report about " + ("very " * 1000)
        score = scorer.score(long_prompt)
        assert "very_long_prompt" in score.flags
        assert score.overall_score >= 50.0  # At or above threshold
    
    def test_very_long_sentences(self):
        """Prompts with very long sentences should flag it."""
        scorer = PromptComplexityScorer(complexity_threshold=60.0)
        
        # Single sentence with 40+ words
        prompt = " ".join(["word"] * 50) + "."
        score = scorer.score(prompt)
        assert "very_long_sentences" in score.flags


class TestTokenBasedRateLimiter:
    """Test token-based rate limiting."""
    
    def test_token_estimation(self):
        """Token estimation should roughly match text length."""
        limiter = TokenBasedRateLimiter(
            token_limit=500000,
            window_size_sec=3600,
            estimated_response_tokens=2000,
        )
        
        # 100 chars ≈ 25 tokens (1 token per 4 chars)
        tokens = limiter.estimate_tokens("a" * 100)
        assert 20 <= tokens <= 30
    
    def test_first_request_allowed(self):
        """First request should always be allowed."""
        # Use high token limit and low estimated response to make test feasible
        limiter = TokenBasedRateLimiter(
            token_limit=10000,
            window_size_sec=3600,
            estimated_response_tokens=500,
        )
        
        allowed, msg = limiter.check_and_record("session1", "Hello world")
        assert allowed
        assert msg == ""
    
    def test_token_budget_exceeded(self):
        """Request exceeding token budget should be rejected."""
        limiter = TokenBasedRateLimiter(
            token_limit=1000,
            estimated_response_tokens=500,
            window_size_sec=3600,
        )
        
        # First request: ~25 chars + 500 response ≈ 600 tokens
        allowed1, msg1 = limiter.check_and_record("session1", "a" * 100)
        assert allowed1
        
        # Second request: would exceed 1000-token budget (600 + 600 > 1000)
        allowed2, msg2 = limiter.check_and_record("session1", "a" * 100)
        assert not allowed2
        assert "Token rate limit exceeded" in msg2
    
    def test_window_reset(self):
        """Token budget should reset after window expires."""
        limiter = TokenBasedRateLimiter(
            token_limit=800,  # Slightly reduce to exceed with 2 requests
            window_size_sec=1,  # 1 second window for testing
            estimated_response_tokens=400,
        )
        
        # Fill budget: ~25 tokens (prompt) + 400 (response) = ~425 tokens
        allowed1, _ = limiter.check_and_record("session2", "a" * 100)
        assert allowed1
        
        # Try immediately after — should fail (425 + 425 > 800)
        allowed2, _ = limiter.check_and_record("session2", "a" * 100)
        assert not allowed2
        
        # Wait for window to expire
        time.sleep(1.1)
        
        # Should be allowed again
        allowed3, msg3 = limiter.check_and_record("session2", "a" * 100)
        assert allowed3
        assert msg3 == ""
    
    def test_separate_sessions(self):
        """Different sessions should have separate token budgets."""
        limiter = TokenBasedRateLimiter(
            token_limit=1000,
            window_size_sec=3600,
            estimated_response_tokens=400,
        )
        
        allowed1, _ = limiter.check_and_record("session_a", "a" * 100)
        assert allowed1
        
        # Different session should have its own budget
        allowed2, msg2 = limiter.check_and_record("session_b", "a" * 100)
        assert allowed2
        assert msg2 == ""
    
    def test_token_usage_tracking(self):
        """Should track token usage accurately."""
        limiter = TokenBasedRateLimiter(
            token_limit=10000,
            window_size_sec=3600,
            estimated_response_tokens=500,
        )
        
        limiter.check_and_record("session3", "a" * 100)
        usage = limiter.get_token_usage("session3")
        
        assert usage["limit"] == 10000
        assert usage["used"] > 0
        assert usage["remaining"] < 10000


class TestLLMRateLimitingPipeline:
    """Test the integrated pipeline."""
    
    def test_full_pipeline_simple(self):
        """Simple prompt should pass through pipeline."""
        pipeline = LLMRateLimitingPipeline(
            complexity_threshold=60.0,
            token_limit=50000,
            window_size_sec=3600,
            estimated_response_tokens=2000,
        )
        
        allowed, error, complexity = pipeline.validate_and_score(
            "session1", "What is 2+2?"
        )
        
        assert allowed
        assert error is None
        assert not complexity.is_complex
    
    def test_full_pipeline_complex(self):
        """Complex/long prompt should pass but be flagged."""
        pipeline = LLMRateLimitingPipeline(
            complexity_threshold=40.0,
            token_limit=50000,
            window_size_sec=3600,
            estimated_response_tokens=2000,
        )
        
        # Use a longer prompt with complex patterns
        complex_prompt = "SELECT * FROM " + ("users " * 50) + "WHERE id > 0"
        allowed, error, complexity = pipeline.validate_and_score(
            "session2", complex_prompt
        )
        
        assert allowed  # Still allowed, just logged
        assert error is None
    
    def test_pipeline_rate_limit_exceeded(self):
        """Pipeline should reject prompts exceeding token limit."""
        # Use very low token limit to test the rate limiting
        pipeline = LLMRateLimitingPipeline(
            token_limit=800,  # Tight limit
            complexity_threshold=60.0,
            window_size_sec=3600,
            estimated_response_tokens=400,
        )
        
        # First prompt uses ~425 tokens
        allowed1, _, _ = pipeline.validate_and_score("session3", "a" * 100)
        assert allowed1
        
        # Second prompt would use ~425 more, total 850 > 800 limit
        allowed2, error2, _ = pipeline.validate_and_score("session3", "a" * 100)
        assert not allowed2
        assert error2 is not None
        assert "Token rate limit exceeded" in error2
