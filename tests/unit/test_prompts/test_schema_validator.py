"""
Unit tests for prompts/schema_validator.py.

Tests SchemaValidator for PATH files and prompt templates.
"""

import pytest

from src.prompts.schema_validator import SchemaValidator


class TestSchemaValidatorPATHFile:
    """Tests for PATH file validation."""

    @pytest.fixture
    def validator(self):
        """Create a SchemaValidator instance."""
        return SchemaValidator()

    def test_valid_v1_path_file(self, validator):
        """Valid v1 PATH file passes validation."""
        content = """
version: v1
routes:
  default: prompts/default.md
  discussion_detailed: prompts/{category}/{type}.md
"""
        result = validator.validate_path_file(content)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_missing_version(self, validator):
        """PATH file without version fails."""
        content = """
routes:
  default: prompts/default.md
"""
        result = validator.validate_path_file(content)
        assert result.is_valid is False
        assert "Missing required field: version" in result.errors

    def test_unsupported_version(self, validator):
        """Unsupported version fails."""
        content = """
version: v999
routes:
  default: prompts/default.md
"""
        result = validator.validate_path_file(content)
        assert result.is_valid is False
        assert any("Unsupported schema version" in e for e in result.errors)

    def test_missing_routes(self, validator):
        """PATH file without routes fails."""
        content = """
version: v1
"""
        result = validator.validate_path_file(content)
        assert result.is_valid is False
        assert "Missing required field: routes" in result.errors

    def test_routes_must_be_dict(self, validator):
        """Routes must be a dictionary."""
        content = """
version: v1
routes:
  - prompts/default.md
"""
        result = validator.validate_path_file(content)
        assert result.is_valid is False
        assert "'routes' must be a dictionary" in result.errors

    def test_invalid_route_name(self, validator):
        """Route name must be valid identifier."""
        content = """
version: v1
routes:
  Invalid-Route: prompts/default.md
"""
        result = validator.validate_path_file(content)
        assert result.is_valid is False
        assert any("Invalid route name" in e for e in result.errors)

    def test_path_traversal_detected(self, validator):
        """Path traversal in route is detected."""
        content = """
version: v1
routes:
  malicious: ../../../etc/passwd
"""
        result = validator.validate_path_file(content)
        assert result.is_valid is False
        assert any("path traversal" in e for e in result.errors)

    def test_absolute_path_rejected(self, validator):
        """Absolute paths are rejected."""
        content = """
version: v1
routes:
  absolute: /etc/prompts/default.md
"""
        result = validator.validate_path_file(content)
        assert result.is_valid is False
        assert any("must not be an absolute path" in e for e in result.errors)

    def test_fallback_chain_references_valid_routes(self, validator):
        """Fallback chain must reference defined routes."""
        content = """
version: v1
routes:
  default: prompts/default.md
fallback_chain:
  - undefined_route
"""
        result = validator.validate_path_file(content)
        assert result.is_valid is False
        assert any("undefined route" in e for e in result.errors)

    def test_valid_fallback_chain(self, validator):
        """Valid fallback chain passes."""
        content = """
version: v1
routes:
  default: prompts/default.md
  detailed: prompts/detailed.md
fallback_chain:
  - detailed
  - default
"""
        result = validator.validate_path_file(content)
        assert result.is_valid is True

    def test_invalid_yaml_syntax(self, validator):
        """Invalid YAML fails."""
        content = """
version: v1
routes:
  - broken
  : invalid
"""
        result = validator.validate_path_file(content)
        assert result.is_valid is False
        assert any("Invalid YAML syntax" in e for e in result.errors)

    def test_file_size_limit(self, validator):
        """Oversized PATH files fail."""
        content = "version: v1\n" + "a" * (validator.MAX_FILE_SIZE + 1)
        result = validator.validate_path_file(content)
        assert result.is_valid is False
        assert any("exceeds maximum size" in e for e in result.errors)


class TestSchemaValidatorTemplates:
    """Tests for prompt template validation."""

    @pytest.fixture
    def validator(self):
        """Create a SchemaValidator instance."""
        return SchemaValidator()

    def test_valid_template(self, validator):
        """Valid template passes."""
        template = """
You are a summarization assistant. Please summarize the following messages:

{messages}

Focus on {category} content.
"""
        result = validator.validate_prompt_template(template)
        assert result.is_valid is True

    def test_template_size_limit(self, validator):
        """Oversized templates fail."""
        template = "x" * (validator.MAX_FILE_SIZE + 1)
        result = validator.validate_prompt_template(template)
        assert result.is_valid is False
        assert any("exceeds maximum size" in e for e in result.errors)

    def test_script_tag_blocked(self, validator):
        """Script tags are blocked."""
        template = "Hello <script>alert('xss')</script> world"
        result = validator.validate_prompt_template(template)
        assert result.is_valid is False
        assert any("dangerous pattern" in e for e in result.errors)

    def test_javascript_protocol_blocked(self, validator):
        """JavaScript protocol is blocked."""
        template = "Click here: javascript:alert('xss')"
        result = validator.validate_prompt_template(template)
        assert result.is_valid is False
        assert any("dangerous pattern" in e for e in result.errors)

    def test_event_handler_blocked(self, validator):
        """Event handlers are blocked."""
        template = '<img src="x" onerror="alert(1)">'
        result = validator.validate_prompt_template(template)
        assert result.is_valid is False
        assert any("dangerous pattern" in e for e in result.errors)

    def test_jinja_injection_blocked(self, validator):
        """Jinja2 template injection is blocked."""
        template = "Hello {{ config.SECRET_KEY }}"
        result = validator.validate_prompt_template(template)
        assert result.is_valid is False
        assert any("dangerous pattern" in e for e in result.errors)

    def test_path_traversal_blocked(self, validator):
        """Path traversal in template is blocked."""
        template = "Include: ../../../etc/passwd"
        result = validator.validate_prompt_template(template)
        assert result.is_valid is False
        assert any("dangerous pattern" in e for e in result.errors)

    def test_eval_blocked(self, validator):
        """eval() is blocked."""
        template = "Result: eval(user_input)"
        result = validator.validate_prompt_template(template)
        assert result.is_valid is False
        assert any("dangerous pattern" in e for e in result.errors)

    def test_nonstandard_variable_warning(self, validator):
        """Non-standard variable names generate warning."""
        template = "Hello {CamelCase} and {with-dash}"
        result = validator.validate_prompt_template(template)
        # Still valid but has warnings
        assert result.is_valid is True
        assert len(result.warnings) >= 2


class TestSchemaValidatorSanitize:
    """Tests for template sanitization."""

    @pytest.fixture
    def validator(self):
        """Create a SchemaValidator instance."""
        return SchemaValidator()

    def test_sanitize_removes_script(self, validator):
        """Sanitize removes script tags."""
        template = "Hello <script>bad</script> world"
        result = validator.sanitize_template(template)
        assert "<script" not in result

    def test_sanitize_removes_eval(self, validator):
        """Sanitize removes eval."""
        template = "Result: eval(x)"
        result = validator.sanitize_template(template)
        assert "eval(" not in result

    def test_sanitize_removes_path_traversal(self, validator):
        """Sanitize removes path traversal."""
        template = "File: ../../secret"
        result = validator.sanitize_template(template)
        assert "../" not in result

    def test_sanitize_preserves_safe_content(self, validator):
        """Sanitize preserves safe content."""
        template = "Hello world, this is a {variable}"
        result = validator.sanitize_template(template)
        assert result == template


class TestSchemaValidatorPath:
    """Tests for path validation."""

    @pytest.fixture
    def validator(self):
        """Create a SchemaValidator instance."""
        return SchemaValidator()

    def test_valid_prompts_path(self, validator):
        """Valid prompts path passes."""
        assert validator.validate_path("prompts/default.md") is True

    def test_valid_variants_path(self, validator):
        """Valid variants path passes."""
        assert validator.validate_path("variants/concise.md") is True

    def test_valid_includes_path(self, validator):
        """Valid includes path passes."""
        assert validator.validate_path("includes/header.md") is True

    def test_path_traversal_raises(self, validator):
        """Path traversal raises ValueError."""
        with pytest.raises(ValueError, match="path traversal"):
            validator.validate_path("prompts/../../../etc/passwd")

    def test_absolute_path_raises(self, validator):
        """Absolute path raises ValueError."""
        with pytest.raises(ValueError, match="absolute paths"):
            validator.validate_path("/etc/passwd")

    def test_disallowed_directory_raises(self, validator):
        """Path outside allowed directories raises."""
        with pytest.raises(ValueError, match="must start with"):
            validator.validate_path("other/file.md")
