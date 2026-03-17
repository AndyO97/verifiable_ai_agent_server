"""
LLM Layer Rate Limiting and Prompt Complexity Scoring

Mitigates Denial-of-Service attacks at the LLM inference layer by:
1. Token-based rate limiting (limiting total tokens per session per time window)
2. Prompt complexity scoring (identifying complex/suspicious prompts)
3. Optional queuing with priority-based scheduling

This addresses security gap 15.2: DoS at LLM Layer
https://github.com/andres-1/project/issues/15.2
"""

import time
import re
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TokenBucket:
    """Token bucket state for a session."""
    tokens_used: int = 0
    last_reset: float = field(default_factory=time.time)
    requests_made: int = 0


@dataclass
class ComplexityScore:
    """Breakdown of prompt complexity."""
    overall_score: float  # 0-100, normalized complexity score
    character_count: int
    word_count: int
    sentence_count: int
    avg_sentence_length: float
    code_likelihood: float  # 0-1, probability the prompt contains code
    tool_call_likelihood: float  # 0-1, probability the prompt requests tools
    special_char_ratio: float  # 0-1, ratio of special chars to total
    is_complex: bool  # True if score > COMPLEXITY_THRESHOLD
    flags: list[str] = field(default_factory=list)  # Warning flags


class PromptComplexityScorer:
    """
    Scores prompt complexity to identify expensive/suspicious prompts.
    
    Complexity is measured across multiple dimensions:
    - Length (character and word counts)
    - Sentence structure and average sentence length
    - Presence of code-like patterns
    - Presence of tool invocation attempts
    - Special character density
    """
    
    # Code pattern indicators (regex flags for code-like content)
    CODE_PATTERNS = [
        r'(?:def|class|import|from|lambda|yield|async|await)\s+',  # Python keywords
        r'(?:function|const|let|var|async|await)\s+',  # JavaScript keywords
        r'<[a-zA-Z][^>]*>.*</[a-zA-Z]+>',  # XML/HTML tags
        r'SELECT|INSERT|UPDATE|DELETE|DROP|ALTER',  # SQL (case-insensitive)
        r'\$\{.*?\}',  # Template literals
        r'#!/(?:bin|usr)',  # Shebang (script marker)
    ]
    
    # Tool invocation patterns
    TOOL_CALL_PATTERNS = [
        r'\b(?:call|invoke|execute|run|trigger)\s+\w+',
        r'\b(?:use|apply|get|fetch|retrieve)\s+\w+',
        r'->|\.|\(',  # Method/function call syntax
    ]
    
    def __init__(self, complexity_threshold: float):
        """
        Initialize the scorer.
        
        Args:
            complexity_threshold: Complexity score threshold (0-100)
        """
        self.complexity_threshold = complexity_threshold
        self._pattern_cache = {
            'code': [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.CODE_PATTERNS],
            'tools': [re.compile(p, re.IGNORECASE) for p in self.TOOL_CALL_PATTERNS],
        }
    
    def score(self, prompt: str) -> ComplexityScore:
        """
        Score the complexity of a prompt.
        
        Args:
            prompt: The user-provided prompt text
        
        Returns:
            ComplexityScore object with detailed breakdown
        """
        if not prompt:
            return ComplexityScore(
                overall_score=0.0,
                character_count=0,
                word_count=0,
                sentence_count=0,
                avg_sentence_length=0.0,
                code_likelihood=0.0,
                tool_call_likelihood=0.0,
                special_char_ratio=0.0,
                is_complex=False,
            )
        
        # Basic metrics
        char_count = len(prompt)
        words = prompt.split()
        word_count = len(words)
        sentences = re.split(r'[.!?]+', prompt.strip())
        sentence_count = len([s for s in sentences if s.strip()])
        avg_sent_len = word_count / max(sentence_count, 1)
        
        # Special character ratio
        special_chars = len(re.findall(r'[^a-zA-Z0-9\s]', prompt))
        special_ratio = special_chars / max(char_count, 1)
        
        # Code likelihood (0-1)
        code_matches = sum(
            1 for pattern in self._pattern_cache['code']
            if pattern.search(prompt)
        )
        code_likelihood = min(1.0, code_matches / max(len(self._pattern_cache['code']), 1))
        
        # Tool call likelihood (0-1)
        tool_matches = sum(
            1 for pattern in self._pattern_cache['tools']
            if pattern.search(prompt)
        )
        tool_likelihood = min(1.0, tool_matches / max(len(self._pattern_cache['tools']), 1))
        
        # Calculate overall score (0-100)
        # Normalized contributions:
        # - Character count (0-50 points): longer prompts are more expensive
        # - Code likelihood (0-20 points): code is expensive to execute
        # - Tool calls (0-15 points): tool invocations are expensive
        # - Special characters (0-15 points): special chars suggest complex queries
        
        score_parts = {
            'length': min(50.0, (char_count / 5000.0) * 50.0),  # Cap at 5000 chars
            'code': code_likelihood * 20.0,
            'tools': tool_likelihood * 15.0,
            'special': special_ratio * 15.0,
        }
        overall_score = sum(score_parts.values())
        
        # Generate warning flags
        flags = []
        if char_count > 5000:
            flags.append("very_long_prompt")
        if code_likelihood > 0.6:
            flags.append("code_detected")
        if tool_likelihood > 0.7:
            flags.append("tool_invocation_likely")
        if special_ratio > 0.3:
            flags.append("high_special_char_density")
        if avg_sent_len > 30:
            flags.append("very_long_sentences")
        
        is_complex = overall_score >= self.complexity_threshold
        
        return ComplexityScore(
            overall_score=overall_score,
            character_count=char_count,
            word_count=word_count,
            sentence_count=sentence_count,
            avg_sentence_length=avg_sent_len,
            code_likelihood=code_likelihood,
            tool_call_likelihood=tool_likelihood,
            special_char_ratio=special_ratio,
            is_complex=is_complex,
            flags=flags,
        )


class TokenBasedRateLimiter:
    """
    Rate limits LLM prompts based on token count.
    
    Tracks estimated prompt + expected response tokens per session over a time window.
    This prevents sophisticated attackers from sending complex prompts at the HTTP
    rate limit threshold to consume disproportionate LLM resources.
    
    Configuration:
    - token_limit: Max total tokens per session per time window
    - window_size_sec: Time window for token tracking
    - estimated_response_tokens: Estimate of average response size
    """
    
    def __init__(
        self,
        token_limit: int,
        window_size_sec: int,
        estimated_response_tokens: int,
    ):
        """
        Initialize the token-based rate limiter.
        
        Args:
            token_limit: Max tokens per session per window
            window_size_sec: Time window for tracking (seconds)
            estimated_response_tokens: Estimated tokens in average response
        """
        self.token_limit = token_limit
        self.window_size_sec = window_size_sec
        self.estimated_response_tokens = estimated_response_tokens
        
        # session_token -> TokenBucket
        self.buckets: dict[str, TokenBucket] = {}
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count from text.
        
        Uses a rough heuristic: ~4 characters per token (GPT-style tokenization).
        For more accuracy, integrate with the actual LLM tokenizer.
        
        Args:
            text: The text to estimate tokens for
        
        Returns:
            Estimated token count (conservative upper bound)
        """
        # Rough estimate: 1 token per 4 characters
        # This is conservative (over-estimates) which is safer for rate limiting
        return max(1, len(text) // 4)
    
    def check_and_record(self, session_token: str, prompt: str) -> Tuple[bool, str]:
        """
        Check if a prompt is allowed under the token rate limit.
        Records the prompt's estimated tokens if allowed.
        
        Args:
            session_token: The HTTP session token
            prompt: The user prompt
        
        Returns:
            (is_allowed, message) tuple
                - is_allowed: True if prompt can be processed
                - message: Explanation if not allowed
        """
        now = time.time()
        
        # Get or create bucket for this session
        if session_token not in self.buckets:
            self.buckets[session_token] = TokenBucket()
        
        bucket = self.buckets[session_token]
        
        # Reset bucket if window has expired
        if now - bucket.last_reset > self.window_size_sec:
            bucket.tokens_used = 0
            bucket.requests_made = 0
            bucket.last_reset = now
        
        # Estimate tokens for prompt + response
        prompt_tokens = self.estimate_tokens(prompt)
        total_tokens = prompt_tokens + self.estimated_response_tokens
        
        # Check if adding this request would exceed limit
        new_total = bucket.tokens_used + total_tokens
        if new_total > self.token_limit:
            remaining_tokens = self.token_limit - bucket.tokens_used
            message = (
                f"Token rate limit exceeded. Prompt would use ~{total_tokens} tokens, "
                f"but only {remaining_tokens} tokens remain in this window's budget. "
                f"Please try again after the window resets or use a simpler prompt."
            )
            logger.warning(
                "token_rate_limit_exceeded",
                session=session_token,
                requested_tokens=total_tokens,
                remaining_tokens=remaining_tokens,
                bucket_total=bucket.tokens_used,
                limit=self.token_limit,
            )
            return False, message
        
        # Record the tokens for this request
        bucket.tokens_used += total_tokens
        bucket.requests_made += 1
        
        logger.debug(
            "token_rate_limit_check_passed",
            session=session_token,
            tokens_used=total_tokens,
            bucket_total=bucket.tokens_used,
            limit=self.token_limit,
        )
        
        return True, ""
    
    def get_token_usage(self, session_token: str) -> dict:
        """
        Get current token usage for a session.
        
        Returns:
            dict with 'used', 'limit', 'remaining', 'window_size_sec', and 'requests_made'
        """
        bucket = self.buckets.get(session_token, TokenBucket())
        remaining = max(0, self.token_limit - bucket.tokens_used)
        return {
            "used": bucket.tokens_used,
            "limit": self.token_limit,
            "remaining": remaining,
            "window_size_sec": self.window_size_sec,
            "requests_made": bucket.requests_made,
        }
    
    def cleanup_expired(self):
        """Periodically clean up expired buckets to prevent memory leaks."""
        now = time.time()
        expired = [
            token for token, bucket in self.buckets.items()
            if now - bucket.last_reset > self.window_size_sec * 2
        ]
        for token in expired:
            del self.buckets[token]
        if expired:
            logger.debug("token_rate_limit_cleanup", removed=len(expired))


class LLMRateLimitingPipeline:
    """
    Combined pipeline for LLM rate limiting.
    
    Orchestrates:
    1. Prompt complexity scoring
    2. Token-based rate limiting
    3. Optional throttling for high-complexity prompts
    """
    
    def __init__(
        self,
        complexity_threshold: float,
        token_limit: int,
        window_size_sec: int,
        estimated_response_tokens: int,
    ):
        """Initialize the pipeline."""
        self.scorer = PromptComplexityScorer(complexity_threshold)
        self.limiter = TokenBasedRateLimiter(
            token_limit=token_limit,
            window_size_sec=window_size_sec,
            estimated_response_tokens=estimated_response_tokens,
        )
    
    def validate_and_score(
        self, session_token: str, prompt: str
    ) -> Tuple[bool, Optional[str], ComplexityScore]:
        """
        Validate a prompt through the full pipeline.
        
        Returns:
            (is_allowed, error_message, complexity_score)
        """
        # Score complexity
        complexity = self.scorer.score(prompt)
        
        # Check token-based rate limit
        allowed, message = self.limiter.check_and_record(session_token, prompt)
        
        if not allowed:
            return False, message, complexity
        
        # Log warnings if complexity is high but under limit
        if complexity.is_complex:
            logger.warning(
                "high_complexity_prompt_accepted",
                session=session_token,
                complexity_score=complexity.overall_score,
                flags=complexity.flags,
            )
        
        return True, None, complexity
