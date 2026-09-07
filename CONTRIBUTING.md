# Contributing to Flux Gestion

Thank you for your interest in contributing to Flux Gestion! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please be respectful and professional in all interactions. We aim to maintain a welcoming and inclusive community.

## Getting Started

### Prerequisites
- Python 3.8+
- Node.js 14+ (for frontend development, if using npm)
- Git
- Docker & Docker Compose (for development with containers)

### Development Setup

1. Fork the repository
2. Clone your fork:
```bash
git clone https://github.com/your-username/fluxgestion.git
cd fluxgestion
```

3. Create a feature branch:
```bash
git checkout -b feature/your-feature-name
```

4. Set up development environment:
```bash
bash init.sh  # Linux/macOS
init.bat      # Windows
```

5. Create a `.env.local` file with your development settings

## Development Workflow

### Code Style

- **Python**: Follow PEP 8
  - Use `black` for formatting: `black .`
  - Use `flake8` for linting: `flake8 api/`
  - Use `isort` for import sorting: `isort .`

- **JavaScript**: Follow Airbnb style guide
  - Use `prettier` for formatting (if using build tools)
  - Use `eslint` for linting (if using build tools)

- **CSS**: Follow BEM naming convention where possible
  - Use CSS variables for theming
  - Maintain responsive design

### Commit Messages

Use clear, descriptive commit messages:
```
[AREA] Brief description (50 chars max)

Longer explanation if needed. Explain the "why", not just the "what".

Fixes #123
Related to #456
```

Areas: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`

### Pull Request Process

1. Update documentation with new features
2. Add tests for new functionality
3. Update CHANGELOG.md
4. Ensure all tests pass: `bash run_tests.sh`
5. Request review from maintainers
6. Address review comments

## Testing

### Running Tests

```bash
# Run all tests
python manage.py test api

# Run specific test class
python manage.py test api.tests.MonthlyObjectiveModelTest

# Run with coverage
coverage run --source='.' manage.py test api
coverage report
coverage html  # Generate HTML report
```

Tests run under `fluxgestion.test_runner.FastPasswordRunner`, declared as
`TEST_RUNNER` in the settings. It swaps in a fast password hasher for the
duration of the suite: the tests create several hundred accounts, and Django's
default PBKDF2 — a million iterations — accounted for most of the runtime. The
production hasher is untouched; nothing under test depends on the algorithm.

### Writing Tests

- Create test functions/classes in `api/test_integration.py`
- Use descriptive test names
- Test both success and error cases
- Mock external services when needed

Example test:
```python
class MyTestCase(APITestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.user = User.objects.create_user(username='test', password='test')
    
    def test_something(self):
        """Test description"""
        response = self.client.get('/api/endpoint/')
        self.assertEqual(response.status_code, 200)
```

## Adding Features

### Backend Features

1. **Models**: Update `api/models.py`
   - Add fields, validators, constraints
   - Create migrations: `python manage.py makemigrations`
   - Update serializers: `api/serializers.py`

2. **Views/API**: Update `api/views.py`
   - Add ViewSet methods
   - Implement filtering/pagination
   - Add custom actions

3. **Admin**: Update `api/admin.py`
   - Register model in admin
   - Add list display, filters, search

4. **Tests**: Add tests in `api/test_integration.py`

### Frontend Features

1. **HTML**: Update `frontend/index.html`
   - Add page containers
   - Add form elements
   - Add modal structures

2. **CSS**: Update `frontend/css/style.css`
   - Add component styles
   - Ensure responsive design
   - Support dark mode

3. **JavaScript**: Update `frontend/js/app.js`
   - Add event listeners
   - Add data loading functions
   - Add form handlers

## Documentation

- Update README.md for user-facing changes
- Update QUICKSTART.md for setup changes
- Update docs/API.md for API changes
- Add inline code comments for complex logic
- Update docstrings for functions/classes

## Reporting Issues

Use GitHub Issues with a clear title and description:

**Bug Reports:**
- Current behavior
- Expected behavior
- Steps to reproduce
- Environment details
- Error messages/logs

**Feature Requests:**
- Problem being solved
- Proposed solution
- Alternative solutions considered
- Use cases

## Visibility rule

Every collection must be scoped through `visible_to(member)`. A member sees
only their own rows; a founder sees the whole team. Adding an endpoint that
queries a model directly, without that scoping, leaks a colleague's figures —
the test suite has cases guarding each model, keep them passing.

## Performance Considerations

- Profile code before optimization
- Use Django ORM efficiently (select_related, prefetch_related)
- Cache expensive operations
- Minimize database queries
- Optimize frontend rendering

## Security

- Never commit secrets or credentials
- Validate all user input
- Use parameterized queries
- Follow OWASP guidelines
- Report security issues privately to maintainers

## Questions?

- Check existing issues and discussions
- Review documentation files
- Ask in pull request comments
- Open a discussion for longer conversations

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.

---

Happy contributing! 🎉
