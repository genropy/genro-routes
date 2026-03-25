# Contributing to genro-routes

Thank you for your interest in contributing to genro-routes!

## Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/genropy/genro-routes.git
   cd genro-routes
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -e ".[all]"
   ```

4. **Run tests**:
   ```bash
   PYTHONPATH=src pytest --cov=src/genro_routes --cov-report=term-missing
   ```

## Making Changes

- Check existing issues and PRs to avoid duplicate work
- For large changes, open an issue first to discuss the approach
- Keep changes focused - one feature/fix per PR

### Code Style

- Follow PEP 8 style guidelines
- Use type hints for function signatures
- Instance methods only (no `@staticmethod` or `@classmethod`)
- All imports at the top of the file

### Running Code Quality Tools

```bash
# Lint
ruff check src/

# Type check
mypy src/

# Format check
black --check src/
```

## Testing Guidelines

- Write tests for all new features
- Maintain or improve test coverage
- Use descriptive test names
- Follow the existing test structure in `tests/`

```bash
# All tests
PYTHONPATH=src pytest

# Specific test file
PYTHONPATH=src pytest tests/test_pydantic_plugin.py -v

# With coverage report
PYTHONPATH=src pytest --cov=src/genro_routes --cov-report=term-missing
```

## Pull Request Process

1. Update documentation for any user-facing changes
2. Add tests for new functionality
3. Ensure all tests pass and coverage is maintained
4. Request review from maintainers

### PR Checklist

- [ ] Code follows project style guidelines
- [ ] Tests added/updated and passing
- [ ] Documentation updated if applicable
- [ ] Commits follow conventional commit format (`feat:`, `fix:`, `docs:`, `test:`)
- [ ] PR description clearly explains the changes

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
